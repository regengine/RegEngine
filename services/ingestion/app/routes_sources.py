"""Federal source ingestion routes (Federal Register, eCFR, openFDA)."""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException

from shared.auth import APIKey, require_api_key
from shared.database import SessionLocal
from shared.task_queue import enqueue_task
from .models import (
    FederalRegisterIngestRequest, ECFRIngestRequest, FDAIngestRequest,
    FederalRegisterResponse, ECFRResponse, FDAResponse, ListSourcesResponse
)

logger = structlog.get_logger("ingestion")
router = APIRouter(tags=["ingestion-sources"])


@router.post("/v1/ingest/federal-register", status_code=202, response_model=FederalRegisterResponse)
async def ingest_federal_register(
    payload: FederalRegisterIngestRequest,
    api_key: APIKey = Depends(require_api_key),
):
    """Ingest documents from Federal Register API."""
    allowed = set(api_key.allowed_jurisdictions or [])
    if "US" not in allowed:
        raise HTTPException(status_code=403, detail="Access to federal regulations requires entitlement")

    job_id = str(uuid.uuid4())
    db = SessionLocal()
    try:
        enqueue_task(
            db,
            task_type="federal_register_ingest",
            payload={
                "vertical": payload.vertical,
                "tenant_id": api_key.tenant_id,
                "job_id": job_id,
                "max_documents": payload.max_documents,
                "date_from": payload.date_from.isoformat() if payload.date_from else None,
                "agencies": payload.agencies,
            },
            tenant_id=api_key.tenant_id,
        )
        db.commit()
    finally:
        db.close()

    return {"status": "accepted", "job_id": job_id, "message": "Federal Register ingestion started"}


@router.post("/v1/ingest/ecfr", status_code=202, response_model=ECFRResponse)
async def ingest_ecfr(
    payload: ECFRIngestRequest,
    api_key: APIKey = Depends(require_api_key),
):
    """Ingest documents from eCFR API."""
    allowed = set(api_key.allowed_jurisdictions or [])
    if "US" not in allowed:
        raise HTTPException(status_code=403, detail="Access to federal regulations requires entitlement")

    job_id = str(uuid.uuid4())
    db = SessionLocal()
    try:
        enqueue_task(
            db,
            task_type="ecfr_ingest",
            payload={
                "vertical": payload.vertical,
                "tenant_id": api_key.tenant_id,
                "job_id": job_id,
                "cfr_title": payload.cfr_title,
                "cfr_part": payload.cfr_part,
            },
            tenant_id=api_key.tenant_id,
        )
        db.commit()
    finally:
        db.close()

    return {"status": "accepted", "job_id": job_id, "message": "eCFR ingestion started"}


@router.post("/v1/ingest/fda", status_code=202, response_model=FDAResponse)
async def ingest_fda(
    payload: FDAIngestRequest,
    api_key: APIKey = Depends(require_api_key),
):
    """Ingest documents from openFDA API."""
    allowed = set(api_key.allowed_jurisdictions or [])
    if "US" not in allowed:
        raise HTTPException(status_code=403, detail="Access to federal regulations requires entitlement")

    job_id = str(uuid.uuid4())
    db = SessionLocal()
    try:
        enqueue_task(
            db,
            task_type="fda_ingest",
            payload={
                "vertical": payload.vertical,
                "tenant_id": api_key.tenant_id,
                "job_id": job_id,
                "max_documents": payload.max_documents,
            },
            tenant_id=api_key.tenant_id,
        )
        db.commit()
    finally:
        db.close()

    return {"status": "accepted", "job_id": job_id, "message": "FDA ingestion started"}


@router.get("/v1/ingest/sources", response_model=ListSourcesResponse)
async def list_sources(api_key: APIKey = Depends(require_api_key)):
    """List available source adapters and their capabilities."""
    return {
        "sources": [
            {
                "id": "federal_register",
                "name": "Federal Register",
                "type": "api",
                "jurisdiction": "US",
                "capabilities": ["date_filter", "agency_filter", "bulk_fetch"],
            },
            {
                "id": "ecfr",
                "name": "eCFR (Code of Federal Regulations)",
                "type": "api",
                "jurisdiction": "US",
                "capabilities": ["title_part_filter"],
            },
            {
                "id": "fda",
                "name": "openFDA Warning Letters",
                "type": "api",
                "jurisdiction": "US",
                "capabilities": ["bulk_fetch"],
            },
        ]
    }
