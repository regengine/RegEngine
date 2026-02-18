import asyncio
from apscheduler.schedulers.blocking import BlockingScheduler
from app.scrapers.internal_discovery import run_regulatory_discovery
from app.leadership import is_leader
from shared.logging import logger
from app.config import get_settings

settings = get_settings()
scheduler = BlockingScheduler()

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
