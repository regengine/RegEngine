#!/usr/bin/env python3
"""Live dual-write parity verifier — is it safe to retire the legacy store? (#1335)

STRICTLY READ-ONLY. This program never issues INSERT, UPDATE, DELETE,
TRUNCATE, COPY, or any DDL — not against production, not against a scratch
database, not ever. That is enforced structurally in three independent
layers:

  1. Every statement goes through :func:`read_only_execute`, which refuses
     anything that is not a bare ``SELECT`` / ``WITH`` (the only exception
     being ``SELECT set_config(...)``, itself a SELECT).
  2. The connection is established with
     ``-c default_transaction_read_only=on``, so PostgreSQL itself rejects
     any write with ``25006 read_only_sql_transaction``.
  3. ``SELECT set_config('default_transaction_read_only', 'on', false)`` is
     re-asserted on the live session in case the server-side default was
     overridden by the role or database.

WHAT THIS ANSWERS
-----------------
The dual write (#1335) keeps two stores in lockstep:

  * canonical — ``fsma.traceability_events``, written by
    ``CanonicalEventStore.persist_event``
  * legacy    — ``fsma.cte_events`` + ``fsma.cte_kdes``, written by
    ``legacy_dual_write.dual_write_legacy`` when ``dual_write=True``

The ONLY reliable cross-store join key is ``sha256_hash``: the two stores
use different idempotency-key formulas, so nothing else joins them.

The read-path cutover (``FDA_EXPORT_V1_READ_CANONICAL``,
``CHAIN_VERIFY_READ_CANONICAL``) is safe exactly when the canonical store
can reproduce, today, every legacy row a regulator-facing export would
have returned. This tool measures that against a real database instead of
waiting out a calendar soak.

THE MAPPING BEING VERIFIED
--------------------------
Read from ``services/shared/canonical_persistence/legacy_dual_write.py``
(``dual_write_legacy``) and the already-proven inverse SQL in
``services/ingestion/app/fda_export/queries.py``
(``fetch_recall_events_canonical``):

    cte_events.id                  = traceability_events.event_id (verbatim)
    cte_events.product_description = COALESCE(product_reference, '')
    cte_events.location_gln        = COALESCE(from_facility_reference,
                                              to_facility_reference)   (#2535)
    cte_events.location_name       = same expression as location_gln   (#2535)
    cte_events.source              = source_system
    cte_kdes (aggregated)          = traceability_events.kdes with
                                     None/JSON-null valued keys DROPPED
    cte_events.ingested_at         = traceability_events.ingested_at
                                     (both DEFAULT now(); the dual write runs
                                     in ONE transaction, so now() is stable and
                                     the two timestamps are byte-identical)

DIRECTIONALITY (this is the whole ballgame)
-------------------------------------------
  * A LEGACY row with no canonical twin is a HARD FAILURE. ``dual_write_legacy``
    runs INSIDE ``persist_event`` AFTER the canonical INSERT, so a legacy
    orphan means a canonical write was lost or swallowed — the #1277
    "both tables or neither" invariant is broken and the canonical store is
    NOT a superset of what the legacy readers can see.
  * A CANONICAL row with no legacy twin is EXPECTED and INFORMATIONAL.
    ``webhook_compat``, ``epcis``, ``canonical_router``, ``auditor_router``
    and ``webhook_router_v2`` deliberately run ``dual_write=False``.

SAME-TRANSACTION vs CROSS-TRANSACTION PAIRS
-------------------------------------------
Not every legacy row was written by ``dual_write_legacy``. The live
``webhook_compat.ingest_events`` route writes the legacy row through the
old ``CTEPersistence.store_event`` and the canonical row through a separate
canonical-only store — two different transactions, two independently
generated primary keys. Such a pair still joins on ``sha256_hash`` but was
never produced by the dual-write mapping, so ``cte_events.id`` legitimately
differs from ``traceability_events.event_id``.

Because the dual write commits both rows in ONE transaction, and
``ingested_at`` defaults to ``now()`` (= ``transaction_timestamp()``), a
true dual-written pair has byte-identical ``ingested_at`` on both sides.
This tool uses that to classify every matched pair:

    same-transaction  -> produced by dual_write_legacy. ANY field divergence
                         here means the dual write itself is broken. HARD.
    cross-transaction -> produced by two different writers. An ``id``
                         divergence here is structural, not corruption — but
                         it still means the v1 export's ``id`` column WOULD
                         CHANGE at read cutover, so it is reported, not hidden.

Use ``--ignore-field id`` to get a verdict on the remaining fields once that
class has been consciously accepted; the choice is echoed in the verdict
block so it cannot be smuggled past a reviewer.

EXIT CODES
----------
    0  SAFE-TO-PROCEED   — rows were compared, zero legacy orphans, zero
                           field divergence. (With ``--limit``, a clean
                           SMOKE result: no violations in the sample, which
                           is NOT by itself a cutover decision.)
    1  DO-NOT-PROCEED    — parity violations found (legacy orphans and/or
                           field divergence).
    2  DO-NOT-PROCEED    — could not complete: bad arguments, unreachable
                           database, missing tables, RLS hiding every row,
                           or a query error. No verdict was reached.
    3  DO-NOT-PROCEED    — ZERO COVERAGE. The scan compared zero rows. This
                           is the classic false-green and is never reported
                           as success.

USAGE
-----
    export DATABASE_URL='postgresql://...'      # read-only role preferred
    python3 scripts/verify_canonical_parity_live.py --since 2026-07-01

See ``--help`` for the full flag list and
``docs/persistence/dual-write-cutover.md`` for where this fits in WS-1.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import UUID

# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------

EXIT_SAFE = 0
EXIT_VIOLATIONS = 1
EXIT_INCOMPLETE = 2
EXIT_ZERO_COVERAGE = 3

APPLICATION_NAME = "regengine_parity_verifier"

# Default settling lag. The cross-transaction writers (webhook_compat) commit
# the legacy row and the canonical row in SEPARATE transactions, so a scan
# that runs right up to now() can observe a legacy row microseconds before
# its canonical twin commits and report a phantom orphan. Excluding the most
# recent few minutes removes that race without weakening the check.
DEFAULT_SETTLE_SECONDS = 300


# ---------------------------------------------------------------------------
# Layer 1 of the read-only guarantee: a statement allowlist
# ---------------------------------------------------------------------------


class ReadOnlyViolation(RuntimeError):
    """Raised if this program ever tries to execute a non-SELECT statement.

    This is a programming-error guard, not an input-validation guard: no SQL
    in this module is assembled from user input. It exists so that a future
    edit which adds a write cannot silently ship — the verifier is contracted
    to be safe to point at production.
    """


# Leading SQL comments and whitespace are stripped before the check so a
# documented query still passes.
_LEADING_NOISE = re.compile(r"^(?:\s|--[^\n]*\n|/\*.*?\*/)+", re.DOTALL)
_ALLOWED_START = re.compile(r"^(select|with)\b", re.IGNORECASE)
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|truncate|drop|alter|create|grant|revoke|copy|"
    r"vacuum|analyze|reindex|cluster|lock|merge|call|do)\b",
    re.IGNORECASE,
)


def assert_read_only(sql: str) -> None:
    """Reject any statement that is not a pure read.

    Two checks, both cheap: the statement must START with SELECT or WITH,
    and must not contain a write keyword anywhere. The second check is
    deliberately blunt — it would reject a legitimate column named
    ``update_count``, and that is the correct trade for a tool whose entire
    value proposition is being safe to run against the production database.
    """
    stripped = _LEADING_NOISE.sub("", sql).strip()
    if not _ALLOWED_START.match(stripped):
        raise ReadOnlyViolation(f"refusing non-SELECT statement: {stripped[:120]!r}")
    if _FORBIDDEN.search(stripped):
        raise ReadOnlyViolation(f"refusing statement containing a write keyword: {stripped[:120]!r}")


def read_only_execute(conn: Any, sql: str, params: Optional[Dict[str, Any]] = None) -> Any:
    """The ONLY way this module touches the database."""
    from sqlalchemy import text  # noqa: PLC0415 — optional dependency, imported late

    assert_read_only(sql)
    return conn.execute(text(sql), params or {})


# ---------------------------------------------------------------------------
# The mapping under test
# ---------------------------------------------------------------------------
#
# (field, legacy SQL expression, canonical SQL expression, value is jsonb)
#
# These strings are module-level literals. Nothing here is derived from
# command-line input, so the f-string assembly in ``_build_diff_expr`` is not
# a dynamic-SQL surface (contrast #1254, which was about interpolating
# *values*). Every value that varies at runtime is a bind parameter.
FieldSpec = Tuple[str, str, str, bool]

MAPPED_FIELDS: Tuple[FieldSpec, ...] = (
    # cte_events.id == traceability_events.event_id, verbatim.
    ("id", "p.id::text", "t.event_id::text", False),
    # product_description = COALESCE(product_reference, '')
    ("product_description", "p.product_description", "COALESCE(t.product_reference, '')", False),
    # location_gln = COALESCE(from_facility_reference, to_facility_reference)  (#2535)
    (
        "location_gln",
        "p.location_gln",
        "COALESCE(t.from_facility_reference, t.to_facility_reference)",
        False,
    ),
    # location_name carries the SAME expression as location_gln (#2535).
    (
        "location_name",
        "p.location_name",
        "COALESCE(t.from_facility_reference, t.to_facility_reference)",
        False,
    ),
    # source = source_system
    ("source", "p.source", "t.source_system", False),
    # cte_kdes aggregate == kdes JSONB minus None-valued keys.
    # ``lk.v`` / ``ck.v`` are the LATERAL aggregates built in the page query;
    # both are NULL when the event has no (non-null) KDEs, so a missing-vs-
    # empty mismatch cannot be masked.
    ("kdes", "lk.v", "ck.v", True),
)

FIELD_NAMES: Tuple[str, ...] = tuple(f[0] for f in MAPPED_FIELDS)


def _build_diff_expr(fields: Sequence[FieldSpec]) -> str:
    """Build the per-row ``diffs`` JSONB expression.

    Emits ``{}`` for a row that matches on every field, so a clean scan
    transfers almost nothing over the wire; a mismatching row carries
    ``{"<field>": [legacy_value, canonical_value]}`` for each field that
    differs, which is what the human needs to triage without a second query.

    ``IS DISTINCT FROM`` (not ``<>``) so NULL-vs-NULL counts as equal and
    NULL-vs-value counts as different — both stores legitimately hold NULL
    in ``location_gln`` when neither facility reference is present.
    """
    parts = []
    for name, legacy, canonical, is_json in fields:
        legacy_json = f"COALESCE({legacy}, 'null'::jsonb)" if is_json else f"to_jsonb({legacy})"
        canon_json = f"COALESCE({canonical}, 'null'::jsonb)" if is_json else f"to_jsonb({canonical})"
        parts.append(
            f"(CASE WHEN {legacy} IS DISTINCT FROM {canonical} "
            f"THEN jsonb_build_object('{name}', jsonb_build_array({legacy_json}, {canon_json})) "
            f"ELSE '{{}}'::jsonb END)"
        )
    if not parts:
        return "'{}'::jsonb"
    return "\n                 || ".join(parts)


# ---------------------------------------------------------------------------
# Query builders
# ---------------------------------------------------------------------------


def build_window_conditions(alias: str, params: Dict[str, Any], opts: "Options") -> List[str]:
    """Tenant + time-window predicates, as bind-parameterized SQL text.

    ``ingested_at`` is the window column because it is the one timestamp the
    dual write makes identical across both stores, and both tables index it
    (``idx_cte_events_ingested`` / ``idx_trace_events_ingested``).
    ``event_timestamp`` is supplier-declared and can be backdated years, so
    it is useless for bounding a "what did we write recently" scan.
    """
    conds: List[str] = []
    if opts.tenants:
        conds.append(f"{alias}.tenant_id = ANY(CAST(:tenants AS uuid[]))")
        params["tenants"] = [str(t) for t in opts.tenants]
    if opts.since is not None:
        conds.append(f"{alias}.ingested_at >= :since")
        params["since"] = opts.since
    if opts.until is not None:
        conds.append(f"{alias}.ingested_at < :until")
        params["until"] = opts.until
    return conds


def build_page_query(opts: "Options", cursor: Optional[Tuple[datetime, str]], batch_size: int) -> Tuple[str, Dict[str, Any]]:
    """One keyset-paginated batch of legacy rows joined to their canonical twins.

    Design notes that matter on a production-sized table:

    * The LIMIT is applied INSIDE the ``page`` CTE, i.e. to the legacy table
      alone. If the LIMIT were applied to the joined result, a legacy row
      with two canonical twins could be split across a page boundary and the
      keyset cursor would skip its remainder.
    * Keyset pagination on ``(ingested_at, id)`` — never OFFSET, which
      re-scans everything already read and degrades quadratically.
    * The join is a LEFT JOIN so orphans (no twin at all) come back in the
      same pass as divergences; no second scan of the legacy table.
    """
    params: Dict[str, Any] = {"batch_size": batch_size}
    conds = build_window_conditions("c", params, opts)
    if cursor is not None:
        conds.append("(c.ingested_at, c.id) > (:cur_ts, CAST(:cur_id AS uuid))")
        params["cur_ts"] = cursor[0]
        params["cur_id"] = cursor[1]
    where = " AND ".join(conds) if conds else "TRUE"

    fields = [f for f in MAPPED_FIELDS if f[0] not in opts.ignore_fields]
    diff_expr = _build_diff_expr(fields)

    sql = f"""
        WITH page AS (
            SELECT c.id, c.tenant_id, c.sha256_hash, c.ingested_at,
                   c.product_description, c.location_gln, c.location_name, c.source
            FROM fsma.cte_events c
            WHERE {where}
            ORDER BY c.ingested_at ASC, c.id ASC
            LIMIT :batch_size
        )
        SELECT
            p.id::text                                  AS legacy_id,
            p.tenant_id::text                           AS tenant_id,
            p.sha256_hash                               AS sha256_hash,
            p.ingested_at                               AS legacy_ingested_at,
            (t.event_id IS NULL)                        AS no_twin,
            (t.ingested_at IS NOT DISTINCT FROM p.ingested_at) AS same_transaction,
            CASE WHEN t.event_id IS NULL THEN '{{}}'::jsonb ELSE (
                 {diff_expr}
            ) END                                       AS diffs
        FROM page p
        LEFT JOIN fsma.traceability_events t
               ON t.tenant_id = p.tenant_id
              AND t.sha256_hash = p.sha256_hash
        LEFT JOIN LATERAL (
            -- Mirrors fetch_recall_events' legacy KDE aggregate exactly.
            SELECT jsonb_object_agg(k.kde_key, k.kde_value) AS v
            FROM fsma.cte_kdes k
            WHERE k.cte_event_id = p.id
        ) lk ON TRUE
        LEFT JOIN LATERAL (
            -- Mirrors fetch_recall_events_canonical: strip JSON-null values,
            -- because dual_write_legacy skips None-valued KDEs entirely.
            SELECT jsonb_object_agg(kv.key, kv.value) AS v
            FROM jsonb_each(COALESCE(t.kdes, '{{}}'::jsonb)) kv
            WHERE kv.value <> 'null'::jsonb
        ) ck ON TRUE
        ORDER BY p.ingested_at ASC, p.id ASC
    """
    return sql, params


def build_legacy_total_query(opts: "Options") -> Tuple[str, Dict[str, Any]]:
    params: Dict[str, Any] = {}
    conds = build_window_conditions("c", params, opts)
    where = " AND ".join(conds) if conds else "TRUE"
    return f"SELECT COUNT(*) FROM fsma.cte_events c WHERE {where}", params


def build_canonical_only_query(opts: "Options") -> Tuple[str, Dict[str, Any]]:
    """Canonical rows with no legacy twin — INFORMATIONAL, never a failure.

    The anti-join probe hits ``idx_cte_events_tenant_sha256`` (v081), so this
    is a windowed scan of the canonical table with an index probe per row
    rather than a second full scan.
    """
    params: Dict[str, Any] = {}
    conds = build_window_conditions("t", params, opts)
    where = " AND ".join(conds) if conds else "TRUE"
    return (
        f"""
        SELECT COUNT(*)
        FROM fsma.traceability_events t
        WHERE {where}
          AND NOT EXISTS (
              SELECT 1 FROM fsma.cte_events c
              WHERE c.tenant_id = t.tenant_id
                AND c.sha256_hash = t.sha256_hash
          )
        """,
        params,
    )


def build_unjoinable_canonical_query(opts: "Options") -> Tuple[str, Dict[str, Any]]:
    """Canonical rows with a NULL sha256_hash.

    ``sha256_hash`` is the only cross-store join key and is NULLABLE on the
    canonical table. A canonical row without one can never be reconciled
    against the legacy store by any tool, including this one, so it is
    surfaced explicitly rather than being quietly folded into the
    canonical-only count.
    """
    params: Dict[str, Any] = {}
    conds = build_window_conditions("t", params, opts)
    conds.append("t.sha256_hash IS NULL")
    where = " AND ".join(conds)
    return f"SELECT COUNT(*) FROM fsma.traceability_events t WHERE {where}", params


# ---------------------------------------------------------------------------
# Options / results
# ---------------------------------------------------------------------------


@dataclass
class Options:
    tenants: Tuple[str, ...] = ()
    since: Optional[datetime] = None
    until: Optional[datetime] = None
    limit: Optional[int] = None
    batch_size: int = 1000
    max_samples: int = 10
    ignore_fields: Tuple[str, ...] = ()
    skip_canonical_only: bool = False
    statement_timeout_ms: int = 60_000
    output_json: bool = False
    settle_seconds: int = DEFAULT_SETTLE_SECONDS
    until_was_explicit: bool = False


@dataclass
class Sample:
    sha256_hash: str
    tenant_id: str
    legacy_id: str
    same_transaction: bool
    diffs: Dict[str, Any]


@dataclass
class Report:
    rows_examined: int = 0
    rows_matched: int = 0
    rows_matched_same_txn: int = 0
    rows_matched_cross_txn: int = 0
    ambiguous_matches: int = 0
    legacy_orphans: int = 0
    diverged_rows: int = 0
    diverged_same_txn: int = 0
    diverged_cross_txn: int = 0
    field_divergence: Dict[str, int] = field(default_factory=dict)
    orphan_samples: List[Sample] = field(default_factory=list)
    divergence_samples: List[Sample] = field(default_factory=list)
    legacy_total_in_window: Optional[int] = None
    canonical_only: Optional[int] = None
    canonical_unjoinable: Optional[int] = None
    truncated_by_limit: bool = False
    duration_seconds: float = 0.0
    notes: List[str] = field(default_factory=list)

    @property
    def rows_compared(self) -> int:
        """Legacy rows that were actually compared field-by-field.

        Orphans are counted as examined but NOT as compared — there was no
        twin to compare them against.
        """
        return self.rows_matched


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------


def _group_by_legacy_id(rows: Iterable[Any]) -> "Dict[str, List[Any]]":
    grouped: Dict[str, List[Any]] = {}
    for row in rows:
        grouped.setdefault(row.legacy_id, []).append(row)
    return grouped


def scan(conn: Any, opts: Options, report: Report) -> None:
    """Walk the legacy table in keyset batches, comparing each row to its twin."""
    cursor: Optional[Tuple[datetime, str]] = None
    remaining = opts.limit

    while True:
        batch_size = opts.batch_size
        if remaining is not None:
            if remaining <= 0:
                report.truncated_by_limit = True
                break
            batch_size = min(batch_size, remaining)

        sql, params = build_page_query(opts, cursor, batch_size)
        rows = read_only_execute(conn, sql, params).fetchall()
        if not rows:
            break

        grouped = _group_by_legacy_id(rows)
        # Advance the cursor to the LAST legacy row of the page. Grouping does
        # not reorder anything — the query is ordered — so the final row is
        # the high-water mark regardless of join fan-out.
        last = rows[-1]
        cursor = (last.legacy_ingested_at, last.legacy_id)

        for legacy_id, candidates in grouped.items():
            report.rows_examined += 1
            if remaining is not None:
                remaining -= 1

            first = candidates[0]
            if len(candidates) == 1 and first.no_twin:
                report.legacy_orphans += 1
                if len(report.orphan_samples) < opts.max_samples:
                    report.orphan_samples.append(
                        Sample(
                            sha256_hash=first.sha256_hash,
                            tenant_id=first.tenant_id,
                            legacy_id=legacy_id,
                            same_transaction=False,
                            diffs={},
                        )
                    )
                continue

            if len(candidates) > 1:
                report.ambiguous_matches += 1

            # Best-match semantics: with more than one canonical row sharing
            # the (tenant_id, sha256_hash) key, the legacy row is considered
            # reconciled if ANY of them satisfies the mapping. Only when none
            # do is it a divergence, and then we report the closest one.
            best = min(candidates, key=lambda r: len(r.diffs or {}))
            diffs = dict(best.diffs or {})

            report.rows_matched += 1
            if best.same_transaction:
                report.rows_matched_same_txn += 1
            else:
                report.rows_matched_cross_txn += 1

            if not diffs:
                continue

            report.diverged_rows += 1
            if best.same_transaction:
                report.diverged_same_txn += 1
            else:
                report.diverged_cross_txn += 1
            for name in diffs:
                report.field_divergence[name] = report.field_divergence.get(name, 0) + 1
            if len(report.divergence_samples) < opts.max_samples:
                report.divergence_samples.append(
                    Sample(
                        sha256_hash=best.sha256_hash,
                        tenant_id=best.tenant_id,
                        legacy_id=legacy_id,
                        same_transaction=bool(best.same_transaction),
                        diffs=diffs,
                    )
                )

        if len(grouped) < batch_size:
            # Short page => the windowed set is exhausted.
            break
        if remaining is not None and remaining <= 0:
            report.truncated_by_limit = True
            break


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------


class Preflight(Exception):
    """A condition that makes the run impossible or its result meaningless."""


def preflight(conn: Any, opts: Options) -> Dict[str, Any]:
    """Establish read-only posture, check the schema, and report the plan risk."""
    info: Dict[str, Any] = {}

    # Layer 3 of the read-only guarantee (layer 2 is the connect-time option).
    read_only_execute(conn, "SELECT set_config('default_transaction_read_only', 'on', false)")
    read_only_execute(
        conn,
        "SELECT set_config('statement_timeout', :ms, false)",
        {"ms": str(opts.statement_timeout_ms)},
    )
    # Never let this tool be the reason a production autovacuum stalls.
    read_only_execute(conn, "SELECT set_config('idle_in_transaction_session_timeout', '60000', false)")

    row = read_only_execute(
        conn,
        "SELECT current_user, current_database(), version(), "
        "current_setting('default_transaction_read_only')",
    ).fetchone()
    info["user"] = row[0]
    info["database"] = row[1]
    info["server_version"] = str(row[2]).split(" on ")[0]
    if row[3] != "on":
        raise Preflight("could not put the session into read-only mode; refusing to continue")

    # RLS: fsma.cte_events / fsma.traceability_events are FORCE ROW LEVEL
    # SECURITY with a policy of ``tenant_id = get_tenant_context()``, and
    # get_tenant_context() RAISES when app.tenant_id is unset. Under the
    # ``regengine`` application role a scan is therefore only possible one
    # tenant at a time; an all-tenant scan needs a role that bypasses RLS
    # (the migration/owner role). Setting the GUC when exactly one tenant was
    # requested makes the common case work under either role.
    if len(opts.tenants) == 1:
        read_only_execute(
            conn,
            "SELECT set_config('app.tenant_id', :tid, false)",
            {"tid": opts.tenants[0]},
        )
        info["tenant_guc"] = opts.tenants[0]

    missing = []
    for table in ("fsma.cte_events", "fsma.cte_kdes", "fsma.traceability_events"):
        present = read_only_execute(conn, "SELECT to_regclass(:t) IS NOT NULL", {"t": table}).scalar()
        if not present:
            missing.append(table)
    if missing:
        raise Preflight(
            f"required table(s) not present or not visible: {', '.join(missing)} — "
            "wrong database, or migrations have not been applied"
        )

    # The canonical table has NO index on (tenant_id, sha256_hash) as of
    # alembic head — v081 added one to fsma.cte_events only. Without it the
    # per-batch twin lookup degrades to a scan of the canonical table. Say so
    # loudly rather than quietly hammering production.
    idx_rows = read_only_execute(
        conn,
        "SELECT indexname, indexdef FROM pg_indexes "
        "WHERE schemaname = 'fsma' AND tablename = 'traceability_events'",
    ).fetchall()
    info["canonical_sha_index"] = next(
        (r[0] for r in idx_rows if "sha256_hash" in (r[1] or "")),
        None,
    )
    return info


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------


def decide(report: Report, opts: Options) -> Tuple[int, str, str]:
    """Return ``(exit_code, headline, reason)``. Pure function — easy to test."""
    if report.legacy_orphans > 0 or report.diverged_rows > 0:
        reasons = []
        if report.legacy_orphans:
            reasons.append(
                f"{report.legacy_orphans:,} legacy row(s) have no canonical twin by "
                "(tenant_id, sha256_hash) — a canonical write was lost (#1277)"
            )
        if report.diverged_rows:
            detail = (
                f"{report.diverged_same_txn:,} in dual-written (same-transaction) pairs, "
                f"{report.diverged_cross_txn:,} in cross-transaction pairs"
            )
            reasons.append(
                f"{report.diverged_rows:,} matched pair(s) do not satisfy the "
                f"dual_write_legacy mapping ({detail})"
            )
        return EXIT_VIOLATIONS, "DO-NOT-PROCEED", "; ".join(reasons)

    if report.rows_compared == 0:
        return (
            EXIT_ZERO_COVERAGE,
            "DO-NOT-PROCEED",
            "ZERO COVERAGE — the scan compared 0 legacy rows against canonical, so it "
            "proves nothing. Check the --since/--until window, the --tenant filter, and "
            "whether row-level security is hiding the rows from this role",
        )

    if report.truncated_by_limit:
        return (
            EXIT_SAFE,
            "SMOKE PASS CLEAN — NOT A CUTOVER DECISION",
            f"no violations in the first {report.rows_compared:,} row(s), but --limit "
            "truncated the scan; re-run without --limit before making a release decision",
        )

    ignored = f" (ignoring field(s): {', '.join(opts.ignore_fields)})" if opts.ignore_fields else ""
    return (
        EXIT_SAFE,
        "SAFE-TO-PROCEED",
        f"{report.rows_compared:,} legacy row(s) in the window each have a canonical twin "
        f"that reproduces the dual_write_legacy mapping exactly{ignored}; 0 legacy orphans, "
        "0 field divergences",
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _fmt(n: Optional[int]) -> str:
    return "not computed" if n is None else f"{n:,}"


def _truncate(value: Any, width: int = 80) -> str:
    text_value = value if isinstance(value, str) else json.dumps(value, default=str, sort_keys=True)
    if len(text_value) > width:
        return text_value[: width - 1] + "…"
    return text_value


def render_text(report: Report, opts: Options, info: Dict[str, Any], exit_code: int, headline: str, reason: str) -> str:
    lines: List[str] = []
    add = lines.append
    rule = "=" * 72

    add(rule)
    add("RegEngine dual-write parity verification (READ-ONLY)   WS-1 / #1335")
    add(rule)
    add(f"database          : {info.get('database', '?')} as {info.get('user', '?')}")
    add(f"server            : {info.get('server_version', '?')}")
    add(f"tenant filter     : {', '.join(opts.tenants) if opts.tenants else 'ALL TENANTS'}")
    add(f"window (ingested_at) : >= {opts.since.isoformat() if opts.since else '(no lower bound)'}")
    add(f"                     <  {opts.until.isoformat() if opts.until else '(no upper bound)'}")
    add(f"batch size        : {opts.batch_size:,}    limit: {opts.limit if opts.limit else 'none'}")
    if opts.ignore_fields:
        add(f"IGNORED FIELDS    : {', '.join(opts.ignore_fields)}  <-- results exclude these")
    add(f"duration          : {report.duration_seconds:.1f}s")
    add("")

    add("COVERAGE")
    add(f"  legacy rows in window (fsma.cte_events)     : {_fmt(report.legacy_total_in_window)}")
    add(f"  legacy rows examined by this scan           : {report.rows_examined:,}")
    add(f"  rows COMPARED against a canonical twin      : {report.rows_compared:,}")
    add(f"    of which same-transaction (dual-written)  : {report.rows_matched_same_txn:,}")
    add(f"    of which cross-transaction (other writer) : {report.rows_matched_cross_txn:,}")
    add(f"  ambiguous (>1 canonical twin for one hash)  : {report.ambiguous_matches:,}")
    if report.truncated_by_limit:
        add("  ** scan TRUNCATED by --limit — partial coverage **")
    add("")

    add("(a) LEGACY ORPHANS   [HARD FAILURE — a canonical write was lost, #1277]")
    add(f"  legacy rows with no canonical twin          : {report.legacy_orphans:,}")
    for sample in report.orphan_samples:
        add(f"    sha256={sample.sha256_hash}  tenant={sample.tenant_id}  cte_events.id={sample.legacy_id}")
    add("")

    add("(b) CANONICAL-ONLY   [INFORMATIONAL — expected, dual_write=False paths]")
    add(f"  canonical rows with no legacy twin          : {_fmt(report.canonical_only)}")
    add(f"  canonical rows with NULL sha256_hash        : {_fmt(report.canonical_unjoinable)}")
    if report.canonical_unjoinable:
        add("    (unjoinable by any tool — sha256_hash is the only cross-store key)")
    add("")

    add("(c) FIELD DIVERGENCE on matched pairs")
    for name in FIELD_NAMES:
        if name in opts.ignore_fields:
            add(f"  {name:<22}: (ignored)")
        else:
            add(f"  {name:<22}: {report.field_divergence.get(name, 0):,}")
    add(
        f"  rows with >=1 divergence : {report.diverged_rows:,} "
        f"(same-txn {report.diverged_same_txn:,} / cross-txn {report.diverged_cross_txn:,})"
    )
    if report.divergence_samples:
        add(f"  first {len(report.divergence_samples)} mismatching sha256_hash value(s):")
        for sample in report.divergence_samples:
            kind = "dual-written" if sample.same_transaction else "cross-transaction"
            add(f"    {sample.sha256_hash}  ({kind}, tenant={sample.tenant_id})")
            for name, pair in sample.diffs.items():
                legacy_value, canonical_value = (pair + [None, None])[:2] if isinstance(pair, list) else (pair, None)
                add(f"        {name}: legacy={_truncate(legacy_value)}")
                add(f"        {' ' * len(name)}  canonical={_truncate(canonical_value)}")
    add("")

    for note in report.notes:
        add(f"NOTE: {note}")
    if report.notes:
        add("")

    add(rule)
    add("VERDICT")
    add(f"  rows compared   : {report.rows_compared:,}")
    add(f"  legacy orphans  : {report.legacy_orphans:,}")
    add(f"  divergences     : {report.diverged_rows:,}")
    add(f"  {headline} — {reason}")
    add(f"  exit code       : {exit_code}")
    add(rule)
    return "\n".join(lines)


def render_json(report: Report, opts: Options, info: Dict[str, Any], exit_code: int, headline: str, reason: str) -> str:
    payload = {
        "verdict": headline,
        "reason": reason,
        "exit_code": exit_code,
        "connection": info,
        "options": {
            "tenants": list(opts.tenants),
            "since": opts.since.isoformat() if opts.since else None,
            "until": opts.until.isoformat() if opts.until else None,
            "limit": opts.limit,
            "batch_size": opts.batch_size,
            "ignore_fields": list(opts.ignore_fields),
        },
        "coverage": {
            "legacy_total_in_window": report.legacy_total_in_window,
            "rows_examined": report.rows_examined,
            "rows_compared": report.rows_compared,
            "same_transaction": report.rows_matched_same_txn,
            "cross_transaction": report.rows_matched_cross_txn,
            "ambiguous_matches": report.ambiguous_matches,
            "truncated_by_limit": report.truncated_by_limit,
        },
        "legacy_orphans": {
            "count": report.legacy_orphans,
            "samples": [
                {"sha256_hash": s.sha256_hash, "tenant_id": s.tenant_id, "legacy_id": s.legacy_id}
                for s in report.orphan_samples
            ],
        },
        "canonical_only": {
            "count": report.canonical_only,
            "null_sha256_hash": report.canonical_unjoinable,
        },
        "field_divergence": {
            "by_field": {n: report.field_divergence.get(n, 0) for n in FIELD_NAMES if n not in opts.ignore_fields},
            "rows": report.diverged_rows,
            "rows_same_transaction": report.diverged_same_txn,
            "rows_cross_transaction": report.diverged_cross_txn,
            "samples": [
                {
                    "sha256_hash": s.sha256_hash,
                    "tenant_id": s.tenant_id,
                    "legacy_id": s.legacy_id,
                    "same_transaction": s.same_transaction,
                    "diffs": s.diffs,
                }
                for s in report.divergence_samples
            ],
        },
        "duration_seconds": round(report.duration_seconds, 3),
        "notes": report.notes,
    }
    return json.dumps(payload, indent=2, default=str)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 date or timestamp; naive values are treated as UTC."""
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"not an ISO-8601 date/timestamp: {value!r} (try 2026-07-01 or 2026-07-01T00:00:00Z)"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_tenant(value: str) -> str:
    """Tenant ids are UUIDs everywhere in this schema; reject anything else.

    Validated rather than trusted even though it is passed as a bind
    parameter — a non-UUID would otherwise fail deep inside a cast with a
    much worse error message.
    """
    try:
        return str(UUID(value.strip()))
    except (ValueError, AttributeError) as exc:
        raise argparse.ArgumentTypeError(f"--tenant must be a UUID, got {value!r}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="verify_canonical_parity_live.py",
        description=(
            "READ-ONLY verification that the canonical store (fsma.traceability_events) "
            "faithfully reproduces the legacy store (fsma.cte_events/cte_kdes) it dual-writes, "
            "so the legacy read path can be retired. Reads DATABASE_URL from the environment."
        ),
        epilog=(
            "EXIT CODES: 0 safe-to-proceed | 1 parity violations | "
            "2 could not complete | 3 zero coverage (false-green guard). "
            "This program never writes to the database."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--tenant",
        action="append",
        type=parse_tenant,
        default=None,
        metavar="UUID",
        help="restrict to this tenant (repeatable). Omit to scan all tenants — which "
        "requires a role that bypasses row-level security.",
    )
    parser.add_argument("--since", type=parse_timestamp, default=None, metavar="TS", help="lower bound on ingested_at (inclusive)")
    parser.add_argument("--until", type=parse_timestamp, default=None, metavar="TS", help="upper bound on ingested_at (exclusive)")
    parser.add_argument("--limit", type=int, default=None, metavar="N", help="stop after N legacy rows — fast smoke pass, never a cutover decision")
    parser.add_argument("--batch-size", type=int, default=1000, metavar="N", help="rows per keyset page (default 1000)")
    parser.add_argument("--max-samples", type=int, default=10, metavar="N", help="mismatching sha256_hash values to print (default 10)")
    parser.add_argument(
        "--ignore-field",
        action="append",
        choices=list(FIELD_NAMES),
        default=None,
        dest="ignore_fields",
        help="exclude a mapped field from the comparison (repeatable). Echoed in the verdict block.",
    )
    parser.add_argument("--skip-canonical-only", action="store_true", help="skip the informational canonical-only anti-join count")
    parser.add_argument(
        "--settle-seconds",
        type=int,
        default=DEFAULT_SETTLE_SECONDS,
        metavar="S",
        help=(
            f"exclude the most recent S seconds when --until is omitted (default {DEFAULT_SETTLE_SECONDS}). "
            "Cross-transaction writers commit the legacy and canonical rows separately, so scanning "
            "right up to now() can report a phantom orphan."
        ),
    )
    parser.add_argument("--statement-timeout-ms", type=int, default=60_000, metavar="MS", help="per-statement timeout (default 60000)")
    parser.add_argument("--json", action="store_true", dest="output_json", help="emit machine-readable JSON instead of the text report")
    return parser


def options_from_args(args: argparse.Namespace) -> Options:
    until = args.until
    until_explicit = until is not None
    if until is None and args.settle_seconds > 0:
        until = datetime.now(timezone.utc) - timedelta(seconds=args.settle_seconds)
    return Options(
        tenants=tuple(args.tenant or ()),
        since=args.since,
        until=until,
        limit=args.limit,
        batch_size=max(1, args.batch_size),
        max_samples=max(0, args.max_samples),
        ignore_fields=tuple(args.ignore_fields or ()),
        skip_canonical_only=args.skip_canonical_only,
        statement_timeout_ms=max(1000, args.statement_timeout_ms),
        output_json=args.output_json,
        settle_seconds=args.settle_seconds,
        until_was_explicit=until_explicit,
    )


def normalize_database_url(url: str) -> str:
    """Force a psycopg2 driver URL.

    Railway hands out ``postgres://`` (rejected by SQLAlchemy 2.x) and parts
    of this repo use ``postgresql+asyncpg://`` (an async driver this
    synchronous script cannot use).
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    for async_prefix in ("postgresql+asyncpg://", "postgresql+psycopg_async://"):
        if url.startswith(async_prefix):
            url = "postgresql+psycopg2://" + url[len(async_prefix) :]
    return url


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    opts = options_from_args(args)

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        print("ERROR: DATABASE_URL is not set. Export it and re-run.", file=sys.stderr)
        return EXIT_INCOMPLETE

    try:
        from sqlalchemy import create_engine  # noqa: PLC0415
    except ImportError:
        print("ERROR: sqlalchemy is not installed (pip install 'sqlalchemy[postgresql]').", file=sys.stderr)
        return EXIT_INCOMPLETE

    engine = create_engine(
        normalize_database_url(database_url),
        future=True,
        pool_pre_ping=True,
        connect_args={
            # Layer 2 of the read-only guarantee: PostgreSQL refuses writes on
            # this connection regardless of what the client sends.
            "options": f"-c default_transaction_read_only=on -c application_name={APPLICATION_NAME}",
            "connect_timeout": 15,
        },
    )

    report = Report()
    info: Dict[str, Any] = {}
    started = time.monotonic()

    try:
        with engine.connect() as conn:
            info = preflight(conn, opts)

            if info.get("canonical_sha_index") is None:
                report.notes.append(
                    "fsma.traceability_events has NO index containing sha256_hash, so each "
                    "batch's twin lookup may scan the canonical table. On a large database "
                    "run with --limit first, or ask a DBA to add: CREATE INDEX CONCURRENTLY "
                    "idx_trace_events_tenant_sha256 ON fsma.traceability_events "
                    "(tenant_id, sha256_hash);  (this tool will NOT create it — it is read-only)"
                )
            if not opts.until_was_explicit and opts.settle_seconds > 0:
                report.notes.append(
                    f"--until defaulted to now() - {opts.settle_seconds}s to avoid phantom "
                    "orphans from in-flight cross-transaction writes."
                )
            if not opts.tenants:
                report.notes.append(
                    "no --tenant filter: this run assumes the connecting role bypasses "
                    "row-level security. If it does not, every row is invisible and the "
                    "zero-coverage guard (exit 3) fires rather than a false green."
                )
            if opts.ignore_fields:
                report.notes.append(
                    f"field(s) {', '.join(opts.ignore_fields)} were EXCLUDED from the "
                    "comparison by operator request; the verdict does not cover them."
                )

            sql, params = build_legacy_total_query(opts)
            report.legacy_total_in_window = read_only_execute(conn, sql, params).scalar()

            scan(conn, opts, report)

            if not opts.skip_canonical_only:
                try:
                    sql, params = build_canonical_only_query(opts)
                    report.canonical_only = read_only_execute(conn, sql, params).scalar()
                    sql, params = build_unjoinable_canonical_query(opts)
                    report.canonical_unjoinable = read_only_execute(conn, sql, params).scalar()
                except Exception as exc:  # noqa: BLE001 — informational only
                    report.notes.append(
                        f"canonical-only count could not be computed ({type(exc).__name__}: "
                        f"{str(exc)[:160]}). It is informational and does not affect the verdict."
                    )
    except ReadOnlyViolation as exc:
        print(f"ERROR: read-only guard tripped — this is a bug in the verifier: {exc}", file=sys.stderr)
        return EXIT_INCOMPLETE
    except Preflight as exc:
        print(f"ERROR: preflight failed: {exc}", file=sys.stderr)
        print("DO-NOT-PROCEED — no verdict was reached.", file=sys.stderr)
        return EXIT_INCOMPLETE
    except Exception as exc:  # noqa: BLE001 — CLI boundary
        message = str(exc)
        print(f"ERROR: {type(exc).__name__}: {message[:500]}", file=sys.stderr)
        if "app.tenant_id not set" in message or "insufficient_privilege" in message:
            print(
                "HINT: row-level security is active for this role. Pass a single --tenant "
                "(the verifier sets app.tenant_id for you) or connect with a role that "
                "bypasses RLS.",
                file=sys.stderr,
            )
        if "statement timeout" in message or "canceling statement" in message:
            print(
                "HINT: raise --statement-timeout-ms, narrow --since/--until, or use --limit "
                "for a smoke pass.",
                file=sys.stderr,
            )
        print("DO-NOT-PROCEED — no verdict was reached.", file=sys.stderr)
        return EXIT_INCOMPLETE
    finally:
        engine.dispose()

    report.duration_seconds = time.monotonic() - started
    exit_code, headline, reason = decide(report, opts)

    if opts.output_json:
        print(render_json(report, opts, info, exit_code, headline, reason))
    else:
        print(render_text(report, opts, info, exit_code, headline, reason))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
