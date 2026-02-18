"""
Finance Vertical Decision Service

SEC-FIN-001/002 REMEDIATION: Added TenantContextMiddleware, CORS,
rate limiting, and structured logging (Feb 2026 P0 security audit).

NOTE: This file was originally auto-generated. Manual security fixes
applied — ensure `regengine compile vertical finance` incorporates
these patterns before regeneration.
"""

import sys
from pathlib import Path
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Centralised path resolution
_SERVICES_DIR = Path(__file__).resolve().parent.parent
if str(_SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICES_DIR))
from shared.paths import ensure_shared_importable
ensure_shared_importable()

from shared.middleware import TenantContextMiddleware, RequestIDMiddleware
from shared.cors import get_allowed_origins, should_allow_credentials
from shared.rate_limiting import setup_rate_limiting

from services.finance_api.routes import router

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.PrintLoggerFactory(),
)
logger = structlog.get_logger("finance_api")

SERVICE_NAME = "finance-api"
SERVICE_VERSION = "1.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("finance_api_startup", service=SERVICE_NAME, version=SERVICE_VERSION)
    yield
    logger.info("finance_api_shutdown", service=SERVICE_NAME)


app = FastAPI(
    title="Finance API",
    description="Finance Vertical Decision Service",
    version=SERVICE_VERSION,
    lifespan=lifespan,
)

# CORS middleware (using shared secure config)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=should_allow_credentials(),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tenant isolation middleware
app.add_middleware(RequestIDMiddleware)
app.add_middleware(TenantContextMiddleware)

# Rate limiting (IP-based via slowapi)
setup_rate_limiting(app)

# Per-tenant rate limiting (Sprint 14)
from shared.tenant_rate_limiting import TenantRateLimitMiddleware
app.add_middleware(TenantRateLimitMiddleware, default_rpm=100)

# Global exception handlers (Sprint 18)
from shared.error_handling import install_exception_handlers
install_exception_handlers(app)

# Include routers
app.include_router(router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": SERVICE_NAME, "version": SERVICE_VERSION}


@app.get("/ready")
async def ready_check():
    """Readiness check endpoint."""
    return {"status": "ready", "service": SERVICE_NAME, "version": SERVICE_VERSION}


@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "docs": "/docs",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
