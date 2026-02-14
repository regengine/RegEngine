from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sys
import threading
from pathlib import Path

# Add shared utilities — centralised path resolution
from pathlib import Path as _P
_shared = str(_P(__file__).resolve().parent.parent / "shared")
if _shared not in sys.path:
    sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
from shared.paths import ensure_shared_importable
ensure_shared_importable()
from shared.middleware import TenantContextMiddleware, RequestIDMiddleware
from shared.tenant_rate_limiting import TenantRateLimitMiddleware

from app.config import settings
from app.consumer import run_consumer, stop_consumer
from app.routes import router as nlp_router

logger = structlog.get_logger("nlp_service")


@asynccontextmanager
async def lifespan(app: FastAPI):
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

app = FastAPI(
    title="NLP Service",
    description="Regulatory text analysis and entity extraction",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=should_allow_credentials(),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestIDMiddleware)
app.add_middleware(TenantContextMiddleware)
app.add_middleware(TenantRateLimitMiddleware, default_rpm=100)

# Global exception handlers (Sprint 18)
from shared.error_handling import install_exception_handlers
install_exception_handlers(app)

app.include_router(nlp_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "nlp-service"}

@app.get("/ready")
async def readiness():
    return {"status": "ready", "service": "nlp-service"}
