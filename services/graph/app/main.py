from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from shared.cors import get_allowed_origins, should_allow_credentials
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=should_allow_credentials(),
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-RegEngine-API-Key", "X-Tenant-ID", "X-Request-ID"],
)

# Global exception handlers (Sprint 18)
from shared.error_handling import install_exception_handlers
install_exception_handlers(app)

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

# Health check is defined in app/routes.py with Neo4j connectivity verification.
# Do NOT use install_health_router() here — it would overwrite the custom check.
