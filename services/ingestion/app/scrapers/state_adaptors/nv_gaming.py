from __future__ import annotations

from typing import Iterable

import requests
import structlog

from .base import FetchedItem, Source, StateRegistryScraper

logger = structlog.get_logger("scrapers.nevada")


class NevadaGamingScraper(StateRegistryScraper):
    """Minimal adaptor for Nevada Gaming Control Board."""

    def list_sources(self) -> Iterable[Source]:
        yield Source(
            url="https://gaming.nv.gov/",
            title="Nevada Gaming Control Board",
            jurisdiction_code="US-NV",
        )

    def fetch(self, source: Source) -> FetchedItem:
        """Fetch actual HTML content from Nevada Gaming Control Board."""
        try:
            response = requests.get(
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
        except requests.RequestException as e:
            logger.warning("fetch_failed", url=source.url, error=str(e))
            return FetchedItem(source=source, content_bytes=b"", content_type="text/html")
