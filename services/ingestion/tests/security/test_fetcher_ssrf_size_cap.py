"""SSRF refusal and size-cap tests for research fetchers.

Covers the Medium 2/3/17 remediation surface in ingestion:

1. ``app.discovery.EthicalScraper`` routes scraping and robots.txt through
   ``shared.safe_http.safe_httpx_get_sync`` (SSRF validation per hop plus a
   response size cap) instead of a raw ``httpx.Client``.
2. ``GenericRSSScraper.list_sources`` downloads the feed through the safe
   helper and hands bytes to feedparser, so feedparser never fetches a URL
   itself.

Every test fails on the pre-fix code (raw client, ``feedparser.parse(url)``,
no ``safe_httpx_get_sync`` symbol in ``app.discovery``).
"""

from __future__ import annotations

import pytest

RSS_BYTES = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Register</title>
    <link>https://example.com/register</link>
    <item>
      <title>Rule update 1</title>
      <link>https://example.com/register/1</link>
      <published>Mon, 01 Jan 2024 00:00:00 GMT</published>
      <description>First update</description>
    </item>
    <item>
      <title>Rule update 2</title>
      <link>https://example.com/register/2</link>
      <published>Tue, 02 Jan 2024 00:00:00 GMT</published>
      <description>Second update</description>
    </item>
  </channel>
</rss>
"""


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}
        self.lists: dict[str, list] = {}

    def get(self, key: str):
        value = self.store.get(key)
        return value

    def set(self, key: str, value) -> None:
        self.store[key] = value.encode() if isinstance(value, str) else value

    def rpush(self, key: str, value) -> None:
        self.lists.setdefault(key, []).append(value)


def _make_scraper(monkeypatch):
    from app import discovery as discovery_module

    monkeypatch.setattr(discovery_module.Redis, "from_url", lambda *args, **kwargs: _FakeRedis())
    scraper = discovery_module.EthicalScraper()
    assert isinstance(scraper.redis, _FakeRedis)
    return discovery_module, scraper


async def test_scrape_refuses_private_url_without_fetch(monkeypatch):
    _, scraper = _make_scraper(monkeypatch)

    # No stubbing: the real SSRF validation must refuse 127.0.0.1 before
    # any connection is opened, and the scrape must fail (never queue an
    # internal URL for manual upload). The old code attempted the
    # connection and failed with "[Errno 61] Connection refused", which
    # lacks this prefix.
    result = await scraper.scrape("FDA", "http://127.0.0.1/secret")
    assert result["status"] == "failed"
    assert result["error"].startswith("URL refused:")


async def test_scrape_refuses_oversized_response(monkeypatch):
    from shared.safe_http import ResponseTooLargeError

    discovery_module, scraper = _make_scraper(monkeypatch)
    monkeypatch.setattr(scraper, "can_fetch", lambda url: True)

    def too_big(*args, **kwargs):
        raise ResponseTooLargeError("Response body exceeds 5242880 bytes")

    monkeypatch.setattr(discovery_module, "safe_httpx_get_sync", too_big)

    result = await scraper.scrape("FDA", "https://example.com/rules")
    assert result["status"] == "failed"
    assert "exceeds" in result["error"].lower()


def test_can_fetch_refuses_private_host(monkeypatch):
    from shared.url_validation import SSRFError

    _, scraper = _make_scraper(monkeypatch)
    with pytest.raises(SSRFError):
        scraper.can_fetch("http://127.0.0.1/anything")


def test_generic_rss_downloads_feed_through_safe_helper(monkeypatch):
    import feedparser
    from app.scrapers.state_adaptors import generic

    real_parse = feedparser.parse

    def guarded(data, *args, **kwargs):
        assert isinstance(data, (bytes, bytearray)), "feedparser must receive bytes, not a URL"
        return real_parse(data, *args, **kwargs)

    monkeypatch.setattr(generic.feedparser, "parse", guarded)

    class FakeResponse:
        content = RSS_BYTES
        headers = {"Content-Type": "application/rss+xml"}

        def raise_for_status(self) -> None:
            pass

    def fake_get(url, **kwargs):
        assert url == "https://example.com/feed"
        assert kwargs.get("max_bytes", 0) > 0, "feed download must carry a size cap"
        return FakeResponse()

    monkeypatch.setattr(generic, "safe_httpx_get_sync", fake_get)
    # Item links are SSRF-validated with a live DNS lookup; pass them through
    # so the test stays offline (rejection is covered in test_scrapers_deep_qa).
    monkeypatch.setattr(generic, "validate_url", lambda url: url)

    scraper = generic.GenericRSSScraper(
        feed_url="https://example.com/feed",
        jurisdiction="US-XX",
        title_prefix="X",
    )
    sources = list(scraper.list_sources())
    assert [s.title for s in sources] == ["X: Rule update 1", "X: Rule update 2"]
    assert [s.url for s in sources] == [
        "https://example.com/register/1",
        "https://example.com/register/2",
    ]


def test_generic_rss_private_feed_url_yields_nothing(monkeypatch):
    from app.scrapers.state_adaptors import generic
    from shared.url_validation import SSRFError

    def fake_get(url, **kwargs):
        raise SSRFError("Resolved IP 127.0.0.1 is not a public global address")

    recorder = {"calls": 0}

    def counting_get(url, **kwargs):
        recorder["calls"] += 1
        return fake_get(url, **kwargs)

    monkeypatch.setattr(generic, "safe_httpx_get_sync", counting_get)

    scraper = generic.GenericRSSScraper(
        feed_url="http://127.0.0.1/feed",
        jurisdiction="US-XX",
        title_prefix="X",
    )
    assert list(scraper.list_sources()) == []
    assert recorder["calls"] == 1


def test_generic_rss_oversized_feed_yields_nothing(monkeypatch):
    from app.scrapers.state_adaptors import generic
    from shared.safe_http import ResponseTooLargeError

    def fake_get(url, **kwargs):
        raise ResponseTooLargeError("Response body exceeds 5242880 bytes")

    monkeypatch.setattr(generic, "safe_httpx_get_sync", fake_get)

    scraper = generic.GenericRSSScraper(
        feed_url="https://example.com/feed",
        jurisdiction="US-XX",
        title_prefix="X",
    )
    assert list(scraper.list_sources()) == []


RELATIVE_LINK_RSS_BYTES = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Agency Register</title>
    <link>https://agency.example/regs/feed.xml</link>
    <item>
      <title>Notice one</title>
      <link>notice.html</link>
    </item>
    <item>
      <title>Notice two</title>
      <link>/regs/item/2</link>
    </item>
  </channel>
</rss>
"""


def test_generic_rss_relative_item_links_resolve_against_final_url(monkeypatch):
    """Relative feed item links must come back absolute.

    feedparser only resolves them when it is told the feed URL. The safe
    helper pins the transport IP, so the logical final-hop URL rides in
    ``response.extensions["safe_final_url"]``. Without that base, the
    relative links stay relative and the follow-up fetch rejects them,
    dropping the items. Fails on the pre-fix code, which parses bytes
    with no base URL.
    """
    from app.scrapers.state_adaptors import generic

    class FakeResponse:
        content = RELATIVE_LINK_RSS_BYTES
        headers = {"Content-Type": "application/rss+xml"}
        extensions = {"safe_final_url": "https://agency.example/regs/feed.xml"}

        def raise_for_status(self) -> None:
            pass

    monkeypatch.setattr(generic, "safe_httpx_get_sync", lambda url, **kwargs: FakeResponse())
    # agency.example never resolves: pass item links through the live-DNS
    # SSRF check so the test exercises link resolution offline.
    monkeypatch.setattr(generic, "validate_url", lambda url: url)

    scraper = generic.GenericRSSScraper(
        feed_url="https://agency.example/regs/feed.xml",
        jurisdiction="US-XX",
        title_prefix="X",
    )
    sources = list(scraper.list_sources())
    assert [s.url for s in sources] == [
        "https://agency.example/regs/notice.html",
        "https://agency.example/regs/item/2",
    ]


def test_generic_rss_relative_item_links_fall_back_to_feed_url(monkeypatch):
    """Stubbed responses without the final-URL tag still resolve links."""
    from app.scrapers.state_adaptors import generic

    class FakeResponse:
        content = RELATIVE_LINK_RSS_BYTES
        headers = {"Content-Type": "application/rss+xml"}

        def raise_for_status(self) -> None:
            pass

    monkeypatch.setattr(generic, "safe_httpx_get_sync", lambda url, **kwargs: FakeResponse())
    # agency.example never resolves: pass item links through the live-DNS
    # SSRF check so the test exercises link resolution offline.
    monkeypatch.setattr(generic, "validate_url", lambda url: url)

    scraper = generic.GenericRSSScraper(
        feed_url="https://agency.example/regs/feed.xml",
        jurisdiction="US-XX",
        title_prefix="X",
    )
    sources = list(scraper.list_sources())
    assert [s.url for s in sources] == [
        "https://agency.example/regs/notice.html",
        "https://agency.example/regs/item/2",
    ]
