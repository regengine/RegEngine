"""Single-event write path for the CTE persistence layer.

Mechanically extracted from ``core.py`` (file split — no logic changes).
``core.CTEPersistence`` composes this mixin. Helpers, constants, models
and hashing functions that used to be module globals of ``core.py`` are
resolved late through the ``core`` module (method-local ``from . import
core as _core``) so existing monkeypatch / ``patch("...cte_persistence.
core.X")`` targets keep affecting this code exactly as before the split.
"""

from __future__ import annotations

import warnings
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import text

if TYPE_CHECKING:  # pragma: no cover — annotation-only import
    from .models import StoreResult


class WritePathMixin:
    """Single-event write path — mixed into :class:`core.CTEPersistence`."""

    # ------------------------------------------------------------------
    # Per-tenant Chain Serialization (fix #1332)
    # ------------------------------------------------------------------

    def _acquire_chain_lock(self, tenant_id: str) -> None:
        """Acquire a per-tenant transaction-scoped advisory lock.

        A chain-head ``SELECT ... FOR UPDATE LIMIT 1`` only
        locks the returned row, not the next slot. On a
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
        validator_results: Optional[List[Dict[str, Any]]] = None,
        canonical_event: Any = None,
    ) -> StoreResult:
        """
        Persist a CTE event with its KDEs, hash chain entry, and alerts.

        This is an atomic operation — either everything is committed or
        nothing is. The caller is responsible for committing the session.

        Returns:
            StoreResult with event_id, hashes, and any alerts.
        """
        # Late-bind through the core module so patched attributes
        # (e.g. core._assert_not_exists) take effect (#file-split).
        from . import core as _core

        # #1335 — LEGACY write path. Migrate callers to
        # ``shared.canonical_persistence.CanonicalEventStore``.
        warnings.warn(
            "CTEPersistence.store_event() is LEGACY (#1335). "
            "Use shared.canonical_persistence.CanonicalEventStore instead.",
            DeprecationWarning,
            stacklevel=2,
        )

        kdes = kdes or {}
        alerts = alerts or []
        validator_results = validator_results or []
        event_id = str(uuid4())

        # --- event_type validation (fix #1312) ---
        # Fail fast on free-form strings (trailing whitespace, wrong
        # case, typos, garbage) BEFORE we hash, chain-lock, or write
        # KDEs. The DB CHECK constraint would also reject bad values,
        # but only after a round-trip that leaves a confusing
        # IntegrityError; this surfaces a clear ValueError with the
        # allowed list.
        event_type = _core._validate_event_type(event_type)

        # --- Timestamp validation (fix #1308) ---
        # Parse + normalize to UTC + reject naive/future/garbage inputs.
        # We keep ``event_timestamp`` as the canonical ISO-8601 string
        # for hashing (compute_event_hash is string-based) but the
        # parsed datetime is what goes into the DB — no more opaque
        # passthroughs.
        event_dt = _core._parse_timestamp(event_timestamp, field="event_timestamp")
        event_timestamp = event_dt.isoformat()
        if event_entry_timestamp is not None:
            entry_dt = _core._parse_timestamp(event_entry_timestamp, field="event_entry_timestamp")
            event_entry_timestamp = entry_dt.isoformat()

        # --- Determine validation status (fix #1324) ---
        # If any validator result or alert carries a rejecting outcome,
        # the event must NOT be written to the hash chain or included in
        # FDA export / graph sync queries. We still persist the event row
        # itself (for audit purposes) with validation_status='rejected'
        # and carry the rejection reasons in the returned StoreResult
        # errors list so callers can surface them to operators.
        _rejection_reasons: List[str] = []
        for item in [*validator_results, *alerts]:
            if _core._is_rejecting_validation_item(item):
                reason = item.get("reason") or item.get("message") or str(item)
                _rejection_reasons.append(reason)
        _final_status = _core._derive_validation_status(alerts, validator_results)

        # --- Serialize chain growth per-tenant (fix #1332) ---
        # Must precede both the idempotency SELECT and the chain-head
        # SELECT so two concurrent first-event writers cannot both see
        # ``chain_head=None`` and compute sequence_num=1. Released
        # automatically at COMMIT / ROLLBACK.
        self._acquire_chain_lock(tenant_id)

        # --- Idempotency check ---
        idempotency_key = _core.compute_idempotency_key(
            event_type,
            traceability_lot_code,
            event_timestamp,
            source,
            kdes,
            location_gln=location_gln,
            location_name=location_name,
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
            _core.logger.info(
                "idempotent_event_skipped",
                extra={
                    "existing_id": str(existing[0]),
                    "tlc": traceability_lot_code,
                },
            )
            return _core.StoreResult(
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
        sha256_hash = _core.compute_event_hash(
            event_id,
            event_type,
            traceability_lot_code,
            product_description,
            quantity,
            unit_of_measure,
            location_gln,
            location_name,
            event_timestamp,
            kdes,
        )
        if canonical_event is not None:
            sha256_hash = _core.compute_canonical_event_hash(event_id, tenant_id, canonical_event)

        # --- Append-only enforcement (#1334) ---
        # Raise before INSERT so callers see a typed DuplicateEventError
        # rather than an IntegrityError.  The idempotency_key check above
        # already handles exact duplicate inputs; this catches the distinct
        # case where the same event content arrives with a different
        # idempotency_key (e.g. from a different source field) but would
        # produce the same SHA-256 hash — an overwrite attempt on an
        # already-locked event record.
        _core._assert_not_exists(sha256_hash, tenant_id, self.session)

        # Get the current chain head for this tenant
        chain_head = self.session.execute(
            text("""
                SELECT chain_hash, sequence_num
                FROM fsma.hash_chain
                WHERE tenant_id = :tid
                ORDER BY sequence_num DESC
                LIMIT 1
            """),
            {"tid": tenant_id},
        ).fetchone()

        previous_chain_hash = chain_head[0] if chain_head else None
        next_sequence = (chain_head[1] + 1) if chain_head else 1

        chain_hash = _core.compute_chain_hash(sha256_hash, previous_chain_hash)

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
                "validation_status": _final_status,
            },
        )

        # --- Rejected events: skip chain write (#1324) ---
        # A rejected event is persisted above for audit but must NOT
        # appear in the hash chain. Returning early here prevents
        # orphan chain rows (the WHERE EXISTS guard below would also
        # block it, but being explicit is clearer and avoids the
        # sequence_num slot being consumed needlessly).
        if _final_status == _core.VALIDATION_STATUS_REJECTED:
            _core.logger.info(
                "cte_event_rejected",
                extra={
                    "event_id": event_id,
                    "event_type": event_type,
                    "tlc": traceability_lot_code,
                    "tenant_id": tenant_id,
                    "reasons": _rejection_reasons,
                },
            )
            return _core.StoreResult(
                success=False,
                event_id=event_id,
                sha256_hash=sha256_hash,
                chain_hash=chain_hash,
                idempotent=False,
                errors=_rejection_reasons,
                kde_completeness=1.0,
                alerts=alerts,
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
                    "kde_value": _core._jsonify_kde(kde_value),
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
        # SQL / accepted-type set / parameter shape live in ``core`` so the
        # batch path writes byte-identical rows for identical input (#2902).
        for alert in alerts:
            nested = self.session.begin_nested()
            try:
                self.session.execute(
                    text(_core.ALERT_INSERT_SQL),
                    _core._alert_insert_params(tenant_id, event_id, alert),
                )
                nested.commit()
            except Exception as exc:
                nested.rollback()
                _core.logger.warning(
                    "alert_insert_failed",
                    extra={
                        "event_id": event_id,
                        "alert_type": alert.get("alert_type", "missing_kde"),
                        "error": str(exc),
                    },
                )

        _core.logger.info(
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

        return _core.StoreResult(
            success=True,
            event_id=event_id,
            sha256_hash=sha256_hash,
            chain_hash=chain_hash,
            idempotent=False,
            errors=[],
            kde_completeness=1.0,
            alerts=alerts,
        )
