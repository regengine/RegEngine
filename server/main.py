"""RegEngine Consolidated API — single FastAPI monolith.

Replaces 6 microservices (ingestion, admin, graph, nlp, compliance, scheduler)
with a single process using router boundaries to preserve decomposition seams.

Architecture decision: 2026-03-29
See: alembic/versions/20260329_task_queue_v050.py for Kafka replacement
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

os.environ.setdefault("USER_AGENT", "RegEngine/1.0 (+https://regengine.co)")

# ── Path bootstrap ───────────────────────────────────────────────
# Ensure the repo root and services/ (hence services/shared) are importable.
# Only those two go on sys.path: production code imports the service
# packages as services.<svc>.app.<module> (WI-02, 2026-11-04), so no single
# service's app/ directory may shadow the others here, matching the image's
# PYTHONPATH=/app:/app/services in the Dockerfile. backend-ci's
# image-import-check and scripts/check_legacy_dead_code.py keep bare
# `app.` imports out of production code.
_APP_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _APP_DIR.parent
_SERVICES_DIR = _ROOT_DIR / "services"

for p in [str(_ROOT_DIR), str(_SERVICES_DIR)]:
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
from fastapi import Depends, FastAPI
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
# Startup order is the deploy-log contract (jev_configured,
# document_extract_configured, the RLS posture gate before auth and workers).
# The best-effort steps live in server/startup_checks.py and
# server/workers_boot.py (WI-14); this function keeps the sequence.
from server import startup_checks, workers_boot


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

    startup_checks.init_admin_database()

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

    startup_checks.register_integration_connectors()
    startup_checks.log_integration_config()

    # Runtime DB-role gate. Production always fails closed if either role is
    # unknown, unexpected, SUPERUSER/BYPASSRLS, or connected to a different
    # PostgreSQL database. REGENGINE_REQUIRE_RLS_ENFORCEMENT=1 keeps the same
    # hard gate available in staging before promotion.
    from shared.database import validate_runtime_database_posture

    validate_runtime_database_posture(_shared_engine, _admin_engine)

    startup_checks.configure_audit_logger(_is_prod)

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

    # Start the background task worker. Everything after auth-runtime
    # initialization is inside this lifecycle guard so a later startup
    # failure still detaches and closes the Redis client.
    from server.workers.task_processor import start_task_worker

    try:
        start_task_worker()
        workers_boot.start_background_workers(app, _register_ingestion_task_handlers)

        yield
    finally:

        async def _shutdown_step(name: str, operation) -> None:
            try:
                result = operation()
                if hasattr(result, "__await__"):
                    await result
            except Exception as exc:
                logger.error("regengine_shutdown_step_failed", step=name, error=str(exc))

        await workers_boot.stop_background_workers(app, _shutdown_step)
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
# slowapi raises RateLimitExceeded when a @limiter.limit decorator
# trips. Without this handler the monolith catch-all returns 500, so
# register the standard 429 handler (covers rate limited routers such
# as integration webhooks when they are enabled).
from slowapi import _rate_limit_exceeded_handler  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402

app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
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

# Environment, auth-config and secret gates evaluated at import (WI-14:
# server/startup_checks.py; production fails fast on a missing DATABASE_URL
# or an insecure placeholder, optional subsystems degrade instead).
startup_checks.run_import_time_checks()

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


# ── Routers ──────────────────────────────────────────────────────
# Domain routers (ingestion, admin, graph, nlp, compliance) are mounted by
# server/routers_mount.py in first-match order; the production route set is
# pinned by tests/test_server_route_snapshot_wi14.py.
from server.routers_mount import mount_routers

mount_routers(app, _router_enabled)


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


# ── Health check ──────────────────────────────────────────────
# /readiness lives in server/readiness.py (WI-14); ``readiness`` is re-exported
# for the probe contract tests that mount it on a bare app.
from server.readiness import readiness, register_readiness_route  # noqa: F401 -- re-exported for tests

register_readiness_route(app, _subsystem_active)
