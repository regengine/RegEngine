"""
Gaming Compliance Service - Main FastAPI application.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog
import sys

from pathlib import Path
_SERVICES_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_SERVICES_DIR))
from shared.middleware import TenantContextMiddleware
from shared.cors import get_allowed_origins, should_allow_credentials

from .config import settings
from .transaction_vault import router as transaction_router
from .logging_config import configure_logging

# Configure structured logging
configure_logging(level=settings.LOG_LEVEL)
logger = structlog.get_logger("gaming_service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    logger.info(
        "gaming_service_startup",
        service=settings.SERVICE_NAME,
        version=settings.SERVICE_VERSION
    )
    
    yield
    
    # Shutdown
    logger.info("gaming_service_shutdown")


# Create FastAPI app
app = FastAPI(
    title="RegEngine Gaming Compliance Service",
    description="Immutable transaction logs and responsible gaming monitoring for casino regulatory compliance",
    version=settings.SERVICE_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=should_allow_credentials(),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tenant isolation middleware
app.add_middleware(TenantContextMiddleware)

# Include routers
app.include_router(transaction_router)


@app.get("/health")
async def health_check():
    """Health check endpoint for load balancers."""
    logger.debug("health_check_requested")
    return {
        "status": "healthy",
        "service": settings.SERVICE_NAME,
        "version": settings.SERVICE_VERSION
    }


@app.get("/")
async def root():
    """Root endpoint with service information."""
    logger.debug("root_endpoint_accessed")
    return {
        "service": "RegEngine Gaming Compliance Service",
        "version": settings.SERVICE_VERSION,
        "docs": "/docs",
        "health": "/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=True
    )
