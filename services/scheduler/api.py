"""Scheduler Service Management API with rate limiting."""

from contextlib import asynccontextmanager
from typing import Optional, TYPE_CHECKING

import structlog
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Production Hardening
from shared.rate_limit import add_rate_limiting, limiter
from shared.metrics_auth import require_metrics_key
from shared.cors import get_allowed_origins

# Import only under type-checking to break the runtime circular import
# between api.py (imported by main.py) and SchedulerService (defined in
# main.py). Annotations stay stringified via the import alias.
if TYPE_CHECKING:
    from services.scheduler.main import SchedulerService

logger = structlog.get_logger("scheduler-api")

# Global reference to scheduler service (set by main)
_scheduler_service: Optional["SchedulerService"] = None


def set_scheduler_service(service: "SchedulerService") -> None:
    """Set the global scheduler service reference."""
    global _scheduler_service
    _scheduler_service = service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager."""
    logger.info("scheduler_api_startup")
    yield
    logger.info("scheduler_api_shutdown")


# Create FastAPI app
app = FastAPI(
    title="Scheduler Service Management API",
    description="Management and monitoring endpoints for regulatory scheduler",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Middleware stack
from shared.middleware.request_id import RequestIDMiddleware
from shared.observability.correlation import CorrelationIdMiddleware
from shared.observability.fastapi_metrics import install_metrics
from shared.tenant_rate_limiting import TenantRateLimitMiddleware
from shared.request_safety import RequestSizeLimitMiddleware, RequestTimeoutMiddleware

app.add_middleware(RequestIDMiddleware)
app.add_middleware(TenantRateLimitMiddleware, default_rpm=60)
app.add_middleware(RequestSizeLimitMiddleware, max_bytes=10 * 1024 * 1024)
app.add_middleware(RequestTimeoutMiddleware, timeout_seconds=120)

# Correlation-ID middleware — registered last so it runs first (outermost). (#1316)
app.add_middleware(CorrelationIdMiddleware)

add_rate_limiting(app)

# Global exception handlers
from shared.error_handling import install_exception_handlers
install_exception_handlers(app)

# Prometheus RED metrics (#1325). The scheduler's own /metrics endpoint below
# serves the default registry via generate_latest(), so we instrument the app
# without exposing a second endpoint to avoid a route collision.
install_metrics(app, service_name="scheduler-service", metrics_path=None)


@app.get("/health")
@limiter.limit("100/minute")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "scheduler",
        "version": "1.0.0"
    }


@app.get("/status", dependencies=[Depends(require_metrics_key)])
@limiter.limit("30/minute")
async def status():
    """Get detailed scheduler status with circuit breaker states.

    Requires METRICS_API_KEY authentication. Rate limited to 30 req/min.
    """
    if _scheduler_service is None:
        return {"status": "starting", "service": "scheduler"}

    return {
        "status": "running",
        "service": "scheduler",
        "circuit_breakers": _scheduler_service.circuit_registry.get_all_status(),
        "last_scrapes": {
            st.value: {
                "success": r.success,
                "count": r.items_found,
                "scraped_at": r.scraped_at.isoformat(),
                "error": r.error_message if not r.success else None
            }
            for st, r in _scheduler_service.last_results.items()
        },
    }


@app.get("/metrics", dependencies=[Depends(require_metrics_key)])
@limiter.limit("100/minute")
async def metrics():
    """Get Prometheus metrics."""
    if _scheduler_service is None:
        return {"metrics": "service not initialized"}

    from app.metrics import metrics as metrics_instance
    content = metrics_instance.get_metrics()

    from fastapi.responses import Response
    return Response(content=content, media_type="text/plain; charset=utf-8")
