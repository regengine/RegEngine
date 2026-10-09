"""Deep QA tests for ``app.scrapers``: SSRF parity, per-item robustness,
failure-type honesty, tenant passthrough, and input sanitization.

Each test below fails on the pre-fix code and passes after the fix.
See the module docstrings of the individual test classes for the bug.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, *, content=b"", headers=None, status_code=200, error=None):
        self.content = content
        self.text = content.decode("utf-8", errors="replace")
        self.headers = headers or {}
        self.status_code = status_code
        self._error = error

    def raise_for_status(self):
        if self._error is not None:
            raise self._error
        if 400 <= self.status_code < 600:
            import httpx

            raise httpx.HTTPStatusError(
                f"status {self.status_code}",
                request=SimpleNamespace(),
                response=self,
            )

    def json(self):  # pragma: no cover - overridden where needed
        raise ValueError("no json")


RSS_BYTES = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item><link>https://example.gov/doc/1</link><title>Doc One</title></item>
  <item><link>https://example.gov/doc/2</link><title>Doc Two</title></item>
</channel></rss>
"""


# ---------------------------------------------------------------------------
# 1. GenericRSSScraper must fetch its feed through the SSRF-safe client
# ---------------------------------------------------------------------------


class TestGenericRSSFeedFetch:
    """Bug: ``list_sources`` called ``feedparser.parse(feed_url)`` directly,
    letting feedparser perform the HTTP fetch with no URL validation, no
    IP pinning, no timeout and no User-Agent (SSRF bypass, RE-SEC-INGEST-003).
    The feed must be fetched via ``safe_httpx_get_sync`` first and only the
    bytes handed to feedparser.
    """

    def test_feed_fetched_via_safe_http_not_feedparser_http(self, monkeypatch):
        from app.scrapers.state_adaptors import generic as mod

        calls = []

        def _safe_get(url, *, timeout=None, headers=None):
            calls.append({"url": url, "timeout": timeout, "headers": headers})
            return _FakeResponse(
                content=RSS_BYTES,
                headers={"Content-Type": "application/rss+xml"},
            )

        monkeypatch.setattr(mod, "safe_httpx_get_sync", _safe_get)

        seen = []
        real_parse = mod.feedparser.parse

        def _parse(payload):
            seen.append(payload)
            if isinstance(payload, str):
                raise AssertionError("feedparser must not receive a URL (raw HTTP fetch)")
            return real_parse(payload)

        monkeypatch.setattr(mod.feedparser, "parse", _parse)
        monkeypatch.setattr(mod, "validate_url", lambda u: u)

        scraper = mod.GenericRSSScraper(
            feed_url="https://example.gov/feed.xml",
            jurisdiction="US-XX",
            title_prefix="X",
        )
        sources = list(scraper.list_sources())

        assert len(calls) == 1
        assert calls[0]["url"] == "https://example.gov/feed.xml"
        assert calls[0]["timeout"] == 30
        assert len(sources) == 2
        assert seen and isinstance(seen[0], (bytes, bytearray))

    def test_entry_missing_link_does_not_kill_discovery(self, monkeypatch):
        """Bug: ``entry.link`` attribute access raised AttributeError on
        entries without a link, aborting the whole discovery loop (and the
        route's ``for`` loop, producing a 500 with zero results)."""
        from app.scrapers.state_adaptors import generic as mod

        monkeypatch.setattr(
            mod,
            "safe_httpx_get_sync",
            lambda url, **kw: _FakeResponse(content=RSS_BYTES),
        )

        class _Entry(dict):
            pass

        fake_feed = SimpleNamespace(
            entries=[
                _Entry(title="No link here"),
                _Entry(link="https://example.gov/ok", title="OK"),
            ]
        )
        monkeypatch.setattr(mod.feedparser, "parse", lambda payload: fake_feed)
        monkeypatch.setattr(mod, "validate_url", lambda u: u)

        scraper = mod.GenericRSSScraper(
            feed_url="https://example.gov/feed.xml",
            jurisdiction="US-XX",
            title_prefix="X",
        )
        sources = list(scraper.list_sources())
        assert [s.url for s in sources] == ["https://example.gov/ok"]

    def test_ssrf_rejected_entry_skipped_others_survive(self, monkeypatch):
        """Discovered item URLs must be validated; one bad URL must not
        poison the rest of the feed."""
        from app.scrapers.state_adaptors import generic as mod
        from shared.url_validation import SSRFError

        monkeypatch.setattr(
            mod,
            "safe_httpx_get_sync",
            lambda url, **kw: _FakeResponse(content=RSS_BYTES),
        )
        real_parse = mod.feedparser.parse
        monkeypatch.setattr(mod.feedparser, "parse", lambda payload: real_parse(payload))

        def _validate(url):
            if "doc/1" in url:
                raise SSRFError("blocked")
            return url

        monkeypatch.setattr(mod, "validate_url", _validate)

        scraper = mod.GenericRSSScraper(
            feed_url="https://example.gov/feed.xml",
            jurisdiction="US-XX",
            title_prefix="X",
        )
        sources = list(scraper.list_sources())
        assert [s.url for s in sources] == ["https://example.gov/doc/2"]

    def test_feed_http_error_yields_nothing_no_raise(self, monkeypatch):
        from app.scrapers.state_adaptors import generic as mod

        def _boom(url, **kw):
            raise RuntimeError("503 upstream")

        monkeypatch.setattr(mod, "safe_httpx_get_sync", _boom)

        scraper = mod.GenericRSSScraper(
            feed_url="https://example.gov/feed.xml",
            jurisdiction="US-XX",
            title_prefix="X",
        )
        assert list(scraper.list_sources()) == []


# ---------------------------------------------------------------------------
# 2. Generic fetch failures must not wear a success content type
# ---------------------------------------------------------------------------


class TestGenericFailureContentType:
    """Bug: ``GenericRSSScraper.fetch`` / ``GenericListScraper.fetch``
    returned ``content_type="error"`` on failure, while CPPA/FL-RSS
    returned empty bytes labeled as ``"text/html"`` /
    ``"application/rss+xml"``. Empty payloads must carry ``None`` so no
    caller can mistake them for real content.
    """

    def test_rss_fetch_failure_content_type_is_none(self, monkeypatch):
        from app.scrapers.state_adaptors import generic as mod
        from app.scrapers.state_adaptors.base import Source

        def _boom(url, **kw):
            raise RuntimeError("down")

        monkeypatch.setattr(mod, "safe_httpx_get_sync", _boom)
        item = mod.GenericRSSScraper(
            feed_url="https://example.gov/f", jurisdiction="US-XX", title_prefix="X"
        ).fetch(Source(url="https://example.gov/d"))
        assert item.content_bytes == b""
        assert item.content_type is None

    def test_list_fetch_failure_content_type_is_none(self, monkeypatch):
        from app.scrapers.state_adaptors import generic as mod
        from app.scrapers.state_adaptors.base import Source

        def _boom(url, **kw):
            raise RuntimeError("down")

        monkeypatch.setattr(mod, "safe_httpx_get_sync", _boom)
        item = mod.GenericListScraper(
            list_url="https://example.gov/l", jurisdiction="US-XX", title_prefix="X"
        ).fetch(Source(url="https://example.gov/d"))
        assert item.content_bytes == b""
        assert item.content_type is None

    def test_list_discovery_skips_unvalidatable_urls(self, monkeypatch):
        """Discovered hrefs (relative links, javascript:, file:, internal
        hosts) must be validated before being yielded as Sources."""
        from app.scrapers.state_adaptors import generic as mod
        from shared.url_validation import SSRFError

        html = (
            b"<html><body>"
            b"<a href='https://example.gov/good.pdf'>Good</a>"
            b"<a href='javascript:alert(1)'>Bad</a>"
            b"</body></html>"
        )
        monkeypatch.setattr(
            mod,
            "safe_httpx_get_sync",
            lambda url, **kw: _FakeResponse(content=html, headers={"Content-Type": "text/html"}),
        )

        def _validate(url):
            if url.startswith("javascript:"):
                raise SSRFError("bad scheme")
            return url

        monkeypatch.setattr(mod, "validate_url", _validate)

        scraper = mod.GenericListScraper(
            list_url="https://example.gov/l", jurisdiction="US-XX", title_prefix="X"
        )
        sources = list(scraper.list_sources())
        assert [s.url for s in sources] == ["https://example.gov/good.pdf"]

    def test_cppa_fetch_failure_content_type_is_none(self, monkeypatch):
        from app.scrapers.state_adaptors import cppa as mod
        from app.scrapers.state_adaptors.base import Source

        def _boom(url, **kw):
            raise httpx.ConnectError("down")

        monkeypatch.setattr(mod, "safe_httpx_get_sync", _boom)
        item = mod.CPPAScraper().fetch(Source(url="https://cppa.ca.gov/regulations/"))
        assert item.content_bytes == b""
        assert item.content_type is None

    def test_fl_rss_fetch_failure_content_type_is_none(self, monkeypatch):
        from app.scrapers.state_adaptors import fl_rss as mod
        from app.scrapers.state_adaptors.base import Source

        def _boom(url, **kw):
            raise httpx.ConnectError("down")

        monkeypatch.setattr(mod, "safe_httpx_get_sync", _boom)
        item = mod.FloridaRSSScraper().fetch(Source(url="https://www.flsenate.gov/x"))
        assert item.content_bytes == b""
        assert item.content_type is None


# ---------------------------------------------------------------------------
# 3. FDA: one malformed item must not nuke the whole feed
# ---------------------------------------------------------------------------


class TestFDAMalformedItems:
    """Bug: ``title.text.strip()`` / ``pub_date.text.strip()`` raised
    AttributeError when the element exists but is empty (``<title/>``),
    and the outer ``except`` then discarded every other item in the feed.
    """

    def _scraper_with_rss(self, monkeypatch, rss: bytes):
        from app.scrapers.state_adaptors import fda_enforcement as mod

        monkeypatch.setattr(
            mod,
            "safe_httpx_get_sync",
            lambda url, **kw: _FakeResponse(content=rss),
        )
        monkeypatch.setattr(mod, "validate_url", lambda u: u)
        return mod.FDAEnforcementScraper()

    def test_empty_title_element_uses_default(self, monkeypatch):
        rss = (
            b"<?xml version='1.0'?><rss><channel>"
            b"<item><link>https://www.fda.gov/letter/1</link><title/></item>"
            b"<item><link>https://www.fda.gov/letter/2</link><title>Fine</title></item>"
            b"</channel></rss>"
        )
        scraper = self._scraper_with_rss(monkeypatch, rss)
        sources = list(scraper.list_sources())
        assert len(sources) == 2
        assert sources[0].title == "Unknown Warning Letter"
        assert sources[1].title == "Fine"

    def test_empty_pubdate_element_yields_none_not_crash(self, monkeypatch):
        rss = (
            b"<?xml version='1.0'?><rss><channel>"
            b"<item><link>https://www.fda.gov/letter/1</link><title>T</title><pubDate/></item>"
            b"</channel></rss>"
        )
        scraper = self._scraper_with_rss(monkeypatch, rss)
        sources = list(scraper.list_sources())
        assert len(sources) == 1
        assert sources[0].metadata["published_date"] is None

    def test_single_quoted_pdf_href_deep_fetched(self, monkeypatch):
        """Bug: the PDF regex only matched double-quoted hrefs, so
        ``<a href='x.pdf'>`` pages never deep-fetched the PDF."""
        from app.scrapers.state_adaptors import fda_enforcement as mod
        from app.scrapers.state_adaptors.base import Source

        html = b"<html><body><a href='warning.pdf'>Download PDF</a></body></html>"
        calls = []

        def _get(url, *, timeout=None, headers=None):
            calls.append(url)
            if url.endswith(".pdf"):
                return _FakeResponse(content=b"%PDF-1.4", headers={"Content-Type": "application/pdf"})
            return _FakeResponse(content=html, headers={"Content-Type": "text/html"})

        monkeypatch.setattr(mod, "safe_httpx_get_sync", _get)
        monkeypatch.setattr(mod, "validate_url", lambda u: u)

        item = mod.FDAEnforcementScraper().fetch(
            Source(url="https://www.fda.gov/letter/1", jurisdiction_code="US-FDA")
        )
        assert item.content_bytes == b"%PDF-1.4"
        assert item.content_type == "application/pdf"


# ---------------------------------------------------------------------------
# 4. NYDFS must route through the SSRF-safe client
# ---------------------------------------------------------------------------


class TestNYDFSSafeHttp:
    """Bug: NYDFS used raw ``requests.get`` (default redirect-following,
    fresh DNS resolution per hop) instead of ``safe_httpx_get_sync``,
    reopening the DNS-rebinding TOCTOU window and dodging the repo's
    no-direct-HTTP guardrail (which only scans for ``httpx.get``)."""

    def test_fetch_does_not_touch_requests(self, monkeypatch):
        from app.scrapers.state_adaptors import nydfs as mod
        from app.scrapers.state_adaptors.base import Source

        class _NoRequests:
            def get(self, *a, **kw):
                raise AssertionError("must not use requests.get")

        # raising=False: on fixed code the module has no ``requests``
        # attribute at all; on buggy code this swaps in the tripwire.
        monkeypatch.setattr(mod, "requests", _NoRequests(), raising=False)
        monkeypatch.setattr(
            mod,
            "safe_httpx_get_sync",
            lambda url, **kw: _FakeResponse(
                content=b"<html><body><p>Hello</p></body></html>",
                headers={"Content-Type": "text/html; charset=utf-8"},
            ),
        )
        monkeypatch.setattr(mod, "validate_url", lambda u: u)

        item = mod.NYDFSScraper().fetch(
            Source(url="https://www.dfs.ny.gov/x", jurisdiction_code="US-NY")
        )
        assert b"Hello" in item.content_bytes
        assert item.content_type == "text/html"

    def test_retry_after_honored_then_success(self, monkeypatch):
        from app.scrapers.state_adaptors import nydfs as mod
        from app.scrapers.state_adaptors.base import Source

        sleeps = []
        monkeypatch.setattr(mod.time, "sleep", lambda s: sleeps.append(s))
        responses = [
            _FakeResponse(content=b"busy", status_code=429, headers={"Retry-After": "0"}),
            _FakeResponse(
                content=b"<html><body><p>OK</p></body></html>",
                headers={"Content-Type": "text/html"},
            ),
        ]
        monkeypatch.setattr(mod, "safe_httpx_get_sync", lambda url, **kw: responses.pop(0))
        monkeypatch.setattr(mod, "validate_url", lambda u: u)

        item = mod.NYDFSScraper().fetch(
            Source(url="https://www.dfs.ny.gov/x", jurisdiction_code="US-NY")
        )
        assert b"OK" in item.content_bytes
        assert sleeps == [0.0]

    def test_persistent_failure_raises_ioerror_family(self, monkeypatch):
        """Callers (``run_state_scrape_job``) catch OSError/IOError; the
        final failure must stay in that family after the requests removal."""
        from app.scrapers.state_adaptors import nydfs as mod
        from app.scrapers.state_adaptors.base import Source

        monkeypatch.setattr(mod.time, "sleep", lambda s: None)
        bad = _FakeResponse(content=b"nope", status_code=500)
        monkeypatch.setattr(mod, "safe_httpx_get_sync", lambda url, **kw: bad)
        monkeypatch.setattr(mod, "validate_url", lambda u: u)

        with pytest.raises(OSError):
            mod.NYDFSScraper().fetch(
                Source(url="https://www.dfs.ny.gov/x", jurisdiction_code="US-NY")
            )

    def test_unclosed_ignored_tag_does_not_swallow_rest_of_page(self):
        """Bug: ``_VisibleTextParser`` pushed nav/script/style on a stack
        but only popped on an exact top-of-stack match, so mismatched
        nesting (``</nav>`` closing while ``<style>`` is still open left
        both on the stack) discarded all remaining page text."""
        from app.scrapers.state_adaptors.nydfs import _extract_visible_text

        html = b"<nav><footer>menu</nav><p>Real regulation text</p>"
        assert "Real regulation text" in _extract_visible_text(html)


# ---------------------------------------------------------------------------
# 5. Google discovery: keep page-1 results, validate item URLs
# ---------------------------------------------------------------------------


class TestGoogleDiscoveryRobustness:
    def _settings(self, monkeypatch):
        from app.scrapers.state_adaptors import google_discovery as mod

        settings = SimpleNamespace(
            google_api_key="k",
            google_cx="cx",
            discovery_query="q",
        )
        monkeypatch.setattr(mod, "get_settings", lambda: settings)
        return mod

    def test_page_two_failure_keeps_page_one_results(self, monkeypatch):
        """Bug: any exception (including a page-2 blip) discarded the
        healthy page-1 results and returned []."""
        mod = self._settings(monkeypatch)

        def _item(i):
            return {"link": f"https://a.gov/{i}.pdf", "title": "t", "snippet": "s"}

        calls = {"n": 0}

        def _get(url, *, timeout=None, headers=None):
            calls["n"] += 1
            if calls["n"] == 1:
                resp = _FakeResponse()
                resp.json = lambda: {"items": [_item(1)]}
                return resp
            raise RuntimeError("page 2 blip")

        monkeypatch.setattr(mod, "safe_httpx_get_sync", _get)
        monkeypatch.setattr(mod, "validate_url", lambda u: u)

        sources = list(mod.GoogleDiscoveryScraper().list_sources())
        assert [s.url for s in sources] == ["https://a.gov/1.pdf"]

    def test_ssrf_rejected_item_url_skipped(self, monkeypatch):
        """Bug: discovered Google result URLs were never validated (unlike
        the FDA adaptor), so metadata-store links could point at internal
        hosts. Fetch would refuse them later, but the Source list itself
        must not carry them."""
        mod = self._settings(monkeypatch)
        from shared.url_validation import SSRFError

        page1 = _FakeResponse()
        page1.json = lambda: {
            "items": [
                {"link": "http://169.254.169.254/secret", "title": "bad", "snippet": "s"},
                {"link": "https://a.gov/ok.pdf", "title": "good", "snippet": "s"},
            ]
        }
        page2 = _FakeResponse()
        page2.json = lambda: {}
        calls = {"n": 0}

        def _get(url, **kw):
            calls["n"] += 1
            return page1 if calls["n"] == 1 else page2

        monkeypatch.setattr(mod, "safe_httpx_get_sync", _get)

        def _validate(url):
            if "169.254" in url:
                raise SSRFError("blocked")
            return url

        monkeypatch.setattr(mod, "validate_url", _validate)

        sources = list(mod.GoogleDiscoveryScraper().list_sources())
        assert [s.url for s in sources] == ["https://a.gov/ok.pdf"]


# ---------------------------------------------------------------------------
# 6. state_generic: S3 key safety + tenant passthrough isolation
# ---------------------------------------------------------------------------


class TestStateGenericKeyAndTenant:
    """Bug: ``jurisdiction_code`` was interpolated verbatim into the S3 key
    (``raw/<jur>/...``), so a caller-controlled value like ``../x`` produced
    keys with ``..`` segments that fail ``validate_s3_key`` downstream and
    confuse bucket lifecycle prefixes. Reject non-conforming codes early.
    """

    def _run(self, monkeypatch, **kw):
        from app.scrapers import state_generic as mod

        s3_uploads, kafka_emits = [], []

        class _S3:
            def upload_bytes(self, bucket, key, data, content_type):
                s3_uploads.append({"bucket": bucket, "key": key})
                return f"s3://{bucket}/{key}"

        class _Kafka:
            def emit(self, topic, payload):
                kafka_emits.append(payload)
                return True

        monkeypatch.setattr(mod, "validate_url", lambda u, **_: u)
        monkeypatch.setattr(
            mod,
            "safe_httpx_get_sync",
            lambda url, **kw2: _FakeResponse(content=b"x", headers={"Content-Type": "text/plain"}),
        )
        scraper = mod.StateRegistryScraper(s3_bucket="b", s3_client=_S3(), kafka=_Kafka())
        out = asyncio.run(scraper.fetch_document(**kw))
        return out, s3_uploads, kafka_emits

    def test_path_traversal_jurisdiction_rejected(self, monkeypatch):
        from app.scrapers import state_generic as mod  # noqa: F401

        with pytest.raises(ValueError, match="[Jj]urisdiction"):
            self._run(monkeypatch, url="https://x.gov/", jurisdiction_code="../../evil")

    def test_slash_jurisdiction_rejected(self, monkeypatch):
        with pytest.raises(ValueError, match="[Jj]urisdiction"):
            self._run(monkeypatch, url="https://x.gov/", jurisdiction_code="US/NY")

    def test_normal_codes_still_accepted(self, monkeypatch):
        for code in ("US-NY", "US-FDA", "US", "unknown"):
            out, uploads, _ = self._run(
                monkeypatch, url="https://x.gov/", jurisdiction_code=code
            )
            assert uploads[0]["key"].startswith(f"raw/{code}/")
            assert out["jurisdiction_code"] == code

    def test_tenant_events_never_cross_contaminate(self, monkeypatch):
        """Tenant and auth boundary: the scraper stamps the caller's
        tenant_id verbatim into each event and shares no state between
        calls, so tenant A's fetch can never leak into tenant B's event."""
        from app.scrapers import state_generic as mod

        s3_uploads, kafka_emits = [], []

        class _S3:
            def upload_bytes(self, bucket, key, data, content_type):
                s3_uploads.append(key)
                return f"s3://{bucket}/{key}"

        class _Kafka:
            def emit(self, topic, payload):
                kafka_emits.append(dict(payload))
                return True

        monkeypatch.setattr(mod, "validate_url", lambda u, **_: u)
        monkeypatch.setattr(
            mod,
            "safe_httpx_get_sync",
            lambda url, **kw: _FakeResponse(content=b"x", headers={"Content-Type": "text/plain"}),
        )
        scraper = mod.StateRegistryScraper(s3_bucket="b", s3_client=_S3(), kafka=_Kafka())
        out_a = asyncio.run(
            scraper.fetch_document(url="https://x.gov/", jurisdiction_code="US", tenant_id="tenant-a")
        )
        out_b = asyncio.run(
            scraper.fetch_document(url="https://x.gov/", jurisdiction_code="US", tenant_id="tenant-b")
        )
        assert out_a["tenant_id"] == "tenant-a"
        assert out_b["tenant_id"] == "tenant-b"
        assert out_a["doc_id"] != out_b["doc_id"]
        assert kafka_emits[0]["tenant_id"] == "tenant-a"
        assert kafka_emits[1]["tenant_id"] == "tenant-b"
        assert s3_uploads[0] != s3_uploads[1]
