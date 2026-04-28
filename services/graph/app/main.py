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

from shared.env_validation import require_env
require_env("DATABASE_URL")

# Sentry error tracking (must be before app creation)
from shared.error_handling import init_sentry
init_sentry()

# Production Hardening (Phase 18)
from shared.observability.context import setup_logging
from shared.middleware.security import add_security
from shared.rate_limit import add_rate_limiting
from shared.observability import add_observability
from shared.observability.fastapi_metrics import install_metrics

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
    title="RegEngine Graph Service",
    description="Knowledge graph construction, regulatory frameworks, and traceability gap analysis for FSMA 204 compliance",
    version="1.0.0",
    lifespan=lifespan,
    contact={"name": "RegEngine Support", "url": "https://github.com/regengine/RegEngine"},
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
)

# Production Hardening Middleware (Phase 18)
add_security(app)
add_rate_limiting(app)
add_observability(app, service_name="graph-service")

from shared.middleware import TenantContextMiddleware, RequestIDMiddleware
from shared.observability.correlation import CorrelationIdMiddleware
from shared.tenant_rate_limiting import TenantRateLimitMiddleware

app.add_middleware(RequestIDMiddleware)
app.add_middleware(TenantContextMiddleware)
app.add_middleware(TenantRateLimitMiddleware, default_rpm=100)

from shared.request_safety import RequestSizeLimitMiddleware, RequestTimeoutMiddleware
app.add_middleware(RequestSizeLimitMiddleware, max_bytes=10 * 1024 * 1024)
app.add_middleware(RequestTimeoutMiddleware, timeout_seconds=120)

# Correlation-ID middleware — registered last so it runs first (outermost). (#1316)
app.add_middleware(CorrelationIdMiddleware)

# Global exception handlers (Sprint 18)
from shared.error_handling import install_exception_handlers
install_exception_handlers(app)

# Prometheus /metrics — RED metrics for every route, auth-guarded (#1325)
install_metrics(app, service_name="graph-service")

app.include_router(graph_router, prefix="/api/v1", tags=["Graph Operations"])


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
