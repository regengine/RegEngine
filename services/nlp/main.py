from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sys
import threading
from pathlib import Path

# Add shared utilities
_SERVICES_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_SERVICES_DIR))
from shared.middleware import TenantContextMiddleware

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

app.add_middleware(TenantContextMiddleware)

app.include_router(nlp_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "nlp-service"}
