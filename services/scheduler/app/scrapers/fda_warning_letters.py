"""FDA Warning Letters scraper.

Scrapes FDA Warning Letters from the official RSS feed and API.
Warning Letters are enforcement actions issued to companies for regulatory violations.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import List, Optional

import httpx
import structlog
from defusedxml import ElementTree
from shared.safe_http import PinnedHTTPSession

from ..models import EnforcementItem, EnforcementSeverity, ScrapeResult, SourceType
from .base import BaseScraper, fetch_with_retry

logger = structlog.get_logger("scraper.fda_warning_letters")

# FDA Warning Letters RSS Feed
FDA_WARNING_LETTERS_RSS = "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/warning-letters/rss.xml"

# Alternative: FDA API endpoint (more structured)
FDA_API_BASE = "https://api.fda.gov/food/enforcement.json"


class _UnreadableRSSFeed(Exception):
    """The RSS body could not be parsed, or defusedxml rejected it."""


class FDAWarningLettersScraper(BaseScraper):
    """Scraper for FDA Warning Letters.

    Primary source: FDA RSS feed
    Fallback: FDA openFDA API

    Warning Letters are issued when FDA finds serious regulatory violations.
    These require immediate attention as they often precede enforcement actions.
    """

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = PinnedHTTPSession()
        self.session.headers.update(
            {
                "User-Agent": "RegEngine/1.0 (Regulatory Compliance Platform)",
                "Accept": "application/xml, application/json",
            }
        )

    @property
    def source_type(self) -> SourceType:
        return SourceType.FDA_WARNING_LETTER

    @property
    def name(self) -> str:
        return "FDA Warning Letters"

    def scrape(self) -> ScrapeResult:
        """Scrape FDA Warning Letters from RSS feed."""
        start_time = time.time()
        items: List[EnforcementItem] = []
        warnings: List[str] = []
        error_message: Optional[str] = None
        rss_unreadable: Optional[str] = None

        try:
            # Try RSS feed first
            try:
                items = self._scrape_rss()
            except _UnreadableRSSFeed as unreadable:
                rss_unreadable = f"rss_unreadable: {unreadable}"

            if items:
                logger.info(
                    "fda_warning_letters_scraped",
                    source="rss",
                    count=len(items),
                )
            else:
                # The feed gave no items (404, empty, or unreadable): try the API.
                logger.debug("no_rss_items_trying_api_fallback")
                items = self._scrape_api()
                logger.info(
                    "fda_warning_letters_scraped",
                    source="api",
                    count=len(items),
                )
                # An unreadable feed still falls back to the API (#3323). If
                # the API is empty too, nothing shows the source is healthy,
                # so record a failed scrape (#3293). If the API has items,
                # data still flows and the broken feed becomes a warning.
                if rss_unreadable:
                    if items:
                        warnings.append(rss_unreadable)
                    else:
                        error_message = f"{rss_unreadable}; openFDA API fallback returned no items"

        # QA5: broad catch is intentional. The scraper contract is to always
        # return a ScrapeResult, never raise: the scheduler records a failure
        # result with an error message, while a raised error skips that
        # bookkeeping. This previously let XML parse errors (a SyntaxError,
        # not a ValueError) escape on malformed RSS bodies.
        except Exception as scrap_error:
            logger.warning(
                "scrape_attempt_failed",
                error=str(scrap_error),
                source="rss_or_api",
            )
            error_message = str(scrap_error)

        duration_ms = (time.time() - start_time) * 1000

        return ScrapeResult(
            source_type=self.source_type,
            success=error_message is None,
            items_found=len(items),
            items_new=len(items),  # Deduplication happens in the scheduler
            items=items,
            error_message=error_message,
            duration_ms=duration_ms,
            warnings=warnings,
        )

    def _scrape_rss(self) -> List[EnforcementItem]:
        """Parse FDA Warning Letters RSS feed."""
        try:
            # #1138: retry on 5xx/transport errors so a single blip doesn't
            # force the scrape down the (slower) fallback path. 404 must
            # still pass through — the RSS feed was deprecated by FDA and
            # 404 is the normal case; we branch on status_code below.
            response = fetch_with_retry(
                self.session,
                FDA_WARNING_LETTERS_RSS,
                timeout=self.timeout,
                log_scope="fda_warning_letters_rss",
                allow_404_passthrough=True,
            )

            if response.status_code == 404:
                logger.info(
                    "rss_feed_defunct_skipping",
                    url=FDA_WARNING_LETTERS_RSS,
                    note="FDA has reorganized feeds; using API fallback",
                )
                return []

            response.raise_for_status()
        except httpx.HTTPError as e:
            # Re-raise for fallback logic in scrape()
            raise e

        items = []
        try:
            root = ElementTree.fromstring(response.content)
        except Exception as parse_error:
            # ParseError is a SyntaxError and EntitiesForbidden is a
            # ValueError. Raised as is, either becomes a failed scrape with
            # no API fallback. scrape() treats an unreadable body as an empty
            # feed and falls back, but unlike a well-formed empty feed it is
            # a failure when the fallback is empty too.
            logger.warning(
                "rss_unreadable_falling_back_to_api",
                error=str(parse_error),
                error_type=type(parse_error).__name__,
            )
            raise _UnreadableRSSFeed(f"{type(parse_error).__name__}: {parse_error}") from parse_error

        # RSS structure: rss/channel/item
        for item in root.findall(".//item"):
            try:
                title = item.findtext("title", "").strip()
                link = item.findtext("link", "").strip()
                description = item.findtext("description", "").strip()
                pub_date_str = item.findtext("pubDate", "")

                if not title or not link:
                    continue

                # Parse date (RFC 822 format)
                published_date = self._parse_rss_date(pub_date_str)

                # Extract company name from title (usually "Company Name - Date")
                company_name = title.split(" - ")[0] if " - " in title else title

                # Create source ID from link (stable identifier)
                source_id = self._create_source_id("fda_wl", link.split("/")[-1])

                items.append(
                    EnforcementItem(
                        source_type=self.source_type,
                        source_id=source_id,
                        title=title,
                        summary=description[:500] if description else None,
                        url=link,
                        published_date=published_date,
                        severity=EnforcementSeverity.HIGH,
                        affected_companies=[company_name],
                        jurisdiction="US-FDA",
                        raw_data={
                            "rss_title": title,
                            "rss_description": description,
                            "rss_pub_date": pub_date_str,
                        },
                    )
                )

            except (ValueError, TypeError, KeyError, AttributeError) as item_error:
                logger.warning(
                    "rss_item_parse_error",
                    error=str(item_error),
                )
                continue

        return items

    def _scrape_api(self) -> List[EnforcementItem]:
        """Fetch from openFDA enforcement API."""
        # Query recent food enforcement actions
        params = {
            "search": 'status:"Ongoing"',
            "limit": 100,
            "sort": "report_date:desc",
        }

        # #1138: retry on 5xx/transport errors with Retry-After honoring.
        response = fetch_with_retry(
            self.session,
            FDA_API_BASE,
            params=params,
            timeout=self.timeout,
            log_scope="fda_warning_letters_api",
        )
        response.raise_for_status()
        data = response.json()

        items = []
        for result in data.get("results", []):
            try:
                recall_number = result.get("recall_number", "")
                if not recall_number:
                    # QA5: rows without a recall number must leave a trace
                    # instead of sharing source_id "fda_enf:". The state
                    # manager dedupes on source_id only, so emitting them
                    # would silently drop distinct actions after the first.
                    logger.warning(
                        "warning_letter_row_missing_recall_number_dropped",
                        report_date=result.get("report_date", ""),
                        classification=result.get("classification", ""),
                        product_hint=str(result.get("product_description", ""))[:80],
                    )
                    continue
                source_id = self._create_source_id("fda_enf", recall_number)

                # Parse date
                report_date = result.get("report_date", "")
                if report_date:
                    published_date = datetime.strptime(report_date, "%Y%m%d").replace(tzinfo=timezone.utc)
                else:
                    published_date = datetime.now(timezone.utc)

                # Determine severity from classification
                classification = result.get("classification", "")
                if re.search(r"\bCLASS\s+II\b", classification, flags=re.IGNORECASE):
                    severity = EnforcementSeverity.HIGH
                elif re.search(r"\bCLASS\s+I\b", classification, flags=re.IGNORECASE):
                    severity = EnforcementSeverity.CRITICAL
                else:
                    severity = EnforcementSeverity.MEDIUM

                recalling_firm = result.get("recalling_firm", "") or "Unknown"
                product_description = result.get("product_description", "") or ""

                items.append(
                    EnforcementItem(
                        source_type=self.source_type,
                        source_id=source_id,
                        title=f"{recalling_firm} - {product_description[:100]}",
                        summary=result.get("reason_for_recall", "")[:500],
                        url=f"https://www.accessdata.fda.gov/scripts/ires/index.cfm?event=ires.dspBriefRecallNumber&RecallNumber={recall_number}",
                        published_date=published_date,
                        severity=severity,
                        affected_products=[product_description] if product_description else [],
                        affected_companies=[recalling_firm],
                        jurisdiction="US-FDA",
                        raw_data=result,
                    )
                )

            except (ValueError, TypeError, KeyError, AttributeError) as item_error:
                logger.warning(
                    "api_item_parse_error",
                    error=str(item_error),
                )
                continue

        return items

    def close(self) -> None:
        """Close the underlying HTTP client to release connections."""
        self.session.close()

    def _parse_rss_date(self, date_str: str) -> datetime:
        """Parse RFC 822 date format used in RSS."""
        if not date_str:
            return datetime.now(timezone.utc)

        try:
            # Example: "Wed, 15 Jan 2026 12:00:00 -0500"
            from email.utils import parsedate_to_datetime

            parsed = parsedate_to_datetime(date_str)
            # QA5: feeds sometimes omit the zone. Return UTC-aware so
            # downstream code never mixes naive and aware datetimes.
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except (ValueError, TypeError, OverflowError):
            return datetime.now(timezone.utc)
