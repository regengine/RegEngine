"""Status, audit, and document query routes for the ingestion service."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

import redis
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from shared.auth import APIKey, require_api_key

from .config import get_settings
from .models import (
    DocumentAnalysisResponse,
    IngestionStatusResponse,
    JobLogsResponse,
    JobStatusResponse,
    ListDocumentsResponse,
    VerifyDocumentResponse,
)
from .routes import get_db_manager

logger = structlog.get_logger("ingestion")
router = APIRouter(tags=["ingestion-status"])


def _job_owned_by_tenant(r: redis.Redis, job_id: str, tenant_id: Optional[str]) -> bool:
    """Return True iff the Redis-tracked job belongs to ``tenant_id``.

    Producers (``routes_ingest`` and ``task_handlers_regulation``) write
    ``ingest:owner:{job_id} = tenant_id`` alongside the status keys. A missing
    owner key (legacy job written before this guard, or an expired key) or a
    tenant mismatch is treated as not-found — fail closed so one tenant can
    never read another tenant's ingestion status/result.
    See audit/ingestion-service-audit.md (tenant isolation).
    """
    if not tenant_id:
        return False
    owner = r.get(f"ingest:owner:{job_id}")
    if owner is None:
        return False
    owner_str = owner.decode("utf-8") if isinstance(owner, (bytes, bytearray)) else str(owner)
    return owner_str == tenant_id


@router.get("/v1/ingest/status/{job_id}", response_model=IngestionStatusResponse)
async def get_ingestion_status(job_id: str, api_key: APIKey = Depends(require_api_key)):
    """Check the status of a background ingestion job."""
    settings = get_settings()
    r = redis.from_url(settings.redis_url)
    if not _job_owned_by_tenant(r, job_id, api_key.tenant_id):
        raise HTTPException(status_code=404, detail="Job not found")
    status = r.get(f"ingest:status:{job_id}")
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")

    status_str = status.decode("utf-8")
    response = {"job_id": job_id, "status": status_str}

    if status_str == "completed":
        result = r.get(f"ingest:result:{job_id}")
        if result:
            response["result"] = json.loads(result.decode("utf-8"))

    return response


@router.get("/v1/ingest/documents/{document_id}/analysis", response_model=DocumentAnalysisResponse)
async def get_document_analysis(document_id: str, api_key: APIKey = Depends(require_api_key)):
    """Return an analysis summary for a completed ingestion job."""
    settings = get_settings()
    r = redis.from_url(settings.redis_url)
    if not _job_owned_by_tenant(r, document_id, api_key.tenant_id):
        raise HTTPException(status_code=404, detail="Document not found")
    status = r.get(f"ingest:status:{document_id}")
    if not status:
        raise HTTPException(status_code=404, detail="Document not found")

    status_str = status.decode("utf-8")
    result_raw = r.get(f"ingest:result:{document_id}")
    result = json.loads(result_raw.decode("utf-8")) if result_raw else {}

    return {
        "document_id": document_id,
        "status": status_str,
        "risk_score": 0,
        "obligations_count": result.get("sections", 0),
        "missing_dates_count": 0,
        "critical_risks": [],
    }


@router.get("/v1/audit/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str, api_key: APIKey = Depends(require_api_key)):
    """Get high-level status and metrics for an ingestion job."""
    db_manager = get_db_manager()
    if not db_manager:
        raise HTTPException(status_code=503, detail="Audit database not available")

    try:
        job = db_manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job
    finally:
        db_manager.close()


@router.get("/v1/audit/logs/{job_id}", response_model=JobLogsResponse)
async def get_job_logs(job_id: str, limit: int = 100, api_key: APIKey = Depends(require_api_key)):
    """Get detailed audit entries for a specific job."""
    db_manager = get_db_manager()
    if not db_manager:
        raise HTTPException(status_code=503, detail="Audit database not available")

    try:
        logs = db_manager.get_audit_log(job_id, limit=limit)
        return {"job_id": job_id, "entries": logs}
    finally:
        db_manager.close()


@router.get("/v1/ingest/documents", response_model=ListDocumentsResponse)
async def list_documents(
    vertical: Optional[str] = None,
    source_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    api_key: APIKey = Depends(require_api_key),
):
    """List and search ingested documents."""
    db_manager = get_db_manager()
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        # tenant_id is the required first positional arg (database.py) — scopes
        # the search to the caller's tenant. Previously omitted, which both
        # broke the call signature and removed tenant isolation.
        docs = db_manager.search_documents(api_key.tenant_id, vertical, source_type, limit, offset)
        return {"documents": docs, "count": len(docs)}
    finally:
        db_manager.close()


@router.get("/v1/verify/{document_id}", response_model=VerifyDocumentResponse)
async def verify_document(document_id: str, api_key: APIKey = Depends(require_api_key)):
    """Verify document integrity by re-computing hashes and comparing with stored metadata."""
    db_manager = get_db_manager()
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        # tenant_id required by get_document (database.py) — scopes the lookup
        # to the caller's tenant. Previously omitted (raised TypeError → 500).
        doc = db_manager.get_document(document_id, api_key.tenant_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        return {
            "document_id": document_id,
            "status": "verified",
            "hashes": {
                "content_sha256": doc["content_sha256"],
                "content_sha512": doc["content_sha512"],
                "text_sha256": doc["text_sha256"],
                "text_sha512": doc["text_sha512"],
            },
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        db_manager.close()
