"""API routes for the admin service."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field
from shared.metrics_auth import require_metrics_key
from shared.pagination import PaginatedResponse, PaginationParams

# Centralised path resolution
from shared.paths import ensure_shared_importable
from shared.rate_limit import limiter
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

ensure_shared_importable()

from shared.api_key_store import DatabaseAPIKeyStore
from shared.auth import APIKeyStore
from shared.funnel_events import get_funnel_stage_metrics

from .api_key_admin_store import get_admin_api_key_store
from .database import arm_global_admin_context, get_session
from .dependencies import PermissionChecker
from .models import TenantContext
from .privileged_auth import (
    PrivilegedActor,
    audit_privileged_action,
    require_sysadmin_high_assurance,
    require_tenant_provisioner_key,
)
from .review_consumer import get_consumer_health
from .sqlalchemy_models import TenantModel
from .tenant_slug_helpers import _ensure_unique_tenant_slug

# Health/metrics router at root level (operational endpoints)
router = APIRouter()

# Versioned API router for admin endpoints
v1_router = APIRouter(prefix="/v1", tags=["v1"])

logger = structlog.get_logger("admin")

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


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    dependencies: Optional[dict] = None


class ReadinessResponse(BaseModel):
    """Readiness probe response."""

    status: str
    service: str


class ConsumerHealthResponse(BaseModel):
    """Consumer health check response."""

    healthy: Optional[bool] = None


class APIKeyRevokeResponse(BaseModel):
    """Response for revoking an API key."""

    status: str
    key_id: str


def require_funnel_read(
    _: bool = Depends(PermissionChecker("admin.funnel.read")),
) -> None:
    """RBAC guard for funnel analytics."""
    return None


@router.get("/health", operation_id="admin_deep_health")
async def health():
    """Health check endpoint with dependency verification."""
    import asyncio
    import os

    from fastapi.responses import JSONResponse
    from shared.observability.health import HealthCheck

    checker = HealthCheck(service_name="admin-api")

    # PostgreSQL check
    admin_db_url = os.getenv("DATABASE_URL") or os.getenv("ADMIN_DATABASE_URL")
    if admin_db_url:

        async def check_postgres():
            try:
                if admin_db_url.startswith("sqlite"):
                    return {"status": "healthy"}
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
                from redis.exceptions import RedisError

                r = redis.from_url(redis_url)
                await r.ping()
                return {"status": "healthy"}
            except (OSError, TimeoutError, ConnectionError, ValueError, ImportError, AttributeError, RedisError) as e:
                # (#562) Log full error server-side; return generic message to clients.
                logger.error("health_check_redis_failed", error=str(e), error_type=type(e).__name__)
                return {"status": "unhealthy", "error": "cache unavailable"}

        checker.add_dependency("redis", check_redis)

    result = await checker.check()
    return JSONResponse(content=result, status_code=200)


@router.get("/ready", response_model=ReadinessResponse)
async def readiness():
    """Readiness probe for k8s orchestration."""
    return {"status": "ready", "service": "admin-api"}


@router.get("/health/consumer", dependencies=[Depends(require_metrics_key)])
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
@limiter.limit("5/minute")
async def create_api_key(
    request: Request,
    body: CreateKeyRequest,
    actor: PrivilegedActor = Depends(require_sysadmin_high_assurance),
    key_store: APIKeyStore | DatabaseAPIKeyStore = Depends(get_admin_api_key_store),
):
    """Create a new API key for an authenticated high-assurance sysadmin."""
    audit_privileged_action(
        request,
        action="api_key.create",
        outcome="attempted",
        actor=actor,
        selected_tenant=body.tenant_id,
    )

    if isinstance(key_store, DatabaseAPIKeyStore):
        # Async DB store — create_key() SHA-256-hashes the key internally;
        # only the hash is persisted. raw_key is returned once here and is
        # never stored or logged (#548).
        new_key = await key_store.create_key(
            name=body.name,
            tenant_id=body.tenant_id,
            rate_limit_per_minute=body.rate_limit_per_minute,
            expires_at=body.expires_at,
            scopes=body.scopes,
            created_by=actor.actor_id,
        )

        logger.info(
            "api_key_created_via_admin",
            key_id=new_key.key_id,
            name=body.name,
            tenant_id=body.tenant_id,
        )

        response = CreateKeyResponse(
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
            name=body.name,
            tenant_id=body.tenant_id,
            rate_limit_per_minute=body.rate_limit_per_minute,
            expires_at=body.expires_at,
            scopes=body.scopes,
        )
        logger.info(
            "api_key_created_via_admin",
            key_id=api_key.key_id,
            name=body.name,
            tenant_id=body.tenant_id,
        )

        response = CreateKeyResponse(
            api_key=raw_key,  # shown ONCE in creation response only (#548)
            key_id=api_key.key_id,
            name=api_key.name,
            tenant_id=api_key.tenant_id,
            created_at=api_key.created_at,
            expires_at=api_key.expires_at,
            rate_limit_per_minute=api_key.rate_limit_per_minute,
            scopes=api_key.scopes,
        )

    audit_privileged_action(
        request,
        action="api_key.create",
        outcome="succeeded",
        actor=actor,
        target=response.key_id,
        selected_tenant=response.tenant_id,
    )
    return response


@v1_router.get("/admin/keys", response_model=PaginatedResponse[APIKeyInfo])
async def list_api_keys(
    request: Request,
    pagination: PaginationParams = Depends(),
    actor: PrivilegedActor = Depends(require_sysadmin_high_assurance),
    key_store: APIKeyStore | DatabaseAPIKeyStore = Depends(get_admin_api_key_store),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
):
    """List API keys for an authenticated high-assurance sysadmin."""
    audit_privileged_action(
        request,
        action="api_key.list",
        outcome="attempted",
        actor=actor,
        selected_tenant=x_tenant_id,
    )

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

    response = PaginatedResponse(
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
    audit_privileged_action(
        request,
        action="api_key.list",
        outcome="succeeded",
        actor=actor,
        target=f"{len(response.items)} keys",
        selected_tenant=x_tenant_id,
    )
    return response


@v1_router.delete("/admin/keys/{key_id}", response_model=APIKeyRevokeResponse)
async def revoke_api_key(
    key_id: str,
    request: Request,
    actor: PrivilegedActor = Depends(require_sysadmin_high_assurance),
    key_store: APIKeyStore | DatabaseAPIKeyStore = Depends(get_admin_api_key_store),
):
    """Revoke an API key for an authenticated high-assurance sysadmin."""
    selected_tenant: str | None = None
    audit_privileged_action(
        request,
        action="api_key.revoke",
        outcome="attempted",
        actor=actor,
        target=key_id,
    )

    if isinstance(key_store, DatabaseAPIKeyStore):
        key_info = await key_store.get_key(key_id)
        selected_tenant = key_info.tenant_id if key_info else None
        success = await key_store.revoke_key(key_id, revoked_by=actor.actor_id)
    else:
        key_info = next((key for key in key_store.list_keys() if key.key_id == key_id), None)
        selected_tenant = key_info.tenant_id if key_info else None
        success = key_store.revoke_key(key_id)

    if success:
        logger.info("api_key_revoked_via_admin", key_id=key_id)
        audit_privileged_action(
            request,
            action="api_key.revoke",
            outcome="succeeded",
            actor=actor,
            target=key_id,
            selected_tenant=selected_tenant,
        )
        return {"status": "revoked", "key_id": key_id}

    audit_privileged_action(
        request,
        action="api_key.revoke",
        outcome="denied",
        actor=actor,
        target=key_id,
        reason="key_not_found",
    )
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="API key not found",
    )


@v1_router.post("/admin/tenants", response_model=TenantCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    request: Request,
    body: TenantCreateRequest,
    actor: PrivilegedActor = Depends(require_sysadmin_high_assurance),
    db: Session = Depends(get_session),
) -> TenantCreateResponse:
    """Create and persist a tenant as a high-assurance sysadmin."""
    return _create_tenant_for_actor(request=request, body=body, actor=actor, db=db)


@v1_router.post(
    "/internal/tenants",
    response_model=TenantCreateResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def create_internal_tenant(
    request: Request,
    body: TenantCreateRequest,
    actor: PrivilegedActor = Depends(require_tenant_provisioner_key),
    db: Session = Depends(get_session),
) -> TenantCreateResponse:
    """Create a tenant for the single-purpose onboarding workload."""
    return _create_tenant_for_actor(request=request, body=body, actor=actor, db=db)


def _create_tenant_for_actor(
    *,
    request: Request,
    body: TenantCreateRequest,
    actor: PrivilegedActor,
    db: Session,
) -> TenantCreateResponse:
    audit_privileged_action(
        request,
        action="tenant.create",
        outcome="attempted",
        actor=actor,
        target="new_tenant",
    )

    # Both callers reach this helper only after their independent authority
    # checks (high-assurance human or exact-scope workload key).  Arm the
    # global RLS branch here, never in the generic DB dependency.
    arm_global_admin_context(db)
    # Store the raw display name verbatim. HTML-escaping is an
    # output-encoding concern: escaping here permanently corrupts the
    # stored value ("A&W" becomes "A&amp;W"), double-escapes on every
    # render, and pollutes the derived slug. Escape at render time.
    tenant_name = body.name
    try:
        tenant = TenantModel(
            name=tenant_name,
            slug=_ensure_unique_tenant_slug(db, tenant_name),
            status="active",
            settings={},
        )
        db.add(tenant)
        db.flush()
        tenant_id = str(tenant.id)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error(
            "tenant_create_failed",
            actor_type=actor.actor_type,
            actor_id=actor.actor_id,
            error_class=type(exc).__name__,
        )
        audit_privileged_action(
            request,
            action="tenant.create",
            outcome="failed",
            actor=actor,
            reason="database_error",
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create tenant",
        ) from exc

    logger.info(
        "tenant_created",
        tenant_id=tenant_id,
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
    )
    audit_privileged_action(
        request,
        action="tenant.create",
        outcome="succeeded",
        actor=actor,
        target=tenant_id,
        selected_tenant=tenant_id,
    )
    return TenantCreateResponse(tenant_id=tenant_id, name=tenant_name)


@v1_router.get(
    "/admin/funnel",
    response_model=FunnelResponse,
    dependencies=[Depends(require_funnel_read)],
)
async def get_funnel_metrics(
    db: Session = Depends(get_session),
) -> FunnelResponse:
    """Return funnel counts and stage conversion rates for the active tenant."""
    tenant_id = TenantContext.get_tenant_context(db)
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="E_NO_TENANT_CONTEXT: funnel metrics require tenant context",
        )
    stages = get_funnel_stage_metrics(tenant_id=str(tenant_id), db_session=db)
    return FunnelResponse(stages=[FunnelStageResponse(**stage) for stage in stages])
