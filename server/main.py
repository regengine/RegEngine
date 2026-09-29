"""RegEngine Consolidated API — single FastAPI monolith.

Replaces 6 microservices (ingestion, admin, graph, nlp, compliance, scheduler)
with a single process using router boundaries to preserve decomposition seams.

Architecture decision: 2026-03-29
See: alembic/versions/20260329_task_queue_v050.py for Kafka replacement
"""

from __future__ import annotations

import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from threading import BoundedSemaphore

os.environ.setdefault("USER_AGENT", "RegEngine/1.0 (+https://regengine.com)")

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
from fastapi import Depends, FastAPI, Request
from shared.env import is_production
from shared.middleware.security import add_security
from shared.observability import add_observability
from shared.rate_limit import add_rate_limiting

from services.admin.app.e2e_safety import assert_e2e_mode_allowed

assert_e2e_mode_allowed()
_is_prod = is_production()


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# ── Lifespan ─────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("regengine_startup", mode="monolith")

    # #2348: warn at boot if document-storage credentials are absent —
    # /v1/ingest/{url,file,direct,regulation} return 503 until configured.
    # Best-effort: a probe failure must never abort monolith startup. NOTE the
    # fully-qualified import path (the standalone ingestion entrypoint uses the
    # service-relative ``app.s3_utils``; the monolith must not).
    try:
        from services.ingestion.app.s3_utils import is_object_storage_configured

        if not is_object_storage_configured():
            logger.warning(
                "object_storage_disabled",
                detail="/v1/ingest/* endpoints will return 503; set "
                "OBJECT_STORAGE_ACCESS_KEY_ID and OBJECT_STORAGE_SECRET_ACCESS_KEY to enable",
            )
    except Exception as exc:
        logger.warning("object_storage_probe_failed", error=str(exc))

    # Initialize admin DB (RLS posture probe + SQLite dev tables; all
    # PostgreSQL DDL, including the RLS helper functions, is Alembic-owned)
    try:
        from services.admin.app.database import init_db

        init_db()
        logger.info("admin_database_initialized")
    except Exception as exc:
        logger.warning("admin_database_init_skipped", error=str(exc))

    # Fail before serving traffic if live Postgres drift would break
    # tenant isolation, the tamper-evident audit hash chain, or auth.
    #
    # Add a Base to this block only when (a) the table is read or
    # mutated by the monolith in steady-state production traffic AND
    # (b) its declared types are load-bearing for tenant isolation,
    # audit integrity, or auth correctness. The check is cheap at
    # startup and catches Alembic-vs-ORM drift that a text-only review
    # cannot see (e.g. UUID column declared as String in the ORM).
    from shared.db_type_assertions import verify_orm_db_type_alignment

    from services.admin.app.database import _engine as _admin_engine
    from services.admin.app.sqlalchemy_models import Base as _admin_base

    verify_orm_db_type_alignment(_admin_engine, _admin_base)

    # api_keys is the authentication surface for every per-tenant
    # request. Drift here silently breaks key validation — much
    # cheaper to fail startup than diagnose a prod 500 storm.
    from shared.api_key_store import Base as _api_key_base
    from shared.database import engine as _shared_engine

    verify_orm_db_type_alignment(_shared_engine, _api_key_base)

    # Canonical FSMA operator persistence (WS-2c): ingestion_runs,
    # ingestion_run_receipts, agent_artifacts, agent_artifact_reviews.
    # Every row is tenant-scoped by a UUID tenant_id that RLS predicates
    # cast — a type drift here is a tenant-isolation break, the same
    # protected class as the admin tables above. Read and mutated in
    # steady state by the ingestion spine and the operator review view.
    from shared.agent_operator_models import Base as _agent_operator_base

    verify_orm_db_type_alignment(_shared_engine, _agent_operator_base)

    # Register integration connectors (best-effort)
    try:
        from shared.external_connectors.register_all import register_all_connectors

        register_all_connectors()
        logger.info("integration_connectors_registered")
    except Exception as exc:
        logger.warning("connector_registration_skipped", error=str(exc))

    # Whether the optional TypeSafe Jev integration is live, so an operator
    # can confirm a newly added TYPESAFE_API_KEY from the deploy logs without
    # reading the variable. Logs switches only, never the key. Through stdlib
    # logging, like registered_connector: the structlog chain drops INFO
    # events without a sampled trace when LOG_ALL_SAMPLED_OUT=false
    # (sampling_aware_filter), and startup has no trace.
    try:
        from shared.jev import JevSettings

        summary = JevSettings.from_env().public_summary()
        logging.getLogger("jev").info(
            "jev_configured %s", " ".join(f"{name}={value}" for name, value in summary.items())
        )
    except Exception as exc:
        logger.warning("jev_config_probe_failed", error=str(exc))

    # Runtime DB-role gate. Production always fails closed if either role is
    # unknown, unexpected, SUPERUSER/BYPASSRLS, or connected to a different
    # PostgreSQL database. REGENGINE_REQUIRE_RLS_ENFORCEMENT=1 keeps the same
    # hard gate available in staging before promotion.
    from shared.database import validate_runtime_database_posture

    validate_runtime_database_posture(_shared_engine, _admin_engine)

    # #2854: GDPR / FSMA audit events must join the hash chain, not an
    # in-process list discarded on every Railway restart.
    from shared.audit_logging import AuditLogger, PostgresHashChainAuditStorage

    AuditLogger.configure(
        storage=PostgresHashChainAuditStorage(),
        environment="production" if _is_prod else "development",
        service_name="regengine",
    )

    # #2883: fill user_emails.email_fingerprint left NULL when v094 ran
    # without AUTH_OTP_HMAC_SECRET. Idempotent. Unset secret is a no-op in
    # non-production and a startup RuntimeError in production (same as v094).
    try:
        from services.admin.app.auth.fingerprint_repair import repair_null_email_fingerprints

        repaired = repair_null_email_fingerprints()
        if repaired:
            logger.info("email_fingerprint_repair_applied", rows=repaired)
    except RuntimeError:
        raise
    except Exception as exc:
        if _is_prod:
            raise
        logger.warning("email_fingerprint_repair_skipped", error=str(exc))

    # Authentication is a hard production dependency: Redis-backed JWT
    # revocation and the signing-key registry must be ready before any worker
    # or request handler can issue/accept credentials. The admin-owned runtime
    # is shared with the legacy entrypoint so the consolidated deploy cannot
    # silently omit revocation wiring.
    from services.admin.app.auth_runtime import initialize_auth_runtime, shutdown_auth_runtime

    auth_runtime = await initialize_auth_runtime()

    # Start background task worker (replaces Kafka consumers). Everything
    # after auth-runtime initialization is inside this lifecycle guard so a
    # later startup failure still detaches and closes the Redis client.
    from server.workers.task_processor import start_task_worker, stop_task_worker

    try:
        start_task_worker()

        # Register only the task handlers whose HTTP surface is enabled, then
        # start the ingestion worker.  Optional routers are intentionally
        # absent from production; leaving their queue handlers registered
        # would preserve an internal path to disabled scraping/discovery/source
        # fetchers through stale or forged task rows.
        try:
            from shared.task_queue import TaskWorker

            from services.admin.app.database import get_admin_engine

            _register_ingestion_task_handlers()
            _ingestion_worker = TaskWorker(engine=get_admin_engine())
            # #2518: keep the daemon thread handle so /readiness can tell a live
            # worker from one whose loop died after start.
            _ingestion_worker_thread = _ingestion_worker.start()
            app.state.ingestion_worker = _ingestion_worker
            app.state.ingestion_worker_thread = _ingestion_worker_thread
            # #2518: record the start outcome so /readiness can report a swallowed
            # boot failure instead of silently passing while ingestion jobs pile up.
            app.state.ingestion_worker_started = True
            logger.info("ingestion_task_worker_started")
        except Exception as exc:
            # #2518: escalate to error (Sentry-captured) — a swallowed worker-start
            # failure used to vanish into warning noise while /readiness stayed green.
            logger.error("ingestion_task_worker_start_failed", error=str(exc))
            app.state.ingestion_worker = None
            app.state.ingestion_worker_thread = None
            app.state.ingestion_worker_started = False

        # Run scheduler jobs in-process: FDA scrapers, recall→tenant alerting,
        # deadline monitoring, retention/archival, nightly FSMA sync. Production
        # has no other home for these — the standalone scheduler entrypoint is
        # prod-blocked and this is the only deployed container. A Postgres
        # advisory lock keeps execution single-flight across gunicorn workers
        # and replicas (see server/workers/embedded_scheduler.py).
        try:
            from server.workers.embedded_scheduler import start_embedded_scheduler

            app.state.embedded_scheduler = start_embedded_scheduler()
            # #2518: distinguish "started" from "intentionally disabled". The
            # runner is None when SCHEDULER_EMBEDDED=0 / non-production — that is a
            # healthy state, not a failure. Only a raised exception is a failure.
            app.state.embedded_scheduler_started = True
        except Exception as exc:
            # #2518: escalate to error (Sentry-captured). A swallowed scheduler-start
            # failure silently disables FDA scrapers, recall→tenant alerting,
            # deadline monitoring, retention/archival, and the nightly FSMA sync —
            # none of which have another execution home in production.
            logger.error("embedded_scheduler_start_failed", error=str(exc))
            app.state.embedded_scheduler = None
            app.state.embedded_scheduler_started = False

        yield
    finally:

        async def _shutdown_step(name: str, operation) -> None:
            try:
                result = operation()
                if hasattr(result, "__await__"):
                    await result
            except Exception as exc:
                logger.error("regengine_shutdown_step_failed", step=name, error=str(exc))

        await _shutdown_step("stop_task_worker", stop_task_worker)
        ingestion_worker = getattr(app.state, "ingestion_worker", None)
        if ingestion_worker is not None:
            await _shutdown_step("stop_ingestion_worker", ingestion_worker.stop)
        embedded_scheduler = getattr(app.state, "embedded_scheduler", None)
        if embedded_scheduler is not None:
            await _shutdown_step("stop_embedded_scheduler", embedded_scheduler.stop)
        from services.admin.app.api_key_admin_store import close_admin_api_key_store

        await _shutdown_step("close_admin_api_key_store", close_admin_api_key_store)
        await _shutdown_step("shutdown_auth_runtime", lambda: shutdown_auth_runtime(auth_runtime))
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

from shared.middleware import RequestIDMiddleware, TenantContextMiddleware
from shared.tenant_rate_limiting import TenantRateLimitMiddleware

from services.admin.app.audit_middleware import AuditContextMiddleware

# Middleware is registered in reverse execution order. RequestIDMiddleware is
# added after AuditContextMiddleware so it establishes request.state.request_id
# first; the audit layer then reuses that ID and applies trusted-proxy source-IP
# resolution to privileged routes.
app.add_middleware(AuditContextMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(TenantContextMiddleware)
# default_rpm=100 matches the consolidated services (ingestion/compliance/nlp/
# graph all use 100) and the documented production default. The monolith is the
# union of those services, so the stricter ceiling is the correct floor.
# Operators can still raise it per-deploy via TENANT_RATE_LIMIT_RPM.
app.add_middleware(TenantRateLimitMiddleware, default_rpm=100)
# Issue #2307: surface X-RateLimit-* headers on 2xx responses by mirroring
# ``request.state.rate_limit_*`` (populated by authz/routes_ingest/webhook
# rate-limit guards) onto the outbound response. Read-only: never consumes
# the bucket, so no double-counting.
from services.ingestion.app.middleware import RateLimitHeadersMiddleware

app.add_middleware(RateLimitHeadersMiddleware)

from shared.request_safety import RequestSizeLimitMiddleware, RequestTimeoutMiddleware

app.add_middleware(RequestSizeLimitMiddleware, max_bytes=10 * 1024 * 1024)
app.add_middleware(RequestTimeoutMiddleware, timeout_seconds=120)

# #1232 — wire the shared IdempotencyMiddleware so webhook_router_v2
# (and every other POST endpoint) de-duplicates retried requests via the
# ``Idempotency-Key`` header. Cache keys are tenant-scoped (#1237) so
# two tenants can safely pick the same key.
from shared.idempotency import IdempotencyMiddleware

app.add_middleware(IdempotencyMiddleware)

# EPIC-I (#1316): correlation-id middleware. Registered last so Starlette's
# reverse-LIFO middleware stack runs it FIRST — every downstream handler,
# logger, and outbound call sees the X-Correlation-ID header value via
# request.state.correlation_id. Not redundant with RequestIDMiddleware:
# that one manages X-Request-ID / request_id_ctx (per-hop ID), while this
# one manages X-Correlation-ID / correlation_id_ctx (end-to-end trace ID
# consumed by kafka_propagation, Sentry scope hooks, and log_config).
from shared.observability.correlation import CorrelationIdMiddleware

app.add_middleware(CorrelationIdMiddleware)


# Stamp the FSMA-204 traceability marker on every response. The standalone
# admin service applied this via @app.middleware; per-app middleware does not
# propagate through include_router, so admin routes mounted here would
# otherwise drop the header. Added last → outermost → always applied on the
# way out.
@app.middleware("http")
async def add_compliance_header(request, call_next):
    response = await call_next(request)
    response.headers["X-FSMA-204-Traceability"] = "true"
    return response


from shared.error_handling import install_exception_handlers

install_exception_handlers(app)

from shared.auth import validate_auth_config

validate_auth_config()

# #1325: mount Prometheus RED metrics on /metrics for the monolith. add_security/
# add_observability above wire CORS + OTel tracing but NOT the Prometheus
# endpoint — install_metrics is the single source of truth for /metrics across
# every RegEngine app, and the monolith (the only deployed container) was the
# lone entrypoint missing it. Auth-guarded (X-Metrics-Key / METRICS_API_KEY),
# idempotent, and /metrics is TrustedHost-exempt. Called before include_router
# to mirror the five per-service entrypoints.
from shared.observability import install_metrics

from server.route_ownership import claim_existing_operation, include_owned_router, owned_api_route

install_metrics(app, service_name="regengine")
claim_existing_operation(app, owner="metrics", method="GET", path="/metrics")


# ── Router feature flags ─────────────────────────────────────────
from server.router_policy import COMPLIANCE_ROUTERS, VALID_ROUTER_NAMES, RouterPolicy

_ROUTER_POLICY = RouterPolicy.from_environment(production=_is_prod)
_MOUNTED_ROUTERS = _ROUTER_POLICY.mounted_routers

if _ROUTER_POLICY.unknown_disabled:
    logger.error(
        "unknown_router_names_in_DISABLED_ROUTERS",
        unknown=sorted(_ROUTER_POLICY.unknown_disabled),
        valid=sorted(VALID_ROUTER_NAMES),
    )

_disabled_compliance = _ROUTER_POLICY.configured_disabled & COMPLIANCE_ROUTERS
if _disabled_compliance:
    logger.critical(
        "compliance_routers_disabled",
        disabled=sorted(_disabled_compliance),
        hint="ALLOW_DISABLE_COMPLIANCE_ROUTERS is set. System running in degraded compliance mode.",
    )


def _router_enabled(name: str) -> bool:
    return _ROUTER_POLICY.enable(name)


def _subsystem_active(name: str) -> bool:
    """Pure predicate used by readiness after app construction."""
    return _ROUTER_POLICY.is_enabled(name)


def _register_ingestion_task_handlers() -> frozenset[str]:
    """Register queue consumers for the release-enabled ingestion surface.

    Core regulation ingestion and the FSMA agent bridge are always-mounted
    surfaces.  Source adapters, scraping, and discovery are optional routers;
    their task handlers must be absent whenever the corresponding router is
    disabled so a queue row cannot bypass the HTTP exposure policy.
    """
    from shared.agent_task_bridge import AGENT_ARTIFACT_TASK_TYPE, register_agent_bridge_handlers

    from services.ingestion.app.task_handlers_regulation import register_regulation_handlers

    registered = {"regulation_ingest", AGENT_ARTIFACT_TASK_TYPE}
    register_regulation_handlers()
    register_agent_bridge_handlers()

    if _ROUTER_POLICY.is_enabled("sources"):
        from services.ingestion.app.task_handlers_sources import register_source_handlers

        register_source_handlers()
        registered.update({"federal_register_ingest", "ecfr_ingest", "fda_ingest"})

    if _ROUTER_POLICY.is_enabled("scraping"):
        from services.ingestion.app.task_handlers_scraping import register_scraping_handlers

        register_scraping_handlers()
        registered.update({"state_scrape", "generic_scrape"})

    if _ROUTER_POLICY.is_enabled("discovery"):
        from services.ingestion.app.task_handlers_discovery import register_discovery_handlers

        register_discovery_handlers()
        registered.add("discovery_scrape")

    logger.info("ingestion_task_handlers_registered", task_types=sorted(registered))
    return frozenset(registered)


# Issue #2517 — same diagnostic gate used by /v1/scheduler/status.
from shared.observability.metrics_auth import require_metrics_key


@owned_api_route(
    app,
    owner="features",
    path="/api/v1/features",
    methods=["GET"],
    tags=["system"],
    # Issue #2517 — the full router topology (enabled/disabled/experimental) is
    # reconnaissance-grade info that lets an anonymous caller fingerprint the
    # deployment's attack surface. Prod already nulls docs/redoc/openapi to
    # avoid exactly this; this endpoint must not re-open the same door.
    # Gated behind X-Metrics-Key (mirrors /v1/scheduler/status) and hidden from
    # the OpenAPI schema in non-prod.
    include_in_schema=False,
    dependencies=[Depends(require_metrics_key)],
)
async def list_enabled_features():
    return {
        "enabled": _MOUNTED_ROUTERS,
        "disabled": sorted(_ROUTER_POLICY.disabled_routers),
        "auto_disabled": sorted(_ROUTER_POLICY.auto_disabled_routers),
        "experimental_enabled": _ROUTER_POLICY.experimental_bypass_enabled,
    }


# =====================================================================
# DOMAIN: INGESTION — CTE events, document processing, webhooks
# =====================================================================
# services/ingestion/app/routes.py is a leftover aggregator with no APIRoute
# objects. Do not mount it: an empty always-on owner is an ungated place for
# new production routes to land without ENABLED_ROUTERS or a security policy.

# Ingest endpoints (extracted from routes.py — /v1/ingest, /v1/ingest/file,
# /v1/ingest/url, /v1/ingest/regulation). Mirrors services/ingestion/main.py.
from services.ingestion.app.routes_ingest import router as ingest_router

include_owned_router(app, ingest_router, owner="core_ingest", tags=["Document Ingestion"])

from services.ingestion.app.routes_health_metrics import router as health_metrics_router

include_owned_router(app, health_metrics_router, owner="health", tags=["Health & Metrics"])

from services.ingestion.app.routes_status import router as status_router

include_owned_router(app, status_router, owner="status")

from services.ingestion.app.webhook_router_v2 import router as webhook_router

include_owned_router(app, webhook_router, owner="webhook", tags=["Webhooks"])

if _router_enabled("scraping"):
    from services.ingestion.app.routes_scraping import router as scraping_router

    include_owned_router(app, scraping_router, owner="scraping", tags=["Web Scraping"])

if _router_enabled("discovery"):
    from services.ingestion.app.routes_discovery import router as discovery_router

    include_owned_router(app, discovery_router, owner="discovery", tags=["Discovery"])

if _router_enabled("sources"):
    from services.ingestion.app.routes_sources import router as sources_router

    include_owned_router(app, sources_router, owner="sources")

if _router_enabled("sandbox"):
    from services.ingestion.app.sandbox.router import router as sandbox_router

    include_owned_router(app, sandbox_router, owner="sandbox")

if _router_enabled("inflow_workbench"):
    from services.ingestion.app.inflow_workbench import router as inflow_workbench_router

    include_owned_router(app, inflow_workbench_router, owner="inflow_workbench")

if _router_enabled("fda_export"):
    from services.ingestion.app.fda_export.router import router as fda_export_router

    include_owned_router(app, fda_export_router, owner="fda_export", tags=["FDA Exports"])

if _router_enabled("proof_verify"):
    # Public hash-chain verifier. Tenantless, no auth, rate-limited.
    # Production-surface justification documented in the router docstring.
    from services.ingestion.app.proof_verify_router import router as proof_verify_router

    include_owned_router(app, proof_verify_router, owner="proof_verify", tags=["Public Proof"])

if _router_enabled("csv"):
    from services.ingestion.app.csv_templates import router as csv_router

    include_owned_router(app, csv_router, owner="csv", tags=["CSV Import"])

if _router_enabled("sensitech"):
    from services.ingestion.app.sensitech_parser import router as sensitech_router

    include_owned_router(app, sensitech_router, owner="sensitech", tags=["IoT Ingestion"])

if _router_enabled("edi"):
    from services.ingestion.app.edi_ingestion import router as edi_router

    include_owned_router(app, edi_router, owner="edi", tags=["EDI Ingestion"])

if _router_enabled("score"):
    from services.ingestion.app.compliance_score import router as score_router

    include_owned_router(app, score_router, owner="score", tags=["Compliance Scoring"])

if _router_enabled("portal"):
    from services.ingestion.app.supplier_portal import router as portal_router

    include_owned_router(app, portal_router, owner="portal", tags=["Supplier Portal"])

if _router_enabled("audit"):
    from services.ingestion.app.mock_audit import router as audit_router

    include_owned_router(app, audit_router, owner="audit", tags=["Audit"])

if _router_enabled("sop"):
    from services.ingestion.app.sop_generator import router as sop_router

    include_owned_router(app, sop_router, owner="sop", tags=["SOP Generation"])

if _router_enabled("export"):
    from services.ingestion.app.epcis_export import router as export_router

    include_owned_router(app, export_router, owner="export", tags=["Data Export"])

if _router_enabled("epcis_ingestion"):
    from services.ingestion.app.epcis.router import router as epcis_ingestion_router

    include_owned_router(app, epcis_ingestion_router, owner="epcis_ingestion", tags=["EPCIS"])

if _router_enabled("qr_decoder"):
    from services.ingestion.app.qr_decoder import router as qr_decoder_router

    include_owned_router(app, qr_decoder_router, owner="qr_decoder", tags=["QR & GS1 Decoding"])

if _router_enabled("label_vision"):
    from services.ingestion.app.label_vision import router as label_vision_router

    include_owned_router(app, label_vision_router, owner="label_vision", tags=["Computer Vision"])

if _router_enabled("exchange"):
    from services.ingestion.app.exchange_api import router as exchange_router

    include_owned_router(app, exchange_router, owner="exchange", tags=["B2B Exchange"])

if _router_enabled("billing"):
    from services.ingestion.app.stripe_billing import router as billing_router
    from services.ingestion.app.stripe_billing.routes import list_plans as _list_billing_plans

    include_owned_router(app, billing_router, owner="billing", tags=["Billing"])

    @owned_api_route(
        app,
        owner="billing",
        path="/billing/plans",
        methods=["GET"],
        tags=["Billing"],
        include_in_schema=False,
    )
    async def list_billing_plans_compat():
        return await _list_billing_plans()


if _router_enabled("alerts"):
    from services.ingestion.app.alerts import router as alerts_router

    include_owned_router(app, alerts_router, owner="alerts", tags=["Alerts"])

if _router_enabled("onboarding"):
    from services.ingestion.app.onboarding import router as onboarding_router

    include_owned_router(app, onboarding_router, owner="onboarding", tags=["Onboarding"])

if _router_enabled("recall"):
    from services.ingestion.app.recall_report import router as recall_router

    include_owned_router(app, recall_router, owner="recall", tags=["Recall Reporting"])

if _router_enabled("recall_simulations"):
    from services.ingestion.app.recall_simulations import router as recall_simulations_router

    include_owned_router(app, recall_simulations_router, owner="recall_simulations", tags=["Recall Simulations"])

if _router_enabled("proof_recall"):
    from services.ingestion.app.proof_recall_router import router as proof_recall_router

    include_owned_router(app, proof_recall_router, owner="proof_recall", tags=["Public Proof"])

if _router_enabled("supplier_mgmt"):
    from services.ingestion.app.supplier_mgmt import router as supplier_mgmt_router

    include_owned_router(app, supplier_mgmt_router, owner="supplier_mgmt", tags=["Supplier Management"])

if _router_enabled("audit_log"):
    from services.ingestion.app.audit_log import router as audit_log_router

    include_owned_router(app, audit_log_router, owner="audit_log", tags=["Audit Logs"])

if _router_enabled("product_catalog"):
    from services.ingestion.app.product_catalog import router as product_catalog_router

    include_owned_router(app, product_catalog_router, owner="product_catalog", tags=["Product Catalog"])

if _router_enabled("notification_prefs"):
    from services.ingestion.app.notification_prefs import router as notification_prefs_router

    include_owned_router(app, notification_prefs_router, owner="notification_prefs", tags=["Notifications"])

if _router_enabled("team_mgmt"):
    from services.ingestion.app.team_mgmt import router as team_mgmt_router

    include_owned_router(app, team_mgmt_router, owner="team_mgmt", tags=["Team Management"])

if _router_enabled("settings"):
    from services.ingestion.app.settings import router as settings_router

    include_owned_router(app, settings_router, owner="settings", tags=["Settings"])

if _router_enabled("integration"):
    from services.ingestion.app.integration_router import router as integration_router

    include_owned_router(app, integration_router, owner="integration", tags=["Integration Connectors"])


# =====================================================================
# DOMAIN: COMPLIANCE CONTROL PLANE — rules, exceptions, workflow
# =====================================================================
if _router_enabled("canonical_records"):
    from services.ingestion.app.canonical_router import router as canonical_records_router

    include_owned_router(app, canonical_records_router, owner="canonical_records")

if _router_enabled("rules"):
    from services.ingestion.app.rules_router import router as rules_engine_router

    include_owned_router(app, rules_engine_router, owner="rules")

if _router_enabled("exceptions"):
    from services.ingestion.app.exception_router import router as exception_queue_router

    include_owned_router(app, exception_queue_router, owner="exceptions")

if _router_enabled("remediation"):
    from services.ingestion.app.remediation.router import router as remediation_router
    from services.ingestion.app.remediation.supplier_router import (
        router as remediation_supplier_router,
    )

    include_owned_router(app, remediation_router, owner="remediation")
    include_owned_router(app, remediation_supplier_router, owner="remediation")

if _router_enabled("request_workflow"):
    from services.ingestion.app.request_workflow_router import router as request_workflow_router

    include_owned_router(app, request_workflow_router, owner="request_workflow")

if _router_enabled("identity"):
    from services.ingestion.app.identity_router import router as identity_resolution_router

    include_owned_router(app, identity_resolution_router, owner="identity")

if _router_enabled("auditor"):
    from services.ingestion.app.auditor_router import router as auditor_review_router

    include_owned_router(app, auditor_review_router, owner="auditor")

if _router_enabled("compliance_metrics"):
    from services.ingestion.app.metrics_router import router as compliance_metrics_router

    include_owned_router(app, compliance_metrics_router, owner="compliance_metrics")

if _router_enabled("readiness"):
    from services.ingestion.app.readiness_router import router as readiness_wizard_router

    include_owned_router(app, readiness_wizard_router, owner="readiness")

    # The compatibility readiness views belong to the approved readiness
    # surface; they must disappear with that owner instead of bypassing the
    # production allowlist as an unconditional mount.
    from services.ingestion.app.fsma_readiness_compat import router as fsma_readiness_compat_router

    include_owned_router(app, fsma_readiness_compat_router, owner="readiness")

if _router_enabled("incidents"):
    from services.ingestion.app.incident_router import router as incident_command_router

    include_owned_router(app, incident_command_router, owner="incidents")

if _router_enabled("chain_verification"):
    from services.ingestion.app.chain_verification_job import router as chain_verification_router

    include_owned_router(app, chain_verification_router, owner="chain_verification")

if _router_enabled("audit_export_log"):
    from services.ingestion.app.audit_export_log import router as audit_export_log_router

    include_owned_router(app, audit_export_log_router, owner="audit_export_log")

if _router_enabled("sla_tracking"):
    from services.ingestion.app.sla_tracking import router as sla_tracking_router

    include_owned_router(app, sla_tracking_router, owner="sla_tracking")

if _router_enabled("export_monitoring"):
    from services.ingestion.app.export_monitoring import router as export_monitoring_router

    include_owned_router(app, export_monitoring_router, owner="export_monitoring")

if _router_enabled("supplier_validation"):
    from services.ingestion.app.supplier_validation import router as supplier_validation_router

    include_owned_router(app, supplier_validation_router, owner="supplier_validation")

if _router_enabled("disaster_recovery"):
    from services.ingestion.app.disaster_recovery import router as disaster_recovery_router

    include_owned_router(app, disaster_recovery_router, owner="disaster_recovery")

# Inbound Email Ingestion (Postmark inbound-parse webhook). Not in
# COMPLIANCE_ROUTERS: unlike remediation/fda_export, disabling this cannot
# corrupt or hide already-ingested compliance data — it only stops accepting
# a new input channel. Not yet in PRODUCTION_ENABLED_ROUTERS — promoting it
# there is a deliberate release-gate decision, same as disaster_recovery/
# supplier_validation above.
if _router_enabled("email_ingest"):
    from services.ingestion.app.email_ingest.router import router as email_ingest_router

    include_owned_router(app, email_ingest_router, owner="email_ingest")


# =====================================================================
# DOMAIN: AGENT ORGANIZATION — pods, agent identities, inboxes, scoped keys
# =====================================================================
if _router_enabled("agent_org"):
    from shared.agent_org.router import router as agent_org_router

    include_owned_router(app, agent_org_router, owner="agent_org", tags=["Agent Organization"])


# =====================================================================
# DOMAIN: ADMIN — tenant management, auth, supplier onboarding
# =====================================================================
if _router_enabled("admin"):
    from services.admin.app.agent_review_routes import router as agent_review_router
    from services.admin.app.compliance_routes import router as admin_compliance_router
    from services.admin.app.routes import router as admin_router, v1_router as admin_v1_router

    # The service-local /health and /metrics compatibility handlers collide
    # with the consolidated app's canonical always-mounted endpoints. They
    # were unreachable (FastAPI dispatches the earlier route) and are excluded
    # explicitly so the production table has one owner per method/path.
    include_owned_router(
        app,
        admin_router,
        owner="admin",
        tags=["Admin"],
        excluded_operations={("GET", "/health"), ("GET", "/metrics")},
    )
    include_owned_router(app, admin_v1_router, owner="admin", tags=["Admin V1"])
    include_owned_router(app, admin_compliance_router, owner="admin", tags=["Admin Compliance"])
    include_owned_router(app, agent_review_router, owner="admin", prefix="/v1", tags=["Agent Reviews"])

    from services.admin.app.system_routes import router as system_router

    include_owned_router(app, system_router, owner="admin", prefix="/v1", tags=["System"])

    from services.admin.app.auth_routes import router as auth_router

    include_owned_router(app, auth_router, owner="admin", tags=["Auth"])

    from services.admin.app.admin.organizations_router import router as admin_organizations_router

    include_owned_router(app, admin_organizations_router, owner="admin")

    from services.admin.app.invite_routes import router as invite_router

    include_owned_router(app, invite_router, owner="admin", prefix="/v1", tags=["Invites"])

    from services.admin.app.user_routes import router as user_router

    include_owned_router(app, user_router, owner="admin", prefix="/v1", tags=["Users"])

    from services.admin.app.supplier_onboarding_routes import router as supplier_onboarding_router

    include_owned_router(app, supplier_onboarding_router, owner="admin", prefix="/v1", tags=["Supplier Onboarding"])

    from services.admin.app.supplier_facilities_routes import router as supplier_facilities_router

    include_owned_router(app, supplier_facilities_router, owner="admin", prefix="/v1", tags=["Supplier Facilities"])

    from services.admin.app.supplier_compliance_routes import router as supplier_compliance_router

    include_owned_router(app, supplier_compliance_router, owner="admin", prefix="/v1", tags=["Supplier Compliance"])

    from services.admin.app.supplier_funnel_routes import router as supplier_funnel_router

    include_owned_router(app, supplier_funnel_router, owner="admin", prefix="/v1", tags=["Supplier Funnel"])

    from services.admin.app.tenant_settings_routes import router as tenant_settings_router

    include_owned_router(app, tenant_settings_router, owner="admin", prefix="/v1", tags=["Tenant Settings"])

    from services.admin.app.bulk_upload.routes import router as bulk_upload_router

    include_owned_router(
        app,
        bulk_upload_router,
        owner="admin",
        prefix="/v1/supplier/bulk-upload",
        tags=["Supplier Bulk Upload"],
    )

    from services.admin.app.review_routes import router as review_router

    include_owned_router(app, review_router, owner="admin", tags=["Review Queue"])

    from services.admin.app.audit_routes import router as admin_audit_router

    include_owned_router(app, admin_audit_router, owner="admin", tags=["Admin Audit"])

    from services.admin.app.tool_verification_routes import router as tool_verification_router

    include_owned_router(app, tool_verification_router, owner="admin", tags=["Tool Verification"])

    from services.admin.app.erasure_routes import router as erasure_router

    include_owned_router(app, erasure_router, owner="admin", tags=["Account"])

    from services.admin.app.data_export_routes import router as data_export_router

    include_owned_router(app, data_export_router, owner="admin", tags=["Account"])


# =====================================================================
# DOMAIN: GRAPH — knowledge graph, traceability, lot tracing
# =====================================================================
if _router_enabled("graph"):
    from services.admin.app.api_overlay import router as overlay_router
    from services.graph.app.routes import router as graph_router

    include_owned_router(app, graph_router, owner="graph", prefix="/api/v1", tags=["Graph Operations"])
    # Overlay data lives in the same Neo4j boundary. It must remain absent
    # from production until graph is promoted with the required two-tenant
    # Neo4j matrix and functional route adapters.
    include_owned_router(app, overlay_router, owner="graph", tags=["Compliance Overlay"])


# =====================================================================
# DOMAIN: NLP — text analysis, entity extraction
# =====================================================================
if _router_enabled("nlp"):
    from services.nlp.app.routes import router as nlp_router

    # These service-local diagnostics collide with graph's earlier
    # compatibility paths in the broad development app and were therefore
    # unreachable. The consolidated /health and /metrics routes are canonical.
    include_owned_router(
        app,
        nlp_router,
        owner="nlp",
        prefix="/api/v1",
        tags=["Text Analysis"],
        excluded_operations={("GET", "/api/v1/health"), ("GET", "/api/v1/metrics")},
    )


# =====================================================================
# DOMAIN: FSMA COMPLIANCE — checklists, industries, validation
# =====================================================================
if _router_enabled("fsma_compliance"):
    from services.compliance.app.routes import router as fsma_router
    from services.compliance.app.snapshots import router as snapshots_router

    include_owned_router(app, fsma_router, owner="fsma_compliance", tags=["FSMA Compliance"])
    include_owned_router(app, snapshots_router, owner="fsma_compliance")


# ── Root endpoint ────────────────────────────────────────────────
@owned_api_route(app, owner="root", path="/", methods=["GET"])
async def root():
    return {
        "service": "RegEngine API",
        "version": app.version,
        "mode": "consolidated",
    }


# ── Scheduler diagnostic ─────────────────────────────────────────
# #1255: restore the standalone scheduler's X-Metrics-Key-gated /status
# surface (circuit breakers + per-source last-scrape state). Mounted
# unconditionally — the embedded scheduler runs in-process, not behind a
# router feature flag.
from server.routes_scheduler_status import router as scheduler_status_router

include_owned_router(app, scheduler_status_router, owner="scheduler")


# ── Health check ─────────────────────────────────────────────────
_READINESS_TIMEOUT_SECONDS = 8.0
# Driver calls can outlive the request deadline (for example stalled DNS).
# Bound admission before submitting, and retain the slot until the underlying
# future finishes, even when the HTTP request times out or is cancelled.
_READINESS_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="readiness")
_READINESS_SLOTS = BoundedSemaphore(2)


def _submit_readiness_probe(request: Request):
    slots = _READINESS_SLOTS
    if not slots.acquire(blocking=False):
        return None
    try:
        future = _READINESS_EXECUTOR.submit(_readiness_checks, request)
    except Exception:
        slots.release()
        raise
    future.add_done_callback(lambda _: slots.release())
    return future


@owned_api_route(app, owner="health", path="/readiness", methods=["GET"], tags=["system"])
async def readiness(request: Request):
    """Bounded dependency readiness; /health remains the liveness endpoint."""
    import asyncio

    from fastapi.responses import JSONResponse

    future = _submit_readiness_probe(request)
    if future is None:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "service": "regengine",
                "checks": {"probe": {"status": "error", "error": "dependency probe capacity exhausted"}},
            },
        )
    try:
        return await asyncio.wait_for(
            asyncio.wrap_future(future),
            timeout=_READINESS_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "service": "regengine",
                "checks": {"probe": {"status": "error", "error": "dependency probe timed out"}},
            },
        )


def _readiness_checks(request: Request):
    """Run synchronous drivers off the event loop with driver-level bounds.

    Postgres is required everywhere. Redis is required in strict deployed
    runtimes, matching auth and checkout enforcement. Neo4j and background
    runners remain optional: their failures report degraded with HTTP 200.
    """
    from fastapi.responses import JSONResponse

    checks: dict[str, dict] = {}

    # --- PostgreSQL ---
    try:
        from sqlalchemy import create_engine, text

        db_url = os.getenv("DATABASE_URL")
        if db_url:
            connect_args = {}
            if db_url.startswith(("postgresql:", "postgresql+psycopg:", "postgresql+psycopg2:", "postgres:")):
                connect_args = {"connect_timeout": 2, "options": "-c statement_timeout=2000"}
            engine = create_engine(db_url, pool_pre_ping=True, connect_args=connect_args)
            try:
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
            finally:
                engine.dispose()
            checks["postgres"] = {"status": "ok"}
        else:
            checks["postgres"] = {"status": "not_configured"}
    except Exception as exc:
        checks["postgres"] = {"status": "error", "error": type(exc).__name__}

    # --- Redis ---
    try:
        import redis as _redis

        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            from redis.backoff import NoBackoff
            from redis.retry import Retry

            r = _redis.from_url(
                redis_url,
                socket_connect_timeout=2,
                socket_timeout=2,
                retry=Retry(NoBackoff(), 0),
            )
            try:
                r.ping()
            finally:
                r.close()
            checks["redis"] = {"status": "ok"}
        else:
            checks["redis"] = {"status": "not_configured"}
    except Exception as exc:
        checks["redis"] = {"status": "error", "error": type(exc).__name__}

    # --- Neo4j (optional graph mirror — never fatal to readiness) ---
    # WS-6: only probe Neo4j when the graph subsystem is actually mounted.
    # The graph routers are release-disabled in production (excluded from
    # ENABLED_ROUTERS), yet NEO4J_URI is set in prod for the
    # best-effort admin supplier-graph mirror. Probing a mirror that no
    # mounted route reads only adds latency to every Railway healthcheck and
    # would flip the deploy-gating payload to ``degraded`` on a Neo4j blip
    # for a subsystem nobody is serving. When graph is disabled we report
    # ``not_probed`` (informational; not an error, so it never degrades). The
    # admin mirror's own health stays observable via its runtime
    # shared.circuit_breaker.neo4j_circuit metrics, not this deploy gate.
    #
    # When the graph subsystem IS active, probe with bounded timeouts: the
    # driver defaults to a 30s connect / 60s acquisition timeout, so without
    # them an unreachable Neo4j hangs the probe long enough to fail the
    # Railway healthcheck even though the response would be 200.
    neo4j_uri = os.getenv("NEO4J_URI")
    if not neo4j_uri:
        checks["neo4j"] = {"status": "not_configured"}
    elif not _subsystem_active("graph"):
        checks["neo4j"] = {
            "status": "not_probed",
            "reason": "graph subsystem disabled",
        }
    else:
        try:
            from neo4j import GraphDatabase

            driver = GraphDatabase.driver(
                neo4j_uri,
                auth=(
                    os.getenv("NEO4J_USER", "neo4j"),
                    os.getenv("NEO4J_PASSWORD", ""),
                ),
                connection_timeout=2.0,
                connection_acquisition_timeout=2.0,
            )
            try:
                driver.verify_connectivity()
            finally:
                driver.close()
            checks["neo4j"] = {"status": "ok"}
        except Exception as exc:
            checks["neo4j"] = {"status": "error", "error": type(exc).__name__}

    # --- Background runners (#2518) ---
    # The ingestion worker and embedded scheduler start in the lifespan inside
    # best-effort try/except blocks. Before #2518 a swallowed start failure left
    # app.state.* = None while /readiness stayed green, so stuck ingestion /
    # disabled recall alerting was invisible to deploy health checks. Report
    # their start outcome here. These are non-fatal (degraded, never 503):
    # mirror the optional-dependency pattern so a background failure surfaces in
    # the payload without blocking a deploy.
    state = getattr(request.app, "state", None)

    # --- Ingestion worker ---
    if state is None or not hasattr(state, "ingestion_worker_started"):
        # Mounted on a minimal app (no lifespan) — nothing to report.
        checks["worker"] = {"status": "not_configured"}
    elif not state.ingestion_worker_started:
        checks["worker"] = {"status": "error", "error": "ingestion worker failed to start"}
    else:
        thread = getattr(state, "ingestion_worker_thread", None)
        if thread is not None and not thread.is_alive():
            checks["worker"] = {"status": "error", "error": "ingestion worker thread is not alive"}
        else:
            checks["worker"] = {"status": "ok"}

    # --- Embedded scheduler ---
    # A None runner with a successful start is the *intended* state when the
    # scheduler is disabled (SCHEDULER_EMBEDDED=0 / non-production) — report
    # that as "disabled", not an error. Only a raised start exception
    # (embedded_scheduler_started is False) is a failure.
    if state is None or not hasattr(state, "embedded_scheduler_started"):
        checks["scheduler"] = {"status": "not_configured"}
    elif not state.embedded_scheduler_started:
        checks["scheduler"] = {"status": "error", "error": "embedded scheduler failed to start"}
    elif getattr(state, "embedded_scheduler", None) is None:
        checks["scheduler"] = {"status": "disabled"}
    elif not getattr(state.embedded_scheduler, "thread_alive", True):
        # #2697: the daemon thread can die after a successful start (init
        # failure inside the thread) — "started ok" alone must not report
        # ok forever. Degrades the payload; never 503 (documented contract).
        checks["scheduler"] = {"status": "error", "error": "embedded scheduler thread is not alive"}
    else:
        checks["scheduler"] = {"status": "ok"}

    # --- Rate-limiter storage (#2711) ---
    # slowapi decorators (1/day GDPR export, 10/min proof-verify, …) bind to
    # whatever storage existed at import. README asserts Redis-backed rate
    # limiting; production running on memory:// means every such budget is
    # per-process (× workers × replicas). Degrades the payload; never 503.
    try:
        from shared.env import is_production as _is_prod_env
        from shared.rate_limit import slowapi_storage_backend

        _rl_backend = slowapi_storage_backend()
        if _rl_backend == "memory" and _is_prod_env():
            checks["rate_limiter"] = {
                "status": "error",
                "backend": _rl_backend,
                "error": "slowapi rate limits are per-process (no Redis storage configured)",
            }
        else:
            checks["rate_limiter"] = {"status": "ok", "backend": _rl_backend}
    except Exception as exc:
        checks["rate_limiter"] = {"status": "error", "error": type(exc).__name__}

    # --- Determine overall status ---
    # Postgres is required for the consolidated API to serve production traffic.
    # Missing DATABASE_URL must fail readiness so deploy health checks do not
    # route requests to an instance that can only satisfy liveness.
    from shared.env import requires_strict_auth_runtime

    pg_ok = checks.get("postgres", {}).get("status") == "ok"
    redis_ok = checks.get("redis", {}).get("status") == "ok"
    redis_required = requires_strict_auth_runtime()
    all_ok = all(c.get("status") != "error" for c in checks.values())

    if not pg_ok or (redis_required and not redis_ok):
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
