"""Unit tests for ``app.scrapers.state_adaptors.fda_enforcement`` — issue #1342.

Covers ``FDAEnforcementScraper`` — the scraper that discovers FDA
Warning Letters via the FDA's official RSS feed and fetches each one
(with PDF deep-fetch if the landing page links to a PDF version).

Branches pinned:

``list_sources`` (RSS discovery):
  - Happy path: RSS parsed, Source objects yielded with URL, title,
    jurisdiction_code "US-FDA", metadata dict containing
    type="warning_letter", published_date, discovery_date ISO string.
  - Missing ``<title>``/``<pubDate>``: defaults to "Unknown Warning Letter"
    and ``published_date=None`` — prevents NoneType crashes downstream.
  - ``<link>`` present but empty/missing: item skipped, count not
    incremented (guards against "link existed in XML but was blank").
  - SSRF validation: when ``validate_url`` raises ``SSRFError`` on an
    item's URL, the item is skipped and logged at debug level — other
    items in the feed still yield (don't let one bad URL nuke discovery).
  - HTTP error or XML parse error: generator returns nothing but does
    NOT raise — the scheduler must keep running.

``fetch`` (per-letter fetch + PDF deep-fetch):
  - HTML-only letter (no PDF link): returns FetchedItem with the raw
    HTML content + original content-type.
  - PDF link present: follows link, validates URL, fetches PDF,
    returns FetchedItem with PDF bytes + ``application/pdf``.
  - PDF link present but SSRF-rejected: falls back to HTML (never
    lose the letter just because the PDF link was internal).
  - PDF link present but PDF HTTP error: falls back to HTML (same
    rationale).
  - SSRF on the landing page URL: returns empty FetchedItem (the
    record is preserved but no content) — prefer to skip rather
    than crash the worker.
  - Top-level HTTP error: returns empty FetchedItem, logs error.

Stubs ``httpx`` + ``shared.url_validation`` so the tests are offline
and deterministic.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))


from app.scrapers.state_adaptors import fda_enforcement as mod  # noqa: E402
from app.scrapers.state_adaptors.base import FetchedItem, Source  # noqa: E402
from app.scrapers.state_adaptors.fda_enforcement import FDAEnforcementScraper  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers — fake httpx.Response
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(
        self,
        *,
        content: bytes = b"",
        text: str = "",
        headers: dict | None = None,
        raise_for_status_error: Exception | None = None,
    ):
        self.content = content
        self.text = text or content.decode("utf-8", errors="replace")
        self.headers = headers or {}
        self._error = raise_for_status_error

    def raise_for_status(self):
        if self._error:
            raise self._error


RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>FDA Warning Letters</title>
    <item>
      <link>https://www.fda.gov/letter/1</link>
      <title>Acme Co. — Warning Letter</title>
      <pubDate>Mon, 01 Jan 2026 12:00:00 GMT</pubDate>
    </item>
    <item>
      <link>https://www.fda.gov/letter/2</link>
    </item>
  </channel>
</rss>
""".encode("utf-8")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _StructlogSpy:
    """Stand-in for a structlog logger.

    The module under test calls ``logger.error("event", key=value, ...)`` —
    structlog-style kwargs. In production ``logger`` is a stdlib
    ``logging.Logger``, which raises ``TypeError`` on extra kwargs (see
    the spawned task "Convert fda_enforcement.py to structlog"). To test
    the *intended* control flow (where logging never raises and the
    scheduler keeps running), we swap the logger for this spy that
    tolerates any kwargs — the same contract structlog provides.
    """

    def __init__(self):
        self.calls: list[tuple[str, str, dict]] = []

    def _record(self, level: str, event: str, **kw):
        self.calls.append((level, event, kw))

    def debug(self, event, **kw):
        self._record("debug", event, **kw)

    def info(self, event, **kw):
        self._record("info", event, **kw)

    def warning(self, event, **kw):
        self._record("warning", event, **kw)

    def error(self, event, **kw):
        self._record("error", event, **kw)


@pytest.fixture(autouse=True)
def _patch_logger(monkeypatch):
    """Replace the stdlib logger with a structlog-compatible spy."""
    spy = _StructlogSpy()
    monkeypatch.setattr(mod, "logger", spy)
    return spy


@pytest.fixture
def scraper():
    return FDAEnforcementScraper()


@pytest.fixture
def capture_httpx_get(monkeypatch):
    """Capture httpx.get calls; default to empty 200 response."""
    calls: list[dict] = []
    responses: list[_FakeResponse] = []

    def _get(url, *, timeout=None, headers=None):
        calls.append({"url": url, "timeout": timeout, "headers": headers})
        if responses:
            return responses.pop(0)
        return _FakeResponse(content=b"", headers={"Content-Type": "text/html"})

    monkeypatch.setattr(mod.httpx, "get", _get)
    return calls, responses


@pytest.fixture
def passthrough_validate_url(monkeypatch):
    """validate_url returns the URL unchanged — no SSRF rejection."""
    monkeypatch.setattr(mod, "validate_url", lambda url: url)


# ---------------------------------------------------------------------------
# list_sources — happy + edge paths
# ---------------------------------------------------------------------------


class TestListSources:
    def test_parses_rss_and_yields_sources(
        self, scraper, capture_httpx_get, passthrough_validate_url
    ):
        calls, responses = capture_httpx_get
        responses.append(_FakeResponse(content=RSS_XML))

        sources = list(scraper.list_sources())

        assert len(sources) == 2
        assert sources[0].url == "https://www.fda.gov/letter/1"
        assert sources[0].title == "Acme Co. \u2014 Warning Letter"
        assert sources[0].jurisdiction_code == "US-FDA"
        assert sources[0].metadata["type"] == "warning_letter"
        assert sources[0].metadata["published_date"] == "Mon, 01 Jan 2026 12:00:00 GMT"
        # discovery_date is an ISO string — just confirm format looks right.
        assert "T" in sources[0].metadata["discovery_date"]

    def test_missing_title_and_pubdate_use_defaults(
        self, scraper, capture_httpx_get, passthrough_validate_url
    ):
        calls, responses = capture_httpx_get
        responses.append(_FakeResponse(content=RSS_XML))

        sources = list(scraper.list_sources())

        # Second item had no <title>/<pubDate>.
        assert sources[1].title == "Unknown Warning Letter"
        assert sources[1].metadata["published_date"] is None

    def test_uses_configured_rss_url_and_user_agent(
        self, scraper, capture_httpx_get, passthrough_validate_url
    ):
        calls, responses = capture_httpx_get
        responses.append(_FakeResponse(content=RSS_XML))

        list(scraper.list_sources())

        assert len(calls) == 1
        assert calls[0]["url"] == FDAEnforcementScraper.RSS_URL
        assert calls[0]["timeout"] == 30
        assert calls[0]["headers"] == {"User-Agent": "RegEngine/1.0"}

    def test_empty_link_text_skipped(
        self, scraper, capture_httpx_get, passthrough_validate_url
    ):
        calls, responses = capture_httpx_get
        xml = b"""<?xml version="1.0"?>
<rss><channel>
  <item><link></link><title>Empty link</title></item>
  <item><link>https://www.fda.gov/letter/ok</link><title>OK</title></item>
</channel></rss>
"""
        responses.append(_FakeResponse(content=xml))

        sources = list(scraper.list_sources())
        assert len(sources) == 1
        assert sources[0].url == "https://www.fda.gov/letter/ok"

    def test_ssrf_rejected_urls_skip_item_without_crashing(
        self, scraper, capture_httpx_get, monkeypatch
    ):
        calls, responses = capture_httpx_get
        responses.append(_FakeResponse(content=RSS_XML))

        # First call (feed fetch) should pass through; per-item
        # validation rejects letter/1 but accepts letter/2.
        def _selective_validate(url: str) -> str:
            if url.endswith("/letter/1"):
                raise mod.SSRFError("blocked")
            return url

        monkeypatch.setattr(mod, "validate_url", _selective_validate)

        sources = list(scraper.list_sources())

        # letter/1 rejected, letter/2 survives.
        urls = [s.url for s in sources]
        assert urls == ["https://www.fda.gov/letter/2"]

    def test_rss_http_error_returns_nothing_no_raise(
        self, scraper, capture_httpx_get, passthrough_validate_url
    ):
        calls, responses = capture_httpx_get
        responses.append(
            _FakeResponse(raise_for_status_error=RuntimeError("bad gateway"))
        )

        # Must NOT raise — scheduler must keep running.
        sources = list(scraper.list_sources())
        assert sources == []

    def test_malformed_xml_returns_nothing_no_raise(
        self, scraper, capture_httpx_get, passthrough_validate_url
    ):
        calls, responses = capture_httpx_get
        responses.append(_FakeResponse(content=b"<not-valid-xml>"))

        sources = list(scraper.list_sources())
        assert sources == []


# ---------------------------------------------------------------------------
# fetch — HTML-only, PDF deep-fetch, SSRF fallbacks
# ---------------------------------------------------------------------------


HTML_NO_PDF = b"<html><body><p>Warning letter body...</p></body></html>"
HTML_WITH_PDF = (
    b'<html><body><a href="warning.pdf">Download PDF</a></body></html>'
)
HTML_WITH_PDF_ABS = (
    b'<html><body><a href="https://www.fda.gov/cdn/warning.pdf">Download PDF</a></body></html>'
)


@pytest.fixture
def source():
    return Source(
        url="https://www.fda.gov/letter/1",
        title="Test Letter",
        jurisdiction_code="US-FDA",
        metadata={},
    )


class TestFetch:
    def test_html_only_returns_fetched_item(
        self, scraper, source, capture_httpx_get, passthrough_validate_url
    ):
        calls, responses = capture_httpx_get
        responses.append(
            _FakeResponse(
                content=HTML_NO_PDF,
                headers={"Content-Type": "text/html; charset=utf-8"},
            )
        )

        item = scraper.fetch(source)
        assert isinstance(item, FetchedItem)
        assert item.source is source
        assert item.content_bytes == HTML_NO_PDF
        assert item.content_type == "text/html; charset=utf-8"

    def test_pdf_link_triggers_deep_fetch(
        self, scraper, source, capture_httpx_get, passthrough_validate_url
    ):
        calls, responses = capture_httpx_get
        # First call: landing page HTML with relative PDF link.
        responses.append(
            _FakeResponse(
                content=HTML_WITH_PDF,
                headers={"Content-Type": "text/html"},
            )
        )
        # Second call: the PDF.
        responses.append(
            _FakeResponse(
                content=b"%PDF-1.4 fake pdf bytes",
                headers={"Content-Type": "application/pdf"},
            )
        )

        item = scraper.fetch(source)
        assert item.content_bytes == b"%PDF-1.4 fake pdf bytes"
        assert item.content_type == "application/pdf"

        # The PDF URL must be resolved against the letter URL — urljoin
        # of a relative "warning.pdf" against the letter URL yields
        # ".../warning.pdf" as a sibling.
        pdf_call = calls[1]
        assert pdf_call["url"].endswith("/warning.pdf")
        assert pdf_call["timeout"] == 45  # PDF fetch gets a longer timeout

    def test_pdf_link_absolute_url_used_verbatim(
        self, scraper, source, capture_httpx_get, passthrough_validate_url
    ):
        calls, responses = capture_httpx_get
        responses.append(
            _FakeResponse(content=HTML_WITH_PDF_ABS, headers={"Content-Type": "text/html"})
        )
        responses.append(
            _FakeResponse(content=b"%PDF", headers={"Content-Type": "application/pdf"})
        )

        scraper.fetch(source)
        assert calls[1]["url"] == "https://www.fda.gov/cdn/warning.pdf"

    def test_pdf_link_ssrf_rejected_falls_back_to_html(
        self, scraper, source, capture_httpx_get, monkeypatch
    ):
        calls, responses = capture_httpx_get
        responses.append(
            _FakeResponse(content=HTML_WITH_PDF, headers={"Content-Type": "text/html"})
        )

        # Accept the landing URL, reject the PDF URL.
        def _selective(url: str) -> str:
            if url.endswith(".pdf"):
                raise mod.SSRFError("internal")
            return url

        monkeypatch.setattr(mod, "validate_url", _selective)

        item = scraper.fetch(source)
        # Fell back to the landing HTML, not a second httpx call.
        assert item.content_bytes == HTML_WITH_PDF
        assert item.content_type == "text/html"
        assert len(calls) == 1  # no PDF fetch attempted

    def test_pdf_fetch_http_error_falls_back_to_html(
        self, scraper, source, capture_httpx_get, passthrough_validate_url
    ):
        calls, responses = capture_httpx_get
        responses.append(
            _FakeResponse(content=HTML_WITH_PDF, headers={"Content-Type": "text/html"})
        )
        responses.append(
            _FakeResponse(raise_for_status_error=RuntimeError("pdf 500"))
        )

        item = scraper.fetch(source)
        # Fallback: we keep the HTML content and type, don't propagate
        # the PDF failure.
        assert item.content_bytes == HTML_WITH_PDF
        assert item.content_type == "text/html"

    def test_landing_page_ssrf_returns_empty_fetched_item(
        self, scraper, source, capture_httpx_get, monkeypatch
    ):
        calls, responses = capture_httpx_get

        monkeypatch.setattr(
            mod, "validate_url",
            lambda url: (_ for _ in ()).throw(mod.SSRFError("blocked")),
        )

        item = scraper.fetch(source)
        assert item.source is source
        assert item.content_bytes == b""
        assert item.content_type is None
        # No network call should have been made.
        assert calls == []

    def test_top_level_http_error_returns_empty_fetched_item(
        self, scraper, source, capture_httpx_get, passthrough_validate_url
    ):
        calls, responses = capture_httpx_get
        responses.append(
            _FakeResponse(raise_for_status_error=RuntimeError("503 upstream"))
        )

        item = scraper.fetch(source)
        assert item.source is source
        assert item.content_bytes == b""
        assert item.content_type is None

    def test_pdf_regex_case_insensitive(
        self, scraper, source, capture_httpx_get, passthrough_validate_url
    ):
        calls, responses = capture_httpx_get
        # Uppercase ".PDF" must still match.
        html = b'<html><a href="warning.PDF">pdf</a></html>'
        responses.append(
            _FakeResponse(content=html, headers={"Content-Type": "text/html"})
        )
        responses.append(
            _FakeResponse(content=b"%PDF", headers={"Content-Type": "application/pdf"})
        )

        item = scraper.fetch(source)
        assert item.content_type == "application/pdf"
