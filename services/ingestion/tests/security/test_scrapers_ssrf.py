"""SSRF regression tests for state-adaptor scrapers (RE-SEC-INGEST-003).

These tests prove that each migrated scraper routes its outbound HTTP through
``shared.safe_http.safe_httpx_get_sync`` (which re-validates every redirect
hop and pins the connection to a validated IP). The previous direct
``httpx.get(validated_url, ...)`` shape left a DNS-rebinding TOCTOU window
between :func:`validate_url` and the connect.

We mock the helper at the module symbol where each scraper imported it (so a
regression where someone reverts to ``httpx.get`` will fail this test).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _make_response(content: bytes = b"<html></html>", content_type: str = "text/html"):
    resp = MagicMock()
    resp.content = content
    resp.text = content.decode("utf-8", errors="ignore")
    resp.headers = {"Content-Type": content_type}
    resp.raise_for_status = MagicMock()
    return resp


def test_cppa_scraper_uses_safe_http():
    from app.scrapers.state_adaptors.base import Source
    from app.scrapers.state_adaptors.cppa import CPPAScraper

    scraper = CPPAScraper()
    src = Source(url="https://cppa.ca.gov/regulations/", title="t", jurisdiction_code="US-CA")

    with patch("app.scrapers.state_adaptors.cppa.safe_httpx_get_sync") as m:
        m.return_value = _make_response(b"<html>cppa</html>")
        item = scraper.fetch(src)

    m.assert_called_once()
    assert m.call_args.args[0] == src.url
    assert item.content_bytes == b"<html>cppa</html>"


def test_fl_rss_scraper_uses_safe_http():
    from app.scrapers.state_adaptors.base import Source
    from app.scrapers.state_adaptors.fl_rss import FloridaRSSScraper

    scraper = FloridaRSSScraper()
    src = Source(url="https://www.flsenate.gov/PublishedContent/Session/", title="t", jurisdiction_code="US-FL")

    with patch("app.scrapers.state_adaptors.fl_rss.safe_httpx_get_sync") as m:
        m.return_value = _make_response(b"<rss/>", content_type="application/rss+xml")
        item = scraper.fetch(src)

    m.assert_called_once()
    assert item.content_bytes == b"<rss/>"


def test_generic_rss_scraper_fetch_uses_safe_http():
    from app.scrapers.state_adaptors.base import Source
    from app.scrapers.state_adaptors.generic import GenericRSSScraper

    scraper = GenericRSSScraper(feed_url="https://example.com/feed", jurisdiction="US-XX", title_prefix="X")
    src = Source(url="https://example.com/doc", title="t", jurisdiction_code="US-XX")

    with patch("app.scrapers.state_adaptors.generic.safe_httpx_get_sync") as m:
        m.return_value = _make_response(b"hi")
        item = scraper.fetch(src)

    m.assert_called_once()
    assert m.call_args.args[0] == src.url
    assert item.content_bytes == b"hi"


def test_generic_list_scraper_uses_safe_http():
    from app.scrapers.state_adaptors.generic import GenericListScraper

    scraper = GenericListScraper(
        list_url="https://example.com/list",
        jurisdiction="US-XX",
        title_prefix="X",
    )

    with patch("app.scrapers.state_adaptors.generic.safe_httpx_get_sync") as m:
        m.return_value = _make_response(b"<html><a href='/d'>d</a></html>")
        # Drain the generator
        list(scraper.list_sources())

    m.assert_called_once()
    assert m.call_args.args[0] == "https://example.com/list"


def test_google_discovery_list_uses_safe_http(monkeypatch):
    from app.scrapers.state_adaptors import google_discovery as gd

    # Stub settings so list_sources runs through.
    settings = MagicMock()
    settings.google_api_key = "k"
    settings.google_cx = "cx"
    settings.discovery_query = "q"
    monkeypatch.setattr(gd, "get_settings", lambda: settings)

    scraper = gd.GoogleDiscoveryScraper()

    resp = _make_response(b"{}")
    resp.json = MagicMock(return_value={"items": []})

    with patch("app.scrapers.state_adaptors.google_discovery.safe_httpx_get_sync") as m:
        m.return_value = resp
        list(scraper.list_sources() or [])

    assert m.call_count >= 1
    # Confirms params were encoded into URL (not passed as separate kwarg).
    first_call_url = m.call_args_list[0].args[0]
    assert first_call_url.startswith("https://www.googleapis.com/customsearch/v1?")
    assert "key=k" in first_call_url and "cx=cx" in first_call_url


def test_google_discovery_fetch_uses_safe_http():
    from app.scrapers.state_adaptors import google_discovery as gd
    from app.scrapers.state_adaptors.base import Source

    settings = MagicMock()
    settings.google_api_key = "k"
    settings.google_cx = "cx"
    with patch.object(gd, "get_settings", lambda: settings):
        scraper = gd.GoogleDiscoveryScraper()

    src = Source(url="https://example.gov/doc.pdf", title="t", jurisdiction_code="US")
    with patch("app.scrapers.state_adaptors.google_discovery.safe_httpx_get_sync") as m:
        m.return_value = _make_response(b"%PDF-", content_type="application/pdf")
        item = scraper.fetch(src)

    m.assert_called_once()
    assert m.call_args.args[0] == src.url
    assert item.content_bytes == b"%PDF-"


def test_fda_enforcement_fetch_uses_safe_http():
    from app.scrapers.state_adaptors.base import Source
    from app.scrapers.state_adaptors.fda_enforcement import FDAEnforcementScraper

    scraper = FDAEnforcementScraper()
    src = Source(url="https://www.fda.gov/warning-letter/abc", title="t", jurisdiction_code="US-FDA")

    # Landing-page response with no PDF link — single safe call expected.
    with patch("app.scrapers.state_adaptors.fda_enforcement.safe_httpx_get_sync") as m:
        m.return_value = _make_response(b"<html>no pdf here</html>")
        item = scraper.fetch(src)

    assert m.call_count == 1
    assert item.content_bytes == b"<html>no pdf here</html>"


def test_fda_enforcement_pdf_deep_fetch_uses_safe_http():
    from app.scrapers.state_adaptors.base import Source
    from app.scrapers.state_adaptors.fda_enforcement import FDAEnforcementScraper

    scraper = FDAEnforcementScraper()
    src = Source(url="https://www.fda.gov/warning-letter/abc", title="t", jurisdiction_code="US-FDA")

    landing = _make_response(b'<a href="https://www.fda.gov/x.pdf">pdf</a>')
    pdf = _make_response(b"%PDF-", content_type="application/pdf")

    with patch(
        "app.scrapers.state_adaptors.fda_enforcement.safe_httpx_get_sync",
        side_effect=[landing, pdf],
    ) as m:
        item = scraper.fetch(src)

    # Both the landing-page hop and the deep PDF hop must route through safe_http.
    assert m.call_count == 2
    assert item.content_type == "application/pdf"


def test_no_direct_httpx_get_in_state_adaptors():
    """Static guardrail: scraper modules must not call ``httpx.get`` directly.

    A regression where someone replaces ``safe_httpx_get_sync`` with the raw
    ``httpx.get`` would silently re-open RE-SEC-INGEST-003. This grep-style
    assertion catches that without needing to wire each new file into a
    bespoke mock test.
    """
    import pathlib

    adaptors_dir = pathlib.Path(__file__).resolve().parents[2] / "app" / "scrapers" / "state_adaptors"
    offenders: list[str] = []
    for py in adaptors_dir.glob("*.py"):
        text = py.read_text()
        # Strip comments before scanning.
        scrubbed = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
        if "httpx.get(" in scrubbed or "httpx.post(" in scrubbed:
            offenders.append(py.name)
    assert offenders == [], f"Direct httpx calls found in: {offenders}"
