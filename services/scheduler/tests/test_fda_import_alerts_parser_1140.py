"""Regression tests for issue #1140 — FDA Import Alerts parser.

Before the fix the scraper used a hand-rolled regex:

    r'href=["\\']([^"\\']+)["\\'][^>]*>(\\d{2}-\\d{2})\\s*[-–]\\s*([^<]+)</a>'

which dropped anything with:
  - a 3- or 4-digit suffix (16-120, 66-400) — real FDA data has these
  - a different separator (em-dash, colon)
  - nested markup inside the anchor (<b>, <span>) because the regex is
    anchored to `>(digits`, so a `<b>` between `<a>` and the digits
    breaks the lookbehind
  - a subcategory letter or number (16-120-A)

…and returned ``success=True, items=[]`` silently. Import alerts are HIGH
severity; silent dropping is a compliance risk.

These tests exercise the BeautifulSoup-based parser via the public
``parse_html`` entry point (no network). They cover:

1. A realistic FDA listing HTML → parses multiple alerts, absolute URLs.
2. Anchor numbers with 3-digit suffix → matched (old regex missed these).
3. Anchor numbers with subcategory letter/digit → matched.
4. Alternate separators (en-dash, em-dash, colon, ASCII hyphen) → matched.
5. Nested markup inside the anchor (<b>, <span>) → matched.
6. Navigation links (Home, Publications) → skipped — not alarmed.
7. Duplicate alerts across sections → deduped on alert_number.
8. Empty but plausible page → ``parser_mismatch_suspected`` warning fires.
9. Empty AND tiny page (e.g. outage) → NO mismatch warning.
10. Garbled HTML (nested tags unclosed) → parser tolerates.
"""
from __future__ import annotations

from app.scrapers.fda_import_alerts import (
    FDA_IMPORT_ALERTS_URL,
    FDAImportAlertsScraper,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


# The page is padded beyond _MIN_PLAUSIBLE_BODY_BYTES (1000) so the
# plausibility guard wouldn't suppress a warning when we want one to fire.
_PLAUSIBLE_PADDING = "<!-- " + ("x" * 1200) + " -->"

REALISTIC_LISTING_HTML = f"""\
<html>
<head><title>FDA Import Alert List</title></head>
<body>
<h1>Import Alerts</h1>
<p>This is the official FDA Import Alert listing.</p>
<table>
  <tr>
    <td><a href="import_alert_import_16-120.html">16-120 - Detention Without Physical Examination of Raw Shrimp from India</a></td>
  </tr>
  <tr>
    <td><a href="import_alert_import_66-40.html">66-40 - Seafood HACCP Violations</a></td>
  </tr>
  <tr>
    <td><a href="import_alert_import_45-02.html">45-02 – Pet Food from China</a></td>
  </tr>
  <tr>
    <td><a href="https://www.accessdata.fda.gov/cms_ia/importalert_99-08.html">99-08: Nitrofurans in Aquaculture</a></td>
  </tr>
</table>
<ul>
  <li><a href="/">Home</a></li>
  <li><a href="/publications">Publications</a></li>
</ul>
{_PLAUSIBLE_PADDING}
</body>
</html>
"""

THREE_DIGIT_SUFFIX_HTML = f"""\
<html><body><p>Import Alert listing page</p>
<a href="alerts/16-120.html">16-120 - Example three-digit suffix</a>
<a href="alerts/99-999.html">99-999 - Maximal three-digit suffix</a>
{_PLAUSIBLE_PADDING}
</body></html>
"""

SUBCATEGORY_HTML = f"""\
<html><body><p>Import Alert list</p>
<a href="a.html">16-120-A - Alpha subcategory</a>
<a href="b.html">16-120-01 - Numeric subcategory</a>
{_PLAUSIBLE_PADDING}
</body></html>
"""

ALTERNATE_SEPARATORS_HTML = f"""\
<html><body><p>Import Alert list</p>
<a href="1.html">10-01 - Hyphen title</a>
<a href="2.html">10-02 – En-dash title</a>
<a href="3.html">10-03 — Em-dash title</a>
<a href="4.html">10-04: Colon title</a>
{_PLAUSIBLE_PADDING}
</body></html>
"""

NESTED_MARKUP_HTML = f"""\
<html><body><p>Import Alert list</p>
<a href="n1.html"><b>16-120</b> - Bold number, plain title</a>
<a href="n2.html">16-121 - <span class="x">Spanned title text</span></a>
<a href="n3.html"><strong>16-122</strong> - <em>Mixed nesting</em></a>
{_PLAUSIBLE_PADDING}
</body></html>
"""

DUPLICATE_ALERTS_HTML = f"""\
<html><body><p>Import Alert list</p>
<h2>By Country</h2>
<a href="country/16-120.html">16-120 - Shrimp from India</a>
<h2>By Product</h2>
<a href="product/16-120.html">16-120 - Shrimp from India (duplicate listing)</a>
{_PLAUSIBLE_PADDING}
</body></html>
"""

# Plausible page with zero alerts — should trigger parser_mismatch_suspected.
PLAUSIBLE_BUT_NO_ALERTS_HTML = f"""\
<html><head><title>Import Alerts</title></head>
<body>
<h1>FDA Import Alert Listing</h1>
<p>Welcome to the Import Alert page. Please select a region below.</p>
<a href="/news">News</a>
<a href="/contact">Contact Us</a>
<a href="/publications">Publications</a>
{_PLAUSIBLE_PADDING}
</body></html>
"""

# Tiny page (outage / CDN holding page / redirect) — should NOT alarm.
TINY_HTML = "<html><body>Temporarily unavailable</body></html>"

# Garbled but technically plausible.
GARBLED_HTML = f"""\
<html><body><p>Import Alert</p>
<a href="a.html"><b>16-120 <unclosed_tag</b>-<em>Broken but tolerable</em></a>
{_PLAUSIBLE_PADDING}
</body></html>
"""


# ---------------------------------------------------------------------------
# Test class — all use parse_html directly, no HTTP.
# ---------------------------------------------------------------------------


class TestFDAImportAlertsParser_Issue1140:
    """Direct exercises of parse_html with fixture HTML."""

    def setup_method(self) -> None:
        # Constructor opens an httpx.Client — close it immediately, we're
        # only testing the parser.
        self.scraper = FDAImportAlertsScraper()

    def teardown_method(self) -> None:
        self.scraper.close()

    # --- realistic listing ------------------------------------------------

    def test_realistic_listing_extracts_all_alerts(self):
        items, warnings = self.scraper.parse_html(REALISTIC_LISTING_HTML)
        assert warnings == [], f"expected no warnings, got {warnings}"

        alert_numbers = sorted(i.raw_data["alert_number"] for i in items)
        assert alert_numbers == ["16-120", "45-02", "66-40", "99-08"]

        # Navigation links are NOT emitted as alerts.
        assert not any("Home" in i.title for i in items)
        assert not any("Publications" in i.title for i in items)

    def test_relative_urls_resolved_against_base(self):
        items, _ = self.scraper.parse_html(REALISTIC_LISTING_HTML)
        by_number = {i.raw_data["alert_number"]: i.url for i in items}

        assert by_number["16-120"].startswith("https://www.accessdata.fda.gov/")
        assert by_number["16-120"].endswith("import_alert_import_16-120.html")

    def test_absolute_urls_preserved(self):
        items, _ = self.scraper.parse_html(REALISTIC_LISTING_HTML)
        by_number = {i.raw_data["alert_number"]: i.url for i in items}

        # The 99-08 row had a fully-qualified URL already.
        assert by_number["99-08"] == (
            "https://www.accessdata.fda.gov/cms_ia/importalert_99-08.html"
        )

    def test_severity_is_high(self):
        items, _ = self.scraper.parse_html(REALISTIC_LISTING_HTML)
        assert all(i.severity.value == "high" for i in items)

    def test_source_type_is_fda_import_alert(self):
        items, _ = self.scraper.parse_html(REALISTIC_LISTING_HTML)
        assert all(i.source_type.value == "fda_import_alert" for i in items)

    # --- shapes the old regex missed --------------------------------------

    def test_three_digit_suffix_extracted(self):
        # Regression: the legacy regex `\d{2}-\d{2}` only matched 2-2.
        items, warnings = self.scraper.parse_html(THREE_DIGIT_SUFFIX_HTML)
        assert warnings == []
        numbers = sorted(i.raw_data["alert_number"] for i in items)
        assert numbers == ["16-120", "99-999"]

    def test_subcategory_letter_extracted(self):
        items, warnings = self.scraper.parse_html(SUBCATEGORY_HTML)
        assert warnings == []
        numbers = sorted(i.raw_data["alert_number"] for i in items)
        assert numbers == ["16-120-01", "16-120-A"]

    def test_all_separators_accepted(self):
        items, warnings = self.scraper.parse_html(ALTERNATE_SEPARATORS_HTML)
        assert warnings == []
        numbers = sorted(i.raw_data["alert_number"] for i in items)
        assert numbers == ["10-01", "10-02", "10-03", "10-04"]

        # The title portion is extracted in each case (not swallowed into
        # the number).
        by_num = {i.raw_data["alert_number"]: i.raw_data["raw_title"] for i in items}
        assert by_num["10-01"] == "Hyphen title"
        assert by_num["10-02"] == "En-dash title"
        assert by_num["10-03"] == "Em-dash title"
        assert by_num["10-04"] == "Colon title"

    def test_nested_markup_handled(self):
        items, warnings = self.scraper.parse_html(NESTED_MARKUP_HTML)
        assert warnings == []
        numbers = sorted(i.raw_data["alert_number"] for i in items)
        assert numbers == ["16-120", "16-121", "16-122"]

    # --- dedupe ------------------------------------------------------------

    def test_duplicate_alerts_deduped(self):
        items, warnings = self.scraper.parse_html(DUPLICATE_ALERTS_HTML)
        assert warnings == []
        # Same alert listed twice — only emit once.
        assert len(items) == 1
        assert items[0].raw_data["alert_number"] == "16-120"

    # --- parser-mismatch detection ----------------------------------------

    def test_plausible_page_with_zero_alerts_emits_warning(self):
        # Page is >1KB and contains "Import Alert" — but parser matched
        # zero rows. The operator MUST hear about this.
        items, warnings = self.scraper.parse_html(PLAUSIBLE_BUT_NO_ALERTS_HTML)

        assert items == []
        assert len(warnings) == 1
        assert warnings[0].startswith("parser_mismatch_suspected")
        assert "body_bytes=" in warnings[0]
        assert "fingerprint=" in warnings[0]

    def test_tiny_page_does_not_alarm(self):
        # A 50-byte "temporarily unavailable" page shouldn't flag parser
        # drift — it's an outage, not structural change.
        items, warnings = self.scraper.parse_html(TINY_HTML)

        assert items == []
        assert warnings == []

    def test_plausible_page_WITH_alerts_does_not_warn(self):
        # Belt-and-braces: make sure the warning only fires on ZERO items.
        items, warnings = self.scraper.parse_html(REALISTIC_LISTING_HTML)
        assert items  # sanity
        assert warnings == []

    # --- tolerance --------------------------------------------------------

    def test_garbled_html_does_not_raise(self):
        # Unclosed tags, mixed nesting — BeautifulSoup recovers, we
        # extract what we can.
        items, warnings = self.scraper.parse_html(GARBLED_HTML)
        # Either we extract the alert or we don't, but we must not crash.
        # If we extract nothing, the plausibility guard should fire (page
        # is >1KB and has "Import Alert" keyword).
        if not items:
            assert any("parser_mismatch_suspected" in w for w in warnings)
        else:
            assert items[0].raw_data["alert_number"] == "16-120"

    # --- ScrapeResult integration -----------------------------------------

    def test_scrape_surfaces_warnings_on_scrape_result(self, monkeypatch):
        """End-to-end: the public scrape() must attach warnings to the
        ScrapeResult so the scheduler's status endpoint can surface them."""
        scraper = FDAImportAlertsScraper()
        try:
            # Mock the HTTP fetch to return our plausible-but-empty page.
            class _MockResponse:
                status_code = 200
                text = PLAUSIBLE_BUT_NO_ALERTS_HTML

                def raise_for_status(self) -> None:
                    return None

            def fake_get(url, timeout=None, **kwargs):
                assert url == FDA_IMPORT_ALERTS_URL
                return _MockResponse()

            monkeypatch.setattr(scraper.session, "get", fake_get)

            result = scraper.scrape()

            # Scrape itself succeeded — HTTP returned 200 — but the parser
            # is suspected of being out of date.
            assert result.success is True
            assert result.items_found == 0
            assert len(result.warnings) == 1
            assert result.warnings[0].startswith("parser_mismatch_suspected")
        finally:
            scraper.close()

    def test_scrape_no_warning_on_healthy_parse(self, monkeypatch):
        scraper = FDAImportAlertsScraper()
        try:
            class _MockResponse:
                status_code = 200
                text = REALISTIC_LISTING_HTML

                def raise_for_status(self) -> None:
                    return None

            monkeypatch.setattr(
                scraper.session, "get", lambda url, timeout=None, **kwargs: _MockResponse()
            )

            result = scraper.scrape()

            assert result.success is True
            assert result.items_found == 4
            assert result.warnings == []
        finally:
            scraper.close()
