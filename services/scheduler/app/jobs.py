"""Legacy scheduler job module.

HISTORICAL NOTE
===============
This module used to define its own module-level
``scheduler = BlockingScheduler()`` and register ``fsma_nightly_sync_job``
and ``regulatory_discovery_job`` against it with ``@scheduler.scheduled_job``.

The entry point at ``services/scheduler/main.py`` never imported this module
and never started this scheduler, so those jobs were dead code — they
never fired in production (issue #1135).

The FSMA nightly sync and regulatory discovery are now scheduled directly
on the real :class:`BlockingScheduler` in ``SchedulerService.schedule_jobs``
as ``run_fsma_nightly_sync`` / ``run_scraper(REGULATORY_DISCOVERY)``.

This module remains only so that existing ``from app.jobs import …``
call-sites (if any) do not hard-break; it is intentionally a thin shim
with no standalone scheduler and no side effects at import time.

Why not delete outright: regression-safety while downstream imports are
being audited. Once confirmed orphaned, delete the file.
"""

from __future__ import annotations

import asyncio
import os

import httpx

from app.scrapers.internal_discovery import run_regulatory_discovery
from app.leadership import is_leader
from shared.observability.context import logger

# Kept for backwards-import compatibility. Do NOT register jobs on
# this scheduler — it is never started. See the module docstring.


async def initial_discovery() -> None:
    """Startup regulatory-discovery run (manual invocation)."""
    if is_leader():
        logger.info("startup_regulatory_discovery_triggered")
        await run_regulatory_discovery()


def regulatory_discovery_job() -> None:
    """Run regulatory discovery on the current process.

    Kept as a module-level function so ``main.py`` or tests can call it
    directly. Use the APScheduler job registered in
    ``SchedulerService.schedule_jobs`` for scheduled execution.
    """
    if is_leader():
        asyncio.run(run_regulatory_discovery())
    else:
        logger.debug("regulatory_discovery_skipped_non_leader")


def fsma_nightly_sync_job() -> None:
    """Kick the ingestion service's "all regulations" endpoint.

    Kept as a callable shim for tests and ops one-off runs. The real
    scheduled execution lives in ``SchedulerService.run_fsma_nightly_sync``
    on the monolith scheduler.
    """
    if not is_leader():
        logger.debug("fsma_nightly_sync_skipped_non_leader")
        return

    ingestion_url = os.getenv("INGESTION_SERVICE_URL", "http://ingestion:8301")
    api_key = os.getenv("REGENGINE_INTERNAL_SECRET", "").strip()
    if not api_key:
        logger.error(
            "fsma_nightly_sync_skipped_missing_secret",
            hint="Set REGENGINE_INTERNAL_SECRET to a non-empty value",
        )
        return

    logger.info("fsma_nightly_sync_started")
    try:
        response = httpx.post(
            f"{ingestion_url}/v1/ingest/all-regulations",
            headers={"X-RegEngine-API-Key": api_key},
            timeout=120.0,
        )
        response.raise_for_status()
        summary = response.json() if response.content else {}
        logger.info(
            "fsma_nightly_sync_complete",
            sources_attempted=summary.get("sources_attempted"),
            ingested=summary.get("ingested"),
            unchanged=summary.get("unchanged"),
            failed=summary.get("failed"),
        )
    except Exception as exc:
        logger.error("fsma_nightly_sync_failed", error=str(exc))


def schedule_startup_jobs() -> None:
    """Compatibility no-op.

    Historically registered startup jobs on an orphaned scheduler.
    Kept so any legacy import path does not break.
    """
    logger.debug("schedule_startup_jobs_noop")
