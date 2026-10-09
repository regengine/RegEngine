"""SSRF regression tests for GenericRSSScraper.list_sources.

Audit finding: the generic RSS adapter let feedparser download the feed
itself (``feedparser.parse(feed_url)``), bypassing the SSRF defenses in
``shared.safe_http``. The fix downloads the feed bytes through
``safe_httpx_get_sync`` first and only then hands bytes to feedparser.

These tests pin that contract at the module symbol where the scraper
imported the helper, so a revert to ``feedparser.parse(url)`` fails.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

FEED_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Texas Register</title>
<item><title>Rule 1</title><link>https://example.texas.gov/rules/1</link>
<pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
<description>Summary one.</description></item>
<item><title>Rule 2</title><link>https://example.texas.gov/rules/2</link>
<pubDate>Tue, 02 Jan 2024 00:00:00 GMT</pubDate>
<description>Summary two.</description></item>
</channel></rss>"""


def _make_response(content: bytes = FEED_XML, content_type: str = "application/rss+xml"):
    resp = MagicMock()
    resp.content = content
    resp.text = content.decode("utf-8", errors="ignore")
    resp.headers = {"Content-Type": content_type}
    resp.raise_for_status = MagicMock()
    return resp


def test_generic_rss_list_sources_downloads_through_safe_http():
    """list_sources must fetch feed bytes via safe_httpx_get_sync."""
    from app.scrapers.state_adaptors.generic import GenericRSSScraper

    scraper = GenericRSSScraper(
        feed_url="https://example.texas.gov/feed",
        jurisdiction="US-TX",
        title_prefix="Texas",
    )

    with patch("app.scrapers.state_adaptors.generic.safe_httpx_get_sync") as m:
        m.return_value = _make_response()
        sources = list(scraper.list_sources())

    m.assert_called_once()
    assert m.call_args.args[0] == "https://example.texas.gov/feed"
    assert [s.url for s in sources] == [
        "https://example.texas.gov/rules/1",
        "https://example.texas.gov/rules/2",
    ]
    assert sources[0].title == "Texas: Rule 1"


def test_generic_rss_list_sources_hands_bytes_not_url_to_feedparser():
    """feedparser must receive downloaded bytes, never the feed URL."""
    from app.scrapers.state_adaptors import generic as generic_mod
    from app.scrapers.state_adaptors.generic import GenericRSSScraper

    scraper = GenericRSSScraper(
        feed_url="https://example.texas.gov/feed",
        jurisdiction="US-TX",
        title_prefix="Texas",
    )

    with (
        patch.object(generic_mod, "safe_httpx_get_sync") as m_safe,
        patch.object(generic_mod.feedparser, "parse") as m_parse,
    ):
        m_safe.return_value = _make_response()
        fake_feed = MagicMock()
        fake_feed.entries = []
        m_parse.return_value = fake_feed
        list(scraper.list_sources())

    m_safe.assert_called_once()
    m_parse.assert_called_once()
    (parse_arg,) = m_parse.call_args.args
    assert isinstance(parse_arg, (bytes, bytearray)), (
        f"feedparser.parse must receive feed bytes, got {type(parse_arg).__name__}"
    )
    assert bytes(parse_arg) == FEED_XML
