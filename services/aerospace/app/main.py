"""
Aerospace Compliance Service - Main FastAPI application.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars
import sys
import uuid

# Add shared utilities to path
from pathlib import Path
_SERVICES_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_SERVICES_DIR))
from shared.middleware import TenantContextMiddleware
from shared.cors import get_allowed_origins, should_allow_credentials
from shared.correlation import CorrelationIdMiddleware, get_correlation_id
from shared.rate_limiting import create_limiter, setup_rate_limiting

from .config import settings
from .fai_vault import router as fai_router
from .logging_config import configure_logging

# Configure structured logging
configure_logging(log_level="INFO")
logger = structlog.get_logger("aerospace")


def get_allowed_origins():
    """Get allowed CORS origins from environment."""
    import os
    origins = os.getenv("CORS_ORIGINS", "*")
    return origins.split(",") if "," in origins else [origins]


def should_allow_credentials():
    """Determine if credentials should be allowed."""
    return True


# Create FastAPI app
app = FastAPI(
    title="RegEngine Aerospace Compliance Service",
    description="AS9102 FAI vault and configuration baseline tracking for AS9100 compliance",
    version=settings.SERVICE_VERSION,
    docs_url="/docs",
    redoc_url="/redoc"
)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Middleware to bind request_id to log context."""
    # Get or generate request_id/correlation_id
    request_id = request.headers.get("X-Request-ID") or request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    
    # Bind to structlog context
    bind_contextvars(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
    )
    
    try:
        response = await call_next(request)
        
        # Log request completion
        logger.info(
            "request_completed",
            status_code=response.status_code,
        )
        
        # Add request_id to response headers
        response.headers["X-Request-ID"] = request_id
        
        return response
    finally:
        # Clear context to prevent leakage
        clear_contextvars()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=should_allow_credentials(),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tenant isolation middleware - extracts tenant_id from JWT or headers
app.add_middleware(TenantContextMiddleware)

# Rate limiting
setup_rate_limiting(app)

# Include routers
app.include_router(fai_router)


# Startup and shutdown events
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


@app.get("/health")
async def health_check():
    """Health check endpoint for load balancers."""
    return {
        "status": "healthy",
        "service": settings.SERVICE_NAME,
        "version": settings.SERVICE_VERSION
    }


@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "RegEngine Aerospace Compliance Service",
        "version": settings.SERVICE_VERSION,
        "docs": "/docs",
        "health": "/health"
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=True
    )

