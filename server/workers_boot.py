"""Background worker boot and shutdown for the monolith (tech-debt WI-14, 2026-11-04).

Split out of ``server/main.py``'s lifespan: the ingestion task worker and the
embedded scheduler start here (after ``start_task_worker()``, which the
lifespan still calls so the posture-gate ordering tests keep their source
anchor) and stop here in the same order as before. ``app.state`` keeps the
same attributes (#2518) so ``/readiness`` reports the same outcomes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Awaitable

from fastapi import FastAPI
from shared.observability.context import logger


def start_background_workers(app: FastAPI, register_ingestion_task_handlers: Callable[[], Any]) -> None:
    """Start the ingestion task worker and the embedded scheduler (best-effort each)."""
    # Register only the task handlers whose HTTP surface is enabled, then
    # start the ingestion worker.  Optional routers are intentionally
    # absent from production; leaving their queue handlers registered
    # would preserve an internal path to disabled scraping/discovery/source
    # fetchers through stale or forged task rows.
    try:
        from shared.task_queue import TaskWorker

        from services.admin.app.database import get_admin_engine

        register_ingestion_task_handlers()
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


async def stop_background_workers(
    app: FastAPI, shutdown_step: Callable[[str, Callable[[], Any]], Awaitable[None]]
) -> None:
    """Stop the task worker, the ingestion worker and the embedded scheduler, in that order."""
    from server.workers.task_processor import stop_task_worker

    await shutdown_step("stop_task_worker", stop_task_worker)
    ingestion_worker = getattr(app.state, "ingestion_worker", None)
    if ingestion_worker is not None:
        await shutdown_step("stop_ingestion_worker", ingestion_worker.stop)
    embedded_scheduler = getattr(app.state, "embedded_scheduler", None)
    if embedded_scheduler is not None:
        await shutdown_step("stop_embedded_scheduler", embedded_scheduler.stop)
