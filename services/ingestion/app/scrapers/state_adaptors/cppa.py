from __future__ import annotations

from typing import Iterable

import httpx
import structlog

from .base import FetchedItem, Source, StateRegistryScraper

logger = structlog.get_logger("scrapers.cppa")


class CPPAScraper(StateRegistryScraper):
    """Minimal CPPA adaptor placeholder for CA privacy regulations."""

    def list_sources(self) -> Iterable[Source]:
        yield Source(
            url="https://cppa.ca.gov/regulations/",
            title="CPPA Regulations",
            jurisdiction_code="US-CA",
        )

    def fetch(self, source: Source) -> FetchedItem:
        """Fetch actual HTML content from CPPA website."""
        try:
            response = httpx.get(
                source.url,
                headers={"User-Agent": "RegEngine/1.0 (Compliance Monitoring)"},
                timeout=30
            )
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "text/html").split(";")[0]
            return FetchedItem(
                source=source,
                content_bytes=response.content,
                content_type=content_type
            )
        except httpx.HTTPError as e:
            # Log error but return empty content to allow graceful degradation
            logger.warning("fetch_failed", url=source.url, error=str(e))
            return FetchedItem(source=source, content_bytes=b"", content_type="text/html")
