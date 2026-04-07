"""API routes for the admin service."""

from __future__ import annotations

import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Optional
from uuid import uuid4

import redis
import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, status, Request, Query
from shared.pagination import PaginationParams, PaginatedResponse
from shared.metrics_auth import require_metrics_key
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field
import html
from sqlalchemy.orm import Session

# Centralised path resolution
from shared.paths import ensure_shared_importable
ensure_shared_importable()

from shared.auth import get_key_store
from shared.api_key_store import DatabaseAPIKeyStore
from shared.funnel_events import get_funnel_stage_metrics

from .config import get_settings
from .database import get_session
from .dependencies import PermissionChecker
from .review_consumer import get_consumer_health

# Health/metrics router at root level (operational endpoints)
router = APIRouter()

# Versioned API router for admin endpoints
v1_router = APIRouter(prefix="/v1", tags=["v1"])

logger = structlog.get_logger("admin")

# ---------------------------------------------------------------------------
# Admin-key brute-force rate limiter (#534)
# Redis-backed sliding-window counter: max 5 failed attempts per IP per 60 s.
# Shared across all service instances. Falls back to in-memory if Redis
# is unavailable (single-instance safety net).
# ---------------------------------------------------------------------------
_ADMIN_MAX_FAILURES = 5
_ADMIN_WINDOW_SECONDS = 60

# In-memory fallback (used only when Redis is unavailable)
_admin_failures: dict[str, list[float]] = defaultdict(list)
_admin_failures_lock = Lock()

_redis_client: redis.Redis | None = None


def _get_rate_limit_redis() -> redis.Redis | None:
    """Lazy-init a Redis client for rate limiting."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return None
    try:
        _redis_client = redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=2)
        _redis_client.ping()
        return _redis_client
    except (redis.RedisError, OSError):
        logger.warning("rate_limiter_redis_unavailable_using_in_memory")
        _redis_client = None
        return None


def _admin_key_rate_limited(ip: str) -> bool:
    """Return True if this IP has exceeded the admin-key failure threshold."""
    r = _get_rate_limit_redis()
    if r is not None:
        try:
            key = f"admin_fail:{ip}"
            count = r.get(key)
            return int(count or 0) >= _ADMIN_MAX_FAILURES
        except redis.RedisError:
            pass  # fall through to in-memory

    # In-memory fallback
    now = time.time()
    with _admin_failures_lock:
        _admin_failures[ip] = [
            t for t in _admin_failures[ip] if now - t < _ADMIN_WINDOW_SECONDS
        ]
        return len(_admin_failures[ip]) >= _ADMIN_MAX_FAILURES


def _record_admin_failure(ip: str) -> int:
    """Record a failed attempt and return the current failure count for this IP."""
    r = _get_rate_limit_redis()
    if r is not None:
        try:
            key = f"admin_fail:{ip}"
            pipe = r.pipeline()
            pipe.incr(key)
            pipe.expire(key, _ADMIN_WINDOW_SECONDS)
            results = pipe.execute()
            return int(results[0])
        except redis.RedisError:
            pass  # fall through to in-memory

    # In-memory fallback
    now = time.time()
    with _admin_failures_lock:
        _admin_failures[ip].append(now)
        if len(_admin_failures[ip]) > _ADMIN_MAX_FAILURES * 4:
            _admin_failures[ip] = _admin_failures[ip][-(_ADMIN_MAX_FAILURES * 2):]
        return len(_admin_failures[ip])


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


class KDEValidationErrorModel(BaseModel):
    """Tracks missing mandatory FSMA 204 Key Data Elements on a CTE event."""

    tenant_id: Optional[str] = Field(None, description="Tenant UUID that owns the record")
    event_id: str = Field(..., description="CTE event identifier")
    cte_type: str = Field(..., description="Critical Tracking Event type (e.g. receiving, shipping)")
    missing_kdes: list[str] = Field(..., description="List of missing mandatory KDE field names")
    facility_gln: Optional[str] = Field(None, description="GLN of the facility where the gap was detected")
    traceability_lot_code: Optional[str] = None
    severity: str = Field("HIGH", description="HIGH if blocks compliance, MEDIUM if degraded")
    detected_at: Optional[datetime] = None


class TenantCreateRequest(BaseModel):
    """Request to create a new tenant for onboarding."""

    name: str = Field(..., min_length=1, max_length=255)


class TenantCreateResponse(BaseModel):
    """Response for tenant creation."""

    tenant_id: str
    name: str
    status: str = "active"


class FunnelStageResponse(BaseModel):
    """Single funnel stage metric."""

    name: str
    count: int
    conversion_from_previous_pct: float


class FunnelResponse(BaseModel):
    """Aggregate funnel metrics response."""

    stages: list[FunnelStageResponse]


def verify_admin_key(
    request: Request,
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key"),
) -> bool:
    """Verify the admin master key with brute-force rate limiting (#534).

    Rate limit: max 5 failed attempts per source IP per 60 seconds.
    Exceeded limit → HTTP 429 with Retry-After header.
    All failures are logged with IP and key prefix for audit purposes.
    """
    ip: str = (request.client.host if request.client else "unknown")

    # Check rate limit BEFORE evaluating the key — don't give timing hints
    if _admin_key_rate_limited(ip):
        logger.warning(
            "admin_key_rate_limited",
            source_ip=ip,
            path=request.url.path,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Too many failed admin authentication attempts from this IP. "
                f"Try again in {_ADMIN_WINDOW_SECONDS} seconds."
            ),
            headers={"Retry-After": str(_ADMIN_WINDOW_SECONDS)},
        )

    settings = get_settings()

    if not x_admin_key or x_admin_key != settings.admin_master_key:
        count = _record_admin_failure(ip)
        logger.warning(
            "unauthorized_admin_access_attempt",
            key_prefix=x_admin_key[:4] if x_admin_key else "None",
            source_ip=ip,
            path=request.url.path,
            failure_count=count,
            failures_until_lockout=max(0, _ADMIN_MAX_FAILURES - count),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
        )
    return True



def require_funnel_read(
    _: bool = Depends(PermissionChecker("admin.funnel.read")),
) -> None:
    """RBAC guard for funnel analytics."""
    return None


@router.get("/health")
async def health():
    """Deep health check endpoint with dependency verification."""
    import asyncio
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
            except (OSError, TimeoutError, ConnectionError, ValueError, RuntimeError) as e:
                # (#562) Log full error server-side; return generic message to clients
                # to avoid leaking connection strings, hostnames, or credentials.
                logger.error("health_check_postgres_failed", error=str(e), error_type=type(e).__name__)
                return {"status": "unhealthy", "error": "database unavailable"}

        checker.add_dependency("postgresql", check_postgres)

    # Neo4j check
    neo4j_uri = os.getenv("NEO4J_URI") or os.getenv("NEO4J_URL")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD")
    if neo4j_uri:
        async def check_neo4j():
            try:
                if not neo4j_password:
                    # Config error — generic message safe to surface
                    return {"status": "unhealthy", "error": "graph database misconfigured"}

                from neo4j import GraphDatabase

                def _probe() -> None:
                    with GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password)) as driver:
                        driver.verify_connectivity()
                        with driver.session() as session:
                            session.run("RETURN 1 AS ok").single()

                await asyncio.to_thread(_probe)
                return {"status": "healthy"}
            except (OSError, TimeoutError, ConnectionError, ValueError, RuntimeError) as e:
                # (#562) Log full error server-side; return generic message to clients.
                logger.error("health_check_neo4j_failed", error=str(e), error_type=type(e).__name__)
                return {"status": "unhealthy", "error": "graph database unavailable"}

        checker.add_dependency("neo4j", check_neo4j)

    # Redis check
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        async def check_redis():
            try:
                import redis.asyncio as redis
                r = redis.from_url(redis_url)
                await r.ping()
                return {"status": "healthy"}
            except (OSError, TimeoutError, ConnectionError, ValueError, ImportError, AttributeError) as e:
                # (#562) Log full error server-side; return generic message to clients.
                logger.error("health_check_redis_failed", error=str(e), error_type=type(e).__name__)
                return {"status": "unhealthy", "error": "cache unavailable"}

        checker.add_dependency("redis", check_redis)

    result = await checker.check()
    sc = 200 if result.get("status") == "healthy" else 503
    return JSONResponse(content=result, status_code=sc)


@router.get("/ready")
async def readiness():
    """Readiness probe for k8s orchestration."""
    return {"status": "ready", "service": "admin-api"}


@router.get("/health/consumer", dependencies=[Depends(verify_admin_key)])
def consumer_health():
    """Health check endpoint for the Kafka review consumer."""
    from fastapi.responses import JSONResponse
    health_info = get_consumer_health()
    status_code = 200 if health_info.get("healthy") else 503
    return JSONResponse(content=health_info, status_code=status_code)


@router.get("/metrics", dependencies=[Depends(require_metrics_key)])
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
        # Async DB store — create_key() SHA-256-hashes the key internally;
        # only the hash is persisted. raw_key is returned once here and is
        # never stored or logged (#548).
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
            key_prefix=new_key.key_prefix,  # first 12 chars for identification; raw key never logged
            name=request.name,
            tenant_id=request.tenant_id,
        )

        return CreateKeyResponse(
            api_key=new_key.raw_key,  # shown ONCE in creation response only (#548)
            key_id=new_key.key_id,
            name=new_key.name,
            tenant_id=new_key.tenant_id,
            created_at=new_key.created_at,
            expires_at=new_key.expires_at,
            rate_limit_per_minute=new_key.rate_limit_per_minute,
            scopes=new_key.scopes,
        )
    else:
        # Sync in-memory store — create_key() hashes and stores only the hash;
        # raw_key is returned here once and never re-exposed (#548).
        raw_key, api_key = key_store.create_key(
            name=request.name,
            tenant_id=request.tenant_id,
            rate_limit_per_minute=request.rate_limit_per_minute,
            expires_at=request.expires_at,
            scopes=request.scopes,
        )
        key_prefix = raw_key[:12]  # first 12 chars for identification; raw key never logged

        logger.info(
            "api_key_created_via_admin",
            key_id=api_key.key_id,
            key_prefix=key_prefix,
            name=request.name,
            tenant_id=request.tenant_id,
        )

        return CreateKeyResponse(
            api_key=raw_key,  # shown ONCE in creation response only (#548)
            key_id=api_key.key_id,
            name=api_key.name,
            tenant_id=api_key.tenant_id,
            created_at=api_key.created_at,
            expires_at=api_key.expires_at,
            rate_limit_per_minute=api_key.rate_limit_per_minute,
            scopes=api_key.scopes,
        )



@v1_router.get("/admin/keys", response_model=PaginatedResponse[APIKeyInfo])
async def list_api_keys(
    pagination: PaginationParams = Depends(),
    _: bool = Depends(verify_admin_key),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
):
    """List API keys with pagination (requires admin authentication)."""
    key_store = get_key_store()

    if isinstance(key_store, DatabaseAPIKeyStore):
        keys = await key_store.list_keys(tenant_id=x_tenant_id)
    else:
        # Fallback for in-memory store (mostly for tests/local dev)
        try:
            keys = key_store.list_keys(tenant_id=x_tenant_id)
        except TypeError:
            keys = key_store.list_keys()

    total = len(keys)
    paged = keys[pagination.skip : pagination.skip + pagination.limit]

    return PaginatedResponse(
        items=[
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
            for key in paged
        ],
        total=total,
        skip=pagination.skip,
        limit=pagination.limit,
    )


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


@v1_router.get(
    "/admin/funnel",
    response_model=FunnelResponse,
    dependencies=[Depends(require_funnel_read)],
)
async def get_funnel_metrics(
    db: Session = Depends(get_session),
) -> FunnelResponse:
    """Return aggregate tenant funnel counts and stage conversion rates."""
    stages = get_funnel_stage_metrics(db_session=db)
    return FunnelResponse(stages=[FunnelStageResponse(**stage) for stage in stages])


