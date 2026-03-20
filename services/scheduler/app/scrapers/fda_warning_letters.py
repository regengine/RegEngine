"""FDA Warning Letters scraper.

Scrapes FDA Warning Letters from the official RSS feed and API.
Warning Letters are enforcement actions issued to companies for regulatory violations.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import List, Optional
from defusedxml import ElementTree

import requests
import structlog

from ..models import EnforcementItem, EnforcementSeverity, ScrapeResult, SourceType
from .base import BaseScraper

logger = structlog.get_logger("scraper.fda_warning_letters")

# FDA Warning Letters RSS Feed
FDA_WARNING_LETTERS_RSS = "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/warning-letters/rss.xml"

# Alternative: FDA API endpoint (more structured)
FDA_API_BASE = "https://api.fda.gov/food/enforcement.json"


class FDAWarningLettersScraper(BaseScraper):
    """Scraper for FDA Warning Letters.

    Primary source: FDA RSS feed
    Fallback: FDA openFDA API

    Warning Letters are issued when FDA finds serious regulatory violations.
    These require immediate attention as they often precede enforcement actions.
    """

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()
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
        error_message: Optional[str] = None

        try:
            # Try RSS feed first
            items = self._scrape_rss()
            
            if items:
                logger.info(
                    "fda_warning_letters_scraped",
                    source="rss",
                    count=len(items),
                )
            else:
                # If _scrape_rss returned [] because of a 404, we try API
                logger.debug("no_rss_items_trying_api_fallback")
                items = self._scrape_api()
                logger.info(
                    "fda_warning_letters_scraped",
                    source="api",
                    count=len(items),
                )

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
        )

    def _scrape_rss(self) -> List[EnforcementItem]:
        """Parse FDA Warning Letters RSS feed."""
        try:
            response = self.session.get(FDA_WARNING_LETTERS_RSS, timeout=self.timeout)
            
            if response.status_code == 404:
                logger.info(
                    "rss_feed_defunct_skipping",
                    url=FDA_WARNING_LETTERS_RSS,
                    note="FDA has reorganized feeds; using API fallback"
                )
                return []
                
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            # Re-raise for fallback logic in scrape()
            raise e

        items = []
        root = ElementTree.fromstring(response.content)

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

            except Exception as item_error:
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

        response = self.session.get(
            FDA_API_BASE,
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()

        items = []
        for result in data.get("results", []):
            try:
                recall_number = result.get("recall_number", "")
                source_id = self._create_source_id("fda_enf", recall_number)

                # Parse date
                report_date = result.get("report_date", "")
                if report_date:
                    published_date = datetime.strptime(report_date, "%Y%m%d").replace(
                        tzinfo=timezone.utc
                    )
                else:
                    published_date = datetime.now(timezone.utc)

                # Determine severity from classification
                classification = result.get("classification", "")
                if "Class I" in classification:
                    severity = EnforcementSeverity.CRITICAL
                elif "Class II" in classification:
                    severity = EnforcementSeverity.HIGH
                else:
                    severity = EnforcementSeverity.MEDIUM

                items.append(
                    EnforcementItem(
                        source_type=self.source_type,
                        source_id=source_id,
                        title=f"{result.get('recalling_firm', 'Unknown')} - {result.get('product_description', '')[:100]}",
                        summary=result.get("reason_for_recall", "")[:500],
                        url=f"https://www.accessdata.fda.gov/scripts/ires/index.cfm?event=ires.dspBriefRecallNumber&RecallNumber={recall_number}",
                        published_date=published_date,
                        severity=severity,
                        affected_products=[result.get("product_description", "")],
                        affected_companies=[result.get("recalling_firm", "")],
                        jurisdiction="US-FDA",
                        raw_data=result,
                    )
                )

            except Exception as item_error:
                logger.warning(
                    "api_item_parse_error",
                    error=str(item_error),
                )
                continue

        return items

    def _parse_rss_date(self, date_str: str) -> datetime:
        """Parse RFC 822 date format used in RSS."""
        if not date_str:
            return datetime.now(timezone.utc)

        try:
            # Example: "Wed, 15 Jan 2026 12:00:00 -0500"
            from email.utils import parsedate_to_datetime

            return parsedate_to_datetime(date_str)
        except Exception:
            return datetime.now(timezone.utc)
