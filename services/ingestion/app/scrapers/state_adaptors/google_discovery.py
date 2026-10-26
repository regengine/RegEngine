from datetime import datetime, timezone
from typing import Iterable, Optional
from urllib.parse import urlencode, urlsplit

import httpx
import structlog
from shared.safe_http import (
    DOCUMENT_MAX_RESPONSE_BYTES,
    ResponseTooLargeError,
    safe_httpx_get_sync,
)
from shared.url_validation import SSRFError, validate_url

from ...config import get_settings
from .base import FetchedItem, Source, StateRegistryScraper

logger = structlog.get_logger("ingestion.scrapers.google_discovery")

# Map of US state government parent domains to jurisdiction codes. Matching is
# done against the parsed URL hostname (exact host or subdomain) rather than a
# substring of the full URL, so a crafted path/query such as
# "https://evil.example.com/?x=.ny.gov" cannot forge a jurisdiction.
_STATE_GOV_DOMAINS: tuple[tuple[str, str], ...] = (
    ("ny.gov", "US-NY"),
    ("ca.gov", "US-CA"),
    ("tx.gov", "US-TX"),
)


def _jurisdiction_from_url(url: str) -> str:
    """Return the jurisdiction code for *url* based on its parsed hostname."""
    host = (urlsplit(url).hostname or "").lower()
    for domain, code in _STATE_GOV_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return code
    return "US"


class GoogleDiscoveryScraper(StateRegistryScraper):
    """
    Active scraper that discovers documents using Google Custom Search API.

    It searches for high-value regulatory documents (PDFs) from government domains.
    """

    def __init__(self):
        self.settings = get_settings()
        self.api_key = self.settings.google_api_key
        self.cx = self.settings.google_cx
        self.base_url = "https://www.googleapis.com/customsearch/v1"

    def list_sources(self) -> Iterable[Source]:
        """
        Execute Google Search query and return results as Sources.
        """
        query = self.settings.discovery_query
        if not self.api_key or not self.cx:
            logger.warning("google_discovery_config_missing", detail="Skipping discovery, no API key/CX configured")
            return []

        logger.info("google_discovery_started", query=query)

        # Collect page by page so a late-page failure keeps the healthy
        # results from earlier pages instead of discarding everything.
        results = []
        try:
            # Fetch up to 20 results (2 pages)
            for start_index in [1, 11]:
                params = {"key": self.api_key, "cx": self.cx, "q": query, "fileType": "pdf", "start": start_index}

                # SSRF defense (RE-SEC-INGEST-003): per-hop validation + IP pinning.
                # safe_httpx_get_sync does not accept params directly; encode into URL.
                full_url = f"{self.base_url}?{urlencode(params)}"
                resp = safe_httpx_get_sync(full_url, timeout=10)
                resp.raise_for_status()
                data = resp.json()

                if "items" in data:
                    results.extend(data["items"])
                else:
                    break

        except Exception as e:
            logger.error("google_discovery_failed", error=str(e))

        sources = []
        for item in results:
            url = item.get("link")
            title = item.get("title")
            snippet = item.get("snippet")

            if not url:
                continue

            try:
                url = validate_url(url)
            except SSRFError as e:
                logger.debug("ssrf_validation_failed_google_discovery", url=item.get("link"), error=str(e))
                continue

            # Determine jurisdiction from the parsed hostname (simple
            # heuristic). See _jurisdiction_from_url for why substring checks
            # on the raw URL are unsafe.
            jurisdiction = _jurisdiction_from_url(url)

            sources.append(
                Source(
                    url=url,
                    title=title,
                    jurisdiction_code=jurisdiction,
                    metadata={
                        "discovery_snippet": snippet,
                        "discovery_date": datetime.now(timezone.utc).isoformat(),
                    },
                )
            )

        logger.info("google_discovery_complete", found=len(sources))
        return sources

    def fetch(self, source: Source) -> FetchedItem:
        """
        Fetch the content of the discovered document.
        """
        try:
            # SSRF defense (RE-SEC-INGEST-003): per-hop validation + IP pinning.
            # Discovered targets are whole documents (usually PDFs), so they
            # get the document budget, not the 5 MiB page default.
            resp = safe_httpx_get_sync(
                source.url,
                timeout=30,
                headers={"User-Agent": "RegEngine/1.0"},
                max_bytes=DOCUMENT_MAX_RESPONSE_BYTES,
            )
            resp.raise_for_status()

            content_type = resp.headers.get("Content-Type", "application/pdf")
            return FetchedItem(source=source, content_bytes=resp.content, content_type=content_type)
        except ResponseTooLargeError as e:
            logger.error("google_fetch_too_large", url=source.url, error=str(e))
            # Return empty item on failure
            return FetchedItem(source=source, content_bytes=b"", content_type=None)
        except Exception as e:
            logger.error("google_fetch_failed", url=source.url, error=str(e))
            # Return empty item on failure
            return FetchedItem(source=source, content_bytes=b"", content_type=None)
