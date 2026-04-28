import os
import sys
from pathlib import Path

from fastapi import FastAPI

# --- Standardized Bootstrap ---
_SERVICE_DIR = Path(__file__).resolve().parent
_SERVICES_DIR = _SERVICE_DIR.parent
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))
if str(_SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICES_DIR))

from shared.paths import ensure_shared_importable
ensure_shared_importable()
# ------------------------------

from shared.env_validation import require_env
require_env("DATABASE_URL")

# Sentry error tracking (must be before app creation)
from shared.error_handling import init_sentry
init_sentry()

# Production Hardening
from shared.logging_config import configure_logging  # (#556) shared structured JSON logging
from shared.middleware.security import add_security
from shared.rate_limit import add_rate_limiting
from shared.observability import add_observability
from shared.observability.fastapi_metrics import install_metrics
from shared.error_handling import install_exception_handlers
from shared.observability.health import HealthCheck, install_health_router
from shared.middleware import RequestIDMiddleware
from shared.observability.correlation import CorrelationIdMiddleware
from shared.tenant_rate_limiting import TenantRateLimitMiddleware

# Initialize structured JSON logging before app/middleware creation
configure_logging(service_name="compliance-service")

from app.routes import router as fsma_router

from shared.env import is_production
_is_prod = is_production()

app = FastAPI(
    title="RegEngine FSMA 204 Compliance Service",
    version="1.0.0",
    description=(
        "FSMA 204 compliance API providing checklists, industry categories, "
        "and configuration validation for food traceability requirements."
    ),
    contact={"name": "RegEngine Support", "url": "https://github.com/regengine/RegEngine"},
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
)

# Production Hardening Middleware
add_security(app)
add_rate_limiting(app)
add_observability(app, service_name="compliance-service")

from fastapi.middleware.cors import CORSMiddleware
from shared.cors import get_allowed_origins, should_allow_credentials

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=should_allow_credentials(),
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-RegEngine-API-Key", "X-Request-ID", "X-Tenant-ID", "X-Correlation-ID"],
)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(TenantRateLimitMiddleware, default_rpm=100)

from shared.request_safety import RequestSizeLimitMiddleware, RequestTimeoutMiddleware
app.add_middleware(RequestSizeLimitMiddleware, max_bytes=10 * 1024 * 1024)
app.add_middleware(RequestTimeoutMiddleware, timeout_seconds=120)

# Correlation-ID middleware — registered last so it runs first (outermost). (#1316)
app.add_middleware(CorrelationIdMiddleware)

install_exception_handlers(app)

# Prometheus /metrics — RED metrics for every route, auth-guarded (#1325)
install_metrics(app, service_name="compliance-service")

from shared.auth import validate_auth_config
validate_auth_config()


@app.get("/")
async def root() -> dict:
    return {
        "service": "compliance-api",
        "product": "RegEngine FSMA 204 Compliance Service",
        "version": app.version,
        "key_endpoints": {
            "industries": "/industries",
            "checklists": "/checklists",
            # /validate was removed (#1203) — compliance rule evaluation is
            # handled by services/ingestion/app/rules_router.py via
            # services/shared/rules/engine.py.
            "fda_audit_spreadsheet": "/v1/fsma/audit/spreadsheet",
        },
    }


app.include_router(fsma_router)

# Standardized Health & Readiness
health = HealthCheck(service_name="compliance-service")
install_health_router(app, service_name="compliance-service", health_check=health)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8500)
