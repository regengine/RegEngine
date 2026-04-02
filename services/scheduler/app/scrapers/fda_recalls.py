"""FDA Recalls scraper.

Scrapes FDA recall announcements via the openFDA API.
These are critical safety alerts that often require 24-hour response.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import List, Optional

import httpx
import structlog

from ..models import EnforcementItem, EnforcementSeverity, ScrapeResult, SourceType
from .base import BaseScraper

logger = structlog.get_logger("scraper.fda_recalls")

# openFDA Enforcement API
FDA_ENFORCEMENT_API = "https://api.fda.gov/food/enforcement.json"


class FDARecallsScraper(BaseScraper):
    """Scraper for FDA Food Recalls.

    Uses the openFDA Enforcement API to fetch recent recall announcements.

    Recall classifications:
    - Class I: Dangerous or defective products that could cause serious health
               problems or death.
    - Class II: Products that might cause a temporary health problem, or pose
                only a slight threat of a serious nature.
    - Class III: Products are unlikely to cause any adverse health reaction,
                 but that violate FDA labeling or manufacturing laws.

    FSMA 204 relevance:
    - Class I and II recalls trigger 24-hour traceability requirements
    - Companies must produce trace reports within 24 hours of request
    """

    def __init__(self, timeout: int = 30, limit: int = 100):
        self.timeout = timeout
        self.limit = limit
        self.session = httpx.Client()
        self.session.headers.update(
            {
                "User-Agent": "RegEngine/1.0 (Regulatory Compliance Platform)",
                "Accept": "application/json",
            }
        )

    @property
    def source_type(self) -> SourceType:
        return SourceType.FDA_RECALL

    @property
    def name(self) -> str:
        return "FDA Food Recalls"

    def scrape(self) -> ScrapeResult:
        """Scrape FDA Recalls from openFDA API."""
        start_time = time.time()
        items: List[EnforcementItem] = []
        error_message: Optional[str] = None

        try:
            items = self._fetch_recalls()
            logger.info(
                "fda_recalls_scraped",
                count=len(items),
            )

        except (httpx.HTTPError, ConnectionError, TimeoutError, ValueError, KeyError) as e:
            error_message = str(e)
            logger.error(
                "fda_recalls_failed",
                error=error_message,
            )

        duration_ms = (time.time() - start_time) * 1000

        return ScrapeResult(
            source_type=self.source_type,
            success=error_message is None,
            items_found=len(items),
            items_new=len(items),
            items=items,
            error_message=error_message,
            duration_ms=duration_ms,
        )

    def _fetch_recalls(self) -> List[EnforcementItem]:
        """Fetch recalls from openFDA API."""
        # Query for recent ongoing recalls
        params = {
            "search": 'status:"Ongoing"',
            "limit": self.limit,
            "sort": "report_date:desc",
        }

        response = self.session.get(
            FDA_ENFORCEMENT_API,
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()

        items = []
        for result in data.get("results", []):
            try:
                item = self._parse_recall(result)
                if item:
                    items.append(item)
            except (ValueError, TypeError, KeyError, AttributeError) as e:
                logger.warning(
                    "recall_parse_error",
                    error=str(e),
                    recall_number=result.get("recall_number", "unknown"),
                )
                continue

        return items

    def _parse_recall(self, result: dict) -> Optional[EnforcementItem]:
        """Parse a single recall from API response."""
        recall_number = result.get("recall_number", "")
        if not recall_number:
            return None

        source_id = self._create_source_id("fda_recall", recall_number)

        # Parse date
        report_date = result.get("report_date", "")
        if report_date:
            try:
                published_date = datetime.strptime(report_date, "%Y%m%d").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                published_date = datetime.now(timezone.utc)
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

        # Extract product info
        product_description = result.get("product_description", "")
        recalling_firm = result.get("recalling_firm", "Unknown")

        # Build title
        title = f"[{classification}] {recalling_firm}"
        if product_description:
            title += f" - {product_description[:80]}"

        # FDA recall page URL
        url = f"https://www.accessdata.fda.gov/scripts/ires/index.cfm?event=ires.dspBriefRecallNumber&RecallNumber={recall_number}"

        return EnforcementItem(
            source_type=self.source_type,
            source_id=source_id,
            title=title,
            summary=result.get("reason_for_recall", "")[:500],
            url=url,
            published_date=published_date,
            severity=severity,
            affected_products=[product_description] if product_description else [],
            affected_companies=[recalling_firm],
            jurisdiction="US-FDA",
            raw_data={
                "recall_number": recall_number,
                "classification": classification,
                "status": result.get("status", ""),
                "distribution_pattern": result.get("distribution_pattern", ""),
                "product_quantity": result.get("product_quantity", ""),
                "voluntary_mandated": result.get("voluntary_mandated", ""),
                "initial_firm_notification": result.get("initial_firm_notification", ""),
                "state": result.get("state", ""),
                "city": result.get("city", ""),
            },
        )

    def get_by_classification(self, classification: str = "Class I") -> ScrapeResult:
        """Fetch recalls of a specific classification.

        Args:
            classification: "Class I", "Class II", or "Class III"

        Returns:
            ScrapeResult with filtered recalls
        """
        start_time = time.time()
        items: List[EnforcementItem] = []
        error_message: Optional[str] = None

        try:
            params = {
                "search": f'classification:"{classification}" AND status:"Ongoing"',
                "limit": self.limit,
                "sort": "report_date:desc",
            }

            response = self.session.get(
                FDA_ENFORCEMENT_API,
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()

            for result in data.get("results", []):
                item = self._parse_recall(result)
                if item:
                    items.append(item)

            logger.info(
                "fda_recalls_by_class_scraped",
                classification=classification,
                count=len(items),
            )

        except (httpx.HTTPError, ConnectionError, TimeoutError, ValueError, KeyError) as e:
            error_message = str(e)
            logger.error(
                "fda_recalls_by_class_failed",
                classification=classification,
                error=error_message,
            )

        duration_ms = (time.time() - start_time) * 1000

        return ScrapeResult(
            source_type=self.source_type,
            success=error_message is None,
            items_found=len(items),
            items_new=len(items),
            items=items,
            error_message=error_message,
            duration_ms=duration_ms,
        )
