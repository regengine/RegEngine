from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sys
from pathlib import Path

# Standardized path discovery
_SERVICES_DIR = Path(__file__).resolve().parent.parent
_APP_ROOT = Path(__file__).resolve().parent

if str(_SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICES_DIR))
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

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

# Local imports (using absolute-style imports from app package)
from app.config import get_settings
settings = get_settings()
from app.routes import router as ingestion_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("ingestion_service_startup")
    yield
    # Shutdown
    logger.info("ingestion_service_shutdown")

app = FastAPI(
    title="Ingestion Service",
    description="Regulatory document ingestion and processing",
    version="1.0.0",
    lifespan=lifespan,
)

# Production Hardening Middleware (Phase 18)
add_security(app)
add_rate_limiting(app)
add_observability(app, service_name="ingestion-service")

from shared.middleware import TenantContextMiddleware, RequestIDMiddleware
from shared.tenant_rate_limiting import TenantRateLimitMiddleware

app.add_middleware(RequestIDMiddleware)
app.add_middleware(TenantContextMiddleware)
app.add_middleware(TenantRateLimitMiddleware, default_rpm=100)

# Global exception handlers (Sprint 18)
from shared.error_handling import install_exception_handlers
install_exception_handlers(app)

app.include_router(ingestion_router)

# Standardized Health & Readiness (Phase 17)
from shared.health import HealthCheck, install_health_router

health = HealthCheck(service_name="ingestion-service")
install_health_router(app, service_name="ingestion-service", health_check=health)

@app.get("/")
async def root():
    return {"message": "Ingestion Service Operational"}
