"""Unit tests for ``app.scrapers.state_adaptors.google_discovery`` — issue #1342.

Covers ``GoogleDiscoveryScraper`` — the active scraper that discovers
regulatory PDFs via Google Custom Search API.

Branches pinned:

``list_sources``:
  - No API key or no CX → returns ``[]`` + "config_missing" warning,
    never touches httpx (don't spend quota on a broken config).
  - Happy path: two-page pagination (start=1 then start=11), up to
    20 results, each with URL/title/snippet.
  - Pagination stops when ``items`` missing from response (don't call
    page 2 if page 1 returned no items — saves a round trip).
  - Jurisdiction heuristic: ``.ny.gov``/``.ca.gov``/``.tx.gov`` domains
    tagged with ``US-NY``/``US-CA``/``US-TX``; anything else falls back
    to ``US``. This is what downstream consumers key off to route
    regulatory content to the right state workspace.
  - Items without a ``link`` are skipped (don't build zero-URL Sources).
  - Exception at any stage → ``[]``, error logged — caller must not
    crash just because Google returned malformed JSON or SSRF tripped.

``fetch``:
  - Happy path: returns FetchedItem with content + headers' Content-Type.
  - Missing Content-Type header → defaults to ``application/pdf``
    (this scraper specifically targets PDFs).
  - HTTP error or SSRF → empty FetchedItem, error logged.

Stubs ``httpx``, ``shared.url_validation.validate_url``, and the
``...config.get_settings`` path so the tests are offline + deterministic.

Known-bug note: the module uses stdlib ``logging.Logger`` but calls
every logger with structlog-style kwargs, which raises ``TypeError``
at runtime. We swap ``mod.logger`` for a structlog-compatible spy so
the control flow can be exercised. The underlying logger bug is
tracked separately ("Convert fda_enforcement.py to structlog" — same
pattern applies here).
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))


from app.scrapers.state_adaptors import google_discovery as mod  # noqa: E402
from app.scrapers.state_adaptors.base import FetchedItem, Source  # noqa: E402
from app.scrapers.state_adaptors.google_discovery import (  # noqa: E402
    GoogleDiscoveryScraper,
)


# ---------------------------------------------------------------------------
# Helpers — structlog-compatible logger spy (see module docstring)
# ---------------------------------------------------------------------------


class _StructlogSpy:
    def __init__(self):
        self.calls: list[tuple[str, str, dict]] = []

    def _record(self, level, event, **kw):
        self.calls.append((level, event, kw))

    def debug(self, event, **kw):
        self._record("debug", event, **kw)

    def info(self, event, **kw):
        self._record("info", event, **kw)

    def warning(self, event, **kw):
        self._record("warning", event, **kw)

    def error(self, event, **kw):
        self._record("error", event, **kw)


class _FakeResponse:
    def __init__(
        self,
        *,
        json_body: dict | None = None,
        content: bytes = b"",
        headers: dict | None = None,
        raise_for_status_error: Exception | None = None,
    ):
        self._json = json_body or {}
        self.content = content
        self.headers = headers or {}
        self._error = raise_for_status_error

    def raise_for_status(self):
        if self._error:
            raise self._error

    def json(self):
        return self._json


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_settings(
    *,
    google_api_key: str | None = "test-key",
    google_cx: str | None = "test-cx",
    discovery_query: str = "FSMA 204 traceability",
):
    return SimpleNamespace(
        google_api_key=google_api_key,
        google_cx=google_cx,
        discovery_query=discovery_query,
    )


@pytest.fixture(autouse=True)
def _patch_logger(monkeypatch):
    spy = _StructlogSpy()
    monkeypatch.setattr(mod, "logger", spy)
    return spy


@pytest.fixture(autouse=True)
def _passthrough_validate_url(monkeypatch):
    monkeypatch.setattr(mod, "validate_url", lambda url: url)


@pytest.fixture
def patch_settings(monkeypatch):
    """Return a fresh callable that installs a SimpleNamespace of settings."""

    def _install(**overrides):
        s = _make_settings(**overrides)
        monkeypatch.setattr(mod, "get_settings", lambda: s)
        return s

    return _install


@pytest.fixture
def capture_httpx_get(monkeypatch):
    calls: list[dict] = []
    responses: list[_FakeResponse] = []

    def _get(url, *, params=None, timeout=None, headers=None):
        calls.append(
            {"url": url, "params": params, "timeout": timeout, "headers": headers}
        )
        if responses:
            return responses.pop(0)
        return _FakeResponse(json_body={})

    monkeypatch.setattr(mod.httpx, "get", _get)
    return calls, responses


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_reads_settings_on_init(self, patch_settings):
        patch_settings(google_api_key="k", google_cx="c")
        scraper = GoogleDiscoveryScraper()
        assert scraper.api_key == "k"
        assert scraper.cx == "c"
        assert scraper.base_url == "https://www.googleapis.com/customsearch/v1"


# ---------------------------------------------------------------------------
# list_sources — config missing
# ---------------------------------------------------------------------------


class TestListSourcesConfigMissing:
    def test_no_api_key_returns_empty_and_warns(
        self, patch_settings, capture_httpx_get, _patch_logger
    ):
        patch_settings(google_api_key=None, google_cx="c")
        scraper = GoogleDiscoveryScraper()
        calls, _ = capture_httpx_get

        result = scraper.list_sources()

        assert result == []
        # Must not touch httpx when config is missing (don't burn
        # quota/credentials on a dead-end call).
        assert calls == []
        assert any(
            level == "warning" and event == "google_discovery_config_missing"
            for level, event, _kw in _patch_logger.calls
        )

    def test_no_cx_returns_empty_and_warns(
        self, patch_settings, capture_httpx_get, _patch_logger
    ):
        patch_settings(google_api_key="k", google_cx=None)
        scraper = GoogleDiscoveryScraper()
        calls, _ = capture_httpx_get

        assert scraper.list_sources() == []
        assert calls == []

    def test_empty_string_api_key_treated_as_missing(
        self, patch_settings, capture_httpx_get
    ):
        patch_settings(google_api_key="", google_cx="c")
        scraper = GoogleDiscoveryScraper()
        calls, _ = capture_httpx_get
        assert scraper.list_sources() == []
        assert calls == []


# ---------------------------------------------------------------------------
# list_sources — happy path + pagination
# ---------------------------------------------------------------------------


def _item(url: str, *, title: str = "Doc", snippet: str = "s") -> dict:
    return {"link": url, "title": title, "snippet": snippet}


class TestListSourcesHappyPath:
    def test_paginates_two_pages(self, patch_settings, capture_httpx_get):
        patch_settings()
        calls, responses = capture_httpx_get
        responses.append(
            _FakeResponse(
                json_body={"items": [_item(f"https://a.gov/{i}.pdf") for i in range(10)]}
            )
        )
        responses.append(
            _FakeResponse(
                json_body={"items": [_item(f"https://b.gov/{i}.pdf") for i in range(10)]}
            )
        )

        sources = list(GoogleDiscoveryScraper().list_sources())

        # Two API calls (start=1 then start=11).
        assert len(calls) == 2
        assert calls[0]["params"]["start"] == 1
        assert calls[1]["params"]["start"] == 11
        # 20 total sources (10 per page).
        assert len(sources) == 20

    def test_page_two_skipped_when_items_missing(
        self, patch_settings, capture_httpx_get
    ):
        patch_settings()
        calls, responses = capture_httpx_get
        # Page 1 returns NO "items" key — we must bail rather than
        # waste another call.
        responses.append(_FakeResponse(json_body={"searchInformation": "empty"}))

        sources = list(GoogleDiscoveryScraper().list_sources())

        assert sources == []
        assert len(calls) == 1  # no page 2

    def test_forwards_api_key_cx_query_and_pdf_filetype(
        self, patch_settings, capture_httpx_get
    ):
        patch_settings(
            google_api_key="abc",
            google_cx="cx-1",
            discovery_query="recall",
        )
        calls, responses = capture_httpx_get
        responses.append(_FakeResponse(json_body={"items": [_item("https://x.gov/1.pdf")]}))

        list(GoogleDiscoveryScraper().list_sources())

        p = calls[0]["params"]
        assert p["key"] == "abc"
        assert p["cx"] == "cx-1"
        assert p["q"] == "recall"
        # Must filter to PDFs — this scraper only handles PDF regulatory docs.
        assert p["fileType"] == "pdf"

    def test_items_without_link_skipped(self, patch_settings, capture_httpx_get):
        patch_settings()
        calls, responses = capture_httpx_get
        responses.append(
            _FakeResponse(
                json_body={
                    "items": [
                        {"title": "no link"},  # link missing
                        _item("https://ok.gov/1.pdf"),
                    ]
                }
            )
        )
        # Second page empty.
        responses.append(_FakeResponse(json_body={}))

        sources = list(GoogleDiscoveryScraper().list_sources())
        assert [s.url for s in sources] == ["https://ok.gov/1.pdf"]


# ---------------------------------------------------------------------------
# list_sources — jurisdiction heuristic
# ---------------------------------------------------------------------------


class TestJurisdictionHeuristic:
    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://health.ny.gov/doc.pdf", "US-NY"),
            ("https://cdph.ca.gov/doc.pdf", "US-CA"),
            ("https://dshs.tx.gov/doc.pdf", "US-TX"),
            ("https://www.fda.gov/doc.pdf", "US"),
            ("https://example.gov/doc.pdf", "US"),
        ],
    )
    def test_maps_domain_to_jurisdiction(
        self, patch_settings, capture_httpx_get, url, expected
    ):
        patch_settings()
        _, responses = capture_httpx_get
        responses.append(_FakeResponse(json_body={"items": [_item(url)]}))
        responses.append(_FakeResponse(json_body={}))

        sources = list(GoogleDiscoveryScraper().list_sources())
        assert sources[0].jurisdiction_code == expected

    def test_attaches_snippet_and_iso_discovery_date(
        self, patch_settings, capture_httpx_get
    ):
        patch_settings()
        _, responses = capture_httpx_get
        responses.append(
            _FakeResponse(
                json_body={
                    "items": [_item("https://a.gov/1.pdf", title="t", snippet="sn")]
                }
            )
        )
        responses.append(_FakeResponse(json_body={}))

        sources = list(GoogleDiscoveryScraper().list_sources())
        md = sources[0].metadata
        assert md["discovery_snippet"] == "sn"
        # ISO-8601 with timezone offset.
        assert "T" in md["discovery_date"]
        assert md["discovery_date"].endswith("+00:00") or md["discovery_date"].endswith("Z")


# ---------------------------------------------------------------------------
# list_sources — error paths
# ---------------------------------------------------------------------------


class TestListSourcesErrors:
    def test_http_error_returns_empty_and_logs_error(
        self, patch_settings, capture_httpx_get, _patch_logger
    ):
        patch_settings()
        _, responses = capture_httpx_get
        responses.append(
            _FakeResponse(raise_for_status_error=RuntimeError("503 upstream"))
        )

        assert list(GoogleDiscoveryScraper().list_sources()) == []
        assert any(
            event == "google_discovery_failed"
            for _level, event, _kw in _patch_logger.calls
        )

    def test_malformed_json_returns_empty(
        self, patch_settings, capture_httpx_get
    ):
        patch_settings()
        _, responses = capture_httpx_get

        class _BadResponse(_FakeResponse):
            def json(self):
                raise ValueError("bad json")

        responses.append(_BadResponse(json_body={}))

        assert list(GoogleDiscoveryScraper().list_sources()) == []


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------


class TestFetch:
    def test_happy_path_returns_fetched_item(
        self, patch_settings, capture_httpx_get
    ):
        patch_settings()
        _, responses = capture_httpx_get
        responses.append(
            _FakeResponse(
                content=b"%PDF-1.4 body",
                headers={"Content-Type": "application/pdf"},
            )
        )

        source = Source(url="https://a.gov/1.pdf")
        item = GoogleDiscoveryScraper().fetch(source)

        assert isinstance(item, FetchedItem)
        assert item.source is source
        assert item.content_bytes == b"%PDF-1.4 body"
        assert item.content_type == "application/pdf"

    def test_missing_content_type_defaults_to_pdf(
        self, patch_settings, capture_httpx_get
    ):
        patch_settings()
        _, responses = capture_httpx_get
        responses.append(_FakeResponse(content=b"%PDF", headers={}))

        source = Source(url="https://a.gov/1.pdf")
        item = GoogleDiscoveryScraper().fetch(source)
        assert item.content_type == "application/pdf"

    def test_uses_regengine_user_agent(self, patch_settings, capture_httpx_get):
        patch_settings()
        calls, responses = capture_httpx_get
        responses.append(_FakeResponse(content=b"x"))

        GoogleDiscoveryScraper().fetch(Source(url="https://a.gov/1.pdf"))
        assert calls[0]["headers"] == {"User-Agent": "RegEngine/1.0"}
        assert calls[0]["timeout"] == 30

    def test_http_error_returns_empty_fetched_item(
        self, patch_settings, capture_httpx_get, _patch_logger
    ):
        patch_settings()
        _, responses = capture_httpx_get
        responses.append(
            _FakeResponse(raise_for_status_error=RuntimeError("404"))
        )

        source = Source(url="https://a.gov/missing.pdf")
        item = GoogleDiscoveryScraper().fetch(source)

        assert item.source is source
        assert item.content_bytes == b""
        assert item.content_type is None
        assert any(
            event == "google_fetch_failed"
            for _level, event, _kw in _patch_logger.calls
        )

    def test_ssrf_raises_caught_and_returns_empty(
        self, patch_settings, capture_httpx_get, monkeypatch
    ):
        patch_settings()
        calls, _ = capture_httpx_get
        monkeypatch.setattr(
            mod, "validate_url",
            lambda url: (_ for _ in ()).throw(RuntimeError("ssrf")),
        )

        item = GoogleDiscoveryScraper().fetch(Source(url="http://10.0.0.1"))
        assert item.content_bytes == b""
        assert calls == []  # never attempted the fetch
