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

# Production Hardening
from shared.middleware.security import add_security
from shared.rate_limit import add_rate_limiting
from shared.observability import add_observability
from shared.error_handling import install_exception_handlers
from shared.health import HealthCheck, install_health_router
from shared.middleware import RequestIDMiddleware
from shared.tenant_rate_limiting import TenantRateLimitMiddleware

from fastapi.middleware.cors import CORSMiddleware
from shared.cors import get_allowed_origins, should_allow_credentials

from app.routes import router as fsma_router

_is_prod = os.getenv("ENV", "").lower() == "production"

app = FastAPI(
    title="RegEngine FSMA 204 Compliance Service",
    version="1.0.0",
    description=(
        "FSMA 204 compliance API providing checklists, industry categories, "
        "and configuration validation for food traceability requirements."
    ),
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
)

# Production Hardening Middleware
add_security(app)
add_rate_limiting(app)
add_observability(app, service_name="compliance-service")

app.add_middleware(RequestIDMiddleware)
app.add_middleware(TenantRateLimitMiddleware, default_rpm=100)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=should_allow_credentials(),
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-RegEngine-API-Key", "X-Tenant-ID", "X-Request-ID"],
)

install_exception_handlers(app)


@app.get("/")
async def root() -> dict:
    return {
        "service": "compliance-api",
        "product": "RegEngine FSMA 204 Compliance Service",
        "version": app.version,
        "key_endpoints": {
            "industries": "/industries",
            "checklists": "/checklists",
            "validate": "/validate",
            "fda_audit_spreadsheet": "/v1/fsma/audit/spreadsheet",
        },
    }


app.include_router(fsma_router)

# Standardized Health & Readiness with dependency checks
from shared.health import check_postgres
health = HealthCheck(service_name="compliance-service")
health.add_dependency("postgres", check_postgres)
install_health_router(app, service_name="compliance-service", health_check=health)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8500)
