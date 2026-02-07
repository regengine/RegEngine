from __future__ import annotations

import time
from typing import Iterable

import requests
from bs4 import BeautifulSoup

from .base import FetchedItem, Source, StateRegistryScraper


class NYDFSScraper(StateRegistryScraper):
    """NYDFS Part 500 Cybersecurity Regulations scraper.

    Fetches regulatory documents from the New York Department of Financial Services.
    """

    BASE_URL = "https://www.dfs.ny.gov"
    CYBERSECURITY_PATH = "/industry_guidance/cybersecurity"
    REQUEST_TIMEOUT = 30
    RETRY_DELAY = 2.0
    MAX_RETRIES = 3

    def list_sources(self) -> Iterable[Source]:
        """List available NYDFS cybersecurity regulation sources."""
        yield Source(
            url=f"{self.BASE_URL}{self.CYBERSECURITY_PATH}",
            title="NYDFS Part 500 - Cybersecurity Requirements",
            jurisdiction_code="US-NY",
        )
        # Additional Part 500 resources
        yield Source(
            url=f"{self.BASE_URL}/apps_and_licensing/virtual_currency_businesses/regulation",
            title="NYDFS Virtual Currency Regulation",
            jurisdiction_code="US-NY",
        )

    def fetch(self, source: Source) -> FetchedItem:
        """Fetch content from NYDFS source with retry logic and rate limiting."""
        headers = {
            "User-Agent": "RegEngine/1.0 (Compliance Automation; +https://github.com/regengine)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        for attempt in range(self.MAX_RETRIES):
            try:
                response = requests.get(
                    source.url,
                    headers=headers,
                    timeout=self.REQUEST_TIMEOUT,
                    allow_redirects=True,
                )

                # Respect rate limits
                if response.status_code == 429:
                    retry_after = int(
                        response.headers.get("Retry-After", self.RETRY_DELAY)
                    )
                    time.sleep(retry_after)
                    continue

                response.raise_for_status()

                # Extract text content from HTML
                content_type = response.headers.get("Content-Type", "text/html")

                if "text/html" in content_type:
                    soup = BeautifulSoup(response.content, "html.parser")
                    # Remove script and style elements
                    for script in soup(["script", "style", "nav", "footer"]):
                        script.decompose()

                    # Get text content
                    text_content = soup.get_text(separator="\n", strip=True)
                    content_bytes = text_content.encode("utf-8")
                else:
                    content_bytes = response.content

                return FetchedItem(
                    source=source,
                    content_bytes=content_bytes,
                    content_type=content_type,
                )

            except requests.Timeout:
                if attempt >= self.MAX_RETRIES - 1:
                    raise
                time.sleep(self.RETRY_DELAY * (attempt + 1))
            except requests.RequestException as e:
                if attempt >= self.MAX_RETRIES - 1:
                    # Return empty content on final failure
                    return FetchedItem(
                        source=source,
                        content_bytes=b"",
                        content_type="text/html",
                    )
                time.sleep(self.RETRY_DELAY * (attempt + 1))

        # Fallback empty response
        return FetchedItem(source=source, content_bytes=b"", content_type="text/html")
