"""FastAPI application entrypoint for the admin service."""

from __future__ import annotations

import os
import threading
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from app.api_overlay import router as overlay_router
from app.config import get_settings
from app.logging_config import configure_logging
from app.routes import router, v1_router
from app.compliance_routes import router as compliance_router
from fastapi import FastAPI
# from shared.correlation import CorrelationIdMiddleware
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
        version="0.4.0",
        environment=os.getenv("REGENGINE_ENV", "development"),
    )
    
    # Database initialization (critical but non-blocking)
    try:
        from app.database import init_db
        init_db()
        log.info("database_initialized")
    except Exception as e:
        log.error("database_init_failed", error=str(e))
        # Continue - service can still serve health checks
    
    # Initialize API Key Store DB if enabled (non-blocking)
    if os.getenv("ENABLE_DB_API_KEYS", "false").lower() == "true":
        try:
            from shared.api_key_store import get_db_key_store
            await get_db_key_store()
            log.info("api_key_store_initialized")
        except Exception as e:
            log.warning("api_key_store_init_failed", error=str(e))
            # Continue - can fall back to static keys

    # Kafka consumer (optional feature, never blocks startup)
    _start_review_consumer()
    
    log.info("startup_complete")
    yield
    
    # Shutdown
    log.info("shutdown_initiated")
    _stop_review_consumer()
    log.info("shutdown_complete")


app = FastAPI(
    title="RegEngine Admin API",
    version="1.0.0",
    lifespan=lifespan,
    description="""
RegEngine Admin API provides tenant self-service capabilities for regulatory compliance management.

## Features

* **API Key Management**: Create and manage API keys for authentication
* **Content Graph Overlay**: Build custom control frameworks mapped to regulatory provisions
* **Tenant Controls**: Define internal controls (NIST CSF, SOC2, ISO27001, etc.)
* **Product Catalog**: Manage products requiring regulatory compliance
* **Compliance Gap Analysis**: Identify unmapped regulatory requirements
* **Provision Mapping**: Link controls to specific regulatory provisions

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
        "url": "https://github.com/regengine/regengine",
    },
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },
)

# CORS configuration
# In production, replace with specific origins
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001,http://localhost:8080").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
# app.add_middleware(CorrelationIdMiddleware)

# Audit context middleware — captures IP, UA, request_id for tamper-evident audit trail
from app.audit_middleware import AuditContextMiddleware
app.add_middleware(AuditContextMiddleware)

# Per-tenant rate limiting (Sprint 14)
from shared.tenant_rate_limiting import TenantRateLimitMiddleware
app.add_middleware(TenantRateLimitMiddleware, default_rpm=200)

@app.middleware("http")
async def add_compliance_header(request, call_next):
    response = await call_next(request)
    response.headers["X-FSMA-204-Traceability"] = "true"
    return response

from shared.error_handling import install_exception_handlers
install_exception_handlers(app)

app.include_router(router)
app.include_router(v1_router)
app.include_router(overlay_router)
app.include_router(compliance_router)

from app.system_routes import router as system_router
app.include_router(system_router, prefix="/v1")


from app.auth_routes import router as auth_router
app.include_router(auth_router)

from app.invite_routes import router as invite_router
app.include_router(invite_router, prefix="/v1")

from app.user_routes import router as user_router
app.include_router(user_router, prefix="/v1")

# Production Compliance OS (CA/LA) — fully decomposed into app/pcos/ package
from app.pcos import router as pcos_router
app.include_router(pcos_router)

# Vertical Expansion (Healthcare, Finance, etc.)
from app.verticals.router import router as verticals_router
app.include_router(verticals_router)

# Review Queue for curator workflow
from app.review_routes import router as review_router
app.include_router(review_router)

# Audit log export (tamper-evident) — ISO 27001 12.4.1
from app.audit_routes import router as audit_router
app.include_router(audit_router)



# ---------------------------------------------------------------------------
# Optional background consumer for nlp.needs_review → HallucinationTracker
# ---------------------------------------------------------------------------
_consumer_thread: threading.Thread | None = None


def _start_review_consumer() -> None:
    """Start the Kafka consumer in a background daemon thread."""
    global _consumer_thread
    if os.getenv("ENABLE_REVIEW_CONSUMER", "false").lower() not in ("1", "true", "yes"):
        return
    try:
        from app.review_consumer import run_consumer

        _consumer_thread = threading.Thread(target=run_consumer, daemon=True)
        _consumer_thread.start()
        structlog.get_logger("admin").info("review_consumer_thread_started")
    except Exception as exc:  # pragma: no cover - optional feature
        structlog.get_logger("admin").warning("review_consumer_import_failed", error=str(exc))


def _stop_review_consumer() -> None:
    """Stop the Kafka consumer gracefully."""
    if _consumer_thread is not None:
        from app.review_consumer import stop_consumer
        stop_consumer()
        _consumer_thread.join(timeout=5)
