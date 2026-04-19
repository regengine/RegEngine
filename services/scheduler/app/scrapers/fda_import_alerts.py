"""FDA Import Alerts scraper.

Scrapes FDA Import Alerts which identify products that may appear to
violate FDA requirements and are subject to Detention Without Physical Examination.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import List, Optional

import httpx
import structlog

from ..models import EnforcementItem, EnforcementSeverity, ScrapeResult, SourceType
from .base import BaseScraper, fetch_with_retry

logger = structlog.get_logger("scraper.fda_import_alerts")

# FDA Import Alerts page
FDA_IMPORT_ALERTS_URL = "https://www.accessdata.fda.gov/cms_ia/ialist.html"

# FDA Import Alert API (via openFDA)
FDA_IMPORT_ALERT_API = "https://api.fda.gov/food/enforcement.json"


class FDAImportAlertsScraper(BaseScraper):
    """Scraper for FDA Import Alerts.

    Import Alerts are issued when FDA identifies products from specific
    countries, geographic regions, or shippers that may violate FDA law.

    These are critical for:
    - Supply chain risk assessment
    - Supplier vetting
    - Import compliance
    """

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = httpx.Client(timeout=30.0)
        self.session.headers.update(
            {
                "User-Agent": "RegEngine/1.0 (Regulatory Compliance Platform)",
                "Accept": "text/html, application/json",
            }
        )

    @property
    def source_type(self) -> SourceType:
        return SourceType.FDA_IMPORT_ALERT

    @property
    def name(self) -> str:
        return "FDA Import Alerts"

    def scrape(self) -> ScrapeResult:
        """Scrape FDA Import Alerts."""
        start_time = time.time()
        items: List[EnforcementItem] = []
        error_message: Optional[str] = None

        try:
            # Scrape the import alerts index
            items = self._scrape_alerts_page()
            logger.info(
                "fda_import_alerts_scraped",
                count=len(items),
            )

        except Exception as e:
            error_message = str(e)
            logger.error(
                "fda_import_alerts_failed",
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

    def close(self) -> None:
        """Close the underlying HTTP client to release connections."""
        self.session.close()

    def _scrape_alerts_page(self) -> List[EnforcementItem]:
        """Parse FDA Import Alerts HTML page."""
        # #1138: retry on 5xx/transport errors.
        response = fetch_with_retry(
            self.session,
            FDA_IMPORT_ALERTS_URL,
            timeout=self.timeout,
            log_scope="fda_import_alerts_html",
        )
        response.raise_for_status()

        items = []

        # Parse HTML (simplified - in production use BeautifulSoup)
        # Import alerts have format: "XX-YY - Alert Title"
        alert_pattern = re.compile(
            r'href=["\']([^"\']+)["\'][^>]*>(\d{2}-\d{2})\s*[-–]\s*([^<]+)</a>',
            re.IGNORECASE,
        )

        for match in alert_pattern.finditer(response.text):
            try:
                url, alert_number, title = match.groups()
                title = title.strip()

                # Make URL absolute
                if not url.startswith("http"):
                    url = f"https://www.accessdata.fda.gov/cms_ia/{url}"

                source_id = self._create_source_id("fda_ia", alert_number)

                # Import alerts are typically HIGH severity
                items.append(
                    EnforcementItem(
                        source_type=self.source_type,
                        source_id=source_id,
                        title=f"Import Alert {alert_number}: {title}",
                        summary=f"FDA Import Alert regarding: {title}",
                        url=url,
                        published_date=datetime.now(timezone.utc),  # Page doesn't have dates
                        severity=EnforcementSeverity.HIGH,
                        affected_products=[],
                        affected_companies=[],
                        jurisdiction="US-FDA",
                        raw_data={
                            "alert_number": alert_number,
                            "raw_title": title,
                        },
                    )
                )

            except Exception as item_error:
                logger.warning(
                    "import_alert_parse_error",
                    error=str(item_error),
                )
                continue

        return items
