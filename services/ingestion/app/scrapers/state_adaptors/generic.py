"""Generic scraper implementations for common patterns.

This module provides reusable scraper classes that can be configured
for different jurisdictions without custom code.
"""

from __future__ import annotations

import requests
import feedparser
from typing import Iterable, Optional

from .base import FetchedItem, Source, StateRegistryScraper

import logging
logger = logging.getLogger("ingestion.scraper.generic")

class GenericRSSScraper(StateRegistryScraper):
    """Generic RSS feed scraper for state regulatory feeds.

    This scraper can be configured for any jurisdiction that publishes
    regulatory updates via RSS/Atom feeds.
    """

    def __init__(self, feed_url: str, jurisdiction: Optional[str] = None, title_prefix: Optional[str] = None):
        """Initialize the RSS scraper.

        Args:
            feed_url: URL of the RSS/Atom feed
            jurisdiction: Jurisdiction code (e.g., "US-FL", "US-TX")
            title_prefix: Prefix for source titles (e.g., "Florida Legislature")
        """
        self.feed_url = feed_url
        self.jurisdiction = jurisdiction or getattr(self, "jurisdiction", "unknown")
        self.title_prefix = title_prefix or getattr(self, "title_prefix", "Generic RSS")

    def list_sources(self) -> Iterable[Source]:
        """Parse RSS feed and yield sources for each entry."""
        feed = feedparser.parse(self.feed_url)
        for entry in feed.entries:
            yield Source(
                url=entry.link,
                title=f"{self.title_prefix}: {entry.title}",
                jurisdiction_code=self.jurisdiction,
                metadata={
                    "published": entry.get("published"),
                    "summary": entry.get("summary"),
                },
            )

    def fetch(self, source: Source) -> FetchedItem:
        """Fetch content from the source URL."""
        try:
            resp = requests.get(
                source.url,
                timeout=30,
                headers={"User-Agent": "RegEngine/1.0"},
            )
            resp.raise_for_status()
            return FetchedItem(
                source=source,
                content_bytes=resp.content,
                content_type=resp.headers.get("Content-Type"),
            )
        except Exception as e:
            logger.warning("generic_fetch_failed", url=source.url, error=str(e))
            return FetchedItem(
                source=source,
                content_bytes=b"",
                content_type="error",
            )


class GenericListScraper(StateRegistryScraper):
    """Generic HTML list page scraper for state regulatory sites.

    This scraper handles sites that publish a list of links to
    regulatory documents on an HTML page.
    """

    def __init__(
        self,
        list_url: str,
        jurisdiction: str,
        title_prefix: str,
        link_selector: str = "a",
        base_url: Optional[str] = None,
    ):
        """Initialize the list scraper.

        Args:
            list_url: URL of the page containing document links
            jurisdiction: Jurisdiction code (e.g., "US-NV")
            title_prefix: Prefix for source titles
            link_selector: CSS selector for document links
            base_url: Base URL for relative links (defaults to list_url domain)
        """
        self.list_url = list_url
        self.jurisdiction = jurisdiction
        self.title_prefix = title_prefix
        self.link_selector = link_selector
        self.base_url = base_url

    def list_sources(self) -> Iterable[Source]:
        """Parse HTML page and yield sources for each document link."""
        try:
            from bs4 import BeautifulSoup
            from urllib.parse import urljoin

            resp = requests.get(
                self.list_url,
                timeout=30,
                headers={"User-Agent": "RegEngine/1.0"},
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, "html.parser")

            base = self.base_url or self.list_url
            for link in soup.select(self.link_selector):
                href = link.get("href")
                if not href:
                    continue
                url = urljoin(base, href)
                title = link.get_text(strip=True) or href
                yield Source(
                    url=url,
                    title=f"{self.title_prefix}: {title}",
                    jurisdiction_code=self.jurisdiction,
                    metadata={"source_page": self.list_url},
                )
        except Exception as e:
            logger.warning("generic_discover_failed", url=self.list_url, error=str(e))
            return

    def fetch(self, source: Source) -> FetchedItem:
        """Fetch content from the source URL."""
        try:
            resp = requests.get(
                source.url,
                timeout=30,
                headers={"User-Agent": "RegEngine/1.0"},
            )
            resp.raise_for_status()
            return FetchedItem(
                source=source,
                content_bytes=resp.content,
                content_type=resp.headers.get("Content-Type"),
            )
        except Exception as e:
            logger.warning("generic_fetch_with_fallback_failed", url=source.url, error=str(e))
            return FetchedItem(
                source=source,
                content_bytes=b"",
                content_type="error",
            )
