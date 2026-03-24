from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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

# Production Hardening (Phase 18)
from shared.logging import setup_logging
from shared.middleware.security import add_security
from shared.rate_limit import add_rate_limiting
from shared.observability import add_observability

# Initialize standardized logging
logger = setup_logging()

# Local imports (using absolute-style imports from app package)
from app.config import get_settings
settings = get_settings()
from app.routes import router as ingestion_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("ingestion_service_startup")
    # Register all integration connectors (best-effort: Kafka/external services
    # may be unavailable in CI or lightweight deployments)
    try:
        from shared.external_connectors.register_all import register_all_connectors
        register_all_connectors()
        logger.info("integration_connectors_registered")
    except Exception as exc:
        logger.warning("connector_registration_skipped: %s", exc)
    yield
    # Shutdown
    logger.info("ingestion_service_shutdown")

from shared.env import is_production
_is_prod = is_production()

app = FastAPI(
    title="Ingestion Service",
    description="Regulatory document ingestion and processing",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
)

allowed_origins = [
    origin.strip()
    for origin in settings.allowed_origins.split(",")
    if origin.strip()
]
if "*" in allowed_origins:
    allowed_origins = ["http://localhost:3000", "https://regengine.co", "https://www.regengine.co"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-RegEngine-API-Key",
        "X-Requested-With",
        "X-Request-ID",
    ],
)

# Production Hardening Middleware (Phase 18)
add_security(app)
add_rate_limiting(app)
add_observability(app, service_name="ingestion-service")

from shared.middleware import TenantContextMiddleware, RequestIDMiddleware
from shared.tenant_rate_limiting import TenantRateLimitMiddleware

app.add_middleware(RequestIDMiddleware)
app.add_middleware(TenantContextMiddleware)
app.add_middleware(TenantRateLimitMiddleware, default_rpm=100)

# API-01 / API-02: Request body size limit (10 MB) and global timeout (120s)
from shared.request_safety import RequestSizeLimitMiddleware, RequestTimeoutMiddleware
app.add_middleware(RequestSizeLimitMiddleware, max_bytes=10 * 1024 * 1024)
app.add_middleware(RequestTimeoutMiddleware, timeout_seconds=120)

# Global exception handlers (Sprint 18)
from shared.error_handling import install_exception_handlers
install_exception_handlers(app)

# ---------------------------------------------------------------------------
# Router Feature Flags — disable non-core routers via DISABLED_ROUTERS env var
# Comma-separated list of router names to skip, e.g.: "billing,mock_audit,recall_simulations"
# ---------------------------------------------------------------------------
import os as _os
_DISABLED_ROUTERS = {
    r.strip().lower()
    for r in _os.getenv("DISABLED_ROUTERS", "").split(",")
    if r.strip()
}


def _router_enabled(name: str) -> bool:
    """Check if a router should be mounted (not in DISABLED_ROUTERS)."""
    return name.lower() not in _DISABLED_ROUTERS


app.include_router(ingestion_router)

# Health & Metrics (extracted from routes.py, Finding #8)
from app.routes_health_metrics import router as health_metrics_router
app.include_router(health_metrics_router)


# Decomposed sub-routers (extracted from routes.py god file)
if _router_enabled("scraping"):
    from app.routes_scraping import router as scraping_router
    app.include_router(scraping_router)


if _router_enabled("discovery"):
    from app.routes_discovery import router as discovery_router
    app.include_router(discovery_router)

# Status, audit, and document query routes
from app.routes_status import router as status_router
app.include_router(status_router)

# Federal source ingestion (Federal Register, eCFR, openFDA)
if _router_enabled("sources"):
    from app.routes_sources import router as sources_router
    app.include_router(sources_router)

# Webhook Ingestion (V2: Postgres-backed CTE persistence)
from app.webhook_router_v2 import router as webhook_router
app.include_router(webhook_router)

# FDA 24-Hour Export
if _router_enabled("fda_export"):
    from app.fda_export_router import router as fda_export_router
    app.include_router(fda_export_router)


# CSV Templates & Import
if _router_enabled("csv"):
    from app.csv_templates import router as csv_router
    app.include_router(csv_router)


# IoT Import (Sensitech TempTale)
if _router_enabled("sensitech"):
    from app.sensitech_parser import router as sensitech_router
    app.include_router(sensitech_router)


# EDI 856 Inbound
if _router_enabled("edi"):
    from app.edi_ingestion import router as edi_router
    app.include_router(edi_router)


# Compliance Score
if _router_enabled("score"):
    from app.compliance_score import router as score_router
    app.include_router(score_router)


# Supplier Portal
if _router_enabled("portal"):
    from app.supplier_portal import router as portal_router
    app.include_router(portal_router)


# Mock Audit Mode
if _router_enabled("audit"):
    from app.mock_audit import router as audit_router
    app.include_router(audit_router)


# SOP Generator
if _router_enabled("sop"):
    from app.sop_generator import router as sop_router
    app.include_router(sop_router)


# EPCIS & FDA Export
if _router_enabled("export"):
    from app.epcis_export import router as export_router
    app.include_router(export_router)


# EPCIS 2.0 Ingestion
if _router_enabled("epcis_ingestion"):
    from app.epcis_ingestion import router as epcis_ingestion_router
    app.include_router(epcis_ingestion_router)


# QR / GS1 Decode
if _router_enabled("qr_decoder"):
    from app.qr_decoder import router as qr_decoder_router
    app.include_router(qr_decoder_router)


# Computer Vision — Label Analysis
if _router_enabled("label_vision"):
    from app.label_vision import router as label_vision_router
    app.include_router(label_vision_router)


# B2B Exchange API (EPCIS shipping package handoff)
if _router_enabled("exchange"):
    from app.exchange_api import router as exchange_router
    app.include_router(exchange_router)


# Stripe Billing
if _router_enabled("billing"):
    from app.stripe_billing import router as billing_router
    app.include_router(billing_router)


# Alerts & Notifications
if _router_enabled("alerts"):
    from app.alerts import router as alerts_router
    app.include_router(alerts_router)


# Onboarding
if _router_enabled("onboarding"):
    from app.onboarding import router as onboarding_router
    app.include_router(onboarding_router)


# Recall Readiness Report
if _router_enabled("recall"):
    from app.recall_report import router as recall_router
    app.include_router(recall_router)


# Recall Simulations
if _router_enabled("recall_simulations"):
    from app.recall_simulations import router as recall_simulations_router
    app.include_router(recall_simulations_router)


# Supplier Management
if _router_enabled("supplier_mgmt"):
    from app.supplier_mgmt import router as supplier_mgmt_router
    app.include_router(supplier_mgmt_router)


# Audit Log
if _router_enabled("audit_log"):
    from app.audit_log import router as audit_log_router
    app.include_router(audit_log_router)


# Product Catalog
if _router_enabled("product_catalog"):
    from app.product_catalog import router as product_catalog_router
    app.include_router(product_catalog_router)


# Notification Preferences
if _router_enabled("notification_prefs"):
    from app.notification_prefs import router as notification_prefs_router
    app.include_router(notification_prefs_router)


# Team Management
if _router_enabled("team_mgmt"):
    from app.team_mgmt import router as team_mgmt_router
    app.include_router(team_mgmt_router)


# Settings
if _router_enabled("settings"):
    from app.settings import router as settings_router
    app.include_router(settings_router)


# Integration Connectors (SafetyCulture, CSV/SFTP, retailers, IoT)
if _router_enabled("integration"):
    from app.integration_router import router as integration_router
    app.include_router(integration_router)

# Standardized Health & Readiness (Phase 17)
# NOTE: Custom /health endpoint already registered via routes_health_metrics.py
# which includes Kafka status. Do NOT install the Phase 17 generic health router
# here — it overwrites the custom endpoint and crashes without configured deps.
# from shared.health import HealthCheck, install_health_router
# health = HealthCheck(service_name="ingestion-service")
# install_health_router(app, service_name="ingestion-service", health_check=health)

@app.get("/")
async def root():
    return {"message": "Ingestion Service Operational"}
