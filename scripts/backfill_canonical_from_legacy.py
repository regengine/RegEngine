#!/usr/bin/env python3
"""WS-1c — backfill canonical rows for legacy ``fsma.cte_events`` orphans (#1335).

Goal
====
Before the legacy write path can be retired (WS-1d), the canonical store
(``fsma.traceability_events``) must be a complete **superset** of the legacy
store (``fsma.cte_events``). Any legacy row with no canonical twin is a gap.
The ONLY cross-store join key is ``sha256_hash`` — the two stores use
different idempotency-key formulas (see
``TraceabilityEvent.compute_idempotency_key`` vs
``cte_persistence.hashing.compute_idempotency_key``), so nothing else joins
them reliably.

Directionality (matches ``tests/invariants/test_dual_write_parity.py``):
canonical-only rows are EXPECTED (several ingestion paths run
``dual_write=False`` by design). Legacy-only rows are the error this script
repairs.

How a canonical row is reconstructed
====================================
``services/shared/canonical_persistence/legacy_dual_write.py ::
dual_write_legacy`` is the forward mapping. This script inverts it:

===========================  ==========================================
legacy ``cte_events`` column  canonical ``traceability_events`` field
===========================  ==========================================
``id``                        ``event_id``           (verbatim)
``event_type``                ``event_type``         (verbatim)
``traceability_lot_code``     ``traceability_lot_code``
``product_description``       ``COALESCE(product_reference,'')`` inverse
``quantity``                  ``quantity``
``unit_of_measure``           ``unit_of_measure``
``location_gln``              ``from_facility_reference`` OR
                              ``to_facility_reference``   ** AMBIGUOUS **
``location_name``             same value as ``location_gln`` (#2535)
``event_timestamp``           ``event_timestamp``
``source``                    ``source_system``
``source_event_id``           ``source_record_id``
``sha256_hash``               ``sha256_hash``        (verbatim, never recomputed)
``chain_hash``                ``chain_hash``         (verbatim)
``epcis_*``                   ``epcis_*``            (verbatim)
``validation_status``         ``status``             ** LOSSY, see below **
``ingested_at``               ``ingested_at`` / ``created_at``
``cte_kdes`` rows             ``kdes``   (None-valued keys were DROPPED)
===========================  ==========================================

The ambiguity problem, and why this script does not guess
=========================================================
``dual_write_legacy`` collapses ``from_facility_reference`` and
``to_facility_reference`` into the single ``location_gln`` column
(``from or to``). Picking one direction at random would fabricate
provenance on an FDA traceability record. That is unacceptable.

Instead this script uses the integrity anchor as an oracle. The canonical
hash preimage (``TraceabilityEvent.compute_sha256_hash``) is::

    event_id|event_type|tlc|product_reference|quantity|unit_of_measure|
    from_facility_reference|to_facility_reference|event_timestamp|json(kdes)

— i.e. it covers **both** facility fields separately. So for every legacy row
we enumerate the (small, closed) set of split hypotheses consistent with
``from or to == location_gln``::

    location_gln IS NOT NULL ->  (gln, NULL)   "from only"
                                 (NULL, gln)   "to only"
                                 (gln, gln)    "from and to"
    location_gln IS NULL     ->  (NULL, NULL)  "neither"

recompute the canonical SHA-256 for each, and accept a hypothesis ONLY when
it reproduces the stored ``sha256_hash`` bit for bit. A match is proof, not a
guess: it simultaneously verifies event_id, event_type, TLC,
product_reference, quantity, UoM, both facility references, the timestamp and
every KDE. Rows where no hypothesis reproduces the stored hash are REFUSED
and reported — never synthesized.

This is also a hard requirement, not just an ethical one: chain verification
(``canonical_persistence/verification.py::_recompute_event_sha256``)
recomputes the canonical hash from the stored canonical columns. A row
inserted with columns that do not reproduce its own ``sha256_hash`` would
turn into a permanent chain-verification failure.

Two classes of legacy orphan
============================
1. ``dual_write_legacy`` rows whose canonical write was lost (#1277). These
   carry the CANONICAL hash formula, so a hypothesis will reproduce it, and
   they are what this script backfills.
2. Rows written by the legacy-native path
   (``cte_persistence.writes.WritePathMixin.store_event``, still live via
   ``webhook_compat.ingest_events``). Those compute their ``sha256_hash``
   with a DIFFERENT formula (``cte_persistence.hashing.compute_event_hash``
   — no ``to_facility``, no ``product_description``, ``location_gln`` only),
   so they can never join to a canonical row by hash even when the same
   real-world event WAS written canonically by the sibling canonical-only
   store call. Backfilling those would (a) duplicate an event that already
   exists canonically and (b) inject a hash into the canonical store that the
   canonical verifier cannot reproduce. This script detects them by
   recomputing the legacy formula, reports them under
   ``legacy_native_hash_formula``, and REFUSES to write them.

What is NOT reconstructible, and what we do about it
====================================================
* ``lot_reference``, ``from_entity_reference``, ``to_entity_reference``,
  ``transport_reference``, ``event_timezone``, ``raw_payload``,
  ``source_file_id``, ``ingestion_run_id``, ``supersedes_event_id``,
  ``confidence_score``, ``schema_version`` — never carried to the legacy
  table. Written as NULL / column default (i.e. "unknown"), never invented.
  ``raw_payload`` stays ``{}``: a fabricated source record is worse than an
  absent one.
* ``validation_status`` is lossy in the forward direction
  (``active``/``superseded``/``draft`` all map to ``valid``). We recover
  ``superseded`` when some canonical row already points at this event via
  ``supersedes_event_id``; otherwise the choice is recorded explicitly in
  ``provenance_metadata.backfill.ambiguities`` rather than being made
  silently. ``--status-ambiguous=skip`` refuses those rows instead.
* ``product_description = ''`` inverts to ``product_reference = NULL``.
  ``''`` and ``NULL`` are hash-equivalent (``product_reference or ""``) so
  the oracle cannot separate them; NULL is the conservative reading of the
  ``COALESCE`` and is counted in the summary.
* KDE keys whose value was ``None`` were dropped by the forward mapping and
  cannot be recovered — such a row simply fails hash verification and is
  reported, not written.

``fsma.hash_chain`` is deliberately NOT touched
===============================================
The chain is append-only and sequence-numbered per tenant; inserting rows
during a backfill would consume sequence numbers and break
``verify_chain``/``verify_chain_canonical``. The chain entry for a legacy
orphan normally already exists (both write paths write one). The script
reports ``chain_entry_missing`` as an informational count for a human to act
on; it never writes to ``fsma.hash_chain``.

Safety
======
* ``--dry-run`` is the DEFAULT. Writing requires an explicit ``--execute``.
  A bare invocation opens a transaction, never issues an INSERT, and rolls
  back.
* Idempotent and resumable. Re-running is safe: a backfilled row is no longer
  an orphan, so the anti-join skips it. Refused rows are re-evaluated
  deterministically to the same decision. ``--state-file`` records a per-tenant
  cursor so an interrupted long run resumes without re-walking refusals.
* Commits per ``--batch-size``; each row insert runs inside a SAVEPOINT so one
  bad row cannot poison its batch.
* Tenant-scoped: ``app.tenant_id`` is set per tenant inside every transaction,
  so RLS (``tenant_isolation_trace_events`` / ``tenant_isolation_cte``) is
  enforced, not bypassed.

Usage
=====
    # inspect only (default, safe)
    DATABASE_URL=... python3 scripts/backfill_canonical_from_legacy.py

    # write
    DATABASE_URL=... python3 scripts/backfill_canonical_from_legacy.py \
        --execute --batch-size 200 --report-path /tmp/ws1c-report.jsonl

Exit codes: 0 = ran cleanly (refusals are a normal, reportable outcome),
1 = one or more rows raised an unexpected error, 2 = could not connect /
no tenants resolved.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid as _uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# --- import bootstrap -------------------------------------------------------
# ``shared.*`` lives under services/; ``services.shared.*`` needs the repo root.
_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "services"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from shared.canonical_event import (  # noqa: E402
    CTEType,
    EventStatus,
    IngestionSource,
    TraceabilityEvent,
)
from shared.cte_persistence.hashing import compute_event_hash  # noqa: E402
from sqlalchemy import bindparam, create_engine, event as sa_event, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

logger = logging.getLogger("backfill-canonical")

BACKFILL_MAPPER_NAME = "backfill_canonical_from_legacy"
BACKFILL_MAPPER_VERSION = "1.0.0"
BACKFILL_ISSUE = "#1335 WS-1c"

# ``traceability_events.schema_version`` is TEXT. The true value for a legacy
# row is unknowable, so we write the column default — the same marker
# pre-#1197 rows carry. ``TraceabilityEvent._coerce_schema_version`` maps it
# to integer 1 on read.
UNKNOWN_SCHEMA_VERSION = "1.0.0"

# Fields the legacy table never carried. Recorded on every backfilled row so a
# consumer (or an auditor) can see exactly what is absent rather than
# inferring that NULL means "the supplier sent nothing".
UNRECOVERABLE_FIELDS = (
    "lot_reference",
    "from_entity_reference",
    "to_entity_reference",
    "transport_reference",
    "event_timezone",
    "raw_payload",
    "source_file_id",
    "ingestion_run_id",
    "supersedes_event_id",
    "confidence_score",
    "schema_version",
)

# --- refusal reasons --------------------------------------------------------
R_LEGACY_NATIVE = "legacy_native_hash_formula"
R_HASH_UNRECONSTRUCTIBLE = "hash_unreconstructible"
R_NOT_CANONICAL_SHAPED = "not_canonical_shaped"
R_QUANTITY_NOT_POSITIVE = "quantity_not_positive"
R_EVENT_ID_TAKEN = "event_id_already_in_canonical"
R_IDEMPOTENCY_COLLISION = "idempotency_key_collision"
R_STATUS_AMBIGUOUS = "status_ambiguous_refused"
R_INSERT_FAILED = "insert_failed"

REFUSAL_HELP = {
    R_LEGACY_NATIVE: (
        "sha256_hash matches cte_persistence.hashing.compute_event_hash, i.e. the row "
        "was written by the legacy-native store_event path, NOT by dual_write_legacy. "
        "Its hash formula differs from the canonical one, so it can never join to "
        "canonical by hash and a canonical twin may already exist under a different "
        "hash. Synthesizing one would duplicate an FDA event — refused by design."
    ),
    R_HASH_UNRECONSTRUCTIBLE: (
        "No facility-split hypothesis reproduced the stored sha256_hash. Known causes: "
        "the original event_timestamp carried a non-UTC offset (the offset string is "
        "part of the hash preimage and is not preserved by timestamptz), a KDE whose "
        "value was None (dropped by the forward mapping), a JSON round-trip that "
        "changed a number's rendering, a facility pair where to_facility is a third "
        "value not derivable from location_gln, or tampering. Refused."
    ),
    R_NOT_CANONICAL_SHAPED: (
        "The legacy row cannot be expressed as a TraceabilityEvent (unknown "
        "event_type / source_system enum value, TLC shorter than 3 chars, ...). "
        "Almost always a legacy-native row. Refused."
    ),
    R_QUANTITY_NOT_POSITIVE: (
        "traceability_events_quantity_check requires quantity > 0; this legacy row "
        "does not satisfy it. Refused rather than mutating the value."
    ),
    R_EVENT_ID_TAKEN: (
        "A canonical row already exists with this event_id but a different "
        "sha256_hash. That is a genuine divergence needing human review — refused."
    ),
    R_IDEMPOTENCY_COLLISION: (
        "A canonical row already exists with the idempotency_key this reconstruction "
        "computes, but a different sha256_hash. The canonical twin probably exists "
        "with drifted content. Refused — needs human review."
    ),
    R_STATUS_AMBIGUOUS: (
        "validation_status='valid' maps back to active|superseded|draft and no "
        "canonical superseder was found; --status-ambiguous=skip was requested."
    ),
    R_INSERT_FAILED: "The INSERT raised; the row's SAVEPOINT was rolled back.",
}


# ---------------------------------------------------------------------------
# Tenant GUC
# ---------------------------------------------------------------------------

try:  # pragma: no cover - import shape depends on the deploy env
    from services.shared.tenant_context import set_tenant_guc as _set_tenant_guc
except Exception:  # pragma: no cover - ops boxes without FastAPI installed
    _set_tenant_guc = None


def set_tenant_context(session: Session, tenant_id: str) -> None:
    """Bind ``app.tenant_id`` for the current transaction.

    Prefers the repo's canonical primitive
    (``services.shared.tenant_context.set_tenant_guc``) so this script uses
    the exact same SQL as production writers; falls back to that primitive's
    own SQL form when FastAPI is not installed in the ops environment.
    """
    _uuid.UUID(str(tenant_id))  # loud failure before any SQL runs
    if _set_tenant_guc is not None:
        _set_tenant_guc(session, str(tenant_id))
        return
    # Import-failure fallback only — unreachable whenever the canonical
    # primitive is available. Suppressed rather than rewritten because both
    # risks the rule guards against are already handled here: the SQL is
    # set_tenant_guc's own documented form verbatim (transaction-scoped
    # `true`, bound parameter, so it is not a *divergent* copy), and the
    # tenant id is UUID-validated above before any SQL runs. Rewriting this
    # to call the primitive unconditionally would break the lean ops images
    # this branch exists for, where the import genuinely fails.
    session.execute(
        text("SELECT set_config('app.tenant_id', :tid, true)"),  # nosemgrep: adhoc-tenant-guc-set-config
        {"tid": str(tenant_id)},
    )


# ---------------------------------------------------------------------------
# Row model
# ---------------------------------------------------------------------------


@dataclass
class LegacyRow:
    """One ``fsma.cte_events`` row plus its reassembled ``kdes`` dict."""

    id: str
    tenant_id: str
    event_type: str
    traceability_lot_code: str
    product_description: str
    quantity: float
    unit_of_measure: str
    location_gln: Optional[str]
    location_name: Optional[str]
    event_timestamp: datetime
    source: str
    source_event_id: Optional[str]
    sha256_hash: str
    chain_hash: str
    epcis_event_type: Optional[str]
    epcis_action: Optional[str]
    epcis_biz_step: Optional[str]
    validation_status: str
    ingested_at: datetime
    kdes: Dict[str, Any] = field(default_factory=dict)


LEGACY_SELECT_COLUMNS = """
    c.id, c.tenant_id, c.event_type, c.traceability_lot_code,
    c.product_description, c.quantity, c.unit_of_measure,
    c.location_gln, c.location_name, c.event_timestamp,
    c.source, c.source_event_id, c.sha256_hash, c.chain_hash,
    c.epcis_event_type, c.epcis_action, c.epcis_biz_step,
    c.validation_status, c.ingested_at
"""


def _row_to_legacy(row: Sequence[Any]) -> LegacyRow:
    return LegacyRow(
        id=str(row[0]),
        tenant_id=str(row[1]),
        event_type=row[2],
        traceability_lot_code=row[3],
        product_description=row[4],
        quantity=float(row[5]),
        unit_of_measure=row[6],
        location_gln=row[7],
        location_name=row[8],
        event_timestamp=row[9],
        source=row[10],
        source_event_id=row[11],
        sha256_hash=row[12],
        chain_hash=row[13],
        epcis_event_type=row[14],
        epcis_action=row[15],
        epcis_biz_step=row[16],
        validation_status=row[17],
        ingested_at=row[18],
    )


# ---------------------------------------------------------------------------
# Reconstruction
# ---------------------------------------------------------------------------

# Human-readable labels for the facility-split hypotheses. Recorded verbatim
# in provenance_metadata so the resolved ambiguity is auditable per row.
H_FROM_ONLY = "from_facility_only"
H_TO_ONLY = "to_facility_only"
H_FROM_AND_TO = "from_and_to_identical"
H_NEITHER = "no_facility_reference"


def facility_hypotheses(
    location_gln: Optional[str],
) -> List[Tuple[str, Optional[str], Optional[str]]]:
    """Closed set of ``(label, from_facility, to_facility)`` candidates.

    The forward mapping is ``location_gln = from_facility or to_facility``.
    Inverting it admits exactly these possibilities (plus the unrecoverable
    ``(gln, <some third value>)``, which no enumeration can produce and which
    therefore surfaces as a hash mismatch).
    """
    if not location_gln:
        return [(H_NEITHER, None, None)]
    return [
        (H_FROM_ONLY, location_gln, None),
        (H_TO_ONLY, None, location_gln),
        (H_FROM_AND_TO, location_gln, location_gln),
    ]


def _build_candidate(
    row: LegacyRow,
    from_facility: Optional[str],
    to_facility: Optional[str],
    status: EventStatus,
) -> TraceabilityEvent:
    """Build a candidate ``TraceabilityEvent`` — no mutation, no hashing side effects.

    Deliberately does NOT call ``prepare_for_persistence()``: that helper runs
    ``_apply_ftl_hint()``, which MUTATES ``kdes`` before hashing. The KDEs read
    back from ``fsma.cte_kdes`` are already post-hint (dual_write_legacy runs
    after prepare), so re-applying anything here would corrupt the preimage.
    """
    return TraceabilityEvent(
        event_id=_uuid.UUID(row.id),
        tenant_id=_uuid.UUID(row.tenant_id),
        source_system=IngestionSource(row.source),
        source_record_id=row.source_event_id,
        event_type=CTEType(row.event_type),
        event_timestamp=row.event_timestamp,
        # COALESCE(product_reference, '') inverse. '' and NULL are
        # hash-equivalent, so this choice is declared, not derived.
        product_reference=row.product_description if row.product_description != "" else None,
        traceability_lot_code=row.traceability_lot_code,
        quantity=row.quantity,
        unit_of_measure=row.unit_of_measure,
        from_facility_reference=from_facility,
        to_facility_reference=to_facility,
        kdes=dict(row.kdes),
        status=status,
        epcis_event_type=row.epcis_event_type,
        epcis_action=row.epcis_action,
        epcis_biz_step=row.epcis_biz_step,
    )


@dataclass
class Reconstruction:
    event: TraceabilityEvent
    hypothesis: str
    product_reference_nulled: bool


def reconstruct(row: LegacyRow, status: EventStatus) -> Tuple[Optional[Reconstruction], Optional[str]]:
    """Return a hash-verified reconstruction, or ``(None, refusal_reason)``.

    A hypothesis is accepted only when ``compute_sha256_hash()`` over the
    rebuilt event equals the legacy row's stored ``sha256_hash`` exactly.
    """
    if row.quantity <= 0:
        return None, R_QUANTITY_NOT_POSITIVE

    model_error: Optional[str] = None
    for label, from_facility, to_facility in facility_hypotheses(row.location_gln):
        try:
            candidate = _build_candidate(row, from_facility, to_facility, status)
        except Exception as exc:  # pydantic ValidationError / bad enum value
            model_error = str(exc)
            break
        if candidate.compute_sha256_hash() == row.sha256_hash:
            return (
                Reconstruction(
                    event=candidate,
                    hypothesis=label,
                    product_reference_nulled=row.product_description == "",
                ),
                None,
            )

    # No canonical hypothesis matched (or none could even be built). The
    # legacy-formula probe is the more specific, more actionable diagnosis, so
    # it is checked first in BOTH failure modes: a legacy-native row commonly
    # also fails to build (``source='api'`` is not an ``IngestionSource``), and
    # reporting it as merely "not canonical shaped" would hide the real reason
    # an operator must not force it into the canonical store.
    if _matches_legacy_formula(row):
        return None, R_LEGACY_NATIVE
    if model_error is not None:
        logger.debug("candidate_model_build_failed", extra={"legacy_id": row.id, "error": model_error})
        return None, R_NOT_CANONICAL_SHAPED
    return None, R_HASH_UNRECONSTRUCTIBLE


def _matches_legacy_formula(row: LegacyRow) -> bool:
    """True when the stored hash is the legacy ``compute_event_hash`` formula.

    Distinguishes a ``store_event`` row (legacy-native, must NOT be
    synthesized into canonical) from a ``dual_write_legacy`` row whose
    canonical twin was lost.
    """
    try:
        return (
            compute_event_hash(
                row.id,
                row.event_type,
                row.traceability_lot_code,
                row.product_description,
                row.quantity,
                row.unit_of_measure,
                row.location_gln,
                row.location_name,
                row.event_timestamp.isoformat(),
                row.kdes,
            )
            == row.sha256_hash
        )
    except Exception:  # pragma: no cover - defensive; classification only
        return False


def build_provenance(
    row: LegacyRow,
    rec: Reconstruction,
    status: EventStatus,
    status_evidence: str,
) -> Dict[str, Any]:
    """Provenance for a backfilled row — explicitly marked, never disguised.

    Keys mirror ``ProvenanceMetadata`` so a strict re-parse still reveals the
    backfill via ``mapper_name`` / ``original_format``; the ``backfill`` block
    carries the full ambiguity record for auditors.
    """
    ambiguities: List[Dict[str, str]] = [
        {
            "field": "from_facility_reference/to_facility_reference",
            "resolution": rec.hypothesis,
            "evidence": "sha256_hash preimage match (proof, not inference)",
        },
        {
            "field": "status",
            "resolution": status.value,
            "evidence": status_evidence,
        },
    ]
    if rec.product_reference_nulled:
        ambiguities.append(
            {
                "field": "product_reference",
                "resolution": "null",
                "evidence": "legacy product_description='' — '' and NULL are hash-equivalent; "
                "NULL is the COALESCE inverse",
            }
        )
    return {
        "mapper_name": BACKFILL_MAPPER_NAME,
        "mapper_version": BACKFILL_MAPPER_VERSION,
        "original_format": "legacy_cte_events",
        "ingestion_timestamp": row.ingested_at.isoformat() if row.ingested_at else None,
        "backfill": {
            "issue": BACKFILL_ISSUE,
            "source_table": "fsma.cte_events",
            "source_row_id": row.id,
            "reconstructed_at": datetime.now(timezone.utc).isoformat(),
            "sha256_verified": True,
            "sha256_hash_preserved_verbatim": True,
            "ambiguities": ambiguities,
            "unrecoverable_fields": list(UNRECOVERABLE_FIELDS),
        },
    }


# ---------------------------------------------------------------------------
# Database access
# ---------------------------------------------------------------------------


def resolve_tenants(session: Session, explicit: Sequence[str]) -> List[str]:
    """Tenant ids to walk.

    RLS on ``fsma.cte_events`` is FORCED and ``get_tenant_context()`` raises
    when ``app.tenant_id`` is unset, so a cross-tenant ``SELECT DISTINCT`` only
    works for a connection that bypasses RLS. Prefer the (non-RLS) ``tenants``
    table, fall back to the distinct scan, and finally ask for ``--tenant-id``.
    """
    if explicit:
        for tid in explicit:
            _uuid.UUID(tid)
        return list(dict.fromkeys(explicit))

    for label, sql in (
        ("tenants", "SELECT id FROM tenants ORDER BY id"),
        ("cte_events", "SELECT DISTINCT tenant_id FROM fsma.cte_events ORDER BY 1"),
    ):
        sp = session.begin_nested()
        try:
            rows = session.execute(text(sql)).fetchall()
            sp.commit()
        except Exception as exc:
            if sp.is_active:
                sp.rollback()
            logger.debug("tenant_enumeration_failed", extra={"source": label, "error": str(exc)})
            continue
        ids = [str(r[0]) for r in rows if r[0] is not None]
        if ids:
            logger.info("tenants_resolved", extra={"source": label, "count": len(ids)})
            return ids
    return []


def count_legacy(session: Session, tenant_id: str) -> Tuple[int, int]:
    """Return ``(total_legacy_rows, orphan_rows)`` for one tenant."""
    total = (
        session.execute(
            text("SELECT COUNT(*) FROM fsma.cte_events WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        ).scalar()
        or 0
    )
    orphans = (
        session.execute(
            text("""
                SELECT COUNT(*)
                FROM fsma.cte_events c
                WHERE c.tenant_id = :tid
                  AND NOT EXISTS (
                      SELECT 1 FROM fsma.traceability_events t
                      WHERE t.tenant_id = c.tenant_id
                        AND t.sha256_hash = c.sha256_hash
                  )
            """),
            {"tid": tenant_id},
        ).scalar()
        or 0
    )
    return int(total), int(orphans)


def fetch_orphan_ids(session: Session, tenant_id: str) -> List[str]:
    """All orphan ids for a tenant, in stable ``(ingested_at, id)`` order.

    Materialized once per tenant: ``fsma.traceability_events`` has no index on
    ``(tenant_id, sha256_hash)``, so the anti-join is a hash anti-join over the
    table. Running it once and paginating in Python keeps that cost O(1) per
    tenant instead of O(batches).
    """
    rows = session.execute(
        text("""
            SELECT c.id
            FROM fsma.cte_events c
            WHERE c.tenant_id = :tid
              AND NOT EXISTS (
                  SELECT 1 FROM fsma.traceability_events t
                  WHERE t.tenant_id = c.tenant_id
                    AND t.sha256_hash = c.sha256_hash
              )
            ORDER BY c.ingested_at, c.id
        """),
        {"tid": tenant_id},
    ).fetchall()
    return [str(r[0]) for r in rows]


_ROWS_SELECT = text(
    f"""
    SELECT {LEGACY_SELECT_COLUMNS}
    FROM fsma.cte_events c
    WHERE c.tenant_id = :tid AND c.id IN :ids
    """
).bindparams(bindparam("ids", expanding=True))

_KDES_SELECT = text(
    """
    SELECT cte_event_id, kde_key, kde_value
    FROM fsma.cte_kdes
    WHERE tenant_id = :tid AND cte_event_id IN :ids
    """
).bindparams(bindparam("ids", expanding=True))


def fetch_rows(session: Session, tenant_id: str, ids: Sequence[str]) -> List[LegacyRow]:
    """Load a chunk of legacy rows plus their KDEs, in the given id order."""
    if not ids:
        return []
    rows = session.execute(_ROWS_SELECT, {"tid": tenant_id, "ids": list(ids)}).fetchall()
    by_id = {str(r[0]): _row_to_legacy(r) for r in rows}

    kde_rows = session.execute(_KDES_SELECT, {"tid": tenant_id, "ids": list(ids)}).fetchall()
    for event_id, key, value in kde_rows:
        target = by_id.get(str(event_id))
        if target is not None:
            target.kdes[key] = value

    return [by_id[i] for i in ids if i in by_id]


def resolve_status(session: Session, row: LegacyRow) -> Tuple[EventStatus, str]:
    """Invert ``validation_status`` with evidence where evidence exists.

    Forward mapping (``legacy_dual_write._STATUS_TO_VALIDATION_STATUS``) is
    many-to-one: active|superseded|draft -> 'valid'. When a canonical row
    already declares ``supersedes_event_id = <this row>`` we KNOW the event was
    superseded; otherwise the choice is recorded as an assumption.
    """
    if row.validation_status == "rejected":
        return EventStatus.REJECTED, "legacy validation_status='rejected' (unambiguous)"
    superseder = session.execute(
        text("""
            SELECT event_id FROM fsma.traceability_events
            WHERE tenant_id = :tid AND supersedes_event_id = :eid
            LIMIT 1
        """),
        {"tid": row.tenant_id, "eid": row.id},
    ).fetchone()
    if superseder:
        return (
            EventStatus.SUPERSEDED,
            f"canonical event {superseder[0]} declares supersedes_event_id = this row",
        )
    return (
        EventStatus.ACTIVE,
        "ASSUMED: legacy validation_status='valid' maps back to active|superseded|draft "
        "and no canonical superseder references this event",
    )


INSERT_SQL = text("""
    INSERT INTO fsma.traceability_events (
        event_id, tenant_id, source_system, source_record_id,
        event_type, event_timestamp, event_timezone,
        product_reference, lot_reference, traceability_lot_code,
        quantity, unit_of_measure,
        from_entity_reference, to_entity_reference,
        from_facility_reference, to_facility_reference,
        transport_reference, kdes, raw_payload, normalized_payload,
        provenance_metadata, confidence_score, status,
        schema_version, sha256_hash, chain_hash, idempotency_key,
        epcis_event_type, epcis_action, epcis_biz_step,
        created_at, ingested_at
    ) VALUES (
        :event_id, :tenant_id, :source_system, :source_record_id,
        :event_type, :event_timestamp, :event_timezone,
        :product_reference, NULL, :traceability_lot_code,
        :quantity, :unit_of_measure,
        NULL, NULL,
        :from_facility_reference, :to_facility_reference,
        NULL, CAST(:kdes AS jsonb), '{}'::jsonb, CAST(:normalized_payload AS jsonb),
        CAST(:provenance_metadata AS jsonb), :confidence_score, :status,
        :schema_version, :sha256_hash, :chain_hash, :idempotency_key,
        :epcis_event_type, :epcis_action, :epcis_biz_step,
        :created_at, :ingested_at
    )
    RETURNING event_id
""")


def insert_params(
    row: LegacyRow,
    rec: Reconstruction,
    provenance: Dict[str, Any],
    confidence_score: float,
) -> Dict[str, Any]:
    """Bind values for one backfilled canonical row.

    ``sha256_hash`` and ``chain_hash`` are copied VERBATIM from the legacy row.
    They are the join key and the integrity anchor; they are never recomputed
    into a different value. (The reconstruction was *verified against*
    ``sha256_hash``, which is what makes the copy safe.)
    """
    event = rec.event
    return {
        "event_id": str(event.event_id),
        "tenant_id": row.tenant_id,
        "source_system": event.source_system.value,
        "source_record_id": event.source_record_id,
        "event_type": event.event_type.value,
        "event_timestamp": event.event_timestamp,
        # Verified: the hash preimage used a +00:00 offset. The zone *name* is
        # not recoverable; 'UTC' is the only value consistent with that proof.
        "event_timezone": "UTC",
        "product_reference": event.product_reference,
        "traceability_lot_code": event.traceability_lot_code,
        "quantity": event.quantity,
        "unit_of_measure": event.unit_of_measure,
        "from_facility_reference": event.from_facility_reference,
        "to_facility_reference": event.to_facility_reference,
        "kdes": json.dumps(event.kdes, default=str),
        # Pure projection of the columns we are writing — no new information.
        "normalized_payload": json.dumps(event.build_normalized_payload(), default=str),
        "provenance_metadata": json.dumps(provenance, default=str),
        "confidence_score": confidence_score,
        "status": event.status.value,
        "schema_version": UNKNOWN_SCHEMA_VERSION,
        "sha256_hash": row.sha256_hash,
        "chain_hash": row.chain_hash,
        "idempotency_key": event.compute_idempotency_key(),
        "epcis_event_type": event.epcis_event_type,
        "epcis_action": event.epcis_action,
        "epcis_biz_step": event.epcis_biz_step,
        "created_at": row.ingested_at,
        "ingested_at": row.ingested_at,
    }


def precheck_conflicts(
    session: Session, row: LegacyRow, idempotency_key: str
) -> Optional[str]:
    """Refuse rather than silently no-op on a canonical-side conflict."""
    taken = session.execute(
        text("""
            SELECT sha256_hash FROM fsma.traceability_events
            WHERE tenant_id = :tid AND event_id = :eid
        """),
        {"tid": row.tenant_id, "eid": row.id},
    ).fetchone()
    if taken is not None:
        return R_EVENT_ID_TAKEN
    clash = session.execute(
        text("""
            SELECT event_id FROM fsma.traceability_events
            WHERE tenant_id = :tid AND idempotency_key = :key
        """),
        {"tid": row.tenant_id, "key": idempotency_key},
    ).fetchone()
    if clash is not None:
        return R_IDEMPOTENCY_COLLISION
    return None


def chain_entry_exists(session: Session, row: LegacyRow) -> bool:
    found = session.execute(
        text("""
            SELECT 1 FROM fsma.hash_chain
            WHERE tenant_id = :tid AND event_hash = :h
            LIMIT 1
        """),
        {"tid": row.tenant_id, "h": row.sha256_hash},
    ).fetchone()
    return found is not None


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


@dataclass
class Summary:
    tenants: int = 0
    legacy_rows_total: int = 0
    already_present: int = 0
    orphans_found: int = 0
    orphans_examined: int = 0
    backfilled: int = 0
    skipped: int = 0
    product_reference_nulled: int = 0
    status_assumed_active: int = 0
    status_recovered_superseded: int = 0
    chain_entry_missing: int = 0
    errors: int = 0
    by_reason: Dict[str, int] = field(default_factory=dict)
    by_hypothesis: Dict[str, int] = field(default_factory=dict)

    def skip(self, reason: str) -> None:
        self.skipped += 1
        self.by_reason[reason] = self.by_reason.get(reason, 0) + 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tenants": self.tenants,
            "legacy_rows_total": self.legacy_rows_total,
            "already_present": self.already_present,
            "orphans_found": self.orphans_found,
            "orphans_examined": self.orphans_examined,
            "backfilled": self.backfilled,
            "skipped": self.skipped,
            "skipped_by_reason": dict(sorted(self.by_reason.items())),
            "facility_hypotheses": dict(sorted(self.by_hypothesis.items())),
            "product_reference_nulled": self.product_reference_nulled,
            "status_assumed_active": self.status_assumed_active,
            "status_recovered_superseded": self.status_recovered_superseded,
            "chain_entry_missing": self.chain_entry_missing,
            "errors": self.errors,
        }


def print_summary(summary: Summary, execute: bool) -> None:
    mode = "EXECUTE (rows written)" if execute else "DRY RUN (nothing written)"
    verb = "backfilled" if execute else "would backfill"
    print("")
    print("=" * 72)
    print(f"WS-1c canonical backfill — {mode}")
    print("=" * 72)
    print(f"  tenants scanned            : {summary.tenants}")
    print(f"  legacy cte_events scanned  : {summary.legacy_rows_total}")
    print(f"  already present in canonical: {summary.already_present}")
    print(f"  legacy orphans found       : {summary.orphans_found}")
    print(f"  orphans examined this run  : {summary.orphans_examined}")
    print(f"  {verb:<27}: {summary.backfilled}")
    print(f"  skipped                    : {summary.skipped}")
    for reason, count in sorted(summary.by_reason.items()):
        print(f"      - {reason}: {count}")
        print(f"          {REFUSAL_HELP.get(reason, '')}")
    if summary.by_hypothesis:
        print("  resolved facility ambiguity (proved by sha256 preimage):")
        for label, count in sorted(summary.by_hypothesis.items()):
            print(f"      - {label}: {count}")
    print(f"  product_reference set NULL from '' : {summary.product_reference_nulled}")
    print(f"  status recovered as superseded     : {summary.status_recovered_superseded}")
    print(f"  status ASSUMED active (ambiguous)  : {summary.status_assumed_active}")
    print(f"  backfilled rows with no fsma.hash_chain entry: {summary.chain_entry_missing}")
    print(f"  unexpected errors          : {summary.errors}")
    if not execute:
        print("")
        print("  Nothing was written. Re-run with --execute to apply.")
    print("=" * 72)


# ---------------------------------------------------------------------------
# State file (resume)
# ---------------------------------------------------------------------------


def load_state(path: Optional[str]) -> Dict[str, str]:
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data.get("cursors", {}) if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("state_file_unreadable", extra={"path": path, "error": str(exc)})
        return {}


def save_state(path: Optional[str], cursors: Dict[str, str]) -> None:
    if not path:
        return
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(
            {"updated_at": datetime.now(timezone.utc).isoformat(), "cursors": cursors},
            fh,
            indent=2,
        )
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Core loop
# ---------------------------------------------------------------------------


def _chunks(seq: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def process_tenant(
    session_factory: Any,
    tenant_id: str,
    args: argparse.Namespace,
    summary: Summary,
    report: Optional[Any],
    cursors: Dict[str, str],
    remaining: Optional[int],
) -> int:
    """Backfill one tenant. Returns the number of orphans examined."""
    session: Session = session_factory()
    try:
        set_tenant_context(session, tenant_id)
        total, orphan_count = count_legacy(session, tenant_id)
        orphan_ids = fetch_orphan_ids(session, tenant_id)
        session.rollback()
        summary.legacy_rows_total += total
        summary.already_present += total - orphan_count
        summary.orphans_found += orphan_count
    finally:
        session.close()

    if not orphan_ids:
        return 0

    resume_after = cursors.get(tenant_id) if args.resume else None
    if resume_after and resume_after in orphan_ids:
        orphan_ids = orphan_ids[orphan_ids.index(resume_after) + 1 :]
        logger.info(
            "resuming_tenant",
            extra={"tenant_id": tenant_id, "after": resume_after, "remaining": len(orphan_ids)},
        )
    if remaining is not None:
        orphan_ids = orphan_ids[:remaining]

    examined = 0
    for chunk in _chunks(orphan_ids, args.batch_size):
        session = session_factory()
        # Buffer of durably-pending backfill successes for THIS batch. In
        # --execute mode nothing in it is counted or emitted until the outer
        # session.commit() below returns; the row inserts live in the open
        # transaction and are not durable until then.
        pending: List[_PendingSuccess] = []
        committed = False
        try:
            # SQLAlchemy autobegins on first execute; set_tenant_context's
            # set_config(..., true) is transaction-scoped, so the GUC covers
            # exactly this batch's transaction.
            set_tenant_context(session, tenant_id)
            rows = fetch_rows(session, tenant_id, chunk)
            for row in rows:
                examined += 1
                _process_row(session, row, args, summary, report, pending)
            if args.execute:
                session.commit()
                committed = True
            else:
                # Belt and braces: the row path never issues an INSERT in
                # dry-run, and the transaction is rolled back regardless.
                session.rollback()
        except Exception:
            session.rollback()
            # The outer commit (or the batch) failed: every savepoint-committed
            # insert was just rolled back. Discard the buffered successes — they
            # must NOT be counted or emitted as backfills — and record the
            # rollback in the audit trail instead.
            _emit_batch_rolled_back(report, tenant_id, pending)
            raise
        finally:
            session.close()
        if args.execute and committed:
            # Durable now: apply the buffered successes (counters + audit records)
            # only after the outer commit landed, then advance the resume cursor.
            for item in pending:
                item.apply(summary, report)
        if args.execute:
            cursors[tenant_id] = chunk[-1]
            save_state(args.state_file, cursors)
        logger.info(
            "batch_done",
            extra={
                "tenant_id": tenant_id,
                "examined": examined,
                "backfilled": summary.backfilled,
                "skipped": summary.skipped,
            },
        )
        print(
            f"  [{tenant_id}] examined={examined}/{len(orphan_ids)} "
            f"backfilled={summary.backfilled} skipped={summary.skipped}",
            flush=True,
        )
    return examined


def _emit(report: Optional[Any], record: Dict[str, Any]) -> None:
    if report is None:
        return
    report.write(json.dumps(record, default=str) + "\n")
    report.flush()


@dataclass
class _PendingSuccess:
    """A durably-pending backfill success, held until the outer commit lands.

    In ``--execute`` mode a row's INSERT runs inside a nested SAVEPOINT; the
    ``sp.commit()`` only RELEASES the savepoint, so the row's durability still
    depends on the batch's OUTER ``session.commit()``. Counting the row as
    backfilled and emitting its "backfill" audit record BEFORE that outer commit
    would make the summary and the JSONL trail lie if the commit then fails and
    the whole batch is rolled back. So the success side effects are buffered
    here and applied by ``apply()`` only after the outer commit returns.
    """

    record: Dict[str, Any]
    hypothesis: str
    product_reference_nulled: bool
    status_superseded: bool
    assumed_status: bool
    has_chain: bool

    def apply(self, summary: Summary, report: Optional[Any]) -> None:
        """Record the durable success: bump counters and emit the audit record."""
        summary.backfilled += 1
        summary.by_hypothesis[self.hypothesis] = summary.by_hypothesis.get(self.hypothesis, 0) + 1
        if self.product_reference_nulled:
            summary.product_reference_nulled += 1
        if self.status_superseded:
            summary.status_recovered_superseded += 1
        elif self.assumed_status:
            summary.status_assumed_active += 1
        if not self.has_chain:
            summary.chain_entry_missing += 1
        _emit(report, self.record)


def _emit_batch_rolled_back(
    report: Optional[Any], tenant_id: str, pending: Sequence[_PendingSuccess]
) -> None:
    """Emit a single batch-level record when an outer commit failed.

    The buffered successes are discarded (never counted, never emitted as
    "backfill") because the rollback undid every savepoint-committed insert.
    This record makes that outcome visible in the audit trail instead of the
    rows silently vanishing.
    """
    if report is None or not pending:
        return
    _emit(
        report,
        {
            "tenant_id": tenant_id,
            "decision": "rolled_back",
            "reason": "batch_commit_failed",
            "explanation": (
                "The outer session.commit() for this batch raised; every "
                "savepoint-committed insert in the batch was rolled back, so "
                "these rows were NOT backfilled and are not counted as such."
            ),
            "rolled_back_legacy_ids": [p.record.get("legacy_id") for p in pending],
        },
    )


def _process_row(
    session: Session,
    row: LegacyRow,
    args: argparse.Namespace,
    summary: Summary,
    report: Optional[Any],
    pending: List[_PendingSuccess],
) -> None:
    summary.orphans_examined += 1

    status, status_evidence = resolve_status(session, row)
    assumed_status = status_evidence.startswith("ASSUMED")
    if assumed_status and args.status_ambiguous == "skip":
        summary.skip(R_STATUS_AMBIGUOUS)
        _emit(report, {"legacy_id": row.id, "tenant_id": row.tenant_id,
                       "decision": "skip", "reason": R_STATUS_AMBIGUOUS})
        return

    rec, reason = reconstruct(row, status)
    if rec is None:
        assert reason is not None
        summary.skip(reason)
        _emit(
            report,
            {
                "legacy_id": row.id,
                "tenant_id": row.tenant_id,
                "sha256_hash": row.sha256_hash,
                "decision": "skip",
                "reason": reason,
                "explanation": REFUSAL_HELP.get(reason, ""),
                "location_gln": row.location_gln,
                "location_name_differs": row.location_name != row.location_gln,
                "source": row.source,
            },
        )
        return

    params = insert_params(
        row,
        rec,
        build_provenance(row, rec, status, status_evidence),
        args.confidence_score,
    )

    conflict = precheck_conflicts(session, row, params["idempotency_key"])
    if conflict is not None:
        summary.skip(conflict)
        _emit(report, {"legacy_id": row.id, "tenant_id": row.tenant_id,
                       "decision": "skip", "reason": conflict,
                       "explanation": REFUSAL_HELP.get(conflict, "")})
        return

    has_chain = chain_entry_exists(session, row)

    record = {
        "legacy_id": row.id,
        "tenant_id": row.tenant_id,
        "sha256_hash": row.sha256_hash,
        "decision": "backfill" if args.execute else "would_backfill",
        "facility_hypothesis": rec.hypothesis,
        "status": status.value,
        "status_evidence": status_evidence,
        "product_reference_nulled": rec.product_reference_nulled,
        "hash_chain_entry_present": has_chain,
    }

    pending_success = _PendingSuccess(
        record=record,
        hypothesis=rec.hypothesis,
        product_reference_nulled=rec.product_reference_nulled,
        status_superseded=status is EventStatus.SUPERSEDED,
        assumed_status=assumed_status,
        has_chain=has_chain,
    )

    if not args.execute:
        # Dry run: the batch is rolled back by design, so "would_backfill" never
        # claims a durable write. Recording the decision immediately is honest
        # and preserves the existing dry-run audit stream / counters.
        pending_success.apply(summary, report)
        return

    sp = session.begin_nested()
    try:
        inserted = session.execute(INSERT_SQL, params).fetchone()
        sp.commit()
    except Exception as exc:
        sp.rollback()
        summary.skip(R_INSERT_FAILED)
        summary.errors += 1
        record.update({"decision": "skip", "reason": R_INSERT_FAILED, "error": str(exc)})
        _emit(report, record)
        logger.error("backfill_insert_failed", extra={"legacy_id": row.id, "error": str(exc)})
        return
    if inserted is None:  # pragma: no cover - pre-checks make this unreachable
        summary.skip(R_INSERT_FAILED)
        record.update({"decision": "skip", "reason": R_INSERT_FAILED})
        _emit(report, record)
        return

    # The INSERT is in the OPEN transaction; the nested sp.commit() above only
    # RELEASED the savepoint, so this row is not durable until the batch's outer
    # session.commit() succeeds. Buffer the success — do NOT count it as
    # backfilled and do NOT emit its "backfill" audit record yet. The batch loop
    # flushes the buffer only after the outer commit returns; on commit failure
    # the whole batch (including this insert) is rolled back and the buffer is
    # discarded, so the counters and audit trail never claim a write that the
    # database rolled back.
    pending.append(pending_success)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="backfill_canonical_from_legacy.py",
        description=(
            "WS-1c (#1335): give every fsma.cte_events row a canonical "
            "fsma.traceability_events twin, joined by sha256_hash. DRY RUN BY "
            "DEFAULT — pass --execute to write. Rows whose canonical form cannot "
            "be PROVEN against the stored sha256_hash are refused and reported, "
            "never guessed."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ambiguity policy:\n"
            "  location_gln collapses from_facility_reference and "
            "to_facility_reference. Each split hypothesis is tested against the "
            "row's sha256_hash preimage; only an exact match is written, and the\n"
            "  resolved hypothesis is recorded in "
            "provenance_metadata.backfill.ambiguities.\n"
            "  fsma.hash_chain is never written to.\n"
        ),
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="SQLAlchemy URL. Defaults to $DATABASE_URL.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually write. Omit for a dry run (the default) which mutates nothing.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Rows per transaction/commit (default: 500).",
    )
    parser.add_argument(
        "--tenant-id",
        action="append",
        default=[],
        metavar="UUID",
        help="Restrict to this tenant (repeatable). Default: every tenant.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Stop after examining this many orphans (bounded first run).",
    )
    parser.add_argument(
        "--report-path",
        default=None,
        metavar="PATH",
        help="Append a JSONL per-row decision log here (audit trail).",
    )
    parser.add_argument(
        "--state-file",
        default=None,
        metavar="PATH",
        help="Persist a per-tenant resume cursor here (written only with --execute).",
    )
    parser.add_argument(
        "--no-resume",
        dest="resume",
        action="store_false",
        default=True,
        help="Ignore any cursor in --state-file and re-walk every orphan.",
    )
    parser.add_argument(
        "--status-ambiguous",
        choices=("active", "skip"),
        default="active",
        help=(
            "What to do when legacy validation_status='valid' (which maps back to "
            "active|superseded|draft) and no canonical superseder is found. "
            "'active' writes active and records the assumption in provenance; "
            "'skip' refuses the row. Default: active."
        ),
    )
    parser.add_argument(
        "--confidence-score",
        type=float,
        default=1.0,
        help=(
            "confidence_score for backfilled rows (default 1.0, matching the "
            "canonical writer). The hash proof covers event identity; lower it if "
            "your policy treats reconstructed rows as lower-confidence."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Also print the summary as JSON.")
    parser.add_argument("--verbose", action="store_true", help="Debug logging.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if not args.database_url:
        print("ERROR: no database URL. Pass --database-url or set DATABASE_URL.", file=sys.stderr)
        return 2
    if args.batch_size < 1:
        print("ERROR: --batch-size must be >= 1", file=sys.stderr)
        return 2
    if not 0.0 <= args.confidence_score <= 1.0:
        print("ERROR: --confidence-score must be within [0.0, 1.0]", file=sys.stderr)
        return 2

    if not args.execute:
        print("DRY RUN — no writes will be issued. Pass --execute to apply.", flush=True)

    try:
        engine = create_engine(args.database_url, future=True)

        # The canonical hash preimage embeds ``event_timestamp.isoformat()``,
        # so the offset the driver renders is part of what we verify against.
        # Pin every pooled connection to UTC — that is what reproduces the
        # '+00:00' the original hash was taken over.
        @sa_event.listens_for(engine, "connect")
        def _force_utc(dbapi_connection, _record):  # pragma: no cover - driver hook
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("SET TIME ZONE 'UTC'")
            finally:
                cursor.close()

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        print(f"ERROR: could not connect to the database: {exc}", file=sys.stderr)
        return 2

    session_factory = sessionmaker(
        bind=engine, future=True, autoflush=False, expire_on_commit=False
    )

    probe: Session = session_factory()
    try:
        tenants = resolve_tenants(probe, args.tenant_id)
        probe.rollback()
    except Exception as exc:
        print(f"ERROR: could not enumerate tenants: {exc}", file=sys.stderr)
        return 2
    finally:
        probe.close()

    if not tenants:
        print(
            "ERROR: no tenants resolved. RLS blocks a cross-tenant scan — pass "
            "--tenant-id explicitly.",
            file=sys.stderr,
        )
        return 2

    summary = Summary(tenants=len(tenants))
    cursors = load_state(args.state_file)
    report = open(args.report_path, "a", encoding="utf-8") if args.report_path else None

    try:
        examined_total = 0
        for tenant_id in tenants:
            remaining = None if args.limit is None else max(0, args.limit - examined_total)
            if remaining == 0:
                break
            try:
                examined_total += process_tenant(
                    session_factory, tenant_id, args, summary, report, cursors, remaining
                )
            except Exception as exc:
                summary.errors += 1
                logger.exception("tenant_failed", extra={"tenant_id": tenant_id, "error": str(exc)})
                print(f"ERROR: tenant {tenant_id} failed: {exc}", file=sys.stderr)
    finally:
        if report is not None:
            report.close()
        engine.dispose()

    print_summary(summary, args.execute)
    if args.json:
        print(json.dumps(summary.to_dict(), indent=2))
    return 1 if summary.errors else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
