"""
Background job logic for scraping operations.
"""
import asyncio
import structlog
from typing import Optional

from .config import get_settings
from .pipeline import ScraperPipeline
from .scrapers.state_adaptors.base import Source
from .scrapers.state_generic import StateRegistryScraper as GenericStateScraper

# Import adaptors map (avoid circular import if possible, or pass it in)
# We will pass the adaptor instance or look it up here if we move ADAPTORS here.

logger = structlog.get_logger("ingestion.jobs")

_PIPELINE = ScraperPipeline()
_GENERIC_SCRAPER = GenericStateScraper()

async def run_state_scrape_job(
    adaptor_name: str,
    adaptor_instance,
    url: str,
    jurisdiction_code: str,
    tenant_id: Optional[str],
):
    """
    Background task to run a state scraper logic.
    """
    logger.info("scrape_job_started", adaptor=adaptor_name, url=url, tenant_id=tenant_id)
    
    try:
        loop = asyncio.get_running_loop()
        
        # Create source
        source = Source(url=url, jurisdiction_code=jurisdiction_code)
        
        # 1. Fetch (run sync adaptor in executor)
        def _fetch_sync():
            return adaptor_instance.fetch(source)
            
        fetched_item = await loop.run_in_executor(None, _fetch_sync)
        
        if not fetched_item.content_bytes:
            logger.warning("scrape_job_empty", adaptor=adaptor_name, url=url)
            return

        # 2. Process via Pipeline
        event = _PIPELINE.process_content(
            content=fetched_item.content_bytes,
            content_type=fetched_item.content_type,
            jurisdiction_code=jurisdiction_code,
            source_url=url,
            tenant_id=tenant_id
        )
        
        if event:
            logger.info("scrape_job_success", event_id=event.event_id)
            
    except Exception as exc:
        logger.error("scrape_job_failed", adaptor=adaptor_name, url=url, error=str(exc))
        # Store job failure status in Redis for status tracking
        try:
            from .config import get_settings
            import redis
            settings = get_settings()
            r = redis.from_url(settings.redis_url)
            import json
            from datetime import datetime
            r.setex(
                f"scrape_job:failed:{url}",
                3600,  # 1 hour TTL
                json.dumps({
                    "adaptor": adaptor_name,
                    "url": url,
                    "error": str(exc),
                    "failed_at": datetime.utcnow().isoformat()
                })
            )
        except Exception as redis_exc:
            logger.debug("job_status_store_failed", error=str(redis_exc))

async def run_generic_scrape_job(
    url: str,
    jurisdiction_code: str,
    tenant_id: Optional[str],
):
    """
    Background task for generic scraping.
    """
    logger.info("generic_scrape_job_started", url=url)
    try:
        # Generic scraper already handles fetch+upload internally (refactor later?)
        # For now, we call it. It is async.
        await _GENERIC_SCRAPER.fetch_document(url, jurisdiction_code, tenant_id=tenant_id)
        logger.info("generic_scrape_job_success", url=url)
    except Exception as exc:
        logger.error("generic_scrape_job_failed", url=url, error=str(exc))
