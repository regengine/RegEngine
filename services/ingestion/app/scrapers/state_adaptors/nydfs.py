from __future__ import annotations

import time
from html.parser import HTMLParser
from typing import Iterable

import httpx
import structlog
from shared.safe_http import safe_httpx_get_sync
from shared.url_validation import SSRFError, validate_url

from .base import FetchedItem, Source, StateRegistryScraper

logger = structlog.get_logger("scrapers.nydfs")


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._ignored: list[str] = []
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"script", "style", "nav", "footer"}:
            self._ignored.append(tag.lower())

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self._ignored:
            # Pop down to and including the matching open tag so one
            # unclosed or mismatched tag cannot swallow the rest of the page.
            while self._ignored and self._ignored[-1] != tag:
                self._ignored.pop()
            if self._ignored:
                self._ignored.pop()

    def handle_data(self, data: str) -> None:
        if self._ignored:
            return
        text = " ".join(data.split())
        if text:
            self._parts.append(text)

    def text(self) -> str:
        return "\n".join(self._parts)


class NYDFSScraper(StateRegistryScraper):
    """NYDFS regulatory source adaptor."""

    BASE_URL = "https://www.dfs.ny.gov"
    REQUEST_TIMEOUT = 30
    MAX_RETRIES = 3
    RETRY_DELAY = 2.0

    def list_sources(self) -> Iterable[Source]:
        yield Source(
            url=f"{self.BASE_URL}/industry_guidance/cybersecurity",
            title="NYDFS Cybersecurity Resource Center",
            jurisdiction_code="US-NY",
        )
        yield Source(
            url=f"{self.BASE_URL}/apps_and_licensing/regulations",
            title="NYDFS Regulations",
            jurisdiction_code="US-NY",
        )

    def fetch(self, source: Source) -> FetchedItem:
        """Fetch and lightly normalize NYDFS HTML/PDF content."""

        try:
            validated_url = validate_url(source.url)
        except SSRFError as exc:
            logger.warning("nydfs_url_rejected", url=source.url, error=str(exc))
            raise ValueError(f"URL validation failed: {exc}") from exc

        # SSRF defense (RE-SEC-INGEST-003): route through safe_httpx_get_sync
        # so every redirect hop is re-validated and the connection is pinned
        # to a validated IP (closes the DNS-rebinding TOCTOU window that raw
        # requests.get left open). Failures surface as OSError (the same
        # IOError family requests errors belonged to) so the scrape-job retry
        # contract is unchanged; SSRF rejections stay ValueError.
        last_error: Exception | None = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = safe_httpx_get_sync(
                    validated_url,
                    headers={"User-Agent": "RegEngine/1.0 (Compliance Monitoring)"},
                    timeout=self.REQUEST_TIMEOUT,
                )
                if response.status_code == 429 and attempt < self.MAX_RETRIES:
                    retry_after = _retry_delay(response.headers.get("Retry-After"), self.RETRY_DELAY)
                    time.sleep(retry_after)
                    continue
                response.raise_for_status()

                content_type = response.headers.get("Content-Type", "application/octet-stream").split(";")[0]
                content = response.content
                if content_type == "text/html":
                    content = _extract_visible_text(content).encode("utf-8")
                return FetchedItem(source=source, content_bytes=content, content_type=content_type)
            except SSRFError as exc:
                raise ValueError(f"URL validation failed: {exc}") from exc
            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY)
                    continue
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY)
                    continue

        if last_error is not None:
            raise OSError(f"NYDFS fetch failed: {last_error}") from last_error
        raise RuntimeError("NYDFS fetch failed without an exception")


def _retry_delay(value: str | None, fallback: float) -> float:
    try:
        if value is None:
            return fallback
        return max(float(value), 0.0)
    except ValueError:
        return fallback


def _extract_visible_text(content: bytes) -> str:
    parser = _VisibleTextParser()
    parser.feed(content.decode("utf-8", errors="replace"))
    return parser.text()
