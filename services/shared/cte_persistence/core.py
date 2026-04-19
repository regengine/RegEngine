# ============================================================
# LEGACY — do NOT add new callers.
#
# This module writes to the old schema (fsma.cte_events + fsma.cte_kdes)
# alongside the canonical writer (canonical_persistence.writer, which
# writes to fsma.traceability_events). The canonical writer is the
# forward path; this module stays only to serve the 11+ live callers
# in services/ingestion/app/ (webhook_router_v2, epcis/persistence,
# fda_export/*, etc.) that have not yet been migrated. Retirement is
# tracked as #1335 and is a multi-sprint effort — each caller's tests
# must stay green at every step.
#
# Divergence from canonical — intentional, documented:
#   - idempotency_key formula uses (location_gln, location_name) while
#     canonical_event.TraceabilityEvent.compute_idempotency_key uses
#     (from_facility, to_facility). The same real-world event dual-
#     written through both paths produces DIFFERENT keys in each
#     table. Cross-table reconciliation must therefore use sha256_hash,
#     not idempotency_key.
#
# Changes here risk breaking FDA export, hash chain integrity, and
# graph sync. Prefer fixing the canonical path when both paths have
# the same bug.
# ============================================================
"""
FSMA 204 CTE Persistence Layer — LEGACY dual-write path.

Provides database-backed storage for Critical Tracking Events to the
older ``fsma.cte_events`` + ``fsma.cte_kdes`` schema. New ingestion
paths should use ``shared.canonical_persistence`` which writes to
``fsma.traceability_events``. Both paths coexist during the in-progress
migration; see the ``UNSAFE ZONE`` comment block above.

Usage:
    from services.shared.cte_persistence import CTEPersistence

    persistence = CTEPersistence(db_session)
    result = persistence.store_event(tenant_id, event, kdes, alerts)
    chain = persistence.verify_chain(tenant_id)
    events = persistence.query_for_export(tenant_id, tlc, start, end)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import (
    DatabaseError,
    OperationalError,
    ProgrammingError,
)
from sqlalchemy.orm import Session

from .models import StoreResult, ChainVerification, MerkleVerification
from .hashing import compute_event_hash, compute_chain_hash, compute_idempotency_key

logger = logging.getLogger("cte-persistence")


# ---------------------------------------------------------------------------
# Timestamp Validation (fix #1308)
# ---------------------------------------------------------------------------

# Clock-skew tolerance for "future" events: small positive offsets can legitimately
# occur across machines whose clocks aren't perfectly in sync (NTP drift, laptop
# sleep, etc.).  Anything beyond this is rejected as a data-quality error.
_FUTURE_SKEW_TOLERANCE = timedelta(minutes=5)


def _parse_timestamp(value: Any, *, field: str) -> datetime:
    """Parse an ISO-8601 timestamp into a timezone-aware UTC datetime.

    Rejects:
        * None, empty strings, non-string inputs
        * Unparseable formats
        * Naive (no-timezone) datetimes — FSMA records must be
          timezone-unambiguous to support the 24-hour notification rule.
        * Timestamps more than _FUTURE_SKEW_TOLERANCE in the future —
          these almost always indicate caller bugs or data exfiltration
          attempts rather than legitimate forward-dated events.

    Does NOT reject very-old timestamps — legacy backfill is a legitimate
    use case and the regulatory 2-year retention lower bound is enforced
    at query time, not at ingest.

    Returns a datetime normalized to UTC.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"{field} is required and must be an ISO-8601 timestamp")

    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        # Accept trailing "Z" for UTC by normalizing to +00:00 first.
        candidate = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(candidate)
        except ValueError as exc:
            raise ValueError(
                f"{field} is not a valid ISO-8601 timestamp: {value!r}"
            ) from exc
    else:
        raise ValueError(
            f"{field} must be a string or datetime, got {type(value).__name__}"
        )

    if dt.tzinfo is None:
        raise ValueError(
            f"{field} must be timezone-aware (got naive datetime: {value!r}). "
            "FSMA records require an unambiguous UTC offset."
        )

    dt = dt.astimezone(timezone.utc)

    now_utc = datetime.now(timezone.utc)
    if dt > now_utc + _FUTURE_SKEW_TOLERANCE:
        raise ValueError(
            f"{field} is in the future beyond the allowed skew tolerance: "
            f"{dt.isoformat()} (now={now_utc.isoformat()})"
        )
    return dt


# ---------------------------------------------------------------------------
# KDE Value Serialization (fix #1311)
# ---------------------------------------------------------------------------

def _jsonify_kde(value: Any) -> str:
    """Serialize a KDE value to JSON text suitable for ``::jsonb`` cast.

    fsma.cte_kdes.kde_value is JSONB; storing ``str(value)`` produced
    Python repr for dicts (``"{'gln': '...'}"``), which is not JSON
    and cannot be round-tripped.  We emit proper JSON:

        - dict / list / bool / None / int / float  → json.dumps
        - str (already a scalar)                   → json.dumps(str)
                                                     (so it becomes "..."
                                                     rather than a bare
                                                     token the parser
                                                     would reject)
        - anything else                            → json.dumps(str(value))
                                                     as a best-effort
                                                     fallback; the cast
                                                     will fail loudly if
                                                     the result is still
                                                     not valid JSON.
    """
    if isinstance(value, (dict, list, bool, int, float)) or value is None:
        return json.dumps(value, default=str, sort_keys=True)
    if isinstance(value, str):
        return json.dumps(value)
    # Datetime and UUID instances end up here — stringify and wrap.
    return json.dumps(str(value))


# ---------------------------------------------------------------------------
# Persistence Layer
# ---------------------------------------------------------------------------

class CTEPersistence:
    """
    LEGACY database-backed persistence for FSMA 204 CTE events.

    New callers should prefer
    ``shared.canonical_persistence.CanonicalEventStore`` which writes
    to ``fsma.traceability_events``. This class exists to serve the
    in-ingestion-service callers that have not yet migrated. Retirement
    is tracked by #1335.

    All methods expect a SQLAlchemy session that has already set
    the tenant context via ``SET LOCAL app.tenant_id = '<uuid>'``, or
    a caller that invokes ``set_tenant_context`` before writing. The
    RLS policies on the ``fsma.*`` tables enforce tenant isolation
    automatically — this module does not filter by ``tenant_id`` in
    read-query ``WHERE`` clauses.
    """

    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------
    # Tenant Context
    # ------------------------------------------------------------------

    def set_tenant_context(self, tenant_id: str) -> None:
        """Set the RLS tenant context for this session.

        Uses ``app.tenant_id`` — the single namespace read by
        ``get_tenant_context()`` and all RLS policies.  Previously this
        method set ``regengine.tenant_id`` which was **never** checked by
        any RLS policy, silently bypassing tenant isolation.
        """
        self.session.execute(
            text("SET LOCAL app.tenant_id = :tid"),
            {"tid": tenant_id},
        )

    # ------------------------------------------------------------------
    # Per-tenant Chain Serialization (fix #1332)
    # ------------------------------------------------------------------

    def _acquire_chain_lock(self, tenant_id: str) -> None:
        """Acquire a per-tenant transaction-scoped advisory lock.

        The chain-head read uses ``SELECT ... FOR UPDATE LIMIT 1``,
        which **locks the returned row, not the next slot**. On a
        tenant's first event the SELECT returns zero rows and locks
        nothing; two concurrent first-event writers both see
        ``chain_head=None`` and both compute ``sequence_num=1``. Adding
        a UNIQUE ``(tenant_id, sequence_num)`` surfaces the race as an
        IntegrityError after the CTE event row has already succeeded —
        leaving an event with no chain membership.

        ``pg_advisory_xact_lock(hashtext(tenant_id))`` serializes the
        chain-growth critical section per tenant. The lock is
        transaction-scoped and released automatically on COMMIT or
        ROLLBACK. ``hashtext()`` collisions across tenants are harmless
        — they just serialize unrelated tenants occasionally. Mirrors
        the pattern in ``canonical_persistence.writer`` (#1251).
        """
        self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:tid))"),
            {"tid": tenant_id},
        )

    # ------------------------------------------------------------------
    # Write Path
    # ------------------------------------------------------------------

    def store_event(
        self,
        tenant_id: str,
        event_type: str,
        traceability_lot_code: str,
        product_description: str,
        quantity: float,
        unit_of_measure: str,
        event_timestamp: str,
        source: str = "api",
        location_gln: Optional[str] = None,
        location_name: Optional[str] = None,
        kdes: Optional[Dict[str, Any]] = None,
        alerts: Optional[List[Dict[str, Any]]] = None,
        epcis_event_type: Optional[str] = None,
        epcis_action: Optional[str] = None,
        epcis_biz_step: Optional[str] = None,
        source_event_id: Optional[str] = None,
        event_entry_timestamp: Optional[str] = None,
    ) -> StoreResult:
        """
        Persist a CTE event with its KDEs, hash chain entry, and alerts.

        This is an atomic operation — either everything is committed or
        nothing is. The caller is responsible for committing the session.

        Returns:
            StoreResult with event_id, hashes, and any alerts.
        """
        kdes = kdes or {}
        alerts = alerts or []
        event_id = str(uuid4())

        # --- Timestamp validation (fix #1308) ---
        # Parse + normalize to UTC + reject naive/future/garbage inputs.
        # We keep ``event_timestamp`` as the canonical ISO-8601 string
        # for hashing (compute_event_hash is string-based) but the
        # parsed datetime is what goes into the DB — no more opaque
        # passthroughs.
        event_dt = _parse_timestamp(event_timestamp, field="event_timestamp")
        event_timestamp = event_dt.isoformat()
        if event_entry_timestamp is not None:
            entry_dt = _parse_timestamp(
                event_entry_timestamp, field="event_entry_timestamp"
            )
            event_entry_timestamp = entry_dt.isoformat()

        # --- Serialize chain growth per-tenant (fix #1332) ---
        # Must precede both the idempotency SELECT and the chain-head
        # SELECT so two concurrent first-event writers cannot both see
        # ``chain_head=None`` and compute sequence_num=1. Released
        # automatically at COMMIT / ROLLBACK.
        self._acquire_chain_lock(tenant_id)

        # --- Idempotency check ---
        idempotency_key = compute_idempotency_key(
            event_type, traceability_lot_code, event_timestamp, source, kdes,
            location_gln=location_gln, location_name=location_name,
        )

        existing = self.session.execute(
            text("""
                SELECT id, sha256_hash, chain_hash
                FROM fsma.cte_events
                WHERE idempotency_key = :key AND tenant_id = :tid
            """),
            {"key": idempotency_key, "tid": tenant_id},
        ).fetchone()

        if existing:
            logger.info(
                "idempotent_event_skipped",
                extra={
                    "existing_id": str(existing[0]),
                    "tlc": traceability_lot_code,
                },
            )
            return StoreResult(
                success=True,
                event_id=str(existing[0]),
                sha256_hash=existing[1],
                chain_hash=existing[2],
                idempotent=True,
                errors=[],
                kde_completeness=1.0,
                alerts=[],
            )

        # --- Compute hashes ---
        sha256_hash = compute_event_hash(
            event_id, event_type, traceability_lot_code,
            product_description, quantity, unit_of_measure,
            location_gln, location_name, event_timestamp, kdes,
        )

        # Get the current chain head for this tenant
        chain_head = self.session.execute(
            text("""
                SELECT chain_hash, sequence_num
                FROM fsma.hash_chain
                WHERE tenant_id = :tid
                ORDER BY sequence_num DESC
                LIMIT 1
                FOR UPDATE
            """),
            {"tid": tenant_id},
        ).fetchone()

        previous_chain_hash = chain_head[0] if chain_head else None
        next_sequence = (chain_head[1] + 1) if chain_head else 1

        chain_hash = compute_chain_hash(sha256_hash, previous_chain_hash)

        # --- Insert CTE event ---
        # event_entry_timestamp: FDA 21 CFR 1.1455 — when the record was entered
        # into the system, distinct from event_timestamp (when the event occurred).
        # Falls back to NOW() if the caller does not supply it.
        _entry_ts = event_entry_timestamp or datetime.now(timezone.utc).isoformat()

        self.session.execute(
            text("""
                INSERT INTO fsma.cte_events (
                    id, tenant_id, event_type, traceability_lot_code,
                    product_description, quantity, unit_of_measure,
                    location_gln, location_name, event_timestamp,
                    event_entry_timestamp,
                    source, source_event_id, idempotency_key,
                    sha256_hash, chain_hash,
                    epcis_event_type, epcis_action, epcis_biz_step,
                    validation_status
                ) VALUES (
                    :id, :tenant_id, :event_type, :tlc,
                    :product_description, :quantity, :unit_of_measure,
                    :location_gln, :location_name, :event_timestamp,
                    :event_entry_timestamp,
                    :source, :source_event_id, :idempotency_key,
                    :sha256_hash, :chain_hash,
                    :epcis_event_type, :epcis_action, :epcis_biz_step,
                    :validation_status
                )
                ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
            """),
            {
                "id": event_id,
                "tenant_id": tenant_id,
                "event_type": event_type,
                "tlc": traceability_lot_code,
                "product_description": product_description,
                "quantity": quantity,
                "unit_of_measure": unit_of_measure,
                "location_gln": location_gln,
                "location_name": location_name,
                "event_timestamp": event_timestamp,
                "event_entry_timestamp": _entry_ts,
                "source": source,
                "source_event_id": source_event_id,
                "idempotency_key": idempotency_key,
                "sha256_hash": sha256_hash,
                "chain_hash": chain_hash,
                "epcis_event_type": epcis_event_type,
                "epcis_action": epcis_action,
                "epcis_biz_step": epcis_biz_step,
                "validation_status": "warning" if alerts else "valid",
            },
        )

        # --- Insert KDEs (fix #1311) ---
        # The column ``fsma.cte_kdes.kde_value`` is JSONB (migration v059).
        # Previously values were stored via ``str(kde_value)`` which
        # produced Python repr for dicts (``"{'gln': '...'}"``), not JSON,
        # so structured KDEs could not round-trip.  We now emit valid
        # JSON text and cast to jsonb in SQL.
        for kde_key, kde_value in kdes.items():
            if kde_value is None:
                continue
            self.session.execute(
                text("""
                    INSERT INTO fsma.cte_kdes (
                        tenant_id, cte_event_id, kde_key, kde_value, is_required
                    ) VALUES (
                        :tenant_id, :cte_event_id, :kde_key,
                        CAST(:kde_value AS jsonb), :is_required
                    )
                    ON CONFLICT (cte_event_id, kde_key) DO NOTHING
                """),
                {
                    "tenant_id": tenant_id,
                    "cte_event_id": event_id,
                    "kde_key": kde_key,
                    "kde_value": _jsonify_kde(kde_value),
                    "is_required": False,  # caller can override
                },
            )

        # --- Insert hash chain entry (only if the event was actually inserted) ---
        # ON CONFLICT DO NOTHING can silently skip the event INSERT if a
        # concurrent writer won the idempotency race. The WHERE EXISTS
        # guard prevents orphan chain entries pointing to non-existent events.
        self.session.execute(
            text("""
                INSERT INTO fsma.hash_chain (
                    tenant_id, cte_event_id, sequence_num,
                    event_hash, previous_chain_hash, chain_hash
                )
                SELECT :tenant_id, :cte_event_id, :sequence_num,
                       :event_hash, :previous_chain_hash, :chain_hash
                WHERE EXISTS (
                    SELECT 1 FROM fsma.cte_events
                    WHERE id = :cte_event_id AND tenant_id = :tenant_id
                )
            """),
            {
                "tenant_id": tenant_id,
                "cte_event_id": event_id,
                "sequence_num": next_sequence,
                "event_hash": sha256_hash,
                "previous_chain_hash": previous_chain_hash,
                "chain_hash": chain_hash,
            },
        )

        # --- Insert alerts (non-fatal: savepoint so event still persists) ---
        _VALID_ALERT_TYPES = {
            "missing_kde", "temperature_excursion", "deadline_approaching",
            "supplier_non_compliant", "chain_break", "export_failure",
        }
        for alert in alerts:
            raw_type = alert.get("alert_type", "missing_kde")
            alert_type = raw_type if raw_type in _VALID_ALERT_TYPES else "missing_kde"
            nested = self.session.begin_nested()
            try:
                self.session.execute(
                    text("""
                        INSERT INTO fsma.compliance_alerts (
                            tenant_id, org_id, event_id, severity, alert_type,
                            title, message
                        ) VALUES (
                            :tenant_id, :org_id, :event_id, :severity, :alert_type,
                            :title, :message
                        )
                    """),
                    {
                        "tenant_id": tenant_id,
                        "org_id": tenant_id,  # scope alerts to tenant until org model exists
                        "event_id": event_id,
                        "severity": alert.get("severity", "warning"),
                        "alert_type": alert_type,
                        "title": alert.get("alert_type", "Compliance Alert"),
                        "message": alert.get("message", ""),
                    },
                )
            except Exception as exc:
                nested.rollback()
                logger.warning("alert_insert_failed", extra={
                    "event_id": event_id, "alert_type": raw_type, "error": str(exc),
                })

        logger.info(
            "cte_event_persisted",
            extra={
                "event_id": event_id,
                "event_type": event_type,
                "tlc": traceability_lot_code,
                "tenant_id": tenant_id,
                "chain_seq": next_sequence,
                "sha256": sha256_hash[:16],
            },
        )

        return StoreResult(
            success=True,
            event_id=event_id,
            sha256_hash=sha256_hash,
            chain_hash=chain_hash,
            idempotent=False,
            errors=[],
            kde_completeness=1.0,
            alerts=alerts,
        )

    # ------------------------------------------------------------------
    # Batch Write Path (optimized for CSV/bulk ingestion)
    # ------------------------------------------------------------------

    def store_events_batch(
        self,
        tenant_id: str,
        events: List[Dict[str, Any]],
        source: str = "csv",
    ) -> List[StoreResult]:
        """
        Persist multiple CTE events in optimized batches.

        Instead of N round-trips per event, this method:
        1. Batch-checks idempotency with a single SELECT ... IN (...)
        2. Computes all hashes in Python (sequential chain, no DB needed)
        3. Batch-INSERTs events, KDEs, and chain entries

        The caller is responsible for committing the session.

        Returns:
            List of StoreResult, one per input event.
        """
        if not events:
            return []

        # --- Serialize chain growth per-tenant (fix #1332) ---
        # Mirrors the single-write path above. Taken before any chain
        # read so two concurrent first-event batches serialize on the
        # same tenant rather than both producing sequence_num=1.
        self._acquire_chain_lock(tenant_id)

        # --- Step 1: Pre-compute idempotency keys (+ validate ts; fix #1308) ---
        prepared = []
        for evt in events:
            event_id = str(uuid4())
            kdes = evt.get("kdes") or {}
            # Parse + validate timestamps, normalize to UTC ISO-8601.
            event_dt = _parse_timestamp(
                evt.get("event_timestamp"), field="event_timestamp"
            )
            evt = dict(evt)  # don't mutate caller input
            evt["event_timestamp"] = event_dt.isoformat()
            if evt.get("event_entry_timestamp") is not None:
                entry_dt = _parse_timestamp(
                    evt["event_entry_timestamp"], field="event_entry_timestamp"
                )
                evt["event_entry_timestamp"] = entry_dt.isoformat()
            idemp_key = compute_idempotency_key(
                evt["event_type"], evt["traceability_lot_code"],
                evt["event_timestamp"], source, kdes,
                location_gln=evt.get("location_gln"),
                location_name=evt.get("location_name"),
            )
            prepared.append({
                "event_id": event_id,
                "idemp_key": idemp_key,
                "evt": evt,
                "kdes": kdes,
            })

        # --- Step 2: Batch idempotency check ---
        all_keys = [p["idemp_key"] for p in prepared]
        existing_map: Dict[str, Tuple[str, str, str]] = {}
        # SQLAlchemy doesn't support WHERE IN with named params for lists easily,
        # so chunk into groups of 100
        for chunk_start in range(0, len(all_keys), 100):
            chunk = all_keys[chunk_start:chunk_start + 100]
            placeholders = ", ".join(f":k{i}" for i in range(len(chunk)))
            params = {f"k{i}": k for i, k in enumerate(chunk)}
            params["tid"] = tenant_id
            rows = self.session.execute(
                text(f"""
                    SELECT idempotency_key, id, sha256_hash, chain_hash
                    FROM fsma.cte_events
                    WHERE tenant_id = :tid AND idempotency_key IN ({placeholders})
                """),
                params,
            ).fetchall()
            for row in rows:
                existing_map[row[0]] = (str(row[1]), row[2], row[3])

        # --- Step 3: Get chain head once ---
        chain_head = self.session.execute(
            text("""
                SELECT chain_hash, sequence_num
                FROM fsma.hash_chain
                WHERE tenant_id = :tid
                ORDER BY sequence_num DESC
                LIMIT 1
                FOR UPDATE
            """),
            {"tid": tenant_id},
        ).fetchone()

        previous_chain_hash = chain_head[0] if chain_head else None
        next_sequence = (chain_head[1] + 1) if chain_head else 1

        # --- Step 4: Compute all hashes in memory, prepare batch inserts ---
        event_rows = []
        kde_rows = []
        chain_rows = []
        results: List[StoreResult] = []

        for p in prepared:
            # Skip idempotent
            if p["idemp_key"] in existing_map:
                eid, sha, ch = existing_map[p["idemp_key"]]
                results.append(StoreResult(
                    success=True, event_id=eid, sha256_hash=sha,
                    chain_hash=ch, idempotent=True, errors=[], kde_completeness=1.0, alerts=[],
                ))
                continue

            evt = p["evt"]
            event_id = p["event_id"]
            kdes = p["kdes"]

            # --- Quantity validation (fix #1306) ---
            # Previous implementation silently clamped ``quantity`` to a
            # minimum of 1.0 (both in the hash input and the row value),
            # so a HARVESTING event for 0.25 kg was persisted and hashed
            # as 1.0 kg.  The single-event path does NOT clamp, so the
            # same input via two code paths produced different SHA-256
            # hashes and different row values.  FSMA audit integrity
            # depends on the persisted regulatory payload matching what
            # the caller sent, so we now reject anything non-positive
            # rather than silently rewriting it.
            raw_qty = evt.get("quantity")
            if raw_qty is None:
                raise ValueError(
                    f"quantity is required for CTE event "
                    f"(tlc={evt.get('traceability_lot_code')}, "
                    f"type={evt.get('event_type')})"
                )
            try:
                quantity = float(raw_qty)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"quantity must be numeric, got {raw_qty!r}"
                ) from exc
            if quantity <= 0:
                raise ValueError(
                    f"quantity must be > 0, got {quantity} "
                    f"(tlc={evt.get('traceability_lot_code')})"
                )

            sha256_hash = compute_event_hash(
                event_id, evt["event_type"], evt["traceability_lot_code"],
                evt.get("product_description", ""), quantity,
                evt.get("unit_of_measure", ""), evt.get("location_gln"),
                evt.get("location_name"), evt["event_timestamp"], kdes,
            )

            chain_hash = compute_chain_hash(sha256_hash, previous_chain_hash)

            event_rows.append({
                "id": event_id,
                "tenant_id": tenant_id,
                "event_type": evt["event_type"],
                "tlc": evt["traceability_lot_code"],
                "product_description": evt.get("product_description", ""),
                "quantity": quantity,
                "unit_of_measure": evt.get("unit_of_measure", ""),
                "location_gln": evt.get("location_gln"),
                "location_name": evt.get("location_name"),
                "event_timestamp": evt["event_timestamp"],
                "source": source,
                "source_event_id": evt.get("source_event_id"),
                "idempotency_key": p["idemp_key"],
                "sha256_hash": sha256_hash,
                "chain_hash": chain_hash,
                "epcis_event_type": evt.get("epcis_event_type"),
                "epcis_action": evt.get("epcis_action"),
                "epcis_biz_step": evt.get("epcis_biz_step"),
                "validation_status": "valid",
            })

            for kde_key, kde_value in kdes.items():
                if kde_value is not None:
                    kde_rows.append({
                        "tenant_id": tenant_id,
                        "cte_event_id": event_id,
                        "kde_key": kde_key,
                        # fix #1311 — JSON text, cast to jsonb in the batch INSERT
                        "kde_value": _jsonify_kde(kde_value),
                        "is_required": False,
                    })

            chain_rows.append({
                "tenant_id": tenant_id,
                "cte_event_id": event_id,
                "sequence_num": next_sequence,
                "event_hash": sha256_hash,
                "previous_chain_hash": previous_chain_hash,
                "chain_hash": chain_hash,
            })

            results.append(StoreResult(
                success=True, event_id=event_id, sha256_hash=sha256_hash,
                chain_hash=chain_hash, idempotent=False, errors=[], kde_completeness=1.0, alerts=[],
            ))

            # Advance chain state for next event
            previous_chain_hash = chain_hash
            next_sequence += 1

        # --- Step 5: Batch INSERT (with lost-race reconciliation — #1248) ---
        # ON CONFLICT DO NOTHING silently discards rows whose idempotency
        # key collides with a concurrent writer's INSERT. Before #1248 we
        # still reported idempotent=False / event_id=<our new uuid> for
        # those, so the caller walked away with a phantom event_id that
        # never landed. RETURNING id tells us exactly which ids actually
        # inserted; the complement is the lost-race set and we re-select
        # the winner rows to patch our StoreResult list.
        inserted_ids: set[str] = set()
        if event_rows:
            # Chunk inserts to avoid parameter limits (Postgres max ~32K params)
            for chunk_start in range(0, len(event_rows), 50):
                chunk = event_rows[chunk_start:chunk_start + 50]
                values_clauses = []
                params: Dict[str, Any] = {}
                for i, row in enumerate(chunk):
                    values_clauses.append(
                        f"(:id_{i}, :tid_{i}, :et_{i}, :tlc_{i}, :pd_{i}, :qty_{i}, :uom_{i}, "
                        f":gln_{i}, :ln_{i}, :ts_{i}, :eets_{i}, :src_{i}, :seid_{i}, :ik_{i}, "
                        f":sha_{i}, :ch_{i}, :eet_{i}, :ea_{i}, :ebs_{i}, :vs_{i})"
                    )
                    params.update({
                        f"id_{i}": row["id"], f"tid_{i}": row["tenant_id"],
                        f"et_{i}": row["event_type"], f"tlc_{i}": row["tlc"],
                        f"pd_{i}": row["product_description"], f"qty_{i}": row["quantity"],
                        f"uom_{i}": row["unit_of_measure"], f"gln_{i}": row["location_gln"],
                        f"ln_{i}": row["location_name"], f"ts_{i}": row["event_timestamp"],
                        f"eets_{i}": row.get("event_entry_timestamp", datetime.now(timezone.utc).isoformat()),
                        f"src_{i}": row["source"], f"seid_{i}": row["source_event_id"],
                        f"ik_{i}": row["idempotency_key"], f"sha_{i}": row["sha256_hash"],
                        f"ch_{i}": row["chain_hash"], f"eet_{i}": row["epcis_event_type"],
                        f"ea_{i}": row["epcis_action"], f"ebs_{i}": row["epcis_biz_step"],
                        f"vs_{i}": row["validation_status"],
                    })
                sql = f"""
                    INSERT INTO fsma.cte_events (
                        id, tenant_id, event_type, traceability_lot_code,
                        product_description, quantity, unit_of_measure,
                        location_gln, location_name, event_timestamp,
                        event_entry_timestamp,
                        source, source_event_id, idempotency_key,
                        sha256_hash, chain_hash,
                        epcis_event_type, epcis_action, epcis_biz_step,
                        validation_status
                    ) VALUES {', '.join(values_clauses)}
                    ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
                    RETURNING id
                """
                returned = self.session.execute(text(sql), params).fetchall()
                for r in returned:
                    inserted_ids.add(str(r[0]))

            # --- #1248 lost-race reconciliation ---
            # For every event_row that was NOT in the returned set, the
            # concurrent writer won; re-select the winner by idempotency
            # key and rewrite our StoreResult so the caller sees the
            # authoritative event_id / sha256 / chain.
            lost_idemp_keys = [
                row["idempotency_key"]
                for row in event_rows
                if str(row["id"]) not in inserted_ids
            ]
            if lost_idemp_keys:
                # Map idempotency_key → position in ``results`` so we can
                # patch the entry the caller is going to see.
                key_to_result_idx: Dict[str, int] = {}
                for idx, p in enumerate(prepared):
                    key_to_result_idx[p["idemp_key"]] = idx
                winners: Dict[str, Tuple[str, str, str]] = {}
                for chunk_start in range(0, len(lost_idemp_keys), 100):
                    chunk_keys = lost_idemp_keys[chunk_start:chunk_start + 100]
                    placeholders = ", ".join(
                        f":lk{i}" for i in range(len(chunk_keys))
                    )
                    lr_params: Dict[str, Any] = {
                        f"lk{i}": k for i, k in enumerate(chunk_keys)
                    }
                    lr_params["tid"] = tenant_id
                    rows = self.session.execute(
                        text(f"""
                            SELECT idempotency_key, id, sha256_hash, chain_hash
                            FROM fsma.cte_events
                            WHERE tenant_id = :tid
                              AND idempotency_key IN ({placeholders})
                        """),
                        lr_params,
                    ).fetchall()
                    for idemp_key, winner_id, sha, ch in rows:
                        winners[idemp_key] = (str(winner_id), sha, ch)
                for idemp_key, (winner_id, sha, ch) in winners.items():
                    ridx = key_to_result_idx.get(idemp_key)
                    if ridx is None:
                        continue
                    results[ridx] = StoreResult(
                        success=True,
                        event_id=winner_id,
                        sha256_hash=sha,
                        chain_hash=ch,
                        idempotent=True,
                        errors=[],
                        kde_completeness=1.0,
                        alerts=[],
                    )
                logger.info(
                    "batch_events_lost_race_reconciled",
                    extra={
                        "tenant_id": tenant_id,
                        "lost_race": len(lost_idemp_keys),
                    },
                )

        if kde_rows:
            for chunk_start in range(0, len(kde_rows), 200):
                chunk = kde_rows[chunk_start:chunk_start + 200]
                values_clauses = []
                params = {}
                for i, row in enumerate(chunk):
                    # fix #1311: cast kde_value param to jsonb in the VALUES tuple
                    values_clauses.append(
                        f"(:tid_{i}, :eid_{i}, :kk_{i}, CAST(:kv_{i} AS jsonb), :ir_{i})"
                    )
                    params.update({
                        f"tid_{i}": row["tenant_id"], f"eid_{i}": row["cte_event_id"],
                        f"kk_{i}": row["kde_key"], f"kv_{i}": row["kde_value"],
                        f"ir_{i}": row["is_required"],
                    })
                sql = f"""
                    INSERT INTO fsma.cte_kdes (
                        tenant_id, cte_event_id, kde_key, kde_value, is_required
                    ) VALUES {', '.join(values_clauses)}
                    ON CONFLICT (cte_event_id, kde_key) DO NOTHING
                """
                self.session.execute(text(sql), params)

        if chain_rows:
            # --- fix #1307 ---
            # Previous implementation blindly INSERTed every chain row,
            # but the companion cte_events INSERT above uses ON CONFLICT
            # DO NOTHING — when a batch lost the idempotency race for one
            # of its events, the chain still wrote and produced an orphan
            # row pointing at a non-existent cte_event_id, which breaks
            # verify_chain's expected_seq = i+1 check.
            #
            # We now mirror the single-event path: each chain row is
            # inserted via INSERT ... SELECT guarded by a WHERE EXISTS
            # check against fsma.cte_events, so orphan rows cannot occur.
            # Rows are issued one at a time to keep the guarded form
            # simple and avoid VALUES-expansion footguns.
            for row in chain_rows:
                self.session.execute(
                    text("""
                        INSERT INTO fsma.hash_chain (
                            tenant_id, cte_event_id, sequence_num,
                            event_hash, previous_chain_hash, chain_hash
                        )
                        SELECT :tenant_id, :cte_event_id, :sequence_num,
                               :event_hash, :previous_chain_hash, :chain_hash
                        WHERE EXISTS (
                            SELECT 1 FROM fsma.cte_events
                            WHERE id = :cte_event_id
                              AND tenant_id = :tenant_id
                        )
                    """),
                    row,
                )

        logger.info(
            "batch_events_persisted",
            extra={
                "tenant_id": tenant_id,
                "total": len(events),
                "new": len(event_rows),
                "idempotent": len(events) - len(event_rows),
                "kdes": len(kde_rows),
            },
        )

        return results

    # ------------------------------------------------------------------
    # Read Path — FDA Export Queries
    # ------------------------------------------------------------------

    # Default recursion depth for _expand_tlcs_via_transformation_links
    # / query_events_by_tlc.  Bounded for two reasons:
    #   1. Postgres recursive CTE cost grows fast with depth; >10 hops
    #      on a dense transformation graph can blow memory.
    #   2. FDA §1.1350(c) records requests must return within 24 hours;
    #      we don't want a single misbehaving lot to DoS export.
    # Kept as a class attribute so tests can monkey-patch it cleanly.
    DEFAULT_TRAVERSAL_DEPTH: int = 5

    def _expand_tlcs_via_transformation_links(
        self,
        tenant_id: str,
        seed_tlc: str,
        depth: Optional[int] = None,
    ) -> List[str]:
        """Return all TLCs reachable from seed_tlc through transformation_links.

        Walks both directions (forward: seed → outputs, backward: seed → inputs)
        using a breadth-first traversal capped at ``depth`` hops.  Returns the
        full set of TLCs including the seed itself.

        Args:
            tenant_id: RLS tenant identifier.
            seed_tlc: TLC to expand from.
            depth: Max recursion depth.  Defaults to
                ``DEFAULT_TRAVERSAL_DEPTH`` (5) — previously hard-coded
                in the signature, now a class attribute so callers and
                tests can raise/lower it without patching the signature
                (#1322).

        Falls back to ``[seed_tlc]`` if the transformation_links table
        does not exist (fresh DB bootstrapping) or is unreachable.  All
        other SQL errors are re-raised so they surface in callers
        instead of silently truncating the trace — prior code swallowed
        ``except Exception`` here which masked real FDA export bugs
        (#1322).
        """
        max_depth = depth if depth is not None else self.DEFAULT_TRAVERSAL_DEPTH
        if max_depth < 0:
            raise ValueError(f"depth must be >= 0, got {max_depth}")

        try:
            # Note: use CAST(:tlc AS text) rather than :tlc::text — SQLAlchemy's
            # text() parameter parser misidentifies :param::cast as a single token,
            # silently dropping the :tlc binding and producing a SyntaxError.
            rows = self.session.execute(
                text("""
                    WITH RECURSIVE tlc_graph(tlc, depth) AS (
                        -- Seed
                        SELECT CAST(:tlc AS text), 0
                        UNION
                        -- Forward: seed was an input → walk to outputs
                        SELECT tl.output_tlc, tg.depth + 1
                        FROM   fsma.transformation_links tl
                        JOIN   tlc_graph tg ON tg.tlc = tl.input_tlc
                        WHERE  tl.tenant_id = :tid AND tg.depth < :max_depth
                        UNION
                        -- Backward: seed is an output → walk to inputs
                        SELECT tl.input_tlc, tg.depth + 1
                        FROM   fsma.transformation_links tl
                        JOIN   tlc_graph tg ON tg.tlc = tl.output_tlc
                        WHERE  tl.tenant_id = :tid AND tg.depth < :max_depth
                    )
                    SELECT DISTINCT tlc FROM tlc_graph
                """),
                {"tid": tenant_id, "tlc": seed_tlc, "max_depth": max_depth},
            ).fetchall()
            return [r[0] for r in rows] if rows else [seed_tlc]
        except ProgrammingError as e:
            # The transformation_links table does not exist — typical on
            # environments that have not run the v043+ migrations yet.
            # Degrade gracefully to "no graph" rather than failing the
            # FDA export entirely.  Rollback so the session is reusable.
            logger.info(
                "transformation_links_table_missing",
                extra={
                    "tenant_id": tenant_id,
                    "seed_tlc": seed_tlc,
                    "error": str(e),
                },
            )
            try:
                self.session.rollback()
            except DatabaseError:
                logger.debug("Rollback failed in recovery handler", exc_info=True)
            return [seed_tlc]
        except OperationalError as e:
            # Transient DB connectivity issue — same degradation
            # (legacy behaviour) but with a proper warning rather than
            # a silent debug log.  Unknown DatabaseErrors below fall
            # through to re-raise.
            logger.warning(
                "transformation_links_traversal_db_unavailable",
                extra={
                    "tenant_id": tenant_id,
                    "seed_tlc": seed_tlc,
                    "error": str(e),
                },
            )
            try:
                self.session.rollback()
            except DatabaseError:
                logger.debug("Rollback failed in recovery handler", exc_info=True)
            return [seed_tlc]

    def query_events_by_tlc(
        self,
        tenant_id: str,
        tlc: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        follow_transformations: bool = True,
        max_depth: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Query CTE events for a TLC within a date range.

        When follow_transformations=True (default), also returns events for all
        TLCs linked via fsma.transformation_links — both upstream inputs and
        downstream outputs.  This satisfies FDA §1.1350(c): a 24-hour records
        request must include the full traceability chain through transformations.

        Set follow_transformations=False for point queries that should not
        expand the result set (e.g. internal dedup checks).

        Args:
            max_depth: Optional override for the transformation-link
                recursion depth.  Defaults to
                ``CTEPersistence.DEFAULT_TRAVERSAL_DEPTH`` (5 hops) —
                see #1322; previously hard-coded.  Raising this trades
                correctness-for-deep-chains against query cost.

        SECURITY (#1321): Previously this method did not call
        ``set_tenant_context``; it relied on the caller having set the
        RLS context and on the explicit ``tenant_id = :tid`` predicate
        in the WHERE.  A caller that forgot to set the context — or who
        passed an attacker-influenced ``tenant_id`` — could cross
        tenant boundaries when the RLS fail-closed default is not
        installed.  We now set the context unconditionally (matching
        ``query_all_events``) and keep the explicit predicate as
        defense-in-depth.
        """
        self.set_tenant_context(tenant_id)

        # Resolve the full set of TLCs to query
        if follow_transformations:
            tlc_set = self._expand_tlcs_via_transformation_links(
                tenant_id, tlc, depth=max_depth,
            )
        else:
            tlc_set = [tlc]

        params: Dict[str, Any] = {"tid": tenant_id}
        tlc_placeholders = ", ".join(f":tlc_{i}" for i in range(len(tlc_set)))
        for i, t in enumerate(tlc_set):
            params[f"tlc_{i}"] = t

        where_clauses = [
            "tenant_id = :tid",
            f"traceability_lot_code IN ({tlc_placeholders})",
            "validation_status != 'rejected'",
        ]

        if start_date:
            where_clauses.append("event_timestamp >= :start_date")
            params["start_date"] = start_date
        if end_date:
            where_clauses.append("event_timestamp <= :end_date")
            params["end_date"] = end_date

        where = " AND ".join(where_clauses)

        rows = self.session.execute(
            text(f"""
                SELECT
                    e.id, e.event_type, e.traceability_lot_code,
                    e.product_description, e.quantity, e.unit_of_measure,
                    e.location_gln, e.location_name,
                    e.event_timestamp, e.sha256_hash, e.chain_hash,
                    e.source, e.validation_status, e.ingested_at,
                    e.event_entry_timestamp
                FROM fsma.cte_events e
                WHERE {where}
                ORDER BY e.event_timestamp ASC
            """),
            params,
        ).fetchall()

        # Tag each event with whether it's the queried TLC or a linked one
        seed_tlc = tlc  # original query TLC, before expansion
        events = []
        for row in rows:
            row_tlc = row[2]
            event = {
                "id": str(row[0]),
                "event_type": row[1],
                "traceability_lot_code": row_tlc,
                "product_description": row[3],
                "quantity": row[4],
                "unit_of_measure": row[5],
                "location_gln": row[6],
                "location_name": row[7],
                "event_timestamp": row[8].isoformat() if row[8] else None,
                "sha256_hash": row[9],
                "chain_hash": row[10],
                "source": row[11],
                "validation_status": row[12],
                "ingested_at": row[13].isoformat() if row[13] else None,
                "event_entry_timestamp": row[14].isoformat() if row[14] else None,
                "kdes": {},
                # Trace relationship metadata (used in FDA export CSV)
                "trace_seed_tlc": seed_tlc,
                "trace_relationship": (
                    "queried" if row_tlc == seed_tlc else "linked_via_transformation"
                ),
            }
            events.append(event)

        # Bulk-fetch KDEs for all events in one query (avoids N+1)
        if events:
            event_ids = [e["id"] for e in events]
            kde_map: Dict[str, Dict[str, str]] = {eid: {} for eid in event_ids}
            for chunk_start in range(0, len(event_ids), 100):
                chunk = event_ids[chunk_start:chunk_start + 100]
                placeholders = ", ".join(f":eid_{i}" for i in range(len(chunk)))
                kde_params: Dict[str, Any] = {f"eid_{i}": eid for i, eid in enumerate(chunk)}
                kde_params["tid"] = tenant_id
                kde_rows = self.session.execute(
                    text(f"""
                        SELECT cte_event_id, kde_key, kde_value
                        FROM fsma.cte_kdes
                        WHERE tenant_id = :tid AND cte_event_id IN ({placeholders})
                    """),
                    kde_params,
                ).fetchall()
                for kr in kde_rows:
                    kde_map[str(kr[0])][kr[1]] = kr[2]
            for event in events:
                event["kdes"] = kde_map.get(event["id"], {})

        return events

    def query_all_events(
        self,
        tenant_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Query CTE events with optional filters. Returns (events, total_count).

        Sets RLS tenant context for consistency with class contract. The explicit
        WHERE tenant_id clause is retained as defense-in-depth.
        """
        self.set_tenant_context(tenant_id)
        params: Dict[str, Any] = {"tid": tenant_id, "lim": limit, "off": offset}
        where_clauses = ["tenant_id = :tid"]

        if start_date:
            where_clauses.append("event_timestamp >= :start_date")
            params["start_date"] = start_date
        if end_date:
            where_clauses.append("event_timestamp <= :end_date")
            params["end_date"] = end_date
        if event_type:
            where_clauses.append("event_type = :event_type")
            params["event_type"] = event_type

        # `where` is composed exclusively from static string literals above;
        # all dynamic values use :named bind parameters -- no user input is
        # ever interpolated into the SQL text itself.
        where = " AND ".join(where_clauses)

        # Get total count
        count_sql = "SELECT COUNT(*) FROM fsma.cte_events WHERE " + where
        count_row = self.session.execute(
            text(count_sql),
            params,
        ).fetchone()
        total = count_row[0] if count_row else 0

        # Get page of results
        select_sql = (
            "SELECT id, event_type, traceability_lot_code,"
            "       product_description, quantity, unit_of_measure,"
            "       event_timestamp, validation_status, sha256_hash"
            " FROM fsma.cte_events"
            " WHERE " + where +
            " ORDER BY event_timestamp DESC"
            " LIMIT :lim OFFSET :off"
        )
        rows = self.session.execute(
            text(select_sql),
            params,
        ).fetchall()

        events = [
            {
                "id": str(r[0]),
                "event_type": r[1],
                "traceability_lot_code": r[2],
                "product_description": r[3],
                "quantity": r[4],
                "unit_of_measure": r[5],
                "event_timestamp": r[6].isoformat() if r[6] else None,
                "validation_status": r[7],
                "sha256_hash": r[8],
            }
            for r in rows
        ]

        return events, total

    # ------------------------------------------------------------------
    # Chain Verification
    # ------------------------------------------------------------------

    def verify_chain(self, tenant_id: str) -> ChainVerification:
        """
        Verify the integrity of a tenant's entire hash chain.

        Walks the chain from genesis to head, recomputing each chain_hash
        and comparing to the stored value. Any mismatch = tamper detected.
        """
        rows = self.session.execute(
            text("""
                SELECT sequence_num, event_hash, previous_chain_hash, chain_hash
                FROM fsma.hash_chain
                WHERE tenant_id = :tid
                ORDER BY sequence_num ASC
            """),
            {"tid": tenant_id},
        ).fetchall()

        if not rows:
            return ChainVerification(
                valid=True,
                chain_length=0,
                errors=[],
                checked_at=datetime.now(timezone.utc).isoformat(),
            )

        errors = []
        for i, row in enumerate(rows):
            seq, event_hash, stored_prev, stored_chain = row

            # Check sequence continuity
            expected_seq = i + 1
            if seq != expected_seq:
                errors.append(
                    f"Sequence gap: expected {expected_seq}, got {seq}"
                )

            # Check previous_chain_hash linkage
            if i == 0:
                if stored_prev is not None:
                    errors.append(
                        f"Genesis entry (seq={seq}) has non-null previous_chain_hash"
                    )
                expected_prev = None
            else:
                expected_prev = rows[i - 1][3]  # chain_hash of previous row
                if stored_prev != expected_prev:
                    errors.append(
                        f"Chain break at seq={seq}: stored prev "
                        f"{stored_prev[:16]}... != expected {expected_prev[:16]}..."
                    )

            # Recompute chain_hash and compare
            recomputed = compute_chain_hash(event_hash, stored_prev)
            if recomputed != stored_chain:
                errors.append(
                    f"Tamper detected at seq={seq}: recomputed chain_hash "
                    f"{recomputed[:16]}... != stored {stored_chain[:16]}..."
                )

        return ChainVerification(
            valid=len(errors) == 0,
            chain_length=len(rows),
            errors=errors,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    # ------------------------------------------------------------------
    # Merkle Tree Verification
    # ------------------------------------------------------------------

    def verify_chain_merkle(self, tenant_id: str) -> MerkleVerification:
        """
        Build a Merkle tree from a tenant's hash chain and return verification info.

        This provides O(log n) inclusion proofs as a complement to the
        linear verify_chain() method. The Merkle tree is computed in memory
        from the ordered event_hashes stored in fsma.hash_chain.
        """
        from shared.merkle_tree import MerkleTree

        rows = self.session.execute(
            text("""
                SELECT event_hash
                FROM fsma.hash_chain
                WHERE tenant_id = :tid
                ORDER BY sequence_num ASC
            """),
            {"tid": tenant_id},
        ).fetchall()

        if not rows:
            return MerkleVerification(
                valid=True,
                merkle_root=None,
                chain_length=0,
                tree_depth=0,
                errors=[],
                checked_at=datetime.now(timezone.utc).isoformat(),
            )

        hashes = [row[0] for row in rows]
        errors = []

        try:
            tree = MerkleTree(hashes)
            merkle_root = tree.root
            tree_depth = tree.depth
        except Exception as e:
            logger.error(
                "merkle_tree_build_failed",
                extra={"tenant_id": tenant_id, "error": str(e)},
            )
            return MerkleVerification(
                valid=False,
                merkle_root=None,
                chain_length=len(hashes),
                tree_depth=0,
                errors=[f"Failed to build Merkle tree: {e}"],
                checked_at=datetime.now(timezone.utc).isoformat(),
            )

        # Verify every leaf can produce a valid proof back to the root
        for i, event_hash in enumerate(hashes):
            try:
                proof = tree.generate_proof(i)
                if not MerkleTree.verify_proof(event_hash, proof, merkle_root):
                    errors.append(
                        f"Merkle proof verification failed for event at index {i}"
                    )
            except Exception as e:
                logger.warning(f"Merkle proof generation failed at index {i}", exc_info=True)
                errors.append(
                    f"Merkle proof generation failed at index {i}: {e}"
                )

        return MerkleVerification(
            valid=len(errors) == 0,
            merkle_root=merkle_root,
            chain_length=len(hashes),
            tree_depth=tree_depth,
            errors=errors,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def get_merkle_proof(
        self, tenant_id: str, event_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a Merkle inclusion proof for a specific event.

        Returns a dict with merkle_root, proof steps, event_hash, and index,
        or None if the event is not found in the chain.
        """
        from shared.merkle_tree import MerkleTree

        rows = self.session.execute(
            text("""
                SELECT cte_event_id, event_hash
                FROM fsma.hash_chain
                WHERE tenant_id = :tid
                ORDER BY sequence_num ASC
            """),
            {"tid": tenant_id},
        ).fetchall()

        if not rows:
            return None

        # Find the target event's index in the chain
        target_index = None
        target_hash = None
        hashes = []
        for i, row in enumerate(rows):
            hashes.append(row[1])
            if str(row[0]) == str(event_id):
                target_index = i
                target_hash = row[1]

        if target_index is None:
            return None

        tree = MerkleTree(hashes)
        proof = tree.generate_proof(target_index)

        return {
            "event_id": str(event_id),
            "event_hash": target_hash,
            "index": target_index,
            "merkle_root": tree.root,
            "tree_depth": tree.depth,
            "chain_length": len(hashes),
            "proof": proof,
        }

    # ------------------------------------------------------------------
    # Export Support
    # ------------------------------------------------------------------

    def log_export(
        self,
        tenant_id: str,
        export_hash: str,
        record_count: int,
        query_tlc: Optional[str] = None,
        query_start_date: Optional[str] = None,
        query_end_date: Optional[str] = None,
        generated_by: Optional[str] = None,
    ) -> str:
        """Log an FDA export event and return the export log ID."""
        export_id = str(uuid4())
        self.session.execute(
            text("""
                INSERT INTO fsma.fda_export_log (
                    id, tenant_id, query_tlc, query_start_date, query_end_date,
                    record_count, export_hash, generated_by
                ) VALUES (
                    :id, :tid, :tlc, :start, :end, :count, :hash, :by
                )
            """),
            {
                "id": export_id,
                "tid": tenant_id,
                "tlc": query_tlc,
                "start": query_start_date,
                "end": query_end_date,
                "count": record_count,
                "hash": export_hash,
                "by": generated_by,
            },
        )
        return export_id

    # ------------------------------------------------------------------
    # Graph Sync Support
    # ------------------------------------------------------------------

    def get_unsynced_events(
        self,
        tenant_id: str,
        since_sequence: int = 0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get CTE events that need to be synced to Neo4j.

        Returns events with their KDEs, ordered by chain sequence,
        starting from the given sequence number.
        """
        rows = self.session.execute(
            text("""
                SELECT
                    e.id, e.event_type, e.traceability_lot_code,
                    e.product_description, e.quantity, e.unit_of_measure,
                    e.location_gln, e.location_name, e.event_timestamp,
                    e.source, h.sequence_num
                FROM fsma.cte_events e
                JOIN fsma.hash_chain h ON h.cte_event_id = e.id
                WHERE e.tenant_id = :tid
                  AND h.sequence_num > :since
                  AND e.validation_status != 'rejected'
                ORDER BY h.sequence_num ASC
                LIMIT :lim
            """),
            {"tid": tenant_id, "since": since_sequence, "lim": limit},
        ).fetchall()

        events = []
        for row in rows:
            events.append({
                "id": str(row[0]),
                "event_type": row[1],
                "traceability_lot_code": row[2],
                "product_description": row[3],
                "quantity": row[4],
                "unit_of_measure": row[5],
                "location_gln": row[6],
                "location_name": row[7],
                "event_timestamp": row[8].isoformat() if row[8] else None,
                "source": row[9],
                "sequence_num": row[10],
                "kdes": {},
            })

        # Bulk-fetch KDEs for all events in one query (avoids N+1)
        if events:
            event_ids = [e["id"] for e in events]
            kde_map: Dict[str, Dict[str, str]] = {eid: {} for eid in event_ids}
            for chunk_start in range(0, len(event_ids), 100):
                chunk = event_ids[chunk_start:chunk_start + 100]
                placeholders = ", ".join(f":eid_{i}" for i in range(len(chunk)))
                kde_params: Dict[str, Any] = {f"eid_{i}": eid for i, eid in enumerate(chunk)}
                kde_params["tid"] = tenant_id
                kde_rows = self.session.execute(
                    text(f"""
                        SELECT cte_event_id, kde_key, kde_value
                        FROM fsma.cte_kdes
                        WHERE tenant_id = :tid AND cte_event_id IN ({placeholders})
                    """),
                    kde_params,
                ).fetchall()
                for kr in kde_rows:
                    kde_map[str(kr[0])][kr[1]] = kr[2]
            for event in events:
                event["kdes"] = kde_map.get(event["id"], {})

        return events
