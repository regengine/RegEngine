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
    cte_events.location_gln        = from_facility_reference
                                     OR-ELSE to_facility_reference   (#2535)
                                     (Python ``or`` in the writer: falls back on
                                     '' as well as NULL, mirrored in SQL as
                                     COALESCE(NULLIF(from, ''), to))
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

TWO LEGACY WRITERS, TWO INCOMPATIBLE HASH FORMULAS  (corrected 2026-08-04)
-------------------------------------------------------------------------
An earlier version of this docstring claimed that a ``webhook_compat`` pair
"still joins on ``sha256_hash``" and merely differs in ``ingested_at``. THAT
WAS FALSE, and the whole ``same-transaction``/``cross-transaction`` taxonomy
built on it was unreachable code. The two writers hash DIFFERENT FIELD SETS:

  legacy-native  ``shared/cte_persistence/hashing.py::compute_event_hash``
      event_id | event_type | tlc | quantity | uom | location_gln |
      timestamp | json(kdes minus description keys)              -- 8 fields
      (``product_description`` deliberately excluded, #1323; no to_facility)

  canonical      ``shared/canonical_event.py::compute_sha256_hash``
      event_id | event_type | tlc | product_reference | quantity | uom |
      from_facility_reference | to_facility_reference | timestamp |
      json(kdes)                                                 -- 10 fields

Different arity, different fields, and the two writers mint independent
``event_id`` values. A legacy row written by ``CTEPersistence.store_event``
(still live via ``webhook_compat.ingest_events`` and its callers:
``csv_templates``, ``sensitech_parser``, ``supplier_portal``) can therefore
NEVER join a canonical row on ``sha256_hash`` — even though the same request
DID write a canonical row through a sibling ``CanonicalEventStore(
dual_write=False)`` call.

So this tool does NOT conclude "a canonical write was lost" from a hash miss.
Every orphan is classified first, in Python, by recomputing the legacy
formula over the legacy row's own columns — the same probe
``scripts/backfill_canonical_from_legacy.py::_matches_legacy_formula`` uses
to decide what it must REFUSE to backfill. Both tools therefore produce the
same partition of the same rows, by construction:

    legacy-native orphan   the stored hash IS ``compute_event_hash(...)`` of
                           this row. Structural non-join, NOT a #1277
                           violation. Backfilling it would duplicate an FDA
                           event, so the backfill refuses it too
                           (``legacy_native_hash_formula``).
    unexplained orphan     neither joins by hash nor reproduces the legacy
                           formula. This is the real thing — a lost
                           canonical write (#1277). HARD FAILURE.

Because "legacy-native" only proves *which writer* wrote the row, not that
its canonical sibling survived, each legacy-native orphan is additionally
probed for a canonical row carrying the same content tuple
(tenant_id, event_type, tlc, event_timestamp, quantity, unit_of_measure) —
the columns ``normalize_webhook_event`` passes through verbatim. That probe
is CORROBORATION, never proof, and is reported as its own number.

There is NO phantom-orphan race. ``dual_write_legacy`` runs inside
``persist_event`` in ONE transaction, and ``webhook_compat`` commits its
legacy and canonical rows in one session transaction via nested savepoints.
No writer commits a legacy row before its canonical sibling in a separate
transaction, so ``--settle-seconds`` defaults to 0. The scan additionally
runs at REPEATABLE READ so every count in the report comes from ONE snapshot.

COVERAGE IS PART OF THE VERDICT
-------------------------------
``--since`` / ``--until`` / ``--limit`` all shrink what was actually proven.
A clean scan of a one-month window on a multi-year compliance table is NOT
a cutover decision — that is the exact false green this tool exists to
prevent. Every run therefore issues an UNWINDOWED probe (tenant predicate
only) and reports how many legacy rows fell OUTSIDE the scanned window. If
that number is non-zero, the verdict is downgraded to PARTIAL COVERAGE with
its own exit code (4). ``SAFE-TO-PROCEED`` + exit 0 is reserved for a scan
that provably covered every legacy row in scope.

WHAT IS AND IS NOT COMPARED
---------------------------
The v1 export emits 14 columns (``fetch_recall_events``). This tool compares
every column that ``dual_write_legacy`` maps, including the three that are
also the recall filter's WHERE predicates (``event_type``,
``traceability_lot_code``, ``event_timestamp``) — a divergence there changes
WHICH ROWS a recall search returns, not just cell values. Columns that are
NOT compared are enumerated by name in the verdict block of every run
(``UNCOMPARED_EXPORT_COLUMNS``), so the report discloses its own blind spots.

EXIT CODES
----------
    0  SAFE-TO-PROCEED   — full coverage, rows compared, zero unexplained
                           orphans, zero field divergence.
    1  DO-NOT-PROCEED    — parity violations found (unexplained legacy
                           orphans and/or field divergence).
    2  DO-NOT-PROCEED    — could not complete: bad arguments, unreachable
                           database, missing tables, RLS hiding every row,
                           or a query error. No verdict was reached.
    3  DO-NOT-PROCEED    — ZERO COVERAGE. The scan compared zero rows. This
                           is the classic false-green and is never reported
                           as success.
    4  NOT-A-DECISION    — the scan was clean but PARTIAL: ``--limit``
                           truncated it, ``--since``/``--until`` excluded
                           legacy rows, or ``--ignore-field`` suppressed a
                           column. Deliberately NOT 0 so that
                           ``if verify; then proceed`` cannot read it green.

USAGE
-----
    export DATABASE_URL='postgresql://...'      # read-only role preferred
    # the gate: no window, no limit, no ignores
    python3 scripts/verify_canonical_parity_live.py --json

See ``--help`` for the full flag list, ``docs/persistence/dual-write-cutover.md``
for where this fits in WS-1, and ``docs/persistence/ws1-cutover-runbook.md``
Step 4 for the pass/fail criteria this tool's exit codes feed.
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
EXIT_PARTIAL = 4

APPLICATION_NAME = "regengine_parity_verifier"

# Default settling lag: NONE.
#
# The previous default of 300s was justified by a claim that "cross-transaction
# writers commit the legacy row and the canonical row in SEPARATE transactions",
# so a scan running up to now() could see a phantom orphan. That claim is false.
# ``dual_write_legacy`` runs inside ``persist_event`` in ONE transaction, and
# ``webhook_compat.ingest_events`` writes its legacy row and its canonical row
# in ONE session transaction (nested savepoints, committed together). No writer
# commits a legacy row before its canonical sibling in a separate transaction.
#
# A non-zero settle window is therefore pure coverage loss, and coverage loss
# now downgrades the verdict (EXIT_PARTIAL). The flag remains for operators
# scanning a read REPLICA, where replication lag is a real effect — but they
# will see the resulting rows counted as outside-window and the verdict
# downgraded accordingly, which is the honest outcome.
DEFAULT_SETTLE_SECONDS = 0

# Export columns (``fetch_recall_events``, services/ingestion/app/fda_export/
# queries.py) that this tool does NOT compare. Printed in every verdict block
# so the report discloses its own blind spots instead of leaving that
# disclosure in a chat message.
UNCOMPARED_EXPORT_COLUMNS: Tuple[Tuple[str, str], ...] = (
    (
        "sha256_hash",
        "it is the join key itself — equal by construction for any matched pair",
    ),
    (
        "chain_hash",
        "the export reads it from the fsma.hash_chain JOIN, not from either event "
        "table; hash_chain is shared by both writers so it is single-sourced",
    ),
    (
        "ingested_at",
        "used as the scan's window column; it is compared implicitly because a "
        "dual-written pair shares one transaction_timestamp()",
    ),
)


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
# The legacy-native hash probe
# ---------------------------------------------------------------------------
#
# This is the ONE thing that lets an orphan be classified instead of merely
# counted. It deliberately imports the SAME function the production legacy
# writer uses and the SAME function scripts/backfill_canonical_from_legacy.py
# uses to decide what it must refuse — so the two tools cannot drift into
# disagreeing about which rows are structurally unjoinable.
#
# The import is guarded because this script is also run from ops boxes that
# have sqlalchemy but not the repo on sys.path. If it fails, orphans are NOT
# silently downgraded: they stay in the unexplained (hard-failure) bucket and
# a loud note explains that classification was unavailable.

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_ROOT, "services"), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:  # pragma: no cover — import shape depends on the deploy environment
    from shared.cte_persistence.hashing import compute_event_hash as _compute_legacy_hash

    LEGACY_HASH_PROBE_AVAILABLE = True
    LEGACY_HASH_PROBE_ERROR = ""
except Exception as _exc:  # noqa: BLE001 — ops environments vary
    _compute_legacy_hash = None  # type: ignore[assignment]
    LEGACY_HASH_PROBE_AVAILABLE = False
    LEGACY_HASH_PROBE_ERROR = f"{type(_exc).__name__}: {_exc}"


def matches_legacy_formula(
    legacy_id: str,
    event_type: str,
    tlc: str,
    product_description: str,
    quantity: Any,
    unit_of_measure: str,
    location_gln: Optional[str],
    location_name: Optional[str],
    event_timestamp: Any,
    kdes: Optional[Dict[str, Any]],
    stored_hash: str,
) -> bool:
    """True when ``stored_hash`` is the LEGACY formula over this row's columns.

    A True result proves the row was written by
    ``CTEPersistence.store_event`` (the legacy-native path, live via
    ``webhook_compat.ingest_events``) and NOT by ``dual_write_legacy``. Its
    absence from the canonical store by hash is then structural, not a lost
    write.

    A False result is NOT proof of the opposite. The probe can produce a
    false negative — the KDE dict is read back out of JSONB and a value that
    was hashed as a Python ``float``/``Decimal``/``datetime`` may render
    differently after the round trip (the same caveat
    ``backfill_canonical_from_legacy.py`` documents under
    ``hash_unreconstructible``). False is therefore the CONSERVATIVE answer:
    the row stays in the hard-failure bucket and gets a human.
    """
    if not LEGACY_HASH_PROBE_AVAILABLE or _compute_legacy_hash is None:
        return False
    try:
        timestamp = event_timestamp.isoformat() if hasattr(event_timestamp, "isoformat") else str(event_timestamp)
        return (
            _compute_legacy_hash(
                str(legacy_id),
                event_type,
                tlc,
                product_description,
                quantity,
                unit_of_measure,
                location_gln,
                location_name,
                timestamp,
                dict(kdes or {}),
            )
            == stored_hash
        )
    except Exception:  # noqa: BLE001 — classification only, never fatal
        return False


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
    # location_gln = from_facility_reference OR-else to_facility_reference  (#2535)
    #
    # dual_write_legacy writes ``from_facility_reference or to_facility_reference``
    # (legacy_dual_write.py) — Python ``or``, which falls back on ANY falsy left
    # operand, i.e. BOTH None AND the empty string ''. A bare
    # ``COALESCE(from, to)`` only substitutes on SQL NULL, so an empty-string
    # from_facility with a populated to_facility diverges: the legacy row
    # faithfully stored ``to`` (the fallback the writer chose for ''), while the
    # canonical side evaluated to '' and IS DISTINCT FROM reported a spurious
    # location divergence (and, symmetrically, a legacy row corrupted to '' would
    # be MASKED). ``NULLIF(from, '')`` collapses '' to NULL first so COALESCE
    # reproduces the writer's ``or`` exactly for every operand combination.
    (
        "location_gln",
        "p.location_gln",
        "COALESCE(NULLIF(t.from_facility_reference, ''), t.to_facility_reference)",
        False,
    ),
    # location_name carries the SAME expression as location_gln (#2535).
    (
        "location_name",
        "p.location_name",
        "COALESCE(NULLIF(t.from_facility_reference, ''), t.to_facility_reference)",
        False,
    ),
    # source = source_system
    ("source", "p.source", "t.source_system", False),
    # ---- the recall-filter predicate columns -------------------------------
    # build_recall_where_clause / build_recall_where_clause_canonical filter on
    # event_type, traceability_lot_code and event_timestamp. A divergence in
    # any of these changes WHICH ROWS a regulator's recall search returns, not
    # merely what a cell says, so they are the highest-value columns in the
    # whole comparison. All three are verbatim column-to-column copies under
    # dual_write_legacy (legacy_dual_write.py: :event_type, :tlc,
    # :event_timestamp).
    ("event_type", "p.event_type", "t.event_type", False),
    ("traceability_lot_code", "p.traceability_lot_code", "t.traceability_lot_code", False),
    # Both sides are TIMESTAMPTZ (verified against the live schema at alembic
    # head), so IS DISTINCT FROM is an exact instant comparison — no textual
    # or timezone coercion is involved.
    ("event_timestamp", "p.event_timestamp", "t.event_timestamp", False),
    # ---- the remaining regulator-visible payload columns -------------------
    # Both quantity columns are DOUBLE PRECISION on both tables and
    # dual_write_legacy binds the identical Python float to each, so a direct
    # IS DISTINCT FROM is exact. (No ::numeric cast: casting would introduce a
    # rounding step that is not in the write path and could MASK a real
    # divergence rather than reveal one.)
    ("quantity", "p.quantity", "t.quantity", False),
    ("unit_of_measure", "p.unit_of_measure", "t.unit_of_measure", False),
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
                   c.product_description, c.location_gln, c.location_name, c.source,
                   c.event_type, c.traceability_lot_code, c.event_timestamp,
                   c.quantity, c.unit_of_measure
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
            -- Carried so an ORPHAN can be CLASSIFIED (legacy-native writer vs
            -- genuinely lost canonical write) without a second query. These
            -- are exactly the inputs to compute_event_hash.
            p.event_type                                AS legacy_event_type,
            p.traceability_lot_code                     AS legacy_tlc,
            p.product_description                       AS legacy_product_description,
            p.quantity                                  AS legacy_quantity,
            p.unit_of_measure                           AS legacy_uom,
            p.location_gln                              AS legacy_location_gln,
            p.location_name                             AS legacy_location_name,
            p.event_timestamp                           AS legacy_event_timestamp,
            lk.v                                        AS legacy_kdes,
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


def build_out_of_window_query(opts: "Options") -> Tuple[str, Dict[str, Any]]:
    """Legacy rows in scope that the scan's WINDOW EXCLUDED.

    This is the fix for the false green that ``--since`` used to produce: the
    old COVERAGE block printed ``legacy rows in window`` (which applies the
    same window as the scan), so a one-month scan of a multi-year compliance
    table read as complete table coverage and still exited 0.

    Only the TENANT predicate is applied here — never ``--since``/``--until``
    — so the result is "how much of this tenant scope did the window hide".
    ``MIN``/``MAX(ingested_at)`` of the hidden set is returned with it so the
    operator can widen the window without guessing.
    """
    params: Dict[str, Any] = {}
    conds: List[str] = []
    if opts.tenants:
        conds.append("c.tenant_id = ANY(CAST(:tenants AS uuid[]))")
        params["tenants"] = [str(t) for t in opts.tenants]
    # The complement of the scanned window.
    window_misses: List[str] = []
    if opts.since is not None:
        window_misses.append("c.ingested_at < :since")
        params["since"] = opts.since
    if opts.until is not None:
        window_misses.append("c.ingested_at >= :until")
        params["until"] = opts.until
    if not window_misses:
        # No window at all — nothing can be outside it. Still issue a real
        # query (rather than fabricating zeros) so the totals come from the
        # same snapshot as everything else.
        window_misses.append("FALSE")
    conds.append("(" + " OR ".join(window_misses) + ")")
    where = " AND ".join(conds)
    return (
        f"""
        SELECT COUNT(*),
               MIN(c.ingested_at),
               MAX(c.ingested_at)
        FROM fsma.cte_events c
        WHERE {where}
        """,
        params,
    )


def build_orphan_content_probe_query() -> str:
    """Does a canonical row exist carrying this legacy row's CONTENT?

    Used ONLY on orphans already classified ``legacy-native`` by the hash
    probe, to corroborate that ``webhook_compat``'s sibling
    ``CanonicalEventStore(dual_write=False)`` call actually landed.

    The tuple is exactly the set of columns ``normalize_webhook_event`` passes
    through verbatim from the webhook event to the canonical model. It is NOT
    a unique key and it is NOT proof of identity — two genuinely distinct
    events can share it. It is reported as corroboration and never feeds the
    pass/fail verdict; what it usefully detects is the alarming case, a
    legacy-native orphan with NO canonical row that even resembles it.
    """
    return """
        SELECT EXISTS (
            SELECT 1
            FROM fsma.traceability_events t
            WHERE t.tenant_id = CAST(:tenant_id AS uuid)
              AND t.event_type = :event_type
              AND t.traceability_lot_code = :tlc
              AND t.event_timestamp = :event_timestamp
              AND t.quantity = :quantity
              AND t.unit_of_measure = :uom
        )
    """


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
    skip_content_probe: bool = False
    max_content_probe: int = 5000


@dataclass
class Sample:
    sha256_hash: str
    tenant_id: str
    legacy_id: str
    same_transaction: bool
    diffs: Dict[str, Any]
    # Orphan classification. None for divergence samples.
    orphan_class: Optional[str] = None


@dataclass
class Report:
    rows_examined: int = 0
    rows_matched: int = 0
    rows_matched_same_txn: int = 0
    rows_matched_cross_txn: int = 0
    ambiguous_matches: int = 0
    legacy_orphans: int = 0
    # --- orphan classification (see matches_legacy_formula) ---
    # legacy-native: stored hash reproduces compute_event_hash over this row.
    # Structural non-join, NOT a #1277 violation, and exactly the class
    # backfill_canonical_from_legacy.py refuses under
    # ``legacy_native_hash_formula``.
    orphans_legacy_native: int = 0
    # unexplained: neither joins by hash nor reproduces the legacy formula.
    # This IS the lost-canonical-write case. Drives the DO-NOT-PROCEED verdict.
    orphans_unexplained: int = 0
    # Corroboration for legacy-native orphans only (see the content probe).
    content_probe_attempted: int = 0
    content_probe_corroborated: int = 0
    content_probe_uncorroborated: int = 0
    diverged_rows: int = 0
    diverged_same_txn: int = 0
    diverged_cross_txn: int = 0
    field_divergence: Dict[str, int] = field(default_factory=dict)
    orphan_samples: List[Sample] = field(default_factory=list)
    divergence_samples: List[Sample] = field(default_factory=list)
    legacy_total_in_window: Optional[int] = None
    # Legacy rows in tenant scope that the --since/--until window EXCLUDED.
    # Non-zero means the scan is PARTIAL, whatever else it found.
    legacy_out_of_window: Optional[int] = None
    out_of_window_oldest: Optional[datetime] = None
    out_of_window_newest: Optional[datetime] = None
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


def classify_orphan(conn: Any, row: Any, opts: Options, report: Report) -> str:
    """Decide what an unjoined legacy row actually means.

    Returns ``"legacy-native"`` (structural, expected while
    ``webhook_compat.ingest_events`` is a live ingest route) or
    ``"unexplained"`` (a lost canonical write, #1277 — a hard failure).

    The hash probe is authoritative for the class. The content probe that
    follows it only annotates a legacy-native orphan with whether a canonical
    row carrying the same content exists; it never changes the class, because
    a content match is corroboration and not identity.
    """
    is_legacy_native = matches_legacy_formula(
        legacy_id=row.legacy_id,
        event_type=row.legacy_event_type,
        tlc=row.legacy_tlc,
        product_description=row.legacy_product_description,
        quantity=row.legacy_quantity,
        unit_of_measure=row.legacy_uom,
        location_gln=row.legacy_location_gln,
        location_name=row.legacy_location_name,
        event_timestamp=row.legacy_event_timestamp,
        kdes=row.legacy_kdes,
        stored_hash=row.sha256_hash,
    )
    if not is_legacy_native:
        report.orphans_unexplained += 1
        return "unexplained"

    report.orphans_legacy_native += 1

    if opts.skip_content_probe or report.content_probe_attempted >= opts.max_content_probe:
        return "legacy-native"

    try:
        corroborated = read_only_execute(
            conn,
            build_orphan_content_probe_query(),
            {
                "tenant_id": row.tenant_id,
                "event_type": row.legacy_event_type,
                "tlc": row.legacy_tlc,
                "event_timestamp": row.legacy_event_timestamp,
                "quantity": row.legacy_quantity,
                "uom": row.legacy_uom,
            },
        ).scalar()
    except Exception as exc:  # noqa: BLE001 — corroboration only, never fatal
        if "content probe" not in " ".join(report.notes):
            report.notes.append(
                f"content probe unavailable ({type(exc).__name__}: {str(exc)[:120]}); "
                "legacy-native orphans are reported without corroboration."
            )
        return "legacy-native"

    report.content_probe_attempted += 1
    if corroborated:
        report.content_probe_corroborated += 1
    else:
        report.content_probe_uncorroborated += 1
    return "legacy-native"


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
                orphan_class = classify_orphan(conn, first, opts, report)
                sample = Sample(
                    sha256_hash=first.sha256_hash,
                    tenant_id=first.tenant_id,
                    legacy_id=legacy_id,
                    same_transaction=False,
                    diffs={},
                    orphan_class=orphan_class,
                )
                # Sample UNEXPLAINED orphans preferentially. The legacy-native
                # class is expected and bulk-countable; every unexplained
                # orphan is a potential lost FDA record and needs a human, so
                # it evicts a legacy-native sample rather than being dropped.
                if len(report.orphan_samples) < opts.max_samples:
                    report.orphan_samples.append(sample)
                elif orphan_class == "unexplained":
                    for i, existing in enumerate(report.orphan_samples):
                        if existing.orphan_class != "unexplained":
                            report.orphan_samples[i] = sample
                            break
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
        # Session scope (`false`), deliberately NOT the canonical
        # set_tenant_guc primitive: that helper is transaction-scoped
        # (`true`), and this parity scan issues many statements outside any
        # single transaction, so a transaction-scoped GUC would fall out of
        # scope mid-scan. Safe to suppress here — the connection is asserted
        # read-only immediately above, so this grants visibility for a
        # read-only scan and cannot be a write-side tenant grant.
        read_only_execute(
            conn,
            "SELECT set_config('app.tenant_id', :tid, false)",  # nosemgrep: adhoc-tenant-guc-set-config
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


def coverage_gaps(report: Report, opts: Options) -> List[str]:
    """Every reason this scan proved LESS than the whole legacy store.

    Each entry is a human-readable phrase. A non-empty list means the run is
    not a cutover decision no matter how clean it was — that is the whole
    point of separating this from the violation check.
    """
    gaps: List[str] = []
    if report.truncated_by_limit:
        gaps.append(f"--limit truncated the scan after {report.rows_compared:,} row(s)")
    if report.legacy_out_of_window:
        window = []
        if opts.since is not None:
            window.append(f"--since {opts.since.isoformat()}")
        if opts.until is not None:
            window.append(f"--until {opts.until.isoformat()}")
        oldest = report.out_of_window_oldest.isoformat() if report.out_of_window_oldest else "?"
        gaps.append(
            f"{report.legacy_out_of_window:,} legacy row(s) fall OUTSIDE the scanned window "
            f"({', '.join(window) or 'settle window'}; oldest excluded ingested_at {oldest}) "
            "and were never compared"
        )
    if opts.ignore_fields:
        gaps.append(
            f"--ignore-field suppressed {', '.join(opts.ignore_fields)} from every comparison"
        )
    if not LEGACY_HASH_PROBE_AVAILABLE and report.legacy_orphans:
        gaps.append(
            "the legacy-native hash probe could not be imported, so orphans could not be "
            "classified"
        )
    # Legacy-native orphans can never join canonical by hash, so the content
    # probe is the ONLY evidence canonical covers them. An orphan the probe
    # could not corroborate — or never examined at all — is a row this scan
    # cannot show the canonical store holds. Retiring the legacy store on
    # exit 0 while such rows exist would discard the sole copy of an FDA
    # traceability record, so both cases must deny SAFE-TO-PROCEED the same
    # way every other unproven-coverage condition above does.
    if report.content_probe_uncorroborated:
        gaps.append(
            f"{report.content_probe_uncorroborated:,} legacy-native orphan(s) have NO "
            "canonical row matching even on content — canonical coverage of these rows "
            "is unproven; investigate each one before any retirement decision"
        )
    unprobed_native = report.orphans_legacy_native - report.content_probe_attempted
    if unprobed_native > 0:
        gaps.append(
            f"{unprobed_native:,} legacy-native orphan(s) were never content-probed "
            "(--skip-content-probe, or the --max-content-probe cap) — their canonical "
            "coverage is unknown; re-run with probing enabled and a cap of at least "
            f"{report.orphans_legacy_native:,}"
        )
    return gaps


def decide(report: Report, opts: Options) -> Tuple[int, str, str]:
    """Return ``(exit_code, headline, reason)``. Pure function — easy to test.

    Order matters and is deliberate:

      1. Real violations lose to nothing. An unexplained orphan or a field
         divergence is DO-NOT-PROCEED even if coverage was also partial.
      2. Zero coverage is never success.
      3. PARTIAL coverage gets its OWN exit code (4), not 0. A clean scan of
         a window is not a clean scan of the table, and ``if verify; then
         proceed`` must not read it as green.
      4. Only a full-coverage, violation-free scan is SAFE-TO-PROCEED.
    """
    reasons: List[str] = []
    if report.orphans_unexplained:
        reasons.append(
            f"{report.orphans_unexplained:,} legacy row(s) have no canonical twin AND do not "
            "reproduce the legacy compute_event_hash formula — these were written by "
            "dual_write_legacy and their canonical write was LOST (#1277)"
        )
    if report.diverged_rows:
        reasons.append(
            f"{report.diverged_rows:,} matched pair(s) do not satisfy the dual_write_legacy "
            f"mapping (fields: {', '.join(sorted(report.field_divergence)) or 'n/a'})"
        )
    if reasons:
        return EXIT_VIOLATIONS, "DO-NOT-PROCEED", "; ".join(reasons)

    if report.rows_compared == 0:
        return (
            EXIT_ZERO_COVERAGE,
            "DO-NOT-PROCEED",
            "ZERO COVERAGE — the scan compared 0 legacy rows against canonical, so it "
            "proves nothing. Check the --since/--until window, the --tenant filter, and "
            "whether row-level security is hiding the rows from this role",
        )

    # Legacy-native orphans are NOT a violation, but they are also NOT nothing:
    # they are rows the canonical store cannot be shown to cover by hash. Say
    # so in the reason text of every verdict that carries them.
    native_note = ""
    if report.orphans_legacy_native:
        uncorroborated = ""
        if report.content_probe_uncorroborated:
            uncorroborated = (
                f", and {report.content_probe_uncorroborated:,} of the "
                f"{report.content_probe_attempted:,} probed had NO canonical row matching even "
                "on content — investigate those before any retirement decision"
            )
        native_note = (
            f"; {report.orphans_legacy_native:,} legacy row(s) were written by the "
            "legacy-native store_event path (their stored hash reproduces "
            "compute_event_hash), so they can never join canonical by sha256_hash — "
            "structural, NOT a lost write, and the same class "
            "backfill_canonical_from_legacy.py refuses under legacy_native_hash_formula"
            f"{uncorroborated}"
        )

    gaps = coverage_gaps(report, opts)
    if gaps:
        return (
            EXIT_PARTIAL,
            "PARTIAL COVERAGE — NOT A CUTOVER DECISION",
            f"no violations in the {report.rows_compared:,} row(s) actually compared, but this "
            f"scan did not cover the whole legacy store: {'; '.join(gaps)}. Re-run with no "
            f"--since/--until, no --limit and no --ignore-field before making a release "
            f"decision{native_note}",
        )

    return (
        EXIT_SAFE,
        "SAFE-TO-PROCEED",
        f"{report.rows_compared:,} legacy row(s) — every row in scope, none excluded by a "
        "window or a limit — have a canonical twin that reproduces the dual_write_legacy "
        f"mapping on all {len(FIELD_NAMES)} mapped columns; 0 unexplained orphans, "
        f"0 field divergences{native_note}",
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
    add(f"  legacy rows OUTSIDE the scanned window      : {_fmt(report.legacy_out_of_window)}")
    if report.legacy_out_of_window:
        oldest = report.out_of_window_oldest.isoformat() if report.out_of_window_oldest else "?"
        newest = report.out_of_window_newest.isoformat() if report.out_of_window_newest else "?"
        add(f"    ** NEVER COMPARED. ingested_at {oldest} .. {newest} **")
        add("    ** this scan is PARTIAL — widen/remove --since/--until to cover them **")
    add(f"  legacy rows examined by this scan           : {report.rows_examined:,}")
    add(f"  rows COMPARED against a canonical twin      : {report.rows_compared:,}")
    add(f"  ambiguous (>1 canonical twin for one hash)  : {report.ambiguous_matches:,}")
    if report.truncated_by_limit:
        add("  ** scan TRUNCATED by --limit — partial coverage **")
    add("")

    add("(a) LEGACY ORPHANS — legacy rows with no canonical row sharing their sha256_hash")
    add(f"  total                                       : {report.legacy_orphans:,}")
    add(
        "  a1. legacy-native hash formula              : "
        f"{report.orphans_legacy_native:,}   [STRUCTURAL — not a lost write]"
    )
    add("      Written by CTEPersistence.store_event (live via webhook_compat.ingest_events).")
    add("      Its stored hash reproduces compute_event_hash, which hashes a DIFFERENT field")
    add("      set than the canonical formula, so it can never join by sha256_hash. This is")
    add("      the class backfill_canonical_from_legacy.py refuses as legacy_native_hash_formula")
    add("      — do NOT feed these to the backfill; doing so would duplicate FDA events.")
    if report.content_probe_attempted or report.orphans_legacy_native:
        add(f"      content-probed                          : {report.content_probe_attempted:,}")
        add(f"        canonical row with matching content   : {report.content_probe_corroborated:,}  [corroborated, not proof]")
        add(f"        NO canonical row even by content      : {report.content_probe_uncorroborated:,}  <-- investigate these")
    add(
        "  a2. unexplained                             : "
        f"{report.orphans_unexplained:,}   [HARD FAILURE — canonical write lost, #1277]"
    )
    if not LEGACY_HASH_PROBE_AVAILABLE:
        add(f"      ** classification UNAVAILABLE ({LEGACY_HASH_PROBE_ERROR}) — every orphan")
        add("      ** was counted as unexplained. Run from the repo root to enable it.")
    for sample in report.orphan_samples:
        label = (sample.orphan_class or "unclassified").upper()
        add(f"    [{label}] sha256={sample.sha256_hash}  tenant={sample.tenant_id}  cte_events.id={sample.legacy_id}")
    add("")

    add("(b) CANONICAL-ONLY   [INFORMATIONAL — expected, dual_write=False paths]")
    add(f"  canonical rows with no legacy twin          : {_fmt(report.canonical_only)}")
    add(f"  canonical rows with NULL sha256_hash        : {_fmt(report.canonical_unjoinable)}")
    if report.canonical_unjoinable:
        add("    (unjoinable by any tool — sha256_hash is the only cross-store key)")
    add("")

    add("(c) FIELD DIVERGENCE on matched pairs   [ANY non-zero here is a HARD FAILURE]")
    for name in FIELD_NAMES:
        if name in opts.ignore_fields:
            add(f"  {name:<22}: (ignored)  <-- NOT VERIFIED")
        else:
            add(f"  {name:<22}: {report.field_divergence.get(name, 0):,}")
    add(f"  rows with >=1 divergence : {report.diverged_rows:,}")
    # A matched pair whose ingested_at differs did NOT come out of one
    # dual_write_legacy transaction. Since the only other legacy writer emits
    # a hash that cannot join at all, such a pair should not exist — it is an
    # anomaly worth a human's eye, not a benign "other writer" class.
    if report.rows_matched_cross_txn:
        add(
            f"  ANOMALY: {report.rows_matched_cross_txn:,} matched pair(s) have DIFFERENT "
            "ingested_at."
        )
        add("    dual_write_legacy writes both rows in one transaction, so ingested_at is")
        add("    identical by construction. A mismatch means something other than the known")
        add("    write paths produced this pair. Investigate before proceeding.")
    add("")
    add("(d) EXPORT COLUMNS NOT COMPARED BY THIS TOOL")
    for column, why in UNCOMPARED_EXPORT_COLUMNS:
        add(f"  {column:<22}: {why}")
    if opts.ignore_fields:
        add(f"  {'(operator --ignore-field)':<22}: {', '.join(opts.ignore_fields)}")
    add("")
    if report.divergence_samples:
        add(f"  first {len(report.divergence_samples)} mismatching sha256_hash value(s):")
        for sample in report.divergence_samples:
            kind = "same-transaction" if sample.same_transaction else "DIFFERING ingested_at"
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
            "legacy_out_of_window": report.legacy_out_of_window,
            "out_of_window_oldest": report.out_of_window_oldest,
            "out_of_window_newest": report.out_of_window_newest,
            "rows_examined": report.rows_examined,
            "rows_compared": report.rows_compared,
            "same_transaction": report.rows_matched_same_txn,
            "cross_transaction": report.rows_matched_cross_txn,
            "ambiguous_matches": report.ambiguous_matches,
            "truncated_by_limit": report.truncated_by_limit,
            "full_coverage": not coverage_gaps(report, opts),
            "gaps": coverage_gaps(report, opts),
        },
        "legacy_orphans": {
            "count": report.legacy_orphans,
            # The count that actually drives the verdict. `count` alone is NOT
            # a failure signal — see the docstring on the two hash formulas.
            "unexplained": report.orphans_unexplained,
            "legacy_native_hash_formula": report.orphans_legacy_native,
            "classification_available": LEGACY_HASH_PROBE_AVAILABLE,
            "content_probe": {
                "attempted": report.content_probe_attempted,
                "corroborated": report.content_probe_corroborated,
                "uncorroborated": report.content_probe_uncorroborated,
            },
            "samples": [
                {
                    "sha256_hash": s.sha256_hash,
                    "tenant_id": s.tenant_id,
                    "legacy_id": s.legacy_id,
                    "orphan_class": s.orphan_class,
                }
                for s in report.orphan_samples
            ],
        },
        "uncompared_export_columns": [c for c, _why in UNCOMPARED_EXPORT_COLUMNS] + list(opts.ignore_fields),
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
            "EXIT CODES: 0 safe-to-proceed (FULL coverage, no violations) | "
            "1 parity violations | 2 could not complete | "
            "3 zero coverage (false-green guard) | "
            "4 clean but PARTIAL coverage — not a cutover decision. "
            "Only 0 means proceed. This program never writes to the database."
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
        help="exclude a mapped field from the comparison (repeatable). Echoed in the verdict "
        "block AND downgrades the run to exit 4 (PARTIAL COVERAGE), because a verdict that "
        "skipped a column is not a verdict on that column.",
    )
    parser.add_argument("--skip-canonical-only", action="store_true", help="skip the informational canonical-only anti-join count")
    parser.add_argument(
        "--settle-seconds",
        type=int,
        default=DEFAULT_SETTLE_SECONDS,
        metavar="S",
        help=(
            f"exclude the most recent S seconds when --until is omitted (default {DEFAULT_SETTLE_SECONDS} "
            "= disabled). There is NO phantom-orphan race against a primary: every writer commits "
            "its legacy and canonical rows in ONE transaction. Useful only against a read replica, "
            "and any rows it excludes are reported as out-of-window and downgrade the verdict."
        ),
    )
    parser.add_argument(
        "--skip-content-probe",
        action="store_true",
        help="skip the per-orphan canonical content lookup used to corroborate legacy-native "
        "orphans. Faster on a database with very many orphans; costs you the "
        "'no canonical row even by content' signal.",
    )
    parser.add_argument(
        "--max-content-probe",
        type=int,
        default=5000,
        metavar="N",
        help="cap the orphan content probe at N lookups (default 5000). The probe has no "
        "supporting index, so it is bounded by default.",
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
        skip_content_probe=args.skip_content_probe,
        max_content_probe=max(0, args.max_content_probe),
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
        # REPEATABLE READ so every number in the report — the in-window total,
        # the out-of-window total, every scan page, the canonical-only
        # anti-join — is read from ONE snapshot. Without it a concurrent
        # ingest between two statements can make the counts disagree and
        # manufacture a phantom orphan or a phantom coverage gap. This is a
        # SQLAlchemy-level option, so it does not go through (or need to be
        # excepted from) the read-only statement allowlist.
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
            info = preflight(conn, opts)

            if info.get("canonical_sha_index") is None:
                report.notes.append(
                    "fsma.traceability_events has NO index containing sha256_hash, so each "
                    "batch's twin lookup may scan the canonical table. On a large database "
                    "run with --limit first, or ask a DBA to add: CREATE INDEX CONCURRENTLY "
                    "idx_trace_events_tenant_sha256 ON fsma.traceability_events "
                    "(tenant_id, sha256_hash);  (this tool will NOT create it — it is read-only)"
                )
            if not LEGACY_HASH_PROBE_AVAILABLE:
                report.notes.append(
                    "the legacy-native hash probe could not be imported "
                    f"({LEGACY_HASH_PROBE_ERROR}). Orphans CANNOT be classified, so every "
                    "orphan is reported as unexplained (the conservative direction). Run "
                    "this script from a checkout of the repo to enable classification."
                )
            if not opts.until_was_explicit and opts.settle_seconds > 0:
                report.notes.append(
                    f"--until was set to now() - {opts.settle_seconds}s by --settle-seconds. "
                    "Rows in that tail are NOT verified and are counted as out-of-window; "
                    "there is no phantom-orphan race against a primary, so 0 is the right "
                    "value unless you are scanning a lagging replica."
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

            # The coverage-honesty probe. This is what stops a --since-narrowed
            # scan of a multi-year table from exiting 0 SAFE-TO-PROCEED: it
            # counts, with the tenant predicate ONLY, the legacy rows the
            # window excluded. Non-zero => EXIT_PARTIAL, never EXIT_SAFE.
            sql, params = build_out_of_window_query(opts)
            out_row = read_only_execute(conn, sql, params).fetchone()
            if out_row is not None:
                report.legacy_out_of_window = out_row[0]
                report.out_of_window_oldest = out_row[1]
                report.out_of_window_newest = out_row[2]

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
