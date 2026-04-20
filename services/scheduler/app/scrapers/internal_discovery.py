import httpx
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential_jitter
from shared.observability.context import logger
from shared.resilient_http import resilient_client
from app.config import get_settings
from shared.metrics import (
    regulatory_discovery_runs_total,
    regulatory_discovery_success,
    regulatory_discovery_failures
)

settings = get_settings()

@retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=1, max=10))
async def run_regulatory_discovery():
    regulatory_discovery_runs_total.inc()
    async with resilient_client(
        timeout=settings.discovery_timeout_seconds,
        circuit_name="ingestion-service",
    ) as client:
        try:
            url = f"{settings.ingestion_service_url}/v1/ingest/all-regulations"

            response = await client.post(
                url,
                headers={"X-RegEngine-API-Key": settings.scheduler_api_key},
            )
            response.raise_for_status()
            logger.info("regulatory_discovery_completed", response=response.json())
            regulatory_discovery_success.inc()
        except Exception as e:
            logger.error("regulatory_discovery_failed", error=str(e))
            regulatory_discovery_failures.inc()
            raise

class InternalDiscoveryScraper:
    """Wrapper class for the async discovery job to maintain compatibility."""
    def __init__(self):
        self.name = "Internal Discovery"

    def scrape(self):
        """Execute the discovery job synchronously."""
        import asyncio
        asyncio.run(run_regulatory_discovery())
        # items[] is empty because internal discovery delegates to the ingestion
        # service and does not collect individual items locally.
        from app.models import ScrapeResult, SourceType
        items: list = []
        return ScrapeResult(
            source_type=SourceType.REGULATORY_DISCOVERY,
            success=True,
            items_found=len(items),
            items=items,
            error_message=None
        )
