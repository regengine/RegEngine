from __future__ import annotations

from typing import Iterable

import requests
import structlog

from .base import FetchedItem, Source, StateRegistryScraper

logger = structlog.get_logger("scrapers.florida")


class FloridaRSSScraper(StateRegistryScraper):
    """Minimal adaptor for Florida legislature RSS/XML feeds."""

    def list_sources(self) -> Iterable[Source]:
        yield Source(
            url="https://www.flsenate.gov/PublishedContent/Session/",
            title="Florida Legislature",
            jurisdiction_code="US-FL",
        )

    def fetch(self, source: Source) -> FetchedItem:
        """Fetch actual RSS/XML content from Florida Legislature."""
        try:
            response = requests.get(
                source.url,
                headers={"User-Agent": "RegEngine/1.0 (Compliance Monitoring)"},
                timeout=30
            )
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "application/rss+xml").split(";")[0]
            return FetchedItem(
                source=source,
                content_bytes=response.content,
                content_type=content_type
            )
        except requests.RequestException as e:
            logger.warning("fetch_failed", url=source.url, error=str(e))
            return FetchedItem(
                source=source, content_bytes=b"", content_type="application/rss+xml"
            )
