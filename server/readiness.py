"""``/readiness`` for the consolidated monolith (tech-debt WI-14, 2026-11-04).

Split out of ``server/main.py`` unchanged. ``server.main`` calls
``register_readiness_route(app, subsystem_active)`` after the routers are
mounted; ``subsystem_active`` is the RouterPolicy predicate the Neo4j probe
consults. Tests monkeypatch the module-level names here
(``_readiness_checks``, ``_READINESS_*``, ``_subsystem_active``).
"""

from __future__ import annotations

import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore

from fastapi import FastAPI, Request

from server.route_ownership import owned_api_route


def _subsystem_active(name: str) -> bool:  # replaced by register_readiness_route
    return False


def register_readiness_route(app: FastAPI, subsystem_active: Callable[[str], bool]) -> None:
    """Bind the RouterPolicy predicate and mount ``GET /readiness`` on ``app``."""
    global _subsystem_active
    _subsystem_active = subsystem_active
    owned_api_route(app, owner="health", path="/readiness", methods=["GET"], tags=["system"])(readiness)


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
    runtimes, matching auth and checkout enforcement. Essential background
    units (ingestion worker; embedded scheduler when SCHEDULER_EMBEDDED is
    on) fail readiness with HTTP 503 so a broken deploy cannot promote
    (diligence E07). Neo4j and the rate limiter stay non-blocking: they
    report in the payload but never alone flip the status code. /health
    remains a separate liveness probe and does not consult these units.
    """
    from fastapi.responses import JSONResponse

    checks: dict[str, dict] = {}

    # --- PostgreSQL ---
    try:
        from sqlalchemy import create_engine, text

        db_url = os.getenv("DATABASE_URL")
        if db_url:
            from shared.db_url import sync_postgres_url

            db_url = sync_postgres_url(db_url)
            connect_args = {}
            if db_url.startswith("postgresql+psycopg:"):
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

    # --- Background runners (#2518 / E07) ---
    # The ingestion worker and embedded scheduler start in the lifespan inside
    # best-effort try/except blocks. Before #2518 a swallowed start failure left
    # app.state.* = None while /readiness stayed green, so stuck ingestion /
    # disabled recall alerting was invisible to deploy health checks. Report
    # their start outcome and thread liveness here. Diligence E07 makes the
    # essential units fail readiness (HTTP 503): the ingestion worker always,
    # and the embedded scheduler only when SCHEDULER_EMBEDDED enables it.
    # disabled / not_configured stay non-blocking. Neo4j and rate_limiter
    # remain informational (never alone 503). /health stays separate.
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
        # #2697 / E07: the daemon thread can die after a successful start
        # (init failure inside the thread) — "started ok" alone must not
        # report ok forever. When the scheduler is essential this fails
        # readiness (503); otherwise it only degrades the payload.
        checks["scheduler"] = {"status": "error", "error": "embedded scheduler thread is not alive"}
    else:
        checks["scheduler"] = {"status": "ok"}

    # --- Rate-limiter storage (#2711 / E07) ---
    # slowapi decorators (1/day GDPR export, 10/min proof-verify, …) bind to
    # whatever storage existed at import. README asserts Redis-backed rate
    # limiting; production running on memory:// means every such budget is
    # per-process (× workers × replicas). Reported in the payload; never
    # alone flips readiness to 503 (diligence E07: rate limiter non-blocking).
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
    # Diligence E07: essential background units also fail readiness so a
    # release cannot promote while ingestion or (when embedded) scheduled
    # compliance work is unavailable. Liveness (/health) stays separate.
    from shared.env import requires_strict_auth_runtime

    from server.workers.embedded_scheduler import embedded_scheduler_enabled

    pg_ok = checks.get("postgres", {}).get("status") == "ok"
    redis_ok = checks.get("redis", {}).get("status") == "ok"
    redis_required = requires_strict_auth_runtime()
    worker_essential_error = checks.get("worker", {}).get("status") == "error"
    scheduler_essential_error = checks.get("scheduler", {}).get("status") == "error" and embedded_scheduler_enabled()
    all_ok = all(c.get("status") != "error" for c in checks.values())

    if not pg_ok or (redis_required and not redis_ok) or worker_essential_error or scheduler_essential_error:
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
