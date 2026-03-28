from contextlib import asynccontextmanager
import threading
import os

# --- Standardized Bootstrap ---
import sys
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

# Local package imports (using absolute-style imports from services root)
# Refers to services/nlp/app/...
from app.config import settings
from app.consumer import run_consumer, stop_consumer
from app.routes import router as nlp_router

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

@asynccontextmanager
async def lifespan(api_app: FastAPI):
    # Startup
    logger.info("nlp_service_startup")
    
    # Start consumer thread
    consumer_thread = threading.Thread(target=run_consumer, daemon=True)
    consumer_thread.start()
    logger.info("nlp_consumer_thread_started")
    
    yield
    
    # Shutdown
    logger.info("nlp_service_shutdown")
    stop_consumer()
    consumer_thread.join(timeout=5.0)

from shared.cors import get_allowed_origins, should_allow_credentials

from shared.env import is_production
_is_prod = is_production()

# Naming the instance 'app' is standard for uvicorn
app = FastAPI(
    title="RegEngine NLP Service",
    description="Regulatory text analysis, entity extraction, and semantic understanding for compliance document processing",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
)

# Production Hardening Middleware (Phase 18)
add_security(app)
add_rate_limiting(app)
add_observability(app, service_name="nlp-service")

from shared.middleware import TenantContextMiddleware, RequestIDMiddleware
from shared.tenant_rate_limiting import TenantRateLimitMiddleware

app.add_middleware(RequestIDMiddleware)
app.add_middleware(TenantContextMiddleware)
app.add_middleware(TenantRateLimitMiddleware, default_rpm=100)

# Global exception handlers (Sprint 18)
from shared.error_handling import install_exception_handlers
install_exception_handlers(app)

app.include_router(nlp_router, prefix="/api/v1", tags=["Text Analysis"])

# Standardized Health & Readiness (Phase 17)
from shared.health import HealthCheck, install_health_router

health = HealthCheck(service_name="nlp-service")
install_health_router(app, service_name="nlp-service", health_check=health)
