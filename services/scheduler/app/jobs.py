import asyncio
import os

import httpx
from apscheduler.schedulers.blocking import BlockingScheduler
from app.scrapers.internal_discovery import run_regulatory_discovery
from app.leadership import is_leader
from shared.logging import logger
from app.config import get_settings

settings = get_settings()
scheduler = BlockingScheduler()

# ---------------------------------------------------------------------------
# Existing job: generic regulatory discovery (interval-based)
# ---------------------------------------------------------------------------

# Startup sync
async def initial_discovery():
    if is_leader():
        logger.info("startup_regulatory_discovery_triggered")
        await run_regulatory_discovery()

@scheduler.scheduled_job('interval', minutes=settings.regulatory_discovery_interval, id='regulatory_discovery')
def regulatory_discovery_job():
    if is_leader():
        asyncio.run(run_regulatory_discovery())
    else:
        logger.debug("regulatory_discovery_skipped_non_leader")

# Register startup job
# Note: In APScheduler 3.x, you typically run startup logic before starting the scheduler
# or use a 'date' trigger with run_date=datetime.now()
def schedule_startup_jobs():
    logger.info("registering_startup_jobs")
    # For MVP/Phase 28 compliance, we'll run it manually in main or use a job
    pass


# ---------------------------------------------------------------------------
# Phase 29: Nightly FSMA sync job (02:00 UTC daily)
# ---------------------------------------------------------------------------

_INGESTION_INTERNAL_URL = os.getenv(
    "INGESTION_SERVICE_URL", "http://ingestion:8301"
)
_INGESTION_API_KEY = os.getenv("INTERNAL_API_KEY", "")


@scheduler.scheduled_job(
    "cron",
    hour=2,
    minute=0,
    id="fsma_nightly_sync",
    timezone="UTC",
    misfire_grace_time=300,  # 5-minute grace window if scheduler was down
)
def fsma_nightly_sync_job():
    """Trigger a full FSMA source sync via the ingestion service at 02:00 UTC.

    Only runs on the elected leader node. The ingestion endpoint handles
    deduplication (ETag + SHA-256), so re-running on unchanged sources is safe.
    """
    if not is_leader():
        logger.debug("fsma_nightly_sync_skipped_non_leader")
        return

    logger.info("fsma_nightly_sync_started")
    try:
        response = httpx.post(
            f"{_INGESTION_INTERNAL_URL}/v1/ingest/all-regulations",
            headers={"X-API-Key": _INGESTION_API_KEY},
            timeout=120.0,
        )
        response.raise_for_status()
        summary = response.json()
        logger.info(
            "fsma_nightly_sync_complete",
            sources_attempted=summary.get("sources_attempted"),
            ingested=summary.get("ingested"),
            unchanged=summary.get("unchanged"),
            failed=summary.get("failed"),
        )
    except Exception as exc:
        logger.error("fsma_nightly_sync_failed", error=str(exc))
