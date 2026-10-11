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

# The 7 FSMA 204 s1.1310 CTEs the ``cte_events`` schema accepts. Deliberately
# a copy of ``cte_persistence.core._ALLOWED_CTE_TYPES``; a drift test pins
# them together.
_PERSISTABLE_CTE_TYPES = frozenset(
    {
        "harvesting",
        "cooling",
        "initial_packing",
        "first_land_based_receiving",
        "shipping",
        "receiving",
        "transformation",
    }
)
from shared.database import get_db_safe
from sqlalchemy import text

from .extraction import _extract_lot_data
from .normalization import (
    _compliance_alerts,
    _event_idempotency_key,
    _extract_kdes,
    _kde_completeness,
    _normalize_epcis_to_cte,
)
from .validation import (
    _enforce_mandatory_gln_check_digits,
    _epcis_product_description,
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

_EPCIS_FALLBACK_CAP_PER_TENANT = int(os.getenv("EPCIS_FALLBACK_CAP_PER_TENANT", "10000"))


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

    tenant_col = "tenant_id" if "tenant_id" in columns else ("org_id" if "org_id" in columns else None)
    event_col = "cte_event_id" if "cte_event_id" in columns else ("event_id" if "event_id" in columns else None)
    if tenant_col is None or event_col is None:
        return []

    message_expr = "message" if "message" in columns else ("description" if "description" in columns else "alert_type")
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
    return [{"severity": row.severity, "alert_type": row.alert_type, "message": row.message} for row in rows]


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

    event_type = normalized.get("epcis_event_type") or "ObjectEvent"
    event: dict[str, Any] = {
        "type": event_type,
        "eventTime": normalized.get("event_time") or datetime.now(timezone.utc).isoformat(),
        "bizStep": normalized.get("epcis_biz_step") or "urn:epcglobal:cbv:bizstep:receiving",
        "ilmd": ilmd,
    }
    # #2970: EPCIS 2.0 TransformationEvent has no ``action`` member — a
    # rebuilt transformation must not round-trip out carrying a
    # fabricated "OBSERVE".
    if event_type != "TransformationEvent":
        event["action"] = normalized.get("epcis_action") or "OBSERVE"
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
            {"kde_type": kde.kde_key, "kde_value": kde.kde_value, "required": bool(kde.is_required)} for kde in kde_rows
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
                WHERE {" AND ".join(where)}
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
        existing_record = tenant_store.get(existing_event_id)
        if existing_record is not None:
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
        # The index references a record the bounded store has evicted (or
        # that never landed). Drop the stale entry and fall through to a
        # fresh ingest instead of raising KeyError (HTTP 500).
        tenant_idx.pop(idempotency_key, None)

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
        alerts.append(
            {
                "severity": "error",
                "alert_type": "fsma_validation",
                "message": (
                    "Event did not pass FSMAEvent schema validation. Excluded from FSMA compliance exports by default."
                ),
            }
        )

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


def _unsupported_cte_type_error(event_type: Any) -> Optional[dict]:
    """Return an error detail when ``event_type`` is not a persistable CTE.

    Mirrors ``cte_persistence.core._ALLOWED_CTE_TYPES`` — the 7 FSMA 204
    s1.1310 CTEs the ``cte_events`` schema actually accepts. Kept as a
    lightweight local check rather than importing that private set, because
    that module is slated for retirement (#1335) and importing it here would
    couple the EPCIS path to its lifetime.

    Returns ``None`` for anything valid, so callers stay a plain ``if``.
    """
    if event_type in _PERSISTABLE_CTE_TYPES:
        return None
    return {
        "error": "unsupported_cte_type",
        "message": (
            f"event_type {event_type!r} is not one of the 7 FSMA 204 "
            "Critical Tracking Events and cannot be persisted. Recognized "
            "bizSteps that map to it (e.g. FSMA 'growing', CBV 'planting') "
            "must be rejected or reclassified upstream. (#2815)"
        ),
        "allowed": sorted(_PERSISTABLE_CTE_TYPES),
    }


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

    # Reject a recognized-but-non-CTE activity HERE, in phase 1, where a
    # rejection belongs.
    #
    # `_normalize_epcis_to_cte` maps FSMA `growing` and CBV `planting` to the
    # event_type "growing" — real bizSteps that are simply not among the 7
    # s1.1310 CTEs. Nothing in phase 1 checked the resulting event_type, so
    # such an event reached phase 2 and blew up there instead: the legacy
    # write's `_validate_event_type` raises a bare ValueError, and the
    # canonical dual-write raises `UnmappedBizStepError` (#2815) for the same
    # input. In `_ingest_batch_events_db_atomic` that lands in the phase-2
    # handler, which frames ANY exception as `batch_persistence_failed`
    # ("Persistence failed mid-batch") — a persistence-crash story for what is
    # really a validation rejection, and it rolls back the whole batch without
    # telling the client which event was at fault.
    #
    # Raising HTTPException here instead means phase 1 collects it into the
    # per-index `batch_validation_failed` map like every other validation
    # failure, and the single-event path re-raises it unchanged as a 422.
    _unsupported = _unsupported_cte_type_error(normalized.get("event_type"))
    if _unsupported is not None:
        raise HTTPException(status_code=422, detail=_unsupported)

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
                tenant_id,
                normalized.get("tlc"),
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
        alerts.append(
            {
                "severity": "error",
                "alert_type": "fsma_validation",
                "message": (
                    "Event did not pass FSMAEvent schema validation. Excluded from FSMA compliance exports by default."
                ),
            }
        )

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

    # No ``now()`` stand-in: an event time the partner never sent is not
    # evidence of when the event happened. ``_validate_epcis`` rejects a
    # missing ``eventTime`` earlier; this guards the advisory-mode path.
    event_time = normalized.get("event_time")
    if not event_time:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "missing_event_time",
                "message": "EPCIS eventTime is required; the ingestion time is not substituted for it.",
            },
        )
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


def _persist_prepared_event_in_session(db_session, tenant_id: str, prepared: dict) -> tuple[dict, int]:
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
    #
    # ``_preeval_summary`` is hoisted to function scope so the threaded
    # canonical-write block below can reuse it via
    # ``RulesEngine.persist_summary`` instead of re-running every rule
    # — eliminates the double-eval that lands when the flag flips on.
    _preeval_summary = None
    from shared.rules.enforcement import (  # noqa: PLC0415
        EnforcementMode,
        current_mode,
        handle_preeval_exception,
        should_reject,
    )

    if current_mode() != EnforcementMode.OFF:
        # Bound before the try so the handler below can reference it even if
        # the import itself is what failed. isinstance(x, ()) is False, so the
        # empty tuple is a safe "no match" sentinel. Imported lazily on purpose:
        # shared.canonical_event has a documented circular-import hazard that
        # breaks BOTH import orders (#2815), so it must not be imported at
        # module scope here.
        _unmapped_bizstep_exc: Any = ()
        try:
            from shared.canonical_event import (  # noqa: PLC0415
                UnmappedBizStepError,
                normalize_epcis_event,
            )
            from shared.rules_engine import RulesEngine  # noqa: PLC0415

            _unmapped_bizstep_exc = UnmappedBizStepError

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
                _pre_event_data,
                persist=False,
                tenant_id=tenant_id,
            )
        except (ImportError, ValueError, TypeError, RuntimeError, AttributeError, KeyError) as _pre_err:
            # A bizStep the legacy gate accepts but that has no canonical CTE
            # -- FSMA ``growing`` and CBV ``planting`` are real, legitimate
            # bizSteps that are simply not among the 7 s1.1310 CTEs -- is a
            # VALIDATION REJECTION, not a crash. UnmappedBizStepError subclasses
            # ValueError, so without this it falls into the broad handler below
            # and ``handle_preeval_exception`` turns a well-formed client event
            # into a 500 (plus Sentry noise) under cte_only/all. Surface it as
            # the same 422 a rules-engine rejection uses, so the batch
            # orchestrator records it as a per-event error and keeps going.
            if isinstance(_pre_err, _unmapped_bizstep_exc):
                raise HTTPException(
                    status_code=422,
                    detail={"errors": [str(_pre_err)]},
                ) from _pre_err
            # Finding A — under enforcement modes a pre-eval crash must
            # become a 5xx, NOT a silent accept. ``handle_preeval_exception``
            # logs+Sentry+raises HTTPException(500) under cte_only/all
            # and warns+returns under off.
            handle_preeval_exception(_pre_err, where="epcis_persistence")

        if _preeval_summary is not None:
            _reject, _reason = should_reject(_preeval_summary)
            if _reject:
                # Finding B — write the durable audit row BEFORE raising
                # the 422 so it survives the caller's outer rollback.
                # Uses its own session so commit is independent.
                try:
                    from shared.rules.rejection_audit import (  # noqa: PLC0415
                        reasons_from_summary,
                        record_rejection,
                    )

                    _first_crit = (_preeval_summary.critical_failures or [None])[0]
                    record_rejection(
                        tenant_id=tenant_id,
                        rule_id=getattr(_first_crit, "rule_id", None),
                        rule_version=getattr(_first_crit, "rule_version", None),
                        event_id=str(_pre_canonical.event_id),
                        reasons=reasons_from_summary(_preeval_summary),
                        source="epcis_preeval",
                        enforcement_mode=current_mode(),
                    )
                except Exception:  # noqa: BLE001
                    # record_rejection never raises, but defend the
                    # reject decision against any future change.
                    logger.error(
                        "epcis_rejection_audit_inline_error",
                    )
                    raise HTTPException(status_code=503, detail="Rejection audit storage is unavailable") from None

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
        product_description=_epcis_product_description(event, kde_map),
        quantity=prepared["quantity_value"],
        # ``quantity`` comes only from a quantityList element here, and EPCIS
        # CBV defines such an element without ``uom`` as a count of
        # instances: ``each`` is the standard's meaning, and it is what the
        # canonical row stores for the same event (the old ``"units"`` made
        # the two rows disagree).
        unit_of_measure=normalized.get("unit_of_measure") or "each",
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
    #
    # #2499 / #2534: this used to run in a ``daemon=True`` worker thread
    # joined with a 5 s timeout (``CANONICAL_DUAL_WRITE_TIMEOUT_S``). That
    # was unsafe on two counts:
    #
    #   * #2499 — the worker issued SQL on the SAME caller-managed
    #     ``db_session`` that the request thread then committed. A
    #     SQLAlchemy Session and its psycopg connection are NOT
    #     thread-safe, so on the timeout path (worker still alive) the
    #     main thread's ``commit()`` raced the worker's ``execute()`` on
    #     one connection — psycopg "another operation in progress",
    #     corrupted transaction state, or a canonical/legacy split.
    #   * #2534 — any worker exception was downgraded to a
    #     ``logger.warning`` and the event was still reported persisted
    #     (HTTP 201) even though the canonical ``traceability_events`` row
    #     and its rule rows silently never landed.
    #
    # Fix: run the canonical write SYNCHRONOUSLY on the request thread,
    # inside the same transaction the caller commits. One connection,
    # used sequentially — no cross-thread sharing. A failure now poisons
    # the session so the caller's ``db_session.commit()`` (single path)
    # or the atomic batch loop fails loudly: the whole event rolls back
    # (legacy CTE row included → "both tables or neither") and the client
    # sees a 5xx instead of a false 201. ``skip_chain_write=True`` is
    # retained: the legacy CTE write above owns the hash chain on this
    # path, so the canonical store must not also grow it.
    if not result.idempotent:
        from shared.canonical_event import normalize_epcis_event  # noqa: PLC0415
        from shared.canonical_persistence import CanonicalEventStore  # noqa: PLC0415
        from shared.rules_engine import RulesEngine  # noqa: PLC0415

        _canonical = normalize_epcis_event(event, tenant_id)
        _store = CanonicalEventStore(db_session, dual_write=False, skip_chain_write=True)
        _store.set_tenant_context(tenant_id)
        _store.persist_event(_canonical)
        _engine = RulesEngine(db_session)
        if _preeval_summary is not None and _preeval_summary.results:
            # Fast path: pre-eval already evaluated this event under
            # enforcement. Persist the pre-computed results directly
            # via persist_summary instead of re-running every rule.
            # Anchor the rows on the canonical event_id we just
            # persisted — pre-eval generated its own canonical with
            # a different ID, so use the new one.
            _engine.persist_summary(
                _preeval_summary,
                tenant_id=tenant_id,
                event_id=str(_canonical.event_id),
            )
        else:
            # Fallback: pre-eval skipped (OFF mode or pre-eval errored)
            # OR returned a no-verdict summary with no results to
            # persist. Re-evaluate with persist=True — bit-for-bit
            # identical to pre-Phase-0 EPCIS behavior on the default
            # production path.
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
        if exc.status_code == 422 and detail.get("error") == "fsma_validation_failed" and _fsma_strict_mode():
            logger.warning("epcis_single_event_refused_unvalidated tenant=%s", tenant_id)
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
        payload, status_code = _persist_prepared_event_in_session(db_session, tenant_id, prepared)
        db_session.commit()
        return payload, status_code
    except Exception:
        db_session.rollback()
        raise
    finally:
        db_session.close()


def _ingest_batch_events_db_atomic(tenant_id: str, events: list[dict]) -> list[tuple[dict, int]]:
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
            payload, status_code = _persist_prepared_event_in_session(db_session, tenant_id, prepared)
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
            logger.warning("epcis_ingest_refused_unvalidated tenant=%s", tenant_id)
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
        # An event whose CTE type is not supported is a client-actionable
        # REJECTION, not a server fault — but every other ValueError below
        # falls through to a bare ``raise`` and surfaces as an unhandled 500.
        # Two distinct paths produce one:
        #   * the legacy write, where ``_validate_event_type`` refuses a
        #     non-CTE ``event_type`` (FSMA ``growing`` / CBV ``planting`` are
        #     real bizSteps that are simply not among the 7 s1.1310 CTEs), and
        #   * the canonical dual-write, which raises ``UnmappedBizStepError``
        #     (a ValueError subclass) for the same inputs (#2815).
        # The canonical path runs unguarded whenever the event is not
        # idempotent, so this is reachable under the DEFAULT
        # ``RULES_ENGINE_ENFORCE=off`` too, not only under enforcement.
        if type(exc).__name__ == "UnmappedBizStepError" or ("is not a recognized FSMA 204 CTE type" in str(exc)):
            logger.warning(
                "epcis_ingest_refused_unsupported_cte_type tenant=%s error=%s",
                tenant_id,
                str(exc),
            )
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "unsupported_cte_type",
                    "message": str(exc),
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
