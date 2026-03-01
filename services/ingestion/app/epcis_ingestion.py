"""EPCIS 2.0 ingestion and validation router.

Accepts EPCIS event payloads, validates required fields, normalizes events to
CTE-like records, and exposes retrieval/export endpoints.
"""

from __future__ import annotations

import json
import logging
import os
from hashlib import sha256
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.webhook_router import _verify_api_key

logger = logging.getLogger("epcis-ingestion")

router = APIRouter(prefix="/api/v1/epcis", tags=["EPCIS 2.0 Ingestion"])


_epcis_store: dict[str, dict] = {}
_epcis_idempotency_index: dict[str, str] = {}


def _publish_sync_event(event_name: str, payload: dict) -> None:
    """Publish a graph-sync event to Redis when configured."""
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return

    try:
        import redis

        client = redis.from_url(redis_url)
        message = {"event": event_name, "data": payload}
        client.rpush("neo4j-sync", json.dumps(message))
    except Exception as exc:
        logger.warning("epcis_sync_publish_failed event=%s error=%s", event_name, str(exc))


class BatchIngestRequest(BaseModel):
    """Batch EPCIS ingest request."""

    events: list[dict] = Field(default_factory=list)


def _extract_lot_data(ilmd: dict | None) -> tuple[str, str]:
    if not ilmd:
        return "", ""
    lot_code = str(ilmd.get("cbvmda:lotNumber") or ilmd.get("lotNumber") or "")
    tlc = str(ilmd.get("fsma:traceabilityLotCode") or lot_code)
    return lot_code, tlc


def _extract_location_id(payload: dict, key: str) -> str:
    raw = payload.get(key, {})
    if isinstance(raw, dict):
        value = raw.get("id")
        return str(value) if value else ""
    return ""


def _extract_party_id(payload: dict, key: str, nested_key: str) -> str:
    items = payload.get(key, [])
    if not isinstance(items, list) or not items:
        return ""
    first = items[0] if isinstance(items[0], dict) else {}
    value = first.get(nested_key)
    return str(value) if value else ""


def _validate_epcis(event: dict) -> list[str]:
    errors: list[str] = []
    required = ["type", "eventTime", "action", "bizStep"]
    for field in required:
        if not event.get(field):
            errors.append(f"Missing required EPCIS field '{field}'")

    if event.get("type") not in {"ObjectEvent", "AggregationEvent", "TransactionEvent", "TransformationEvent"}:
        errors.append("Unsupported EPCIS event type")

    lot_code, tlc = _extract_lot_data(event.get("ilmd") or event.get("extension", {}).get("ilmd"))
    if not tlc and not lot_code:
        errors.append("Missing traceability lot code (fsma:traceabilityLotCode or cbvmda:lotNumber)")

    return errors


def _event_idempotency_key(event: dict) -> str:
    explicit = event.get("eventID")
    if explicit:
        return str(explicit)
    normalized = json.dumps(event, sort_keys=True, separators=(",", ":"))
    return sha256(normalized.encode("utf-8")).hexdigest()


def _normalize_epcis_to_cte(event: dict) -> dict:
    event_type_map = {
        "urn:epcglobal:cbv:bizstep:receiving": "receiving",
        "urn:epcglobal:cbv:bizstep:shipping": "shipping",
        "urn:epcglobal:cbv:bizstep:transforming": "transforming",
        "urn:epcglobal:cbv:bizstep:commissioning": "creating",
        "urn:epcglobal:cbv:bizstep:packing": "initial_packing",
    }

    ilmd = event.get("ilmd") or event.get("extension", {}).get("ilmd") or {}
    lot_code, tlc = _extract_lot_data(ilmd)
    epc_list = event.get("epcList", [])
    product_id = epc_list[0] if isinstance(epc_list, list) and epc_list else None
    biz_step = str(event.get("bizStep") or "")

    quantity = None
    unit = None
    quantity_list = event.get("extension", {}).get("quantityList", [])
    if quantity_list and isinstance(quantity_list, list) and isinstance(quantity_list[0], dict):
        quantity = quantity_list[0].get("quantity")
        unit = quantity_list[0].get("uom")

    normalized = {
        "event_type": event_type_map.get(biz_step, "receiving"),
        "epcis_event_type": event.get("type"),
        "epcis_action": event.get("action"),
        "epcis_biz_step": event.get("bizStep"),
        "event_time": event.get("eventTime"),
        "event_timezone": event.get("eventTimeZoneOffset", "+00:00"),
        "lot_code": lot_code,
        "tlc": tlc,
        "product_id": product_id,
        "location_id": _extract_location_id(event, "bizLocation") or _extract_location_id(event, "readPoint"),
        "source_location_id": _extract_party_id(event, "sourceList", "source"),
        "dest_location_id": _extract_party_id(event, "destinationList", "destination"),
        "quantity": quantity,
        "unit_of_measure": unit,
        "data_source": "api",
        "validation_status": "valid",
    }
    return normalized


def _extract_kdes(event: dict) -> list[dict]:
    ilmd = event.get("ilmd") or event.get("extension", {}).get("ilmd") or {}
    kdes: list[dict] = []
    for key, value in ilmd.items():
        if value is None:
            continue
        kde_name = key.split(":", 1)[-1]
        kdes.append(
            {
                "kde_type": kde_name,
                "kde_value": str(value),
                "required": kde_name in {"traceabilityLotCode", "lotNumber"},
            }
        )
    return kdes


def _compliance_alerts(normalized: dict, kdes: list[dict]) -> list[dict]:
    alerts: list[dict] = []

    if not normalized.get("tlc"):
        alerts.append(
            {
                "severity": "critical",
                "alert_type": "missing_kde",
                "message": "Traceability lot code is missing",
            }
        )

    if normalized.get("event_type") in {"shipping", "receiving"} and (
        not normalized.get("source_location_id") or not normalized.get("dest_location_id")
    ):
        alerts.append(
            {
                "severity": "warning",
                "alert_type": "incomplete_route",
                "message": "Shipping/receiving event is missing source or destination identifiers",
            }
        )

    if not kdes:
        alerts.append(
            {
                "severity": "warning",
                "alert_type": "missing_kde",
                "message": "No ILMD KDE fields were provided",
            }
        )

    return alerts


def _ingest_single_event(event: dict) -> tuple[dict, int]:
    errors = _validate_epcis(event)
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    idempotency_key = _event_idempotency_key(event)
    existing_event_id = _epcis_idempotency_index.get(idempotency_key)
    if existing_event_id:
        existing_record = _epcis_store[existing_event_id]
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

    stored = {
        "id": event_id,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "idempotency_key": idempotency_key,
        "epcis_document": event,
        "normalized_cte": normalized,
        "kdes": kdes,
        "alerts": alerts,
    }
    _epcis_store[event_id] = stored

    _publish_sync_event(
        "cte.created",
        {
            "cte": {
                "id": event_id,
                **normalized,
            }
        },
    )

    required_count = sum(1 for kde in kdes if kde["required"]) or 1
    populated_required = sum(1 for kde in kdes if kde["required"] and kde["kde_value"])
    kde_completeness = populated_required / required_count
    stored["kde_completeness"] = round(kde_completeness, 2)
    _epcis_idempotency_index[idempotency_key] = event_id

    logger.info(
        "epcis_event_ingested event_id=%s event_type=%s tlc=%s",
        event_id,
        normalized["event_type"],
        normalized["tlc"],
    )

    return (
        {
            "status": 201,
            "cte_id": event_id,
            "validation_status": normalized["validation_status"],
            "kde_completeness": round(kde_completeness, 2),
            "alerts": alerts,
            "idempotent": False,
        },
        201,
    )


@router.post("/events", status_code=201, summary="Ingest EPCIS 2.0 event")
async def ingest_epcis_event(
    event: dict,
    _: None = Depends(_verify_api_key),
):
    payload, status_code = _ingest_single_event(event)
    return JSONResponse(content=payload, status_code=status_code)


@router.post("/events/batch", summary="Batch ingest EPCIS events")
async def ingest_epcis_batch(
    request: BatchIngestRequest,
    _: None = Depends(_verify_api_key),
):
    if not request.events:
        raise HTTPException(status_code=400, detail="Batch ingest requires at least one event")

    created: list[dict] = []
    failed: list[dict] = []
    processed: list[dict] = []

    for idx, event in enumerate(request.events):
        try:
            payload, status_code = _ingest_single_event(event)
            processed.append({"index": idx, "status_code": status_code, **payload})
            if status_code == 201:
                created.append(payload)
        except HTTPException as exc:
            failed.append({"index": idx, "detail": exc.detail})

    response_payload = {
        "total": len(request.events),
        "created": len(created),
        "failed": len(failed),
        "results": processed,
        "errors": failed,
    }

    successful = len(processed)
    if failed and successful:
        return JSONResponse(content=response_payload, status_code=207)
    if failed and not successful:
        return JSONResponse(content=response_payload, status_code=400)
    return JSONResponse(content=response_payload, status_code=201)


@router.get("/events/{event_id}", summary="Get EPCIS event by id")
async def get_epcis_event(
    event_id: str,
    _: None = Depends(_verify_api_key),
):
    event = _epcis_store.get(event_id)
    if not event:
        raise HTTPException(status_code=404, detail=f"EPCIS event '{event_id}' not found")
    return event


@router.get("/export", summary="Export all ingested events as EPCIS 2.0")
async def export_epcis_events(
    start_date: str | None = Query(default=None, description="Filter events at or after this ISO timestamp"),
    end_date: str | None = Query(default=None, description="Filter events before this ISO timestamp"),
    product_id: str | None = Query(default=None, description="Filter by EPC product identifier"),
    _: None = Depends(_verify_api_key),
):
    def _parse_iso(value: str | None) -> datetime | None:
        if not value:
            return None
        parsed = value.replace("Z", "+00:00")
        return datetime.fromisoformat(parsed)

    start_dt = _parse_iso(start_date)
    end_dt = _parse_iso(end_date)

    filtered_records: list[dict] = []
    for entry in _epcis_store.values():
        normalized = entry.get("normalized_cte", {})
        event_time = normalized.get("event_time")
        if event_time:
            event_dt = _parse_iso(str(event_time))
            if start_dt and event_dt and event_dt < start_dt:
                continue
            if end_dt and event_dt and event_dt >= end_dt:
                continue
        if product_id and normalized.get("product_id") != product_id:
            continue
        filtered_records.append(entry)

    events = [entry["epcis_document"] for entry in filtered_records]
    return {
        "@context": ["https://ref.gs1.org/standards/epcis/2.0.0/epcis-context.jsonld"],
        "type": "EPCISDocument",
        "schemaVersion": "2.0",
        "creationDate": datetime.now(timezone.utc).isoformat(),
        "epcisBody": {"eventList": events},
        "metadata": {
            "events_count": len(events),
            "source": "regengine-epcis-ingestion",
            "filters": {
                "start_date": start_date,
                "end_date": end_date,
                "product_id": product_id,
            },
        },
    }


@router.post("/validate", summary="Validate EPCIS event payload")
async def validate_epcis_event(
    event: dict,
    _: None = Depends(_verify_api_key),
):
    errors = _validate_epcis(event)
    normalized = _normalize_epcis_to_cte(event) if not errors else None
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "normalized": normalized,
    }
