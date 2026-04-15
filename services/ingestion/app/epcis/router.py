"""EPCIS 2.0 FastAPI route handlers.

Defines all HTTP endpoints for EPCIS event ingestion, retrieval,
export, validation, XML ingestion, and batch processing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.shared.tenant_resolution import resolve_tenant_id
from app.webhook_compat import _verify_api_key

from services.ingestion.app.epcis.normalization import (
    _normalize_epcis_to_cte,
)
from services.ingestion.app.epcis.persistence import (
    _allow_in_memory_fallback,
    _epcis_store,
    _fetch_event_from_db,
    _ingest_single_event,
    _list_events_from_db,
)
from services.ingestion.app.epcis.validation import (
    _validate_epcis,
)
from services.ingestion.app.epcis.xml_parser import (
    _is_xml_content,
    _parse_epcis_xml,
)

router = APIRouter(prefix="/api/v1/epcis", tags=["EPCIS 2.0 Ingestion"])

_resolve_tenant_id = resolve_tenant_id


class BatchIngestRequest(BaseModel):
    events: list[dict] = Field(default_factory=list)


@router.post("/events", status_code=201, summary="Ingest EPCIS 2.0 event")
async def ingest_epcis_event(
    event: dict,
    tenant_id: Optional[str] = Query(default=None, description="Optional tenant override"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    x_regengine_api_key: Optional[str] = Header(default=None, alias="X-RegEngine-API-Key"),
    _: None = Depends(_verify_api_key),
):
    resolved_tenant = _resolve_tenant_id(tenant_id, x_tenant_id, x_regengine_api_key)
    if not resolved_tenant:
        raise HTTPException(status_code=400, detail="Tenant context required")

    payload, status_code = _ingest_single_event(resolved_tenant, event)
    return JSONResponse(content=payload, status_code=status_code)


@router.post("/events/batch", summary="Batch ingest EPCIS events")
async def ingest_epcis_batch(
    request: BatchIngestRequest,
    tenant_id: Optional[str] = Query(default=None, description="Optional tenant override"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    x_regengine_api_key: Optional[str] = Header(default=None, alias="X-RegEngine-API-Key"),
    _: None = Depends(_verify_api_key),
):
    if not request.events:
        raise HTTPException(status_code=400, detail="Batch ingest requires at least one event")

    resolved_tenant = _resolve_tenant_id(tenant_id, x_tenant_id, x_regengine_api_key)
    if not resolved_tenant:
        raise HTTPException(status_code=400, detail="Tenant context required")

    created: list[dict] = []
    failed: list[dict] = []
    processed: list[dict] = []

    for idx, event in enumerate(request.events):
        try:
            payload, status_code = _ingest_single_event(resolved_tenant, event)
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
    tenant_id: Optional[str] = Query(default=None, description="Optional tenant override"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    x_regengine_api_key: Optional[str] = Header(default=None, alias="X-RegEngine-API-Key"),
    _: None = Depends(_verify_api_key),
):
    resolved_tenant = _resolve_tenant_id(tenant_id, x_tenant_id, x_regengine_api_key)
    if not resolved_tenant:
        raise HTTPException(status_code=400, detail="Tenant context required")

    event = None
    try:
        event = _fetch_event_from_db(resolved_tenant, event_id)
    except Exception as exc:
        if not _allow_in_memory_fallback():
            raise HTTPException(status_code=503, detail="Database unavailable") from exc
        import logging
        logger = logging.getLogger("epcis-ingestion")
        logger.warning("epcis_get_db_failed_using_fallback error=%s", str(exc))

    if event is None and _allow_in_memory_fallback():
        event = _epcis_store.get(event_id)

    if not event:
        raise HTTPException(status_code=404, detail=f"EPCIS event '{event_id}' not found")
    return event


@router.get("/export", summary="Export all ingested events as EPCIS 2.0")
async def export_epcis_events(
    start_date: str | None = Query(default=None, description="Filter events at or after this ISO timestamp"),
    end_date: str | None = Query(default=None, description="Filter events before this ISO timestamp"),
    product_id: str | None = Query(default=None, description="Filter by EPC product identifier"),
    tenant_id: Optional[str] = Query(default=None, description="Optional tenant override"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    x_regengine_api_key: Optional[str] = Header(default=None, alias="X-RegEngine-API-Key"),
    _: None = Depends(_verify_api_key),
):
    resolved_tenant = _resolve_tenant_id(tenant_id, x_tenant_id, x_regengine_api_key)
    if not resolved_tenant:
        raise HTTPException(status_code=400, detail="Tenant context required")

    events: list[dict] = []
    try:
        events = _list_events_from_db(resolved_tenant, start_date, end_date, product_id)
    except Exception as exc:
        if not _allow_in_memory_fallback():
            raise HTTPException(status_code=503, detail="Database unavailable") from exc
        import logging
        logger = logging.getLogger("epcis-ingestion")
        logger.warning("epcis_export_db_failed_using_fallback error=%s", str(exc))

    if not events and _allow_in_memory_fallback():
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
            "source": "regengine-epcis-ingestion",
            "event_count": len(events),
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
        "valid": not errors,
        "errors": errors,
        "normalized_cte": normalized,
    }


@router.post("/events/xml", status_code=201, summary="Ingest EPCIS 2.0 XML document")
async def ingest_epcis_xml(
    request: Request,
    tenant_id: Optional[str] = Query(default=None, description="Optional tenant override"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    x_regengine_api_key: Optional[str] = Header(default=None, alias="X-RegEngine-API-Key"),
    _: None = Depends(_verify_api_key),
):
    """Ingest an EPCIS 2.0 XML document containing one or more events.

    Parses the XML, extracts ObjectEvent, AggregationEvent, TransactionEvent,
    and TransformationEvent elements, then ingests each through the standard
    EPCIS pipeline with FSMAEvent validation.
    """
    resolved_tenant = _resolve_tenant_id(tenant_id, x_tenant_id, x_regengine_api_key)
    if not resolved_tenant:
        raise HTTPException(status_code=400, detail="Tenant context required")

    raw_body = await request.body()
    if not raw_body:
        raise HTTPException(status_code=400, detail="Empty XML payload")

    if not _is_xml_content(raw_body):
        raise HTTPException(status_code=400, detail="Payload does not appear to be XML")

    events = _parse_epcis_xml(raw_body)
    if not events:
        raise HTTPException(
            status_code=422,
            detail="No EPCIS events found in XML document",
        )

    created: list[dict] = []
    failed: list[dict] = []
    processed: list[dict] = []

    for idx, event in enumerate(events):
        try:
            payload, status_code = _ingest_single_event(resolved_tenant, event)
            processed.append({"index": idx, "status_code": status_code, **payload})
            if status_code == 201:
                created.append(payload)
        except HTTPException as exc:
            failed.append({"index": idx, "detail": exc.detail})

    response_payload = {
        "total": len(events),
        "created": len(created),
        "failed": len(failed),
        "results": processed,
        "errors": failed,
        "format": "EPCIS_XML_2.0",
    }

    successful = len(processed)
    if failed and successful:
        return JSONResponse(content=response_payload, status_code=207)
    if failed and not successful:
        return JSONResponse(content=response_payload, status_code=400)
    return JSONResponse(content=response_payload, status_code=201)
