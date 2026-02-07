import logging
import requests
from typing import Iterable, Optional
from datetime import datetime, timezone

from ...config import get_settings
from .base import StateRegistryScraper, Source, FetchedItem

logger = logging.getLogger("ingestion.scrapers.google_discovery")

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
        
        try:
            # Fetch up to 20 results (2 pages)
            results = []
            for start_index in [1, 11]:
                params = {
                    "key": self.api_key,
                    "cx": self.cx,
                    "q": query,
                    "fileType": "pdf",
                    "start": start_index
                }
                
                resp = requests.get(self.base_url, params=params, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                
                if "items" in data:
                    results.extend(data["items"])
                else:
                    break

            sources = []
            for item in results:
                url = item.get("link")
                title = item.get("title")
                snippet = item.get("snippet")
                
                if not url:
                    continue

                # Determine jurisdiction from domain (simple heuristic)
                jurisdiction = "US"
                if ".ny.gov" in url:
                    jurisdiction = "US-NY"
                elif ".ca.gov" in url:
                    jurisdiction = "US-CA"
                elif ".tx.gov" in url:
                    jurisdiction = "US-TX"
                
                sources.append(Source(
                    url=url,
                    title=title,
                    jurisdiction_code=jurisdiction,
                    metadata={"discovery_snippet": snippet, "discovery_date": datetime.now(timezone.utc).isoformat()}
                ))

            logger.info("google_discovery_complete", found=len(sources))
            return sources

        except Exception as e:
            logger.error("google_discovery_failed", error=str(e))
            return []

    def fetch(self, source: Source) -> FetchedItem:
        """
        Fetch the content of the discovered document.
        """
        try:
            resp = requests.get(source.url, timeout=30, headers={"User-Agent": "RegEngine/1.0"})
            resp.raise_for_status()
            
            content_type = resp.headers.get("Content-Type", "application/pdf")
            return FetchedItem(
                source=source,
                content_bytes=resp.content,
                content_type=content_type
            )
        except Exception as e:
            logger.error("google_fetch_failed", url=source.url, error=str(e))
            # Return empty item on failure
            return FetchedItem(source=source, content_bytes=b"", content_type=None)
