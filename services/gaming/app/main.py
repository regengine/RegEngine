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
from .transaction_vault import router as transaction_router
from .config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("gaming_service_startup")
    yield
    # Shutdown
    logger.info("gaming_service_shutdown")

app = FastAPI(
    title="Gaming Compliance Service",
    description="International gaming and gambling regulatory engine",
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

app.include_router(transaction_router, prefix="/api/v1/gaming")

# Standardized Health & Readiness (Phase 17)
from shared.health import HealthCheck, install_health_router

health = HealthCheck(service_name="gaming-service")
install_health_router(app, service_name="gaming-service", health_check=health)
