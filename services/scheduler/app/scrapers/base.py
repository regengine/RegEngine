"""Base scraper interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

import structlog

from ..models import EnforcementItem, ScrapeResult, SourceType

logger = structlog.get_logger("scraper.base")


class BaseScraper(ABC):
    """Abstract base class for regulatory scrapers.

    All scrapers must implement:
    - source_type: The type of source being scraped
    - scrape(): Fetches and parses items from the source
    """

    @property
    @abstractmethod
    def source_type(self) -> SourceType:
        """Return the source type for this scraper."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this scraper."""
        pass

    @abstractmethod
    def scrape(self) -> ScrapeResult:
        """Execute the scrape operation.

        Returns:
            ScrapeResult containing found items and metadata
        """
        pass

    def _create_source_id(self, *parts: str) -> str:
        """Create a stable source ID from parts."""
        return ":".join(str(p) for p in parts)
