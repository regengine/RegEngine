from __future__ import annotations

import time
from typing import List, Optional

import httpx
import structlog

from app.config import get_settings
from app.models import EnforcementItem, ScrapeResult, SourceType
from .base import BaseScraper

logger = structlog.get_logger("internal-discovery-scraper")

class InternalDiscoveryScraper(BaseScraper):
    """Scraper that triggers the internal bulk discovery endpoint (v2)."""

    def __init__(self):
        super().__init__(name="Internal Regulation Discovery", source_type=SourceType.REGULATORY_DISCOVERY)
        self.settings = get_settings()

    def scrape(self) -> ScrapeResult:
        """Trigger the bulk discovery scan and return result metadata."""
        start_time = time.time()
        url = f"{self.settings.ingestion_service_url}/v1/ingest/all-regulations"
        headers = {"X-API-Key": self.settings.scheduler_api_key}

        try:
            with httpx.Client(timeout=30) as client:
                response = client.post(url, headers=headers)
                response.raise_for_status()
                data = response.json()
            
            duration_ms = (time.time() - start_time) * 1000
            
            # Since this is a trigger for other background jobs, we return result metadata
            # but no actual EnforcementItems (as they are handled by ingestion service)
            return ScrapeResult(
                source_type=self.source_type,
                success=True,
                items_found=data.get("total_sources") or 0,
                duration_ms=duration_ms
            )

        except Exception as e:
            logger.error("internal_discovery_trigger_failed", error=str(e))
            return ScrapeResult(
                source_type=self.source_type,
                success=False,
                error_message=str(e)
            )
