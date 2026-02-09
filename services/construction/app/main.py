"""
Construction Compliance Service - Main application.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sys

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars
import uuid
from fastapi import FastAPI, Request

from pathlib import Path
_SERVICES_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_SERVICES_DIR))
from shared.middleware import TenantContextMiddleware, RequestIDMiddleware
from shared.cors import get_allowed_origins, should_allow_credentials
from shared.rate_limiting import create_limiter, setup_rate_limiting

from .config import settings
from .bim_tracking import router as bim_router
from .logging_config import configure_logging

# Configure structured logging
configure_logging()
logger = structlog.get_logger(__name__)

# Create FastAPI app
app = FastAPI(
    title="RegEngine Construction Compliance Service",
    description="BIM change tracking and OSHA safety inspection management per 29 CFR 1926 for construction regulatory compliance",
    version=settings.SERVICE_VERSION,
    docs_url="/docs",
    redoc_url="/redoc"
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

# Rate limiting
setup_rate_limiting(app)

app.include_router(bim_router)


@app.get("/health")
async def health():
    """Health check endpoint for load balancers."""
    return {"status": "healthy", "service": settings.SERVICE_NAME, "version": settings.SERVICE_VERSION}





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
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "service": settings.SERVICE_NAME,
                "version": settings.SERVICE_VERSION,
                "database": "disconnected",
                "error": str(e)
            }
        )


@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "RegEngine Construction Compliance Service",
        "version": settings.SERVICE_VERSION,
        "docs": "/docs",
        "health": "/health",
        "ready": "/ready"
    }


@app.on_event("startup")
async def startup_event():
    """Log service startup."""
    logger.info("Service starting up", service=settings.SERVICE_NAME)


@app.on_event("shutdown")
async def shutdown_event():
    """Log service shutdown."""
    logger.info("Service shutting down", service=settings.SERVICE_NAME)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=True)
