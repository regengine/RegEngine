"""RegEngine Consolidated API — single FastAPI monolith.

Replaces 6 microservices (ingestion, admin, graph, nlp, compliance, scheduler)
with a single process using router boundaries to preserve decomposition seams.

Architecture decision: 2026-03-29
See: alembic/versions/20260329_task_queue_v050.py for Kafka replacement
"""
from __future__ import annotations

import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

# ── Path bootstrap ───────────────────────────────────────────────
# Ensure services/ and services/shared are importable
_APP_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _APP_DIR.parent
_SERVICES_DIR = _ROOT_DIR / "services"
_INGESTION_DIR = _SERVICES_DIR / "ingestion"
_ADMIN_DIR = _SERVICES_DIR / "admin"
_GRAPH_DIR = _SERVICES_DIR / "graph"
_NLP_DIR = _SERVICES_DIR / "nlp"
_COMPLIANCE_DIR = _SERVICES_DIR / "compliance"

for p in [
    str(_ROOT_DIR),
    str(_SERVICES_DIR),
    str(_INGESTION_DIR),
    str(_ADMIN_DIR),
    str(_GRAPH_DIR),
    str(_NLP_DIR),
    str(_COMPLIANCE_DIR),
]:
    if p not in sys.path:
        sys.path.insert(0, p)

from shared.paths import ensure_shared_importable
ensure_shared_importable()

# ── Sentry (before app creation) ─────────────────────────────────
from shared.error_handling import init_sentry
init_sentry()

# ── Logging ──────────────────────────────────────────────────────
from shared.observability.context import setup_logging
logger = setup_logging()

# ── Imports ──────────────────────────────────────────────────────
from fastapi import FastAPI

from shared.env import is_production
from shared.middleware.security import add_security
from shared.rate_limit import add_rate_limiting
from shared.observability import add_observability

_is_prod = is_production()


# ── Lifespan ─────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("regengine_startup", mode="monolith")

    # Initialize admin DB (RLS functions, no create_all)
    try:
        from services.admin.app.database import init_db
        init_db()
        logger.info("admin_database_initialized")
    except Exception as exc:
        logger.warning("admin_database_init_skipped", error=str(exc))

    # Register integration connectors (best-effort)
    try:
        from shared.external_connectors.register_all import register_all_connectors
        register_all_connectors()
        logger.info("integration_connectors_registered")
    except Exception as exc:
        logger.warning("connector_registration_skipped", error=str(exc))

    # Start background task worker (replaces Kafka consumers)
    from server.workers.task_processor import start_task_worker, stop_task_worker
    start_task_worker()

    # Register ingestion task handlers and start ingestion worker
    try:
        from services.ingestion.app.task_handlers_sources import register_source_handlers
        from services.ingestion.app.task_handlers_scraping import register_scraping_handlers
        from services.ingestion.app.task_handlers_discovery import register_discovery_handlers
        from services.ingestion.app.task_handlers_regulation import register_regulation_handlers
        from shared.task_queue import TaskWorker
        from shared.database import engine as _db_engine
        register_source_handlers()
        register_scraping_handlers()
        register_discovery_handlers()
        register_regulation_handlers()
        _ingestion_worker = TaskWorker(engine=_db_engine)
        _ingestion_worker.start()
        app.state.ingestion_worker = _ingestion_worker
        logger.info("ingestion_task_worker_started")
    except Exception as exc:
        logger.warning("ingestion_task_worker_start_failed", error=str(exc))
        app.state.ingestion_worker = None

    yield

    # Shutdown
    stop_task_worker()
    if getattr(app.state, "ingestion_worker", None):
        app.state.ingestion_worker.stop()
    logger.info("regengine_shutdown")


# ── App creation ─────────────────────────────────────────────────
app = FastAPI(
    title="RegEngine API",
    description="FSMA 204 Compliance Platform — consolidated API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
)


# ── Middleware stack ──────────────────────────────────────────────
# CORS is handled by add_security() via shared middleware (single source of truth).
add_security(app)
add_rate_limiting(app)
add_observability(app, service_name="regengine")

from shared.middleware import TenantContextMiddleware, RequestIDMiddleware
from shared.tenant_rate_limiting import TenantRateLimitMiddleware

app.add_middleware(RequestIDMiddleware)
app.add_middleware(TenantContextMiddleware)
app.add_middleware(TenantRateLimitMiddleware, default_rpm=200)

from shared.request_safety import RequestSizeLimitMiddleware, RequestTimeoutMiddleware
app.add_middleware(RequestSizeLimitMiddleware, max_bytes=10 * 1024 * 1024)
app.add_middleware(RequestTimeoutMiddleware, timeout_seconds=120)

from shared.error_handling import install_exception_handlers
install_exception_handlers(app)

from shared.auth import validate_auth_config
validate_auth_config()


# ── Router feature flags ─────────────────────────────────────────
_DISABLED_ROUTERS = {
    r.strip().lower()
    for r in os.getenv("DISABLED_ROUTERS", "").split(",")
    if r.strip()
}
_MOUNTED_ROUTERS: list[str] = []


def _router_enabled(name: str) -> bool:
    enabled = name.lower() not in _DISABLED_ROUTERS
    if enabled:
        _MOUNTED_ROUTERS.append(name.lower())
    return enabled


@app.get("/api/v1/features", tags=["system"])
async def list_enabled_features():
    return {"enabled": _MOUNTED_ROUTERS, "disabled": sorted(_DISABLED_ROUTERS)}


# =====================================================================
# DOMAIN: INGESTION — CTE events, document processing, webhooks
# =====================================================================
from services.ingestion.app.routes import router as ingestion_core_router
app.include_router(ingestion_core_router, tags=["Document Ingestion"])

from services.ingestion.app.routes_health_metrics import router as health_metrics_router
app.include_router(health_metrics_router, tags=["Health & Metrics"])

from services.ingestion.app.routes_status import router as status_router
app.include_router(status_router)

from services.ingestion.app.webhook_router_v2 import router as webhook_router
app.include_router(webhook_router, tags=["Webhooks"])

if _router_enabled("scraping"):
    from services.ingestion.app.routes_scraping import router as scraping_router
    app.include_router(scraping_router, tags=["Web Scraping"])

if _router_enabled("discovery"):
    from services.ingestion.app.routes_discovery import router as discovery_router
    app.include_router(discovery_router, tags=["Discovery"])

if _router_enabled("sources"):
    from services.ingestion.app.routes_sources import router as sources_router
    app.include_router(sources_router)

if _router_enabled("sandbox"):
    from services.ingestion.app.sandbox.router import router as sandbox_router
    app.include_router(sandbox_router)

if _router_enabled("inflow_workbench"):
    from services.ingestion.app.inflow_workbench import router as inflow_workbench_router
    app.include_router(inflow_workbench_router)

if _router_enabled("fda_export"):
    from services.ingestion.app.fda_export.router import router as fda_export_router
    app.include_router(fda_export_router, tags=["FDA Exports"])

if _router_enabled("csv"):
    from services.ingestion.app.csv_templates import router as csv_router
    app.include_router(csv_router, tags=["CSV Import"])

if _router_enabled("sensitech"):
    from services.ingestion.app.sensitech_parser import router as sensitech_router
    app.include_router(sensitech_router, tags=["IoT Ingestion"])

if _router_enabled("edi"):
    from services.ingestion.app.edi_ingestion import router as edi_router
    app.include_router(edi_router, tags=["EDI Ingestion"])

if _router_enabled("score"):
    from services.ingestion.app.compliance_score import router as score_router
    app.include_router(score_router, tags=["Compliance Scoring"])

if _router_enabled("portal"):
    from services.ingestion.app.supplier_portal import router as portal_router
    app.include_router(portal_router, tags=["Supplier Portal"])

if _router_enabled("audit"):
    from services.ingestion.app.mock_audit import router as audit_router
    app.include_router(audit_router, tags=["Audit"])

if _router_enabled("sop"):
    from services.ingestion.app.sop_generator import router as sop_router
    app.include_router(sop_router, tags=["SOP Generation"])

if _router_enabled("export"):
    from services.ingestion.app.epcis_export import router as export_router
    app.include_router(export_router, tags=["Data Export"])

if _router_enabled("epcis_ingestion"):
    from services.ingestion.app.epcis.router import router as epcis_ingestion_router
    app.include_router(epcis_ingestion_router, tags=["EPCIS"])

if _router_enabled("qr_decoder"):
    from services.ingestion.app.qr_decoder import router as qr_decoder_router
    app.include_router(qr_decoder_router, tags=["QR & GS1 Decoding"])

if _router_enabled("label_vision"):
    from services.ingestion.app.label_vision import router as label_vision_router
    app.include_router(label_vision_router, tags=["Computer Vision"])

if _router_enabled("exchange"):
    from services.ingestion.app.exchange_api import router as exchange_router
    app.include_router(exchange_router, tags=["B2B Exchange"])

if _router_enabled("billing"):
    from services.ingestion.app.stripe_billing import router as billing_router
    app.include_router(billing_router, tags=["Billing"])

if _router_enabled("alerts"):
    from services.ingestion.app.alerts import router as alerts_router
    app.include_router(alerts_router, tags=["Alerts"])

if _router_enabled("onboarding"):
    from services.ingestion.app.onboarding import router as onboarding_router
    app.include_router(onboarding_router, tags=["Onboarding"])

if _router_enabled("recall"):
    from services.ingestion.app.recall_report import router as recall_router
    app.include_router(recall_router, tags=["Recall Reporting"])

if _router_enabled("recall_simulations"):
    from services.ingestion.app.recall_simulations import router as recall_simulations_router
    app.include_router(recall_simulations_router, tags=["Recall Simulations"])

if _router_enabled("supplier_mgmt"):
    from services.ingestion.app.supplier_mgmt import router as supplier_mgmt_router
    app.include_router(supplier_mgmt_router, tags=["Supplier Management"])

if _router_enabled("audit_log"):
    from services.ingestion.app.audit_log import router as audit_log_router
    app.include_router(audit_log_router, tags=["Audit Logs"])

if _router_enabled("product_catalog"):
    from services.ingestion.app.product_catalog import router as product_catalog_router
    app.include_router(product_catalog_router, tags=["Product Catalog"])

if _router_enabled("notification_prefs"):
    from services.ingestion.app.notification_prefs import router as notification_prefs_router
    app.include_router(notification_prefs_router, tags=["Notifications"])

if _router_enabled("team_mgmt"):
    from services.ingestion.app.team_mgmt import router as team_mgmt_router
    app.include_router(team_mgmt_router, tags=["Team Management"])

if _router_enabled("settings"):
    from services.ingestion.app.settings import router as settings_router
    app.include_router(settings_router, tags=["Settings"])

if _router_enabled("integration"):
    from services.ingestion.app.integration_router import router as integration_router
    app.include_router(integration_router, tags=["Integration Connectors"])


# =====================================================================
# DOMAIN: COMPLIANCE CONTROL PLANE — rules, exceptions, workflow
# =====================================================================
if _router_enabled("canonical_records"):
    from services.ingestion.app.canonical_router import router as canonical_records_router
    app.include_router(canonical_records_router)

if _router_enabled("rules"):
    from services.ingestion.app.rules_router import router as rules_engine_router
    app.include_router(rules_engine_router)

if _router_enabled("exceptions"):
    from services.ingestion.app.exception_router import router as exception_queue_router
    app.include_router(exception_queue_router)

if _router_enabled("request_workflow"):
    from services.ingestion.app.request_workflow_router import router as request_workflow_router
    app.include_router(request_workflow_router)

if _router_enabled("identity"):
    from services.ingestion.app.identity_router import router as identity_resolution_router
    app.include_router(identity_resolution_router)

if _router_enabled("auditor"):
    from services.ingestion.app.auditor_router import router as auditor_review_router
    app.include_router(auditor_review_router)

if _router_enabled("compliance_metrics"):
    from services.ingestion.app.metrics_router import router as compliance_metrics_router
    app.include_router(compliance_metrics_router)

if _router_enabled("readiness"):
    from services.ingestion.app.readiness_router import router as readiness_wizard_router
    app.include_router(readiness_wizard_router)

if _router_enabled("incidents"):
    from services.ingestion.app.incident_router import router as incident_command_router
    app.include_router(incident_command_router)

if _router_enabled("chain_verification"):
    from services.ingestion.app.chain_verification_job import router as chain_verification_router
    app.include_router(chain_verification_router)

if _router_enabled("audit_export_log"):
    from services.ingestion.app.audit_export_log import router as audit_export_log_router
    app.include_router(audit_export_log_router)

if _router_enabled("sla_tracking"):
    from services.ingestion.app.sla_tracking import router as sla_tracking_router
    app.include_router(sla_tracking_router)

if _router_enabled("export_monitoring"):
    from services.ingestion.app.export_monitoring import router as export_monitoring_router
    app.include_router(export_monitoring_router)

if _router_enabled("supplier_validation"):
    from services.ingestion.app.supplier_validation import router as supplier_validation_router
    app.include_router(supplier_validation_router)

if _router_enabled("disaster_recovery"):
    from services.ingestion.app.disaster_recovery import router as disaster_recovery_router
    app.include_router(disaster_recovery_router)


# =====================================================================
# DOMAIN: ADMIN — tenant management, auth, overlay, supplier onboarding
# =====================================================================
if _router_enabled("admin"):
    from services.admin.app.routes import router as admin_router, v1_router as admin_v1_router
    from services.admin.app.api_overlay import router as overlay_router
    from services.admin.app.compliance_routes import router as admin_compliance_router
    app.include_router(admin_router, tags=["Admin"])
    app.include_router(admin_v1_router, tags=["Admin V1"])
    app.include_router(overlay_router, tags=["Compliance Overlay"])
    app.include_router(admin_compliance_router, tags=["Admin Compliance"])

    from services.admin.app.system_routes import router as system_router
    app.include_router(system_router, prefix="/v1", tags=["System"])

    from services.admin.app.auth_routes import router as auth_router
    app.include_router(auth_router, tags=["Auth"])

    from services.admin.app.invite_routes import router as invite_router
    app.include_router(invite_router, prefix="/v1", tags=["Invites"])

    from services.admin.app.user_routes import router as user_router
    app.include_router(user_router, prefix="/v1", tags=["Users"])

    from services.admin.app.supplier_onboarding_routes import router as supplier_onboarding_router
    app.include_router(supplier_onboarding_router, prefix="/v1", tags=["Supplier Onboarding"])

    from services.admin.app.supplier_facilities_routes import router as supplier_facilities_router
    app.include_router(supplier_facilities_router, prefix="/v1", tags=["Supplier Facilities"])

    from services.admin.app.supplier_compliance_routes import router as supplier_compliance_router
    app.include_router(supplier_compliance_router, prefix="/v1", tags=["Supplier Compliance"])

    from services.admin.app.supplier_funnel_routes import router as supplier_funnel_router
    app.include_router(supplier_funnel_router, prefix="/v1", tags=["Supplier Funnel"])

    from services.admin.app.bulk_upload.routes import router as bulk_upload_router
    app.include_router(bulk_upload_router, prefix="/v1/supplier/bulk-upload", tags=["Supplier Bulk Upload"])

    from services.admin.app.review_routes import router as review_router
    app.include_router(review_router, tags=["Review Queue"])

    from services.admin.app.audit_routes import router as admin_audit_router
    app.include_router(admin_audit_router, tags=["Admin Audit"])


# =====================================================================
# DOMAIN: GRAPH — knowledge graph, traceability, lot tracing
# =====================================================================
if _router_enabled("graph"):
    from services.graph.app.routes import router as graph_router
    app.include_router(graph_router, prefix="/api/v1", tags=["Graph Operations"])


# =====================================================================
# DOMAIN: NLP — text analysis, entity extraction
# =====================================================================
if _router_enabled("nlp"):
    from services.nlp.app.routes import router as nlp_router
    app.include_router(nlp_router, prefix="/api/v1", tags=["Text Analysis"])


# =====================================================================
# DOMAIN: FSMA COMPLIANCE — checklists, industries, validation
# =====================================================================
if _router_enabled("fsma_compliance"):
    from services.compliance.app.routes import router as fsma_router
    app.include_router(fsma_router, tags=["FSMA Compliance"])


# ── Root endpoint ────────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "service": "RegEngine API",
        "version": app.version,
        "mode": "consolidated",
    }


# ── Health check ─────────────────────────────────────────────────
@app.get("/health", tags=["system"])
async def health():
    """Lightweight liveness probe — always returns 200 if the process is up."""
    return {"status": "healthy", "service": "regengine"}


@app.get("/readiness", tags=["system"])
async def readiness():
    """Deep readiness probe — verifies critical dependencies.

    Returns 200 if all dependencies are reachable, 503 otherwise.
    Use this for load balancer health checks so traffic isn't routed
    to instances that can't actually serve requests.
    """
    import asyncio
    from fastapi.responses import JSONResponse

    checks: dict[str, dict] = {}

    # --- PostgreSQL ---
    try:
        from sqlalchemy import text, create_engine
        db_url = os.getenv("DATABASE_URL")
        if db_url:
            engine = create_engine(db_url, pool_pre_ping=True)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            engine.dispose()
            checks["postgres"] = {"status": "ok"}
        else:
            checks["postgres"] = {"status": "not_configured"}
    except Exception as exc:
        checks["postgres"] = {"status": "error", "error": str(exc)[:200]}

    # --- Redis ---
    try:
        import redis as _redis
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            r = _redis.from_url(redis_url, socket_connect_timeout=2)
            r.ping()
            r.close()
            checks["redis"] = {"status": "ok"}
        else:
            checks["redis"] = {"status": "not_configured"}
    except Exception as exc:
        checks["redis"] = {"status": "error", "error": str(exc)[:200]}

    # --- Neo4j ---
    try:
        from neo4j import GraphDatabase
        neo4j_uri = os.getenv("NEO4J_URI")
        if neo4j_uri:
            driver = GraphDatabase.driver(
                neo4j_uri,
                auth=(
                    os.getenv("NEO4J_USER", "neo4j"),
                    os.getenv("NEO4J_PASSWORD", ""),
                ),
            )
            driver.verify_connectivity()
            driver.close()
            checks["neo4j"] = {"status": "ok"}
        else:
            checks["neo4j"] = {"status": "not_configured"}
    except Exception as exc:
        checks["neo4j"] = {"status": "error", "error": str(exc)[:200]}

    # --- Determine overall status ---
    # Postgres is required; Redis and Neo4j are degraded but not fatal
    pg_ok = checks.get("postgres", {}).get("status") in ("ok", "not_configured")
    all_ok = all(c.get("status") != "error" for c in checks.values())

    if not pg_ok:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "service": "regengine",
                "checks": checks,
            },
        )

    return {
        "status": "ready" if all_ok else "degraded",
        "service": "regengine",
        "checks": checks,
    }
