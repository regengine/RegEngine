import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
# --- Standardized Bootstrap ---
import sys
from pathlib import Path
_SERVICE_DIR = Path(__file__).resolve().parents[1]
_SERVICES_DIR = _SERVICE_DIR.parent
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))
if str(_SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICES_DIR))

from shared.paths import ensure_shared_importable
ensure_shared_importable()
# ------------------------------

# Sentry error tracking (must be before app creation)
from shared.error_handling import init_sentry
init_sentry()

# Production Hardening (Phase 18)
from shared.logging import setup_logging
from shared.middleware.security import add_security
from shared.rate_limit import add_rate_limiting
from shared.observability import add_observability

# Initialize standardized logging
logger = setup_logging()

# Local imports (using absolute-style imports from 'app' package inside graph service)
from app.routes import router as graph_router
from app.config import settings

from shared.env import is_production
_is_prod = is_production()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("graph_service_startup")
    yield
    # Shutdown
    logger.info("graph_service_shutdown")

app = FastAPI(
    title="Graph Service",
    description="Knowledge graph and fact linkage service",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
)

# Production Hardening Middleware (Phase 18)
add_security(app)
add_rate_limiting(app)
add_observability(app, service_name="graph-service")

from shared.middleware import TenantContextMiddleware, RequestIDMiddleware
from shared.tenant_rate_limiting import TenantRateLimitMiddleware

app.add_middleware(RequestIDMiddleware)
app.add_middleware(TenantContextMiddleware)
app.add_middleware(TenantRateLimitMiddleware, default_rpm=100)

# Global exception handlers (Sprint 18)
from shared.error_handling import install_exception_handlers
install_exception_handlers(app)

from shared.auth import validate_auth_config
validate_auth_config()

app.include_router(graph_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "service": "RegEngine Graph Service",
        "version": app.version,
        "status": "operational",
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
            "gaps": "/graph/gaps",
            "frameworks": "/graph/frameworks",
        },
    }

# Standardized Health & Readiness (Phase 17)
from shared.health import HealthCheck, install_health_router

health = HealthCheck(service_name="graph-service")
install_health_router(app, service_name="graph-service", health_check=health)
