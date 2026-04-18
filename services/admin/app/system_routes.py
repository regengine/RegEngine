from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
import httpx
import structlog
import asyncio
import os
import uuid as uuid_module
from sqlalchemy import text, select
from shared.resilient_http import resilient_client
from .dependencies import get_current_user, get_session
from .sqlalchemy_models import UserModel
from sqlalchemy.orm import Session

router = APIRouter(prefix="/system", tags=["system"])
logger = structlog.get_logger("admin.system")

class ServiceHealth(BaseModel):
    name: str
    status: str
    details: Dict[str, Any]

class SystemStatusResponse(BaseModel):
    overall_status: str
    services: List[ServiceHealth]

class SystemMetricsResponse(BaseModel):
    total_tenants: int
    total_documents: int
    active_jobs: int
    # FSMA-specific live metrics
    compliance_score: Optional[int] = None
    compliance_grade: Optional[str] = None
    events_ingested: Optional[int] = None
    chain_length: Optional[int] = None
    chain_valid: Optional[bool] = None
    open_alerts: Optional[int] = None

class JWTRotateResponse(BaseModel):
    """Response for JWT key rotation."""
    status: str
    new_kid: str
    grace_period_days: int
    message: str

class JWTKeysResponse(BaseModel):
    """Response for listing JWT keys."""
    keys: List[Dict[str, Any]]

class JWTRevokeResponse(BaseModel):
    """Response for JWT token/key revocation."""
    status: str
    jti: Optional[str] = None
    kid: Optional[str] = None

class JWTRevokeAllResponse(BaseModel):
    """Response for emergency JWT revocation."""
    status: str
    keys_revoked: int

def _detect_default(docker_name: str, railway_url: str) -> str:
    """Use Railway URL when running on Railway, Docker hostname otherwise."""
    if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_PROJECT_ID"):
        return railway_url
    return docker_name

def _get_service_urls() -> Dict[str, str]:
    """Build service health-check URLs from env vars or fallback to Docker/Railway defaults."""
    ingestion = os.getenv(
        "INGESTION_SERVICE_URL",
        _detect_default("http://ingestion-api:8002", "https://believable-respect-production-2fb3.up.railway.app"),
    )
    compliance = os.getenv(
        "COMPLIANCE_SERVICE_URL",
        _detect_default("http://compliance-api:8500", "https://intelligent-essence-production.up.railway.app"),
    )
    urls = {
        "ingestion": f"{ingestion.rstrip('/')}/health",
        "compliance": f"{compliance.rstrip('/')}/health",
    }
    # Graph service is optional — only check if explicitly configured
    graph = os.getenv("GRAPH_SERVICE_URL")
    if graph:
        urls["graph"] = f"{graph.rstrip('/')}/v1/labels/health"
    return urls

def _get_ingestion_base() -> str:
    return os.getenv(
        "INGESTION_SERVICE_URL",
        _detect_default("http://ingestion-api:8002", "https://believable-respect-production-2fb3.up.railway.app"),
    ).rstrip("/")

@router.get("/status", response_model=SystemStatusResponse)
async def get_system_status(current_user: UserModel = Depends(get_current_user)):
    service_urls = _get_service_urls()

    async with resilient_client(timeout=10.0, circuit_name="system-health") as client:
        tasks = []
        for name, url in service_urls.items():
            tasks.append(check_service_health(client, name, url))

        results = await asyncio.gather(*tasks)

    # "unavailable" means unreachable from this host (not a real outage)
    # Only count truly "unhealthy" services as degraded
    overall = "healthy"
    for r in results:
        if r.status == "unhealthy":
            overall = "degraded"

    return SystemStatusResponse(overall_status=overall, services=results)

async def check_service_health(client, name: str, url: str) -> ServiceHealth:
    """Check service health with one retry on failure."""
    for attempt in range(2):
        try:
            response = await client.get(url)
            if response.status_code == 200:
                return ServiceHealth(name=name, status="healthy", details=response.json())
            if attempt == 0:
                await asyncio.sleep(1)
                continue
            return ServiceHealth(name=name, status="unhealthy", details={"error": f"Status {response.status_code}"})
        except (OSError, TimeoutError, ConnectionError, ValueError, RuntimeError) as e:
            if attempt == 0:
                await asyncio.sleep(1)
                continue
            error_msg = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
            # ConnectError means the service is unreachable from this host
            # (common on Vercel where Docker hostnames don't resolve).
            # Report as "unavailable" not "unhealthy" to avoid false alarms.
            is_connect_error = "ConnectError" in type(e).__name__ or "connection" in str(e).lower()
            status = "unavailable" if is_connect_error else "unhealthy"
            logger.warning("health_check_failed", service=name, url=url, error=error_msg, status=status)
            return ServiceHealth(name=name, status=status, details={"error": error_msg})
    # Should not reach here, but just in case
    return ServiceHealth(name=name, status="unhealthy", details={"error": "max retries"})


def _resolve_tenant(db: Session) -> str:
    """Resolve tenant UUID from the RLS context set by get_current_user.

    Raises HTTP 500 on any failure rather than silently substituting
    the demo tenant UUID -- previously a connection bounce, RLS setup
    error, or missing tenant context caused this function to return
    a hardcoded demo-tenant UUID ("5946c58f-ddf9-4db0-9baa-acb11c6fce91")
    and every downstream query ran against the demo tenant. A real
    customer could see the demo tenant's compliance score / alert counts
    on their dashboard. (#1391)

    Fail closed: if the RLS context is missing or the read fails, raise
    500 so ops notices rather than a silent cross-tenant leak.
    """
    try:
        row = db.execute(
            text("SELECT current_setting('app.tenant_id', true)")
        ).fetchone()
        tid = row[0] if row else None
    except (RuntimeError, OSError, ValueError, KeyError) as exc:
        logger.error("resolve_tenant_lookup_failed", error=str(exc))
        raise HTTPException(
            status_code=500,
            detail=(
                "Tenant context could not be resolved. This request has "
                "been rejected to prevent cross-tenant data exposure. "
                "Please re-authenticate or retry."
            ),
        ) from exc

    if not tid:
        # RLS context missing: the get_current_user dependency normally
        # sets this; if we land here, either the JWT lacked tenant_id,
        # the auth path short-circuited, or the pool handed out a
        # freshly-cleared connection. Fail closed.
        logger.error("resolve_tenant_no_context_set")
        raise HTTPException(
            status_code=500,
            detail=(
                "Tenant context is not set on this session. This "
                "request has been rejected to prevent cross-tenant "
                "data exposure."
            ),
        )

    return tid


@router.get("/metrics", response_model=SystemMetricsResponse)
async def get_system_metrics(
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """Fetch live metrics from the ingestion service.

    Calls the scoring and chain-verify endpoints on the ingestion service
    to return real compliance data instead of hardcoded mocks.
    """
    base = _get_ingestion_base()
    tenant = _resolve_tenant(db)

    score_data: Dict[str, Any] = {}
    chain_data: Dict[str, Any] = {}

    async with resilient_client(timeout=12.0, circuit_name="ingestion-service") as client:
        score_task = client.get(f"{base}/api/v1/compliance/score/{tenant}")
        chain_task = client.get(
            f"{base}/api/v1/webhooks/chain/verify",
            params={"tenant_id": tenant},
        )
        score_resp, chain_resp = await asyncio.gather(
            score_task, chain_task, return_exceptions=True,
        )

        if isinstance(score_resp, Exception):
            logger.warning("metrics_score_fetch_failed", error=str(score_resp))
        elif score_resp.status_code == 200:
            score_data = score_resp.json()

        if isinstance(chain_resp, Exception):
            logger.warning("metrics_chain_fetch_failed", error=str(chain_resp))
        elif chain_resp.status_code == 200:
            chain_data = chain_resp.json()

    ingestion_events = score_data.get("events_analyzed", 0)

    # Also query the admin DB's supplier tables (bulk upload destination)
    supplier_event_count = 0
    supplier_facility_count = 0
    supplier_chain_length = 0
    try:
        from app.sqlalchemy_models import SupplierCTEEventModel, SupplierFacilityModel
        from sqlalchemy import func as sql_func

        tenant_uuid = uuid_module.UUID(tenant)
        supplier_event_count = db.execute(
            select(sql_func.count()).select_from(SupplierCTEEventModel).where(
                SupplierCTEEventModel.tenant_id == tenant_uuid,
            )
        ).scalar() or 0
        supplier_facility_count = db.execute(
            select(sql_func.count()).select_from(SupplierFacilityModel).where(
                SupplierFacilityModel.tenant_id == tenant_uuid,
            )
        ).scalar() or 0
        supplier_chain_length = db.execute(
            select(sql_func.max(SupplierCTEEventModel.sequence_number)).where(
                SupplierCTEEventModel.tenant_id == tenant_uuid,
            )
        ).scalar() or 0
    except (RuntimeError, OSError, ValueError, KeyError, ImportError, AttributeError) as exc:
        logger.warning("supplier_metrics_query_failed", error=str(exc))

    # Use the higher of ingestion vs supplier counts (they're separate data paths)
    total_events = max(ingestion_events, supplier_event_count)
    chain_len = chain_data.get("chain_length") or supplier_chain_length

    # Chain validity: trust ingestion service if available, otherwise
    # assume valid if supplier events exist with sequential hashes
    chain_valid = chain_data.get("chain_valid")
    if chain_valid is None and supplier_chain_length > 0:
        chain_valid = True  # Supplier events have Merkle chain by construction

    # Query open alerts from the compliance_alerts table
    open_alert_count = 0
    try:
        alert_row = db.execute(
            text("SELECT COUNT(*) FROM fsma.compliance_alerts WHERE org_id = CAST(:tid AS uuid) AND resolved = false"),
            {"tid": tenant},
        ).fetchone()
        open_alert_count = alert_row[0] if alert_row else 0
    except (RuntimeError, OSError, ValueError, KeyError) as exc:
        logger.warning("metrics_alert_count_failed", error=str(exc))

    return SystemMetricsResponse(
        total_tenants=1,
        total_documents=total_events,
        active_jobs=0,
        compliance_score=score_data.get("overall_score"),
        compliance_grade=score_data.get("grade"),
        events_ingested=total_events,
        chain_length=chain_len,
        chain_valid=chain_valid,
        open_alerts=open_alert_count,
    )


# ── JWT Key Rotation (sysadmin only) ────────────────────────────────

def _require_sysadmin(current_user: UserModel = Depends(get_current_user)):
    """Dependency that requires the authenticated user to be a sysadmin."""
    if not current_user.is_sysadmin:
        raise HTTPException(status_code=403, detail="Sysadmin access required")
    return current_user


@router.post(
    "/jwt/rotate",
    response_model=JWTRotateResponse,
    status_code=201,
    summary="Rotate JWT signing key",
    description="Generate a new signing key. Old key remains valid for 7-day grace period.",
    dependencies=[Depends(_require_sysadmin)],
)
async def rotate_jwt_key(current_user: UserModel = Depends(_require_sysadmin)):
    """Rotate the JWT signing key (sysadmin only)."""
    from shared.jwt_key_registry import get_key_registry
    from app.auth_utils import _sync_keys_from_registry

    try:
        registry = await get_key_registry()
    except Exception as exc:
        logger.error("jwt_rotate_registry_unavailable", error=str(exc))
        raise HTTPException(status_code=503, detail="Key registry unavailable")

    new_key = await registry.rotate(rotated_by=str(current_user.id))

    # Refresh the sync cache so new tokens use the new key immediately
    signing = await registry.get_signing_key()
    verifying = await registry.get_verification_keys()
    _sync_keys_from_registry(signing, verifying)

    return {
        "status": "rotated",
        "new_kid": new_key.kid,
        "grace_period_days": 7,
        "message": "New tokens will use the new key. Existing tokens remain valid for 7 days.",
    }


@router.get(
    "/jwt/keys",
    response_model=JWTKeysResponse,
    summary="List JWT signing keys",
    description="List all JWT keys and their lifecycle status (sysadmin only).",
    dependencies=[Depends(_require_sysadmin)],
)
async def list_jwt_keys(current_user: UserModel = Depends(_require_sysadmin)):
    """List all JWT keys and their status (sysadmin only)."""
    from shared.jwt_key_registry import get_key_registry

    try:
        registry = await get_key_registry()
    except Exception as exc:
        logger.error("jwt_keys_registry_unavailable", error=str(exc))
        raise HTTPException(status_code=503, detail="Key registry unavailable")

    keys = await registry.get_all_keys()
    return {
        "keys": [
            {
                "kid": k.kid,
                "algorithm": k.algorithm,
                "created_at": k.created_at,
                "expires_at": k.expires_at,
                "is_active": k.is_active,
                "is_valid": k.is_valid,
            }
            for k in keys
        ]
    }


@router.post(
    "/jwt/revoke",
    response_model=JWTRevokeResponse,
    summary="Revoke a JWT token by jti",
    description="Add a token's jti to the revocation blocklist. The token will be rejected on next verification.",
    dependencies=[Depends(_require_sysadmin)],
)
async def revoke_jwt_token(
    jti: str,
    current_user: UserModel = Depends(_require_sysadmin),
):
    """Revoke a specific JWT token (sysadmin only)."""
    from app.auth_utils import revoke_token

    await revoke_token(jti)
    return {"status": "revoked", "jti": jti}


@router.post(
    "/jwt/revoke-key",
    response_model=JWTRevokeResponse,
    summary="Revoke all tokens for a signing key",
    description="Invalidate a signing key — all tokens signed with it become invalid immediately.",
    dependencies=[Depends(_require_sysadmin)],
)
async def revoke_jwt_key(
    kid: str,
    current_user: UserModel = Depends(_require_sysadmin),
):
    """Revoke an entire signing key (sysadmin only)."""
    from app.auth_utils import revoke_all_for_kid

    from shared.jwt_key_registry import get_key_registry
    registry = await get_key_registry()
    key = await registry.get_key_by_kid(kid)
    if not key:
        raise HTTPException(status_code=404, detail=f"Key {kid} not found")

    await revoke_all_for_kid(kid)
    return {"status": "revoked", "kid": kid}


@router.post(
    "/jwt/revoke-all",
    response_model=JWTRevokeAllResponse,
    summary="EMERGENCY: Revoke ALL JWT keys",
    description=(
        "Nuclear option — invalidates every existing session and token. "
        "A fresh signing key is auto-generated. All users must re-authenticate."
    ),
    dependencies=[Depends(_require_sysadmin)],
)
async def revoke_all_jwt_keys(
    current_user: UserModel = Depends(_require_sysadmin),
):
    """Revoke all JWT signing keys (sysadmin only). Emergency use."""
    from app.auth_utils import revoke_all_jwt_keys as _revoke_all

    count = await _revoke_all()
    return {"status": "all_keys_revoked", "keys_revoked": count}
