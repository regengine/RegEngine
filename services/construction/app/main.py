from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sys
from pathlib import Path

# Standardized path discovery
_SERVICES_DIR = Path(__file__).resolve().parent.parent.parent
if str(_SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICES_DIR))

# Ensure shared utilities are importable
from shared.paths import ensure_shared_importable
ensure_shared_importable()

# Production Hardening (Phase 18)
from shared.logging import setup_logging
from shared.middleware.security import add_security
from shared.rate_limit import add_rate_limiting
from shared.observability import add_observability

# Initialize standardized logging
logger = setup_logging()

# Local imports
from .bim_tracking import router as bim_router
from .config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("construction_service_startup")
    yield
    # Shutdown
    logger.info("construction_service_shutdown")

app = FastAPI(
    title="Construction Compliance Service",
    description="OSHA safety standards and field inspection tracking",
    version="1.0.0",
    lifespan=lifespan,
)

# Production Hardening Middleware (Phase 18)
add_security(app)
add_rate_limiting(app)
add_observability(app)

from shared.middleware import TenantContextMiddleware, RequestIDMiddleware
from shared.tenant_rate_limiting import TenantRateLimitMiddleware

app.add_middleware(RequestIDMiddleware)
app.add_middleware(TenantContextMiddleware)
app.add_middleware(TenantRateLimitMiddleware, default_rpm=100)

# Global exception handlers (Sprint 18)
from shared.error_handling import install_exception_handlers
install_exception_handlers(app)

app.include_router(bim_router, prefix="/api/v1/construction")

# Standardized Health & Readiness (Phase 17)
from shared.health import HealthCheck, install_health_router
from .db_session import get_db
from sqlalchemy import text

health = HealthCheck(service_name="construction-service")

async def check_database():
    try:
        db = next(get_db())
        try:
            db.execute(text("SELECT 1"))
            return True
        finally:
            db.close()
    except Exception:
        return False

health.add_dependency("postgres", check_database)
install_health_router(app, service_name="construction-service", health_check=health)
