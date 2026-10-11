"""Generic scraper implementations for common patterns.

This module provides reusable scraper classes that can be configured
for different jurisdictions without custom code.
"""

from __future__ import annotations

from typing import Iterable, Optional

import feedparser
import structlog
from shared.safe_http import DEFAULT_MAX_RESPONSE_BYTES, safe_httpx_get_sync
from shared.url_validation import SSRFError, validate_url

from .base import FetchedItem, Source, StateRegistryScraper

logger = structlog.get_logger("ingestion.scraper.generic")

FEED_MAX_BYTES = DEFAULT_MAX_RESPONSE_BYTES


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
        """Parse RSS feed and yield sources for each entry.

        The feed bytes are downloaded through ``safe_httpx_get_sync`` (SSRF
        validation on every hop plus a size cap) and only then handed to
        feedparser, so feedparser never fetches a URL itself.
        """
        try:
            resp = safe_httpx_get_sync(
                self.feed_url,
                timeout=30,
                headers={"User-Agent": "RegEngine/1.0"},
                max_bytes=FEED_MAX_BYTES,
            )
            resp.raise_for_status()
            # feedparser resolves relative item links only when it knows the
            # feed URL. The safe helper pins the transport IP, so resp.url
            # carries the IP literal; the logical final-hop URL rides in
            # extensions (falling back to the request URL when a stubbed
            # response in tests does not carry it).
            extensions = getattr(resp, "extensions", None) or {}
            base_url = extensions.get("safe_final_url", self.feed_url)
            feed = feedparser.parse(
                resp.content,
                response_headers={"content-location": base_url},
            )
        except Exception as e:
            logger.warning("generic_rss_discover_failed", url=self.feed_url, error=str(e))
            return
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
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
        except Exception as e:
            logger.warning("generic_rss_discover_failed", url=self.feed_url, error=str(e))
            return
        for entry in feed.entries:
            try:
                link = entry.get("link")
                if not link:
                    continue
                try:
                    url = validate_url(link)
                except SSRFError as e:
                    logger.debug("ssrf_validation_failed_generic_rss", url=link, error=str(e))
                    continue
                title = entry.get("title") or link
                yield Source(
                    url=url,
                    title=f"{self.title_prefix}: {title}",
                    jurisdiction_code=self.jurisdiction,
                    metadata={
                        "published": entry.get("published"),
                        "summary": entry.get("summary"),
                    },
                )
            except Exception as e:
                logger.warning("generic_rss_entry_skipped", error=str(e))
                continue

    def fetch(self, source: Source) -> FetchedItem:
        """Fetch content from the source URL.

        SSRF defense (RE-SEC-INGEST-003): per-hop URL validation + IP pinning.
        """
        try:
            resp = safe_httpx_get_sync(
                source.url,
                timeout=30,
                headers={"User-Agent": "RegEngine/1.0"},
                max_bytes=FEED_MAX_BYTES,
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
                content_type=None,
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
            from urllib.parse import urljoin

            from bs4 import BeautifulSoup

            # SSRF defense (RE-SEC-INGEST-003): per-hop validation + IP pinning.
            resp = safe_httpx_get_sync(
                self.list_url,
                timeout=30,
                headers={"User-Agent": "RegEngine/1.0"},
                max_bytes=FEED_MAX_BYTES,
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, "html.parser")

            base = self.base_url or self.list_url
            for link in soup.select(self.link_selector):
                href = link.get("href")
                if not href:
                    continue
                try:
                    url = validate_url(urljoin(base, href))
                except SSRFError as e:
                    logger.debug("ssrf_validation_failed_generic_list", url=href, error=str(e))
                    continue
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
        """Fetch content from the source URL.

        SSRF defense (RE-SEC-INGEST-003): per-hop URL validation + IP pinning.
        """
        try:
            resp = safe_httpx_get_sync(
                source.url,
                timeout=30,
                headers={"User-Agent": "RegEngine/1.0"},
                max_bytes=FEED_MAX_BYTES,
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
                content_type=None,
            )
