"""FDA Import Alerts scraper.

Scrapes FDA Import Alerts which identify products that may appear to
violate FDA requirements and are subject to Detention Without Physical Examination.
"""

from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from urllib.parse import urljoin

import httpx
import structlog
from bs4 import BeautifulSoup

from ..models import EnforcementItem, EnforcementSeverity, ScrapeResult, SourceType
from .base import BaseScraper

logger = structlog.get_logger("scraper.fda_import_alerts")

# FDA Import Alerts page
FDA_IMPORT_ALERTS_URL = "https://www.accessdata.fda.gov/cms_ia/ialist.html"

# FDA Import Alert API (via openFDA)
FDA_IMPORT_ALERT_API = "https://api.fda.gov/food/enforcement.json"

# ── #1140: parser-mismatch detection ────────────────────────────────────────
# The previous implementation used a hand-rolled regex
#     r'href=["\']([^"\']+)["\'][^>]*>(\d{2}-\d{2})\s*[-–]\s*([^<]+)</a>'
# which failed silently whenever FDA shipped any of:
#   * a different alert-number shape (real data has 3- and 4-digit suffixes,
#     and sub-category letters — the 2-2 shape only ever covered a subset);
#   * a different separator (FDA has used "-", "–", "—", and ":");
#   * an anchor with nested markup (<b>, <span>) so the `>(\d…)` look-behind
#     didn't line up against the number;
#   * a different outer structure (table vs list vs JS-rendered widget).
#
# When that happened the scrape returned success=True with zero items and
# nothing alarmed. Import Alerts are HIGH severity; silent drops are a real
# compliance risk.
#
# Fix:
#   1. Parse with BeautifulSoup (already a dep) so nested markup is handled.
#   2. Accept a broader alert-number shape + broader separators.
#   3. Plausibility guard: if the response looks like the right page but we
#      extract zero items, surface a ``parser_mismatch_suspected`` warning on
#      the ScrapeResult. The scheduler alerter fires on non-empty warnings.
_MIN_PLAUSIBLE_BODY_BYTES = 1000
_PLAUSIBILITY_KEYWORDS: Tuple[str, ...] = ("Import Alert", "import alert")

# Alert number formats observed in FDA data (and historical):
#   "66-40"       — 2-2 digits (the ONLY shape the old regex matched)
#   "16-120"      — 2-3 digits
#   "16-120-A"    — with letter subcategory
#   "16-120-01"   — with numeric subcategory
# So: <1-3 digits>-<1-4 digits>(-<alnum>)?
_ALERT_NUMBER_PATTERN = re.compile(r"^\s*(\d{1,3}-\d{1,4}(?:-[A-Za-z0-9]+)?)\b")

# Separator between alert number and title. FDA has used ASCII hyphen, en-dash,
# em-dash, and colon at various times.
_TITLE_SEPARATOR = re.compile(r"\s*[-–—:]\s+")


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
        warnings: List[str] = []
        error_message: Optional[str] = None

        try:
            # Scrape the import alerts index
            items, warnings = self._scrape_alerts_page()
            logger.info(
                "fda_import_alerts_scraped",
                count=len(items),
                warnings=warnings or None,
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
            warnings=warnings,
        )

    def close(self) -> None:
        """Close the underlying HTTP client to release connections."""
        self.session.close()

    def _scrape_alerts_page(self) -> Tuple[List[EnforcementItem], List[str]]:
        """Fetch and parse the FDA Import Alerts HTML page.

        Returns a tuple ``(items, warnings)``. Warnings are soft signals —
        the scrape didn't fail, but the operator should investigate (e.g.
        the parser may be out of date because FDA changed the HTML).
        """
        response = self.session.get(FDA_IMPORT_ALERTS_URL, timeout=self.timeout)
        response.raise_for_status()

        return self.parse_html(response.text, base_url=FDA_IMPORT_ALERTS_URL)

    def parse_html(
        self,
        html: str,
        *,
        base_url: str = FDA_IMPORT_ALERTS_URL,
    ) -> Tuple[List[EnforcementItem], List[str]]:
        """Parse FDA Import Alerts HTML into EnforcementItems.

        Public entry point so tests can exercise the parser with captured
        fixture HTML without hitting the network. Also used by
        ``_scrape_alerts_page`` after a successful fetch.

        Parser strategy:
          1. Use BeautifulSoup with ``lxml`` (or ``html.parser`` fallback).
          2. Walk every ``<a>`` tag in the document.
          3. For each anchor, check whether the anchor text (with nested
             markup collapsed) starts with an Import Alert number shape:
             ``digits-digits(-alnum)?``. If so extract (number, title).
          4. Dedupe by alert number — FDA sometimes lists the same alert
             under multiple sections (country / product / etc.)
          5. If the response body is plausibly the right page (reachable,
             ≥1KB, contains "Import Alert") but we extracted zero alerts,
             append a ``parser_mismatch_suspected`` warning so the
             scheduler alarm fires.

        Returns
        -------
        ``(items, warnings)``
        """
        warnings: List[str] = []

        # Prefer lxml; fall back to the stdlib parser if lxml isn't
        # importable at runtime (shouldn't happen given pyproject pins,
        # but we want to stay resilient in case a deployment ships
        # without it).
        try:
            soup = BeautifulSoup(html, "lxml")
        except Exception as lxml_err:  # noqa: BLE001 - log + fall back
            logger.warning(
                "fda_import_alerts_lxml_unavailable",
                error=str(lxml_err),
            )
            soup = BeautifulSoup(html, "html.parser")

        items: List[EnforcementItem] = []
        seen_alert_numbers: set[str] = set()

        for anchor in soup.find_all("a"):
            href = anchor.get("href")
            if not href:
                continue

            # get_text collapses nested markup (bold, spans) that
            # historically broke the hand-rolled regex.
            text = anchor.get_text(" ", strip=True)
            if not text:
                continue

            parsed = self._extract_alert_from_anchor(text)
            if parsed is None:
                continue

            alert_number, title = parsed
            if alert_number in seen_alert_numbers:
                continue
            seen_alert_numbers.add(alert_number)

            # Resolve relative URLs against the page URL.
            absolute_url = urljoin(base_url, href)

            source_id = self._create_source_id("fda_ia", alert_number)

            items.append(
                EnforcementItem(
                    source_type=self.source_type,
                    source_id=source_id,
                    title=(
                        f"Import Alert {alert_number}: {title}"
                        if title
                        else f"Import Alert {alert_number}"
                    ),
                    summary=(
                        f"FDA Import Alert regarding: {title}"
                        if title
                        else f"FDA Import Alert {alert_number}"
                    ),
                    url=absolute_url,
                    published_date=datetime.now(timezone.utc),  # Page has no per-row date
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

        # Plausibility guard. If we got zero items but the page clearly
        # looks like the Import Alert listing, FDA changed the markup —
        # emit a warning so the scheduler alerter fires.
        if not items and self._looks_plausible(html):
            page_fingerprint = hashlib.sha256(
                html[:4096].encode("utf-8", errors="ignore")
            ).hexdigest()[:16]
            warning_msg = (
                "parser_mismatch_suspected: page looks like Import Alert listing "
                f"but zero alerts parsed (body_bytes={len(html)}, "
                f"fingerprint={page_fingerprint})"
            )
            warnings.append(warning_msg)
            logger.warning(
                "fda_import_alerts_parser_mismatch_suspected",
                body_bytes=len(html),
                fingerprint=page_fingerprint,
                anchor_count=len(soup.find_all("a")),
                note=(
                    "HTML looks plausible but zero alerts parsed — "
                    "FDA may have changed the page structure"
                ),
            )

        return items, warnings

    @staticmethod
    def _extract_alert_from_anchor(text: str) -> Optional[Tuple[str, str]]:
        """Pull an ``(alert_number, title)`` pair out of anchor text.

        Returns ``None`` if the text doesn't look like an alert row.

        Examples accepted:
            "16-120 - Detention Without Physical Examination of …"
            "16-120 – Shrimp from India"
            "66-40: Seafood HACCP"
            "16-120-A - Subcategory Example"
            "16-120"                                   (number only — title empty)

        Examples rejected (returns None):
            "Home"                                     (navigation link)
            "More info"                                (no alert number)
            "Publications"                             (no alert number)
        """
        match = _ALERT_NUMBER_PATTERN.match(text)
        if not match:
            return None
        alert_number = match.group(1)
        remainder = text[match.end():]

        # Split on the separator if present; otherwise the anchor text is
        # just the number and we return an empty title.
        split = _TITLE_SEPARATOR.split(remainder, maxsplit=1)
        if len(split) == 2 and split[1].strip():
            title = split[1].strip()
        else:
            title = remainder.lstrip(" -–—:").strip()

        # Guard against pathological titles — truncate to keep the DB
        # payload sane.
        if len(title) > 400:
            title = title[:400].rstrip() + "…"

        return alert_number, title

    @staticmethod
    def _looks_plausible(html: str) -> bool:
        """Does this response look like it's still the Import Alert page?

        Used to distinguish:
          * "FDA genuinely published no new alerts today" — the page may
            still be large; with this check disabled we'd spuriously alarm.
          * "parser is broken because the HTML changed" — the page is
            full-sized and contains the right keywords, but we parsed zero
            alerts.

        We treat the response as plausible iff body ≥ 1KB AND the page
        mentions "Import Alert" (case-sensitive or lower). Those two
        together rule out tiny error pages, redirects, and CDN holdings.
        """
        if len(html) < _MIN_PLAUSIBLE_BODY_BYTES:
            return False
        return any(kw in html for kw in _PLAUSIBILITY_KEYWORDS)
