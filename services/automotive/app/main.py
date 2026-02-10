"""
Automotive Compliance Service - Main FastAPI application.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog
import sys

# Add shared utilities
from pathlib import Path
_SERVICES_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_SERVICES_DIR))
from shared.middleware import TenantContextMiddleware, RequestIDMiddleware
from shared.cors import get_allowed_origins, should_allow_credentials
from shared.rate_limiting import create_limiter, setup_rate_limiting

from .config import settings
from .ppap_vault import router as ppap_router
from .logging_config import configure_logging

# Configure structured logging
configure_logging()
logger = structlog.get_logger("automotive")

# Create FastAPI app
app = FastAPI(
    title="RegEngine Automotive Compliance Service",
    description="PPAP vault and LPA tracking for IATF 16949 compliance",
    version=settings.SERVICE_VERSION,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=should_allow_credentials(),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request ID middleware
app.add_middleware(RequestIDMiddleware)

# Tenant isolation middleware
app.add_middleware(TenantContextMiddleware)

# Rate limiting
setup_rate_limiting(app)

# Include routers
app.include_router(ppap_router)


@app.get("/health")
async def health_check():
    """Health check endpoint for load balancers."""
    return {
        "status": "healthy",
        "service": settings.SERVICE_NAME,
        "version": settings.SERVICE_VERSION
    }





@app.get("/ready")
async def ready_check():
    """Readiness check endpoint that validates DB connectivity.
    
    Returns 503 if database is unreachable.
    """
    from fastapi import status
    from fastapi.responses import JSONResponse
    from sqlalchemy import text
    from .db_session import get_db
    
    try:
        # Get a database session
        db = next(get_db())
        try:
            # Execute a simple query to check connectivity
            db.execute(text("SELECT 1"))
            return {
                "status": "ready",
                "service": settings.SERVICE_NAME,
                "version": settings.SERVICE_VERSION,
                "database": "connected"
            }
        finally:
            db.close()
    except Exception as e:
        logger.error("readiness_check_failed", error=str(e))
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "service": settings.SERVICE_NAME,
                "version": settings.SERVICE_VERSION,
                "database": "disconnected",
                "error": type(e).__name__
            }
        )


@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "RegEngine Automotive Compliance Service",
        "version": settings.SERVICE_VERSION,
        "docs": "/docs",
        "health": "/health",
        "ready": "/ready"
    }


@app.on_event("startup")
async def startup_event():
    """Log service startup."""
    logger.info(
        "service_starting",
        service=settings.SERVICE_NAME,
        version=settings.SERVICE_VERSION,
        port=settings.PORT,
    )


@app.on_event("shutdown")
async def shutdown_event():
    """Log service shutdown."""
    logger.info(
        "service_shutting_down",
        service=settings.SERVICE_NAME,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=True
    )
