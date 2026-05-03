import sys
import os
import threading
from pathlib import Path
_SERVICE_DIR = Path(__file__).resolve().parent
_SERVICES_DIR = _SERVICE_DIR.parent
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))
if str(_SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICES_DIR))

from shared.paths import ensure_shared_importable
ensure_shared_importable()
# ------------------------------

from shared.env_validation import require_env
require_env("ADMIN_DATABASE_URL")

# Sentry error tracking (must be before app creation)
from shared.error_handling import init_sentry
init_sentry()

import structlog
from app.api_overlay import router as overlay_router
from app.config import get_settings
from app.logging_config import configure_logging
from app.routes import router, v1_router
from app.compliance_routes import router as compliance_router
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional
from fastapi import FastAPI
from shared.observability.correlation import CorrelationIdMiddleware
from shared.observability.fastapi_metrics import install_metrics
from fastapi.middleware.cors import CORSMiddleware


settings = get_settings()
configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Modern lifespan context manager with graceful degradation.
    
    The service will start even if some dependencies are unavailable,
    enabling health checks to report partial availability.
    """
    log = structlog.get_logger("startup")
    log.info(
        "service_starting",
        version="1.0.0",
        environment=os.getenv("REGENGINE_ENV", "development"),
    )
    
    # Database initialization (critical but non-blocking)
    try:
        from app.database import init_db
        init_db()
        log.info("database_initialized")
    except (ImportError, RuntimeError, ConnectionError, OSError) as e:
        log.error("database_init_failed", error=str(e))
        # Continue - service can still serve health checks
    
    # Initialize API Key Store DB if enabled (non-blocking)
    if os.getenv("ENABLE_DB_API_KEYS", "false").lower() == "true":
        try:
            from shared.api_key_store import get_db_key_store
            await get_db_key_store()
            log.info("api_key_store_initialized")
        except (ImportError, RuntimeError, ConnectionError, OSError) as e:
            log.warning("api_key_store_init_failed", error=str(e))
            # Continue - can fall back to static keys

    # Supabase credential check — warn loudly if missing so Railway logs surface the issue.
    # Missing credentials cause /reset-password and token-validation to return 503.
    _sb_url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    _sb_key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_SERVICE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
        or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    )
    if not _sb_url or not _sb_key:
        log.warning(
            "supabase_credentials_missing",
            detail=(
                "SUPABASE_URL (or NEXT_PUBLIC_SUPABASE_URL) and "
                "SUPABASE_SERVICE_ROLE_KEY are not set. "
                "Password reset and Supabase token validation will return 503. "
                "Set these variables in Railway → admin service → Variables."
            ),
        )
    else:
        log.info("supabase_credentials_present")

    # JWT Key Registry (non-blocking — falls back to static AUTH_SECRET_KEY)
    try:
        from shared.jwt_key_registry import JWTKeyRegistry, set_key_registry
        from app.auth_utils import _sync_keys_from_registry, set_revocation_redis
        import redis.asyncio as _aioredis

        _redis_url = os.getenv("REDIS_URL", "rediss://redis:6379/0")
        _jwt_redis = _aioredis.from_url(_redis_url, decode_responses=True)

        # Share the Redis client for token revocation checks
        set_revocation_redis(_jwt_redis)
        _jwt_registry = JWTKeyRegistry(redis_client=_jwt_redis)
        await _jwt_registry.initialize()
        set_key_registry(_jwt_registry)

        # Cache keys into auth_utils for sync access
        _signing = await _jwt_registry.get_signing_key()
        _verifying = await _jwt_registry.get_verification_keys()
        _sync_keys_from_registry(_signing, _verifying)

        # Clean up any expired keys
        await _jwt_registry.cleanup_expired_keys()

        log.info("jwt_key_registry_ready", active_kid=_signing.kid)
    except Exception as e:
        log.warning("jwt_key_registry_init_failed", error=str(e))
        # Continue — auth_utils falls back to static SECRET_KEY

    # Kafka consumer (optional feature, never blocks startup)
    _start_review_consumer()

    log.info("startup_complete")
    yield
    
    # Shutdown
    log.info("shutdown_initiated")
    _stop_review_consumer()
    log.info("shutdown_complete")


from shared.env import is_production
_is_prod = is_production()

app = FastAPI(
    title="RegEngine Admin API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
    description="""
RegEngine Admin API provides tenant self-service capabilities for regulatory compliance management.

## Features

* **API Key Management**: Create and manage API keys for authentication
* **Content Graph Overlay**: Build FSMA-aligned controls mapped to traceability obligations
* **Tenant Controls**: Define internal traceability controls and operating checks
* **Product Catalog**: Manage foods and traceability-lot coverage
* **Compliance Gap Analysis**: Identify missing FSMA coverage and evidence gaps
* **Provision Mapping**: Link controls to FDA traceability requirements

## Authentication

All endpoints require an API key in the `X-RegEngine-API-Key` header:

```
X-RegEngine-API-Key: your_api_key_here
```

API keys are tenant-specific and provide automatic tenant isolation.

## Quick Start

1. Obtain an API key from your administrator
2. Create tenant controls: `POST /overlay/controls`
3. Create products: `POST /overlay/products`
4. Map controls to provisions: `POST /overlay/mappings`
5. Link controls to products: `POST /overlay/products/link-control`
6. View compliance coverage: `GET /overlay/products/{id}/requirements`

## Rate Limiting

API requests are rate-limited to prevent abuse. See response headers:
* `X-RateLimit-Limit`: Maximum requests per window
* `X-RateLimit-Remaining`: Requests remaining
* `X-RateLimit-Reset`: When the limit resets

## Support

For API support, consult the documentation at `/docs` (this page) or `/redoc`.
    """,
    contact={
        "name": "RegEngine Support",
        "url": "https://regengine.co/docs",
    },
    license_info={
        "name": "Proprietary",
        "url": "https://regengine.co/terms",
    },
)

# CORS configuration — explicit origins only, never wildcard with credentials
_PROD_ORIGINS = [
    "https://regengine.co",
    "https://www.regengine.co",
    "https://app.regengine.co",
]
_DEV_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:8000",
    "http://localhost:8002",
    "http://localhost:8080",
    "http://localhost:8400",
    "http://127.0.0.1:3000",
]
_raw_cors = os.getenv("CORS_ORIGINS", "")
if _raw_cors:
    cors_origins = [origin.strip() for origin in _raw_cors.split(",") if origin.strip()]
    if "*" in cors_origins:
        import warnings
        warnings.warn(
            "CORS_ORIGINS contains '*' which is insecure with allow_credentials=True. "
            "Falling back to production origins.",
            stacklevel=2,
        )
        cors_origins = _PROD_ORIGINS
else:
    cors_origins = _PROD_ORIGINS if _is_prod else _DEV_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-RegEngine-API-Key", "X-Admin-Key", "X-Tenant-ID", "X-Request-ID", "X-Correlation-ID"],
)

# Audit context middleware — captures IP, UA, request_id for tamper-evident audit trail
from app.audit_middleware import AuditContextMiddleware
app.add_middleware(AuditContextMiddleware)

# Per-IP rate limiting on auth endpoints (SlowAPI)
from shared.rate_limit import add_rate_limiting
add_rate_limiting(app)

# Per-tenant rate limiting (Sprint 14)
from shared.tenant_rate_limiting import TenantRateLimitMiddleware
app.add_middleware(TenantRateLimitMiddleware, default_rpm=200)

# API-01 / API-02: Request body size limit (10 MB) and global timeout (120s)
from shared.request_safety import RequestSizeLimitMiddleware, RequestTimeoutMiddleware
app.add_middleware(RequestSizeLimitMiddleware, max_bytes=10 * 1024 * 1024)
app.add_middleware(RequestTimeoutMiddleware, timeout_seconds=120)

# Correlation-ID middleware — registered LAST so it runs FIRST (outermost).
# This makes correlation_id available to every downstream middleware and
# handler via request.state / contextvar / structlog contextvars. (#1316)
app.add_middleware(CorrelationIdMiddleware)

@app.middleware("http")
async def add_compliance_header(request, call_next):
    response = await call_next(request)
    response.headers["X-FSMA-204-Traceability"] = "true"
    return response

from shared.error_handling import install_exception_handlers
install_exception_handlers(app)

# Prometheus /metrics — RED metrics for every route, auth-guarded (#1325)
install_metrics(app, service_name="admin-service")

from shared.auth import validate_auth_config
validate_auth_config()

app.include_router(router)
app.include_router(v1_router)
app.include_router(overlay_router)
app.include_router(compliance_router)

from app.system_routes import router as system_router
app.include_router(system_router, prefix="/v1")


from app.auth_routes import router as auth_router
app.include_router(auth_router)

from app.password_reset_routes import router as password_reset_router
app.include_router(password_reset_router)

from app.invite_routes import router as invite_router
app.include_router(invite_router, prefix="/v1")

from app.user_routes import router as user_router
app.include_router(user_router, prefix="/v1")

from app.supplier_onboarding_routes import router as supplier_onboarding_router
app.include_router(supplier_onboarding_router, prefix="/v1")

from app.supplier_facilities_routes import router as supplier_facilities_router
app.include_router(supplier_facilities_router, prefix="/v1")

from app.supplier_compliance_routes import router as supplier_compliance_router
app.include_router(supplier_compliance_router, prefix="/v1")

from app.supplier_funnel_routes import router as supplier_funnel_router
app.include_router(supplier_funnel_router, prefix="/v1")

from app.tenant_settings_routes import router as tenant_settings_router
app.include_router(tenant_settings_router, prefix="/v1")

from app.bulk_upload.routes import router as bulk_upload_router
app.include_router(bulk_upload_router, prefix="/v1/supplier/bulk-upload", tags=["Supplier Onboarding Bulk"])


# Review Queue for curator workflow
from app.review_routes import router as review_router
app.include_router(review_router)

# Audit log export (tamper-evident) — ISO 27001 12.4.1
from app.audit_routes import router as audit_router
app.include_router(audit_router)

# Tool email verification — public lead capture for free tools (no auth required)
from app.tool_verification_routes import router as tool_verification_router
app.include_router(tool_verification_router)

# GDPR right-to-erasure
from app.erasure_routes import router as erasure_router
app.include_router(erasure_router)

# GDPR right-to-access / data portability (Art. 15 / 20) -- #1094
from app.data_export_routes import router as data_export_router
app.include_router(data_export_router)

# Partner Gateway (white-label) — skeleton implementation, see
# regengine-partner-gateway-openapi.yaml for the contract and
# services/admin/app/partner_gateway/router.py for the TODO list of
# unimplemented operations.
from app.partner_gateway.router import router as partner_gateway_router
app.include_router(partner_gateway_router)



# ---------------------------------------------------------------------------
# Optional background consumer for nlp.needs_review → HallucinationTracker
# ---------------------------------------------------------------------------
_consumer_thread: Optional[threading.Thread] = None


def _start_review_consumer() -> None:
    """Start the Kafka consumer in a background daemon thread.

    Gated by two conditions (both must be true):
    1. ``ENABLE_REVIEW_CONSUMER=true`` — operator has opted in to this feature.
    2. ``EVENT_BACKBONE=kafka`` — operator has not switched to the PG backbone.

    When ``EVENT_BACKBONE`` defaults to ``pg`` the consumer stays dormant,
    preventing the Kafka/PG split-brain described in #1159.
    """
    global _consumer_thread
    # Event backbone gating (#1159): do not start the legacy Kafka consumer
    # unless the operator has explicitly opted in via EVENT_BACKBONE=kafka.
    from shared.event_backbone import kafka_enabled
    if not kafka_enabled():
        structlog.get_logger("admin").info(
            "event_backbone_active",
            backbone="pg",
            detail="Kafka consumers disabled (EVENT_BACKBONE=pg); task_processor handles events",
        )
        return
    if os.getenv("ENABLE_REVIEW_CONSUMER", "false").lower() not in ("1", "true", "yes"):
        return
    try:
        from app.review_consumer import run_consumer

        _consumer_thread = threading.Thread(target=run_consumer, daemon=True)
        _consumer_thread.start()
        structlog.get_logger("admin").info("review_consumer_thread_started", event_backbone_active="kafka")
    except (ImportError, RuntimeError, ConnectionError) as exc:  # pragma: no cover - optional feature
        structlog.get_logger("admin").warning("review_consumer_import_failed", error=str(exc))


def _stop_review_consumer() -> None:
    """Stop the Kafka consumer gracefully."""
    if _consumer_thread is not None:
        from app.review_consumer import stop_consumer
        stop_consumer()
        _consumer_thread.join(timeout=5)
