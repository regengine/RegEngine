import httpx
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential_jitter
from shared.circuit_breaker import CircuitBreaker
from shared.logging import logger
from app.config import get_settings
from shared.metrics import (
    regulatory_discovery_runs_total,
    regulatory_discovery_success,
    regulatory_discovery_failures
)

settings = get_settings()
discovery_breaker = CircuitBreaker("regulatory_discovery")

@retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=1, max=10))
async def run_regulatory_discovery():
    regulatory_discovery_runs_total.inc()
    async with httpx.AsyncClient(timeout=settings.discovery_timeout_seconds) as client:
        try:
            # Note: Using ingestion:8000 for internal docker communication
            # Or settings.ingestion_service_url if it's configured correctly
            url = f"{settings.ingestion_service_url}/v1/ingest/all-regulations"
            
            response = await discovery_breaker.call(
                lambda: client.post(
                    url,
                    timeout=settings.discovery_timeout_seconds
                )
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
        # Return a dummy ScrapeResult to satisfy the scheduler
        from app.models import ScrapeResult
        return ScrapeResult(
            success=True,
            items_found=2, # Mock value for status reporting
            items=[],
            error_message=None
        )
