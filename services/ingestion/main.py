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
    yield
    # Shutdown
    logger.info("ingestion_service_shutdown")

app = FastAPI(
    title="Ingestion Service",
    description="Regulatory document ingestion and processing",
    version="1.0.0",
    lifespan=lifespan,
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

# Global exception handlers (Sprint 18)
from shared.error_handling import install_exception_handlers
install_exception_handlers(app)

app.include_router(ingestion_router)

# Decomposed sub-routers (extracted from routes.py god file)
from app.routes_scraping import router as scraping_router
app.include_router(scraping_router)

from app.routes_discovery import router as discovery_router
app.include_router(discovery_router)

# Webhook Ingestion (V2: Postgres-backed CTE persistence)
from app.webhook_router_v2 import router as webhook_router
app.include_router(webhook_router)

# FDA 24-Hour Export
from app.fda_export_router import router as fda_export_router
app.include_router(fda_export_router)

# CSV Templates & Import
from app.csv_templates import router as csv_router
app.include_router(csv_router)

# IoT Import (Sensitech TempTale)
from app.sensitech_parser import router as sensitech_router
app.include_router(sensitech_router)

# EDI 856 Inbound
from app.edi_ingestion import router as edi_router
app.include_router(edi_router)

# Compliance Score
from app.compliance_score import router as score_router
app.include_router(score_router)

# Supplier Portal
from app.supplier_portal import router as portal_router
app.include_router(portal_router)

# Mock Audit Mode
from app.mock_audit import router as audit_router
app.include_router(audit_router)

# SOP Generator
from app.sop_generator import router as sop_router
app.include_router(sop_router)

# EPCIS & FDA Export
from app.epcis_export import router as export_router
app.include_router(export_router)

# EPCIS 2.0 Ingestion
from app.epcis_ingestion import router as epcis_ingestion_router
app.include_router(epcis_ingestion_router)

# QR / GS1 Decode
from app.qr_decoder import router as qr_decoder_router
app.include_router(qr_decoder_router)

# B2B Exchange API (EPCIS shipping package handoff)
from app.exchange_api import router as exchange_router
app.include_router(exchange_router)

# Stripe Billing
from app.stripe_billing import router as billing_router
app.include_router(billing_router)

# Alerts & Notifications
from app.alerts import router as alerts_router
app.include_router(alerts_router)

# Onboarding
from app.onboarding import router as onboarding_router
app.include_router(onboarding_router)

# Recall Readiness Report
from app.recall_report import router as recall_router
app.include_router(recall_router)

# Recall Simulations
from app.recall_simulations import router as recall_simulations_router
app.include_router(recall_simulations_router)

# Supplier Management
from app.supplier_mgmt import router as supplier_mgmt_router
app.include_router(supplier_mgmt_router)

# Audit Log
from app.audit_log import router as audit_log_router
app.include_router(audit_log_router)

# Product Catalog
from app.product_catalog import router as product_catalog_router
app.include_router(product_catalog_router)

# Notification Preferences
from app.notification_prefs import router as notification_prefs_router
app.include_router(notification_prefs_router)

# Team Management
from app.team_mgmt import router as team_mgmt_router
app.include_router(team_mgmt_router)

# Settings
from app.settings import router as settings_router
app.include_router(settings_router)

# Standardized Health & Readiness (Phase 17)
from shared.health import HealthCheck, install_health_router

health = HealthCheck(service_name="ingestion-service")
install_health_router(app, service_name="ingestion-service", health_check=health)

@app.get("/")
async def root():
    return {"message": "Ingestion Service Operational"}
