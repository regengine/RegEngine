"""API routes for the admin service."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, status, Request, Query
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field
import html

# Centralised path resolution
from shared.paths import ensure_shared_importable
ensure_shared_importable()

from shared.auth import get_key_store
from shared.api_key_store import DatabaseAPIKeyStore

from .config import get_settings
from .metrics import get_hallucination_tracker
from .review_consumer import get_consumer_health

# Health/metrics router at root level (operational endpoints)
router = APIRouter()

# Versioned API router for admin endpoints
v1_router = APIRouter(prefix="/v1", tags=["v1"])

logger = structlog.get_logger("admin")
REVIEW_ITEM_NOT_FOUND = "Review item not found"


class CreateKeyRequest(BaseModel):
    """Request model for creating an API key."""

    name: str
    tenant_id: Optional[str] = None  # UUID of tenant (for multi-tenancy)
    rate_limit_per_minute: int = 60
    expires_at: Optional[datetime] = None
    scopes: list[str] = ["read", "ingest"]


class CreateKeyResponse(BaseModel):
    """Response model for API key creation."""

    api_key: str
    key_id: str
    name: str
    tenant_id: Optional[str] = None
    created_at: datetime
    expires_at: Optional[datetime]
    rate_limit_per_minute: int
    scopes: list[str]
    warning: str = "Store this key securely. It will not be shown again."


class APIKeyInfo(BaseModel):
    """API key information (without the raw key)."""

    key_id: str
    name: str
    tenant_id: Optional[str] = None
    created_at: datetime
    expires_at: Optional[datetime]
    rate_limit_per_minute: int
    enabled: bool
    scopes: list[str]


class HallucinationCreateRequest(BaseModel):
    """Payload for recording a hallucination that requires review."""

    tenant_id: Optional[str] = Field(None, description="Tenant UUID that owns the document")
    document_id: str
    doc_hash: str
    extractor: str
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    extraction: dict
    provenance: Optional[dict] = None
    text_raw: Optional[str] = None


class ReviewActionRequest(BaseModel):
    """Reviewer action payload for approve/reject."""

    reviewer_id: str
    notes: Optional[str] = None


class ReviewItemResponse(BaseModel):
    """Response model for review queue items."""

    review_id: str
    tenant_id: Optional[str]
    document_id: Optional[str]
    doc_hash: str
    extractor: Optional[str]
    confidence_score: float
    status: str
    created_at: datetime
    updated_at: Optional[datetime]
    reviewer_id: Optional[str]
    extraction: dict
    provenance: Optional[dict]
    text_raw: Optional[str]


class TenantCreateRequest(BaseModel):
    """Request to create a new tenant for onboarding."""

    name: str = Field(..., min_length=1, max_length=255)


class TenantCreateResponse(BaseModel):
    """Response for tenant creation."""

    tenant_id: str
    name: str
    status: str = "active"


def verify_admin_key(
    request: Request,
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key"),
) -> bool:
    """Verify the admin master key.
    
    SECURITY NOTE: The hardcoded 'admin' key bypass has been removed for production safety.
    For local testing, use ADMIN_MASTER_KEY from .env or shared/auth.py with AUTH_TEST_BYPASS_TOKEN.
    """
    settings = get_settings()
    
    if not x_admin_key or x_admin_key != settings.admin_master_key:
        logger.warning(
            "unauthorized_admin_access_attempt",
            key_prefix=x_admin_key[:4] if x_admin_key else "None",
            source_ip=request.client.host if request.client else "unknown",
            path=request.url.path,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
        )
    return True



def _tracker():
    return get_hallucination_tracker()


@router.get("/health")
async def health():
    """Deep health check endpoint with dependency verification."""
    import os
    from fastapi.responses import JSONResponse
    from shared.health import HealthCheck

    checker = HealthCheck(service_name="admin-api")

    # PostgreSQL check
    admin_db_url = os.getenv("DATABASE_URL") or os.getenv("ADMIN_DATABASE_URL")
    if admin_db_url:
        async def check_postgres():
            try:
                # Basic connection check
                import psycopg
                # Robustly strip SQLAlchemy-style dialect prefixes for direct psycopg connection
                conn_info = admin_db_url
                for prefix in ["postgresql+psycopg://", "postgresql+asyncpg://", "postgresql+psycopg2://"]:
                    if conn_info.startswith(prefix):
                        conn_info = conn_info.replace(prefix, "postgresql://")
                        break
                
                async with await psycopg.AsyncConnection.connect(conn_info) as conn:
                    await conn.execute("SELECT 1")
                return {"status": "healthy"}
            except Exception as e:
                return {"status": "unhealthy", "error": str(e)}
        
        checker.add_dependency("postgresql", check_postgres)

    # Redis check
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        async def check_redis():
            try:
                import redis.asyncio as redis
                r = redis.from_url(redis_url)
                await r.ping()
                return {"status": "healthy"}
            except Exception as e:
                return {"status": "unhealthy", "error": str(e)}
        
        checker.add_dependency("redis", check_redis)

    result = await checker.check()
    sc = 200 if result.get("status") == "healthy" else 503
    return JSONResponse(content=result, status_code=sc)


@router.get("/ready")
async def readiness():
    """Readiness probe for k8s orchestration."""
    return {"status": "ready", "service": "admin-api"}


@router.get("/health/consumer")
def consumer_health():
    """Health check endpoint for the Kafka review consumer."""
    from fastapi.responses import JSONResponse
    health_info = get_consumer_health()
    status_code = 200 if health_info.get("healthy") else 503
    return JSONResponse(content=health_info, status_code=status_code)


@router.get("/metrics")
def metrics():
    """Prometheus metrics endpoint."""
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@v1_router.post("/admin/keys", response_model=CreateKeyResponse)
async def create_api_key(
    request: CreateKeyRequest,
    _: bool = Depends(verify_admin_key),
):
    """Create a new API key (requires admin authentication)."""
    key_store = get_key_store()

    if isinstance(key_store, DatabaseAPIKeyStore):
        # Async DB store
        new_key = await key_store.create_key(
            name=request.name,
            tenant_id=request.tenant_id,
            rate_limit_per_minute=request.rate_limit_per_minute,
            expires_at=request.expires_at,
            scopes=request.scopes,
        )
        
        logger.info(
            "api_key_created_via_admin",
            key_id=new_key.key_id,
            name=request.name,
            tenant_id=request.tenant_id,
        )

        return CreateKeyResponse(
            api_key=new_key.raw_key,
            key_id=new_key.key_id,
            name=new_key.name,
            tenant_id=new_key.tenant_id,
            created_at=new_key.created_at,
            expires_at=new_key.expires_at,
            rate_limit_per_minute=new_key.rate_limit_per_minute,
            scopes=new_key.scopes,
        )
    else:
        # Sync in-memory store
        raw_key, api_key = key_store.create_key(
            name=request.name,
            tenant_id=request.tenant_id,
            rate_limit_per_minute=request.rate_limit_per_minute,
            expires_at=request.expires_at,
            scopes=request.scopes,
        )

        logger.info(
            "api_key_created_via_admin",
            key_id=api_key.key_id,
            name=request.name,
            tenant_id=request.tenant_id,
        )

        return CreateKeyResponse(
            api_key=raw_key,
            key_id=api_key.key_id,
            name=api_key.name,
            tenant_id=api_key.tenant_id,
            created_at=api_key.created_at,
            expires_at=api_key.expires_at,
            rate_limit_per_minute=api_key.rate_limit_per_minute,
            scopes=api_key.scopes,
        )



@v1_router.get("/admin/keys", response_model=list[APIKeyInfo])
async def list_api_keys(
    _: bool = Depends(verify_admin_key),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
):
    """List all API keys (requires admin authentication)."""
    key_store = get_key_store()
    
    if isinstance(key_store, DatabaseAPIKeyStore):
        keys = await key_store.list_keys(tenant_id=x_tenant_id)
    else:
        # Fallback for in-memory store (mostly for tests/local dev)
        # Check if list_keys supports tenant_id in the mock/memory store
        try:
            keys = key_store.list_keys(tenant_id=x_tenant_id)
        except TypeError:
            keys = key_store.list_keys()

    return [
        APIKeyInfo(
            key_id=key.key_id,
            name=key.name,
            tenant_id=key.tenant_id,
            created_at=key.created_at,
            expires_at=key.expires_at,
            rate_limit_per_minute=key.rate_limit_per_minute,
            enabled=key.enabled,
            scopes=key.scopes,
        )
        for key in keys
    ]


@v1_router.delete("/admin/keys/{key_id}")
async def revoke_api_key(
    key_id: str,
    _: bool = Depends(verify_admin_key),
):
    """Revoke an API key (requires admin authentication)."""
    key_store = get_key_store()

    if isinstance(key_store, DatabaseAPIKeyStore):
        success = await key_store.revoke_key(key_id, revoked_by="admin")
    else:
        success = key_store.revoke_key(key_id)

    if success:
        logger.info("api_key_revoked_via_admin", key_id=key_id)
        return {"status": "revoked", "key_id": key_id}

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="API key not found",
    )


@v1_router.post("/admin/review/flagged-extractions", response_model=ReviewItemResponse)
def create_flagged_extraction_record(
    request: HallucinationCreateRequest,
    _: bool = Depends(verify_admin_key),
):
    """Persist a hallucination review item and update tracker state."""

    tracker = _tracker()
    try:
        record = tracker.record_hallucination(
            tenant_id=request.tenant_id,
            document_id=request.document_id,
            doc_hash=request.doc_hash,
            extractor=request.extractor,
            confidence_score=request.confidence_score,
            extraction=request.extraction,
            provenance=request.provenance,
            text_raw=request.text_raw,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return ReviewItemResponse(**record)


@v1_router.get("/admin/review/flagged-extractions")
def list_flagged_extraction_records(
    status_filter: Optional[str] = Query("PENDING", description="Status filter: PENDING/APPROVED/REJECTED"),
    tenant_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    cursor: Optional[str] = Query(None, description="Pagination cursor from previous response"),
    _: bool = Depends(verify_admin_key),
):
    """Return hallucination review items for reviewers with cursor-based pagination."""

    tracker = _tracker()
    try:
        result = tracker.list_hallucinations(
            status=status_filter,
            tenant_id=tenant_id,
            limit=limit,
            cursor=cursor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return {
        "items": [ReviewItemResponse(**item) for item in result["items"]],
        "next_cursor": result["next_cursor"],
        "has_more": result["has_more"],
    }


@v1_router.get("/review/items")
def list_review_items_alias(
    status: str = Query("PENDING"),
    limit: int = Query(50, ge=1, le=500),
    _: bool = Depends(verify_admin_key),
):
    """Alias for /admin/review/flagged-extractions to support legacy frontend calls."""
    tracker = _tracker()
    result = tracker.list_hallucinations(status=status, limit=limit)
    return result["items"]


@v1_router.post("/admin/tenants", response_model=TenantCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    request: TenantCreateRequest,
    _: bool = Depends(verify_admin_key),
) -> TenantCreateResponse:
    """Create a tenant identifier for onboarding flows."""

    tenant_id = str(uuid4())
    sanitized_name = html.escape(request.name)
    logger.info("tenant_created_via_admin", tenant_id=tenant_id, name=sanitized_name)
    return TenantCreateResponse(tenant_id=tenant_id, name=sanitized_name)


@v1_router.get("/admin/review/flagged-extractions/{review_id}", response_model=ReviewItemResponse)
def get_flagged_extraction_record(
    review_id: str,
    _: bool = Depends(verify_admin_key),
):
    """Fetch a single hallucination review item."""

    tracker = _tracker()
    try:
        item = tracker.get_hallucination(review_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=REVIEW_ITEM_NOT_FOUND) from exc

    return ReviewItemResponse(**item)


@v1_router.post("/admin/review/flagged-extractions/{review_id}/approve", response_model=ReviewItemResponse)
def approve_flagged_extraction(
    review_id: str,
    request: ReviewActionRequest,
    _: bool = Depends(verify_admin_key),
):
    """Approve a hallucination after human review."""

    tracker = _tracker()
    try:
        updated = tracker.resolve_hallucination(
            review_id,
            new_status="APPROVED",
            reviewer_id=request.reviewer_id,
            notes=request.notes,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=REVIEW_ITEM_NOT_FOUND) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return ReviewItemResponse(**updated)


@v1_router.post("/admin/review/flagged-extractions/{review_id}/reject", response_model=ReviewItemResponse)
def reject_flagged_extraction(
    review_id: str,
    request: ReviewActionRequest,
    _: bool = Depends(verify_admin_key),
):
    """Reject a hallucination and capture reviewer notes."""

    tracker = _tracker()
    try:
        updated = tracker.resolve_hallucination(
            review_id,
            new_status="REJECTED",
            reviewer_id=request.reviewer_id,
            notes=request.notes,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=REVIEW_ITEM_NOT_FOUND) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return ReviewItemResponse(**updated)
