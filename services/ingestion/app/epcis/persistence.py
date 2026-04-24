"""EPCIS event persistence layer.

Handles database queries, event fetching, listing, and ingestion with
fallback to in-memory storage when DB is unavailable outside production.
"""

from __future__ import annotations

import json
import logging
import os
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text

from shared.database import get_db_safe

from services.ingestion.app.epcis.extraction import _extract_lot_data
from services.ingestion.app.epcis.normalization import (
    _compliance_alerts,
    _event_idempotency_key,
    _extract_kdes,
    _kde_completeness,
    _normalize_epcis_to_cte,
)
from services.ingestion.app.epcis.validation import (
    _default_product_description,
    _enforce_mandatory_gln_check_digits,
    _validate_as_fsma_event,
    _validate_epcis,
    _validate_epcis_glns,
)

logger = logging.getLogger("epcis-ingestion")

# Tenant-scoped in-memory fallback stores (#1148). Outer dict is keyed by
# ``tenant_id``; inner OrderedDicts are bounded per-tenant via FIFO
# eviction in ``_fallback_store_put`` / ``_fallback_idempotency_put``.
# Production fallback is gated off via ``_allow_in_memory_fallback`` —
# these stores exist for development, tests, and the explicit
# ``ALLOW_EPCIS_IN_MEMORY_FALLBACK`` override.
_epcis_store: dict[str, "OrderedDict[str, dict]"] = {}
_epcis_idempotency_index: dict[str, "OrderedDict[str, str]"] = {}

_EPCIS_FALLBACK_CAP_PER_TENANT = int(
    os.getenv("EPCIS_FALLBACK_CAP_PER_TENANT", "10000")
)


def _fallback_store_for(tenant_id: str) -> "OrderedDict[str, dict]":
    return _epcis_store.setdefault(tenant_id, OrderedDict())


def _fallback_idempotency_for(tenant_id: str) -> "OrderedDict[str, str]":
    return _epcis_idempotency_index.setdefault(tenant_id, OrderedDict())


def _fallback_store_put(tenant_id: str, event_id: str, record: dict) -> None:
    store = _fallback_store_for(tenant_id)
    store[event_id] = record
    while len(store) > _EPCIS_FALLBACK_CAP_PER_TENANT:
        store.popitem(last=False)


def _fallback_idempotency_put(tenant_id: str, idem_key: str, event_id: str) -> None:
    idx = _fallback_idempotency_for(tenant_id)
    idx[idem_key] = event_id
    while len(idx) > _EPCIS_FALLBACK_CAP_PER_TENANT:
        idx.popitem(last=False)


def _is_production() -> bool:
    from shared.env import is_production
    return is_production()


# Safety: Allow in-memory fallback only outside production.
# This prevents unintended data loss if DB unavailability is transient.
def _allow_in_memory_fallback() -> bool:
    explicit = os.getenv("ALLOW_EPCIS_IN_MEMORY_FALLBACK")
    if explicit is not None:
        return explicit.lower() in {"1", "true", "yes"}
    return not _is_production()


def _batch_transactional() -> bool:
    """Return True when batch ingest MUST run under a single DB transaction.

    Default: True (atomic). This is the regulatory-safe default for #1156 —
    a mid-batch failure rolls back every event so downstream graph/compliance
    readers never observe a partial supply chain.

    Set ``EPCIS_BATCH_TRANSACTIONAL=false`` only for temporary migration
    windows or legacy consumers that explicitly want HTTP 207 partial-success
    semantics. Per-request override via ``?mode=partial`` is still accepted
    regardless of this flag.
    """
    explicit = os.getenv("EPCIS_BATCH_TRANSACTIONAL")
    if explicit is None:
        return True
    return explicit.strip().lower() in {"1", "true", "yes", "on", "atomic"}


def _fsma_strict_mode() -> bool:
    """Return True when FSMA schema validation MUST block persistence (#1239, #1151).

    Default: strict in production, strict outside production. This is the
    regulatory-correctness default — events that fail FSMAEvent schema
    validation are refused with HTTP 422 rather than silently persisted
    with only a warning.

    Two environment variables are recognized:
      * ``STRICT_FSMA_VALIDATION`` (preferred, matches #1151 naming)
      * ``FSMA_STRICT_MODE`` (legacy #1239 alias)

    Set either to ``false`` during staging migrations if you absolutely
    need the legacy advisory behaviour. Even then, failed events are
    marked ``fsma_validation_status=failed`` so the FDA 24-hour export
    can filter them out.
    """
    explicit = os.getenv("STRICT_FSMA_VALIDATION")
    if explicit is None:
        explicit = os.getenv("FSMA_STRICT_MODE")
    if explicit is None:
        return True
    return explicit.strip().lower() in {"1", "true", "yes", "on", "strict"}


def _safe_iso(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, str):
        return value
    return datetime.now(timezone.utc).isoformat()


def _build_kde_map(event: dict, normalized: dict, idempotency_key: str) -> dict[str, Any]:
    kde_map = {kde["kde_type"]: kde["kde_value"] for kde in _extract_kdes(event)}

    kde_map["epcis_document_json"] = json.dumps(event, sort_keys=True, separators=(",", ":"))
    kde_map["epcis_idempotency_key"] = idempotency_key

    if normalized.get("product_id"):
        kde_map["product_id"] = normalized["product_id"]
    if normalized.get("source_location_id"):
        kde_map["ship_from_gln"] = normalized["source_location_id"]
    if normalized.get("dest_location_id"):
        kde_map["ship_to_gln"] = normalized["dest_location_id"]

    return kde_map


def _query_alert_rows(db_session, tenant_id: str, event_id: str) -> list[dict]:
    # Allowlisted column identifiers for fsma.compliance_alerts dynamic SQL
    _ALLOWED_COLS = frozenset(
        {
            "tenant_id",
            "org_id",
            "cte_event_id",
            "event_id",
            "message",
            "description",
            "alert_type",
            "severity",
            "created_at",
            "id",
            "title",
            "resolved",
            "acknowledged",
            "resolved_at",
            "acknowledged_at",
            "resolved_by",
            "acknowledged_by",
            "details",
            "metadata",
            "entity_id",
        }
    )

    raw_columns = {
        row[0]
        for row in db_session.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'fsma'
                  AND table_name = 'compliance_alerts'
                """
            )
        ).fetchall()
    }
    # Only allow known-safe column names to prevent SQL injection
    columns = raw_columns & _ALLOWED_COLS
    if not columns:
        return []

    tenant_col = (
        "tenant_id"
        if "tenant_id" in columns
        else ("org_id" if "org_id" in columns else None)
    )
    event_col = (
        "cte_event_id"
        if "cte_event_id" in columns
        else ("event_id" if "event_id" in columns else None)
    )
    if tenant_col is None or event_col is None:
        return []

    message_expr = (
        "message"
        if "message" in columns
        else ("description" if "description" in columns else "alert_type")
    )
    # All interpolated identifiers are guaranteed members of _ALLOWED_COLS
    rows = db_session.execute(
        text(
            f"""
            SELECT severity, alert_type, {message_expr} AS message
            FROM fsma.compliance_alerts
            WHERE {tenant_col} = :tenant_id
              AND {event_col} = :event_id
            ORDER BY created_at DESC
            """
        ),
        {"tenant_id": tenant_id, "event_id": event_id},
    ).fetchall()
    return [
        {"severity": row.severity, "alert_type": row.alert_type, "message": row.message}
        for row in rows
    ]


def _parse_epcis_document(kdes: dict[str, Any], normalized: dict[str, Any]) -> dict:
    raw_json = kdes.get("epcis_document_json")
    if raw_json:
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            logger.warning("epcis_document_json_parse_failed")

    ilmd: dict[str, Any] = {}
    if normalized.get("lot_code"):
        ilmd["cbvmda:lotNumber"] = normalized["lot_code"]
    if normalized.get("tlc"):
        ilmd["fsma:traceabilityLotCode"] = normalized["tlc"]

    event: dict[str, Any] = {
        "type": normalized.get("epcis_event_type") or "ObjectEvent",
        "eventTime": normalized.get("event_time") or datetime.now(timezone.utc).isoformat(),
        "action": normalized.get("epcis_action") or "OBSERVE",
        "bizStep": normalized.get("epcis_biz_step") or "urn:epcglobal:cbv:bizstep:receiving",
        "ilmd": ilmd,
    }
    if normalized.get("source_location_id"):
        event["sourceList"] = [
            {"type": "urn:epcglobal:cbv:sdt:possessing_party", "source": normalized["source_location_id"]}
        ]
    if normalized.get("dest_location_id"):
        event["destinationList"] = [
            {"type": "urn:epcglobal:cbv:sdt:possessing_party", "destination": normalized["dest_location_id"]}
        ]
    return event


def _fetch_event_from_db(tenant_id: str, event_id: str) -> Optional[dict]:
    db_session = get_db_safe()
    try:
        row = db_session.execute(
            text(
                """
                SELECT
                    id::text AS id,
                    ingested_at,
                    idempotency_key,
                    event_type,
                    epcis_event_type,
                    epcis_action,
                    epcis_biz_step,
                    event_timestamp,
                    traceability_lot_code,
                    source,
                    location_gln,
                    quantity,
                    unit_of_measure
                FROM fsma.cte_events
                WHERE tenant_id = :tenant_id
                  AND id = :event_id
                LIMIT 1
                """
            ),
            {"tenant_id": tenant_id, "event_id": event_id},
        ).fetchone()
        if not row:
            return None

        kde_rows = db_session.execute(
            text(
                """
                SELECT kde_key, kde_value, is_required
                FROM fsma.cte_kdes
                WHERE tenant_id = :tenant_id
                  AND cte_event_id = :event_id
                """
            ),
            {"tenant_id": tenant_id, "event_id": event_id},
        ).fetchall()

        kdes = [
            {"kde_type": kde.kde_key, "kde_value": kde.kde_value, "required": bool(kde.is_required)}
            for kde in kde_rows
        ]
        kde_map = {kde["kde_type"]: kde["kde_value"] for kde in kdes}

        normalized = {
            "event_type": row.event_type,
            "epcis_event_type": row.epcis_event_type,
            "epcis_action": row.epcis_action,
            "epcis_biz_step": row.epcis_biz_step,
            "event_time": _safe_iso(row.event_timestamp),
            "lot_code": kde_map.get("lotNumber", ""),
            "tlc": row.traceability_lot_code,
            "product_id": kde_map.get("product_id"),
            "location_id": row.location_gln,
            "source_location_id": kde_map.get("ship_from_gln"),
            "dest_location_id": kde_map.get("ship_to_gln"),
            "quantity": row.quantity,
            "unit_of_measure": row.unit_of_measure,
            "data_source": row.source,
            "validation_status": "valid",
        }

        alerts = _query_alert_rows(db_session, tenant_id, row.id)
        return {
            "id": row.id,
            "ingested_at": _safe_iso(row.ingested_at),
            "idempotency_key": row.idempotency_key,
            "epcis_document": _parse_epcis_document(kde_map, normalized),
            "normalized_cte": normalized,
            "kdes": kdes,
            "alerts": alerts,
            "kde_completeness": _kde_completeness(kdes),
        }
    finally:
        db_session.close()


def _list_events_from_db(
    tenant_id: str,
    start_date: Optional[str],
    end_date: Optional[str],
    product_id: Optional[str],
) -> list[dict]:
    db_session = get_db_safe()
    try:
        where = ["tenant_id = :tenant_id"]
        params: dict[str, Any] = {"tenant_id": tenant_id}

        if start_date:
            where.append("event_timestamp >= :start_date")
            params["start_date"] = start_date
        if end_date:
            where.append("event_timestamp < :end_date")
            params["end_date"] = end_date

        rows = db_session.execute(
            text(
                f"""
                SELECT
                    id::text AS id,
                    event_type,
                    epcis_event_type,
                    epcis_action,
                    epcis_biz_step,
                    event_timestamp,
                    traceability_lot_code,
                    source,
                    location_gln,
                    quantity,
                    unit_of_measure
                FROM fsma.cte_events
                WHERE {' AND '.join(where)}
                ORDER BY event_timestamp DESC
                LIMIT 2000
                """
            ),
            params,
        ).fetchall()

        events: list[dict] = []
        for row in rows:
            kde_rows = db_session.execute(
                text(
                    """
                    SELECT kde_key, kde_value
                    FROM fsma.cte_kdes
                    WHERE tenant_id = :tenant_id
                      AND cte_event_id = :event_id
                    """
                ),
                {"tenant_id": tenant_id, "event_id": row.id},
            ).fetchall()
            kde_map = {kde.kde_key: kde.kde_value for kde in kde_rows}

            normalized = {
                "event_type": row.event_type,
                "epcis_event_type": row.epcis_event_type,
                "epcis_action": row.epcis_action,
                "epcis_biz_step": row.epcis_biz_step,
                "event_time": _safe_iso(row.event_timestamp),
                "lot_code": kde_map.get("lotNumber", ""),
                "tlc": row.traceability_lot_code,
                "product_id": kde_map.get("product_id"),
                "location_id": row.location_gln,
                "source_location_id": kde_map.get("ship_from_gln"),
                "dest_location_id": kde_map.get("ship_to_gln"),
                "quantity": row.quantity,
                "unit_of_measure": row.unit_of_measure,
                "data_source": row.source,
                "validation_status": "valid",
            }

            if product_id and normalized.get("product_id") != product_id:
                continue

            events.append(_parse_epcis_document(kde_map, normalized))

        return events
    finally:
        db_session.close()


def _ingest_single_event_fallback(tenant_id: str, event: dict) -> tuple[dict, int]:
    """Persist an event to the tenant-scoped in-memory fallback store.

    #1148: store and idempotency index are keyed by ``tenant_id`` — prior
    flat layout allowed cross-tenant reads when the DB was unreachable.
    Each tenant's partition is bounded by ``EPCIS_FALLBACK_CAP_PER_TENANT``
    (default 10_000) and evicts FIFO.
    """
    errors = _validate_epcis(event)
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    idempotency_key = _event_idempotency_key(event)
    tenant_idx = _fallback_idempotency_for(tenant_id)
    tenant_store = _fallback_store_for(tenant_id)
    existing_event_id = tenant_idx.get(idempotency_key)
    if existing_event_id:
        existing_record = tenant_store[existing_event_id]
        return (
            {
                "status": 200,
                "cte_id": existing_event_id,
                "validation_status": existing_record["normalized_cte"]["validation_status"],
                "kde_completeness": existing_record.get("kde_completeness", 1.0),
                "alerts": existing_record["alerts"],
                "idempotent": True,
            },
            200,
        )

    event_id = str(uuid4())
    normalized = _normalize_epcis_to_cte(event)
    kdes = _extract_kdes(event)
    alerts = _compliance_alerts(normalized, kdes)
    # #1259: fail-closed on malformed mandatory GLNs before persistence.
    _enforce_mandatory_gln_check_digits(normalized)
    alerts.extend(_validate_epcis_glns(normalized))

    # Validate against FSMAEvent Pydantic model before storing.
    # #1239: in strict mode (default), validation failure is a hard 422 —
    # the event is NOT persisted. In advisory mode we persist with an
    # error-severity alert so FDA exports can filter it out.
    fsma_validated = _validate_as_fsma_event(normalized, tenant_id)
    if fsma_validated:
        normalized["fsma_validation_status"] = "passed"
    else:
        if _fsma_strict_mode():
            logger.warning(
                "epcis_fsma_validation_rejected tenant=%s tlc=%s event=%s",
                tenant_id,
                normalized.get("tlc"),
                normalized.get("event_time"),
            )
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "fsma_validation_failed",
                    "message": (
                        "Event failed FSMAEvent schema validation and was "
                        "not persisted. Set FSMA_STRICT_MODE=false only for "
                        "temporary migration windows."
                    ),
                },
            )
        normalized["fsma_validation_status"] = "failed"
        alerts.append({
            "severity": "error",
            "alert_type": "fsma_validation",
            "message": (
                "Event did not pass FSMAEvent schema validation. Excluded "
                "from FSMA compliance exports by default."
            ),
        })

    stored = {
        "id": event_id,
        "tenant_id": tenant_id,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "idempotency_key": idempotency_key,
        "epcis_document": event,
        "normalized_cte": normalized,
        "kdes": kdes,
        "alerts": alerts,
        "kde_completeness": _kde_completeness(kdes),
    }
    _fallback_store_put(tenant_id, event_id, stored)
    _fallback_idempotency_put(tenant_id, idempotency_key, event_id)

    return (
        {
            "status": 201,
            "cte_id": event_id,
            "validation_status": "warning" if alerts else "valid",
            "kde_completeness": stored["kde_completeness"],
            "alerts": alerts,
            "idempotent": False,
        },
        201,
    )


def _prepare_event_for_persistence(tenant_id: str, event: dict) -> dict:
    """Pre-DB validation + normalization pipeline.

    Runs all checks that can reject an event before any DB work:
    structural EPCIS validation, CTE normalization (includes unmapped
    bizStep rejection per #1153), FSMA schema gate (#1239), and
    quantity acceptance (#1249 — no silent clamp to 1.0). Raises
    ``HTTPException`` on any failure so the batch orchestrator can
    abort before opening a DB transaction.
    """
    errors = _validate_epcis(event)
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    idempotency_key = _event_idempotency_key(event)
    normalized = _normalize_epcis_to_cte(event)
    kdes = _extract_kdes(event)
    alerts = _compliance_alerts(normalized, kdes)
    # #1259: fail-closed on malformed mandatory GLNs before persistence.
    _enforce_mandatory_gln_check_digits(normalized)
    alerts.extend(_validate_epcis_glns(normalized))
    kde_map = _build_kde_map(event, normalized, idempotency_key)

    # Validate against FSMAEvent Pydantic model before DB persistence.
    # #1239: strict mode (default) — raise 422 rather than store a
    # known-bad event. Advisory mode still stores but with an
    # error-severity alert so FDA exports can filter it out.
    fsma_validated = _validate_as_fsma_event(normalized, tenant_id)
    if fsma_validated:
        kde_map["fsma_validation_status"] = "passed"
    else:
        if _fsma_strict_mode():
            logger.warning(
                "epcis_fsma_validation_rejected_db tenant=%s tlc=%s",
                tenant_id, normalized.get("tlc"),
            )
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "fsma_validation_failed",
                    "message": (
                        "Event failed FSMAEvent schema validation and was "
                        "not persisted. Set FSMA_STRICT_MODE=false only for "
                        "temporary migration windows."
                    ),
                },
            )
        kde_map["fsma_validation_status"] = "failed"
        alerts.append({
            "severity": "error",
            "alert_type": "fsma_validation",
            "message": (
                "Event did not pass FSMAEvent schema validation. Excluded "
                "from FSMA compliance exports by default."
            ),
        })

    # #1249: quantity must be explicit. We no longer synthesize 1.0 for
    # missing / non-numeric / non-positive values — that falsified FDA
    # traceability records. Zero and negative quantities are legitimate
    # FSMA values (empty pallet, reversal, recall correction) and are
    # persisted as-is after FSMAEvent validation (which enforces ge=0
    # for strict mode; advisory mode stores the original).
    quantity = normalized.get("quantity")
    if quantity is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "missing_quantity",
                "message": (
                    "FSMA 204 requires a numeric quantity KDE. Silent "
                    "synthesis to 1.0 was removed per #1249 — events must "
                    "supply quantity via EPCIS quantityList."
                ),
            },
        )
    try:
        quantity_value = float(quantity)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "non_numeric_quantity",
                "quantity": str(quantity),
                "message": (
                    "EPCIS quantity must be numeric. Non-numeric values "
                    "are rejected per #1249 rather than coerced to 1.0."
                ),
            },
        )

    event_time = normalized.get("event_time") or datetime.now(timezone.utc).isoformat()
    return {
        "event": event,
        "idempotency_key": idempotency_key,
        "normalized": normalized,
        "kdes": kdes,
        "alerts": alerts,
        "kde_map": kde_map,
        "quantity_value": quantity_value,
        "event_time": event_time,
    }


def _persist_prepared_event_in_session(
    db_session, tenant_id: str, prepared: dict
) -> tuple[dict, int]:
    """Persist a prepared event using a caller-managed DB session.

    Does NOT commit or close the session — the caller is responsible
    for lifecycle. This is what the atomic batch path uses so a single
    rollback can unwind every per-event change (#1156).
    """
    from shared.cte_persistence import CTEPersistence

    normalized = prepared["normalized"]
    kde_map = prepared["kde_map"]
    event = prepared["event"]
    alerts = prepared["alerts"]
    kdes = prepared["kdes"]

    # Pre-eval rules enforcement gate (Phase 0 #1d).
    # Runs BEFORE the primary CTE write so a reject can prevent the
    # event from ever being persisted. Uses persist=False to avoid
    # writing eval rows that would be orphaned on a rejection.
    #
    # Short-circuits on OFF mode (current prod default) to avoid the
    # eval CPU cost on every ingested event. EPCIS is the hot path.
    #
    # Canonical-normalization / engine errors are swallowed and
    # treated as no-verdict — a transient bug in the rules subsystem
    # must not take down ingestion for every tenant. This matches the
    # best-effort pattern the threaded canonical block below already
    # uses (#1335).
    from shared.rules.enforcement import current_mode, should_reject, EnforcementMode  # noqa: PLC0415
    if current_mode() != EnforcementMode.OFF:
        _preeval_summary = None
        try:
            from shared.canonical_event import normalize_epcis_event  # noqa: PLC0415
            from shared.rules_engine import RulesEngine  # noqa: PLC0415
            _pre_canonical = normalize_epcis_event(event, tenant_id)
            _pre_engine = RulesEngine(db_session)
            _pre_event_data = {
                "event_id": str(_pre_canonical.event_id),
                "event_type": _pre_canonical.event_type.value,
                "traceability_lot_code": _pre_canonical.traceability_lot_code,
                "product_reference": _pre_canonical.product_reference,
                "quantity": _pre_canonical.quantity,
                "unit_of_measure": _pre_canonical.unit_of_measure,
                "from_facility_reference": _pre_canonical.from_facility_reference,
                "to_facility_reference": _pre_canonical.to_facility_reference,
                "from_entity_reference": _pre_canonical.from_entity_reference,
                "to_entity_reference": _pre_canonical.to_entity_reference,
                "kdes": _pre_canonical.kdes,
            }
            _preeval_summary = _pre_engine.evaluate_event(
                _pre_event_data, persist=False, tenant_id=tenant_id,
            )
        except (ImportError, ValueError, TypeError, RuntimeError,
                AttributeError, KeyError) as _pre_err:
            logger.warning(
                "epcis_rules_preeval_skipped: %s", str(_pre_err),
            )

        if _preeval_summary is not None:
            _reject, _reason = should_reject(_preeval_summary)
            if _reject:
                # Raise HTTPException so the caller's db_session.rollback()
                # unwinds any in-flight state and the HTTP layer returns
                # a structured 422. For the atomic-batch caller this
                # rolls back the entire batch; partial-mode callers use
                # the single-event path and get per-event semantics.
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": "rule_violation",
                        "reason": _reason,
                        "tenant_id": tenant_id,
                    },
                )

    persistence = CTEPersistence(db_session)
    result = persistence.store_event(
        tenant_id=tenant_id,
        event_type=normalized["event_type"],
        traceability_lot_code=normalized["tlc"],
        product_description=_default_product_description(normalized),
        quantity=prepared["quantity_value"],
        unit_of_measure=normalized.get("unit_of_measure") or "units",
        event_timestamp=prepared["event_time"],
        source="epcis",
        source_event_id=str(event.get("eventID") or prepared["idempotency_key"]),
        location_gln=normalized.get("location_id"),
        location_name=None,
        kdes=kde_map,
        alerts=alerts,
        epcis_event_type=normalized.get("epcis_event_type"),
        epcis_action=normalized.get("epcis_action"),
        epcis_biz_step=normalized.get("epcis_biz_step"),
    )

    # Canonical normalization — write to traceability_events + evaluate rules.
    # (#1335) Fan-out timeout: legacy write already committed; canonical is
    # best-effort.  Cap via CANONICAL_DUAL_WRITE_TIMEOUT_S (default 5 s) so a
    # slow canonical DB path does not block the EPCIS ingest response.
    if not result.idempotent:
        import os  # noqa: PLC0415
        import threading as _threading  # noqa: PLC0415
        _timeout_s = float(os.environ.get("CANONICAL_DUAL_WRITE_TIMEOUT_S", "5"))

        def _epcis_canonical_write() -> None:
            from shared.canonical_event import normalize_epcis_event  # noqa: PLC0415
            from shared.canonical_persistence import CanonicalEventStore  # noqa: PLC0415
            from shared.rules_engine import RulesEngine  # noqa: PLC0415
            _canonical = normalize_epcis_event(event, tenant_id)
            _store = CanonicalEventStore(db_session, dual_write=False, skip_chain_write=True)
            _store.set_tenant_context(tenant_id)
            _store.persist_event(_canonical)
            _engine = RulesEngine(db_session)
            _event_data = {
                "event_id": str(_canonical.event_id),
                "event_type": _canonical.event_type.value,
                "traceability_lot_code": _canonical.traceability_lot_code,
                "product_reference": _canonical.product_reference,
                "quantity": _canonical.quantity,
                "unit_of_measure": _canonical.unit_of_measure,
                "from_facility_reference": _canonical.from_facility_reference,
                "to_facility_reference": _canonical.to_facility_reference,
                "from_entity_reference": _canonical.from_entity_reference,
                "to_entity_reference": _canonical.to_entity_reference,
                "kdes": _canonical.kdes,
            }
            _engine.evaluate_event(_event_data, persist=True, tenant_id=tenant_id)

        import threading  # noqa: PLC0415
        _epcis_exc: list[BaseException] = []

        def _guarded_epcis_canonical_write() -> None:
            try:
                _epcis_canonical_write()
            except Exception as _exc:  # noqa: BLE001
                _epcis_exc.append(_exc)

        _t = _threading.Thread(target=_guarded_epcis_canonical_write, daemon=True)
        _t.start()
        _t.join(timeout=_timeout_s)
        if _t.is_alive():
            logger.warning(
                "epcis_canonical_write_timeout",
                event_id=getattr(result, "event_id", None),
                timeout_s=_timeout_s,
            )
        elif _epcis_exc:
            logger.warning(
                "epcis_canonical_write_skipped: %s",
                _epcis_exc[0],
            )

    status_code = 200 if result.idempotent else 201
    return (
        {
            "status": status_code,
            "cte_id": result.event_id,
            "validation_status": "warning" if alerts else "valid",
            "kde_completeness": _kde_completeness(kdes),
            "alerts": alerts,
            "idempotent": result.idempotent,
        },
        status_code,
    )


def _ingest_single_event_db(tenant_id: str, event: dict) -> tuple[dict, int]:
    """Own-session convenience wrapper for single-event DB ingest.

    #1151: refuse to persist an event whose FSMAEvent validation is
    missing. ``_prepare_event_for_persistence`` already raises HTTP 422
    on strict-mode validation failure; we convert that to a code-level
    ``ValueError("E_EPCIS_UNVALIDATED")`` here so callers that are not
    on the HTTP edge get a clear programmatic signal. We also re-assert
    on ``fsma_validation_status`` before committing — a future caller
    that bypasses the preparation helper (or an advisory-mode caller
    whose ``fsma_validated`` is ``None``) must not silently persist into
    the traceability graph when ``STRICT_FSMA_VALIDATION`` is on.
    """
    try:
        prepared = _prepare_event_for_persistence(tenant_id, event)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        if (
            exc.status_code == 422
            and detail.get("error") == "fsma_validation_failed"
            and _fsma_strict_mode()
        ):
            logger.warning(
                "epcis_single_event_refused_unvalidated tenant=%s", tenant_id
            )
            raise ValueError("E_EPCIS_UNVALIDATED") from exc
        raise

    # #1151: hard gate on fsma_validation_status before any DB work.
    # ``_prepare_event_for_persistence`` sets this to 'passed' or 'failed'
    # (strict mode already 422s on failure; advisory mode falls through
    # with 'failed'). A missing status means some caller skipped the
    # FSMA gate — refuse to persist in strict mode.
    kde_map = prepared.get("kde_map") or {}
    fsma_status = kde_map.get("fsma_validation_status")
    if fsma_status != "passed" and _fsma_strict_mode():
        logger.warning(
            "epcis_single_event_refused_unvalidated tenant=%s status=%r",
            tenant_id,
            fsma_status,
        )
        raise ValueError("E_EPCIS_UNVALIDATED")

    db_session = get_db_safe()
    try:
        payload, status_code = _persist_prepared_event_in_session(
            db_session, tenant_id, prepared
        )
        db_session.commit()
        return payload, status_code
    except Exception:
        db_session.rollback()
        raise
    finally:
        db_session.close()


def _ingest_batch_events_db_atomic(
    tenant_id: str, events: list[dict]
) -> list[tuple[dict, int]]:
    """Atomic batch ingest: validate all events first, then persist under a
    single DB transaction. Any per-event failure rolls back the whole batch.

    Closes #1156 — previously each event committed independently, leaving
    partial state on mid-batch failure.
    """
    # Phase 1: pre-validate all events. Collect every error so the caller
    # can return a per-index error map without half-committing work.
    prepared_events: list[dict] = []
    errors: list[dict] = []
    for idx, event in enumerate(events):
        try:
            prepared_events.append(_prepare_event_for_persistence(tenant_id, event))
        except HTTPException as exc:
            errors.append({"index": idx, "status_code": exc.status_code, "detail": exc.detail})

    if errors:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "batch_validation_failed",
                "mode": "atomic",
                "message": (
                    "One or more events failed pre-DB validation. No events "
                    "were persisted. Use ?mode=partial to opt in to "
                    "per-event processing with HTTP 207 semantics."
                ),
                "errors": errors,
            },
        )

    # Phase 2: persist every prepared event under a single session. Track
    # the in-flight index so a mid-batch failure can identify the offending
    # event in the rollback log (#1156).
    db_session = get_db_safe()
    results: list[tuple[dict, int]] = []
    failing_index: Optional[int] = None
    try:
        for idx, prepared in enumerate(prepared_events):
            failing_index = idx
            payload, status_code = _persist_prepared_event_in_session(
                db_session, tenant_id, prepared
            )
            results.append((payload, status_code))
        failing_index = None
        db_session.commit()
        return results
    except Exception as exc:
        db_session.rollback()
        logger.warning(
            "epcis_batch_rollback tenant=%s failed_index=%s batch_size=%s error=%s",
            tenant_id,
            failing_index,
            len(prepared_events),
            str(exc),
        )
        raise HTTPException(
            status_code=400,
            detail={
                "error": "batch_persistence_failed",
                "mode": "atomic",
                "failed_index": failing_index,
                "message": (
                    "Persistence failed mid-batch. All events in this batch "
                    "were rolled back. Use ?mode=partial for best-effort "
                    "per-event ingest."
                ),
                "cause": str(exc),
            },
        ) from exc
    finally:
        db_session.close()


def _ingest_single_event(tenant_id: str, event: dict) -> tuple[dict, int]:
    try:
        return _ingest_single_event_db(tenant_id, event)
    except HTTPException:
        # Validation failures (400/422) must surface as-is — do not fall
        # back to in-memory for rejected events.
        raise
    except ValueError as exc:
        # #1151: ``E_EPCIS_UNVALIDATED`` is a hard validation failure
        # from ``_ingest_single_event_db``. Map to 422 at the HTTP edge
        # instead of silently falling back to in-memory (that's what
        # let malformed events into the graph pre-fix).
        if str(exc) == "E_EPCIS_UNVALIDATED":
            logger.warning(
                "epcis_ingest_refused_unvalidated tenant=%s", tenant_id
            )
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "fsma_validation_failed",
                    "message": (
                        "Event failed FSMAEvent schema validation and was "
                        "not persisted. Set STRICT_FSMA_VALIDATION=false "
                        "only for temporary migration windows."
                    ),
                },
            ) from exc
        raise
    except Exception as exc:
        if not _allow_in_memory_fallback():
            logger.error("epcis_db_persistence_failed_no_fallback error=%s", str(exc))
            raise HTTPException(
                status_code=503,
                detail="Database unavailable — EPCIS ingest cannot proceed.",
            ) from exc

        logger.warning("epcis_db_persistence_failed_using_fallback error=%s", str(exc))
        return _ingest_single_event_fallback(tenant_id, event)
