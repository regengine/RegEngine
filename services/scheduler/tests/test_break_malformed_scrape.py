"""Break tests: malformed scraper payloads must not escape or poison items."""

from __future__ import annotations

import json

import httpx
from app.scrapers.fda_import_alerts import FDAImportAlertsScraper
from app.scrapers.fda_warning_letters import FDAWarningLettersScraper

_PAD = "Import Alert " * 40


_API_PAYLOAD = {
    "results": [
        {
            "recall_number": "F-0001-2026",
            "report_date": "20260115",
            "classification": "Class I",
            "recalling_firm": "Acme Greens",
            "product_description": "Spinach",
            "reason_for_recall": "Listeria",
            "status": "Ongoing",
        }
    ]
}


def _fetch_rss_then_api(rss_body: bytes):
    def fake_fetch(_session, url, **_kwargs):
        if str(url).endswith("rss.xml"):
            body = rss_body
        else:
            body = json.dumps(_API_PAYLOAD).encode()
        return httpx.Response(200, content=body, request=httpx.Request("GET", str(url)))

    return fake_fetch


def _assert_api_fallback(result) -> None:
    assert result.success is True
    assert result.error_message is None
    assert [item.raw_data.get("recall_number") for item in result.items] == ["F-0001-2026"]


def test_truncated_rss_falls_back_to_api(monkeypatch):
    """A truncated feed body raises ParseError, which is a SyntaxError.

    scrape() only catches ValueError (and HTTP errors). The parse error
    used to escape, so the openFDA fallback never ran and the circuit
    counted a crash.
    """
    scraper = FDAWarningLettersScraper()
    monkeypatch.setattr(
        "app.scrapers.fda_warning_letters.fetch_with_retry",
        _fetch_rss_then_api(b"<?xml version='1.0'?><rss><channel><item><title>x</title>"),
    )

    _assert_api_fallback(scraper.scrape())


def test_rss_with_entities_falls_back_to_api(monkeypatch):
    """A feed that defusedxml rejects must be treated as an empty feed.

    EntitiesForbidden is a ValueError, so scrape() used to record a
    failed scrape and skip the API fallback.
    """
    scraper = FDAWarningLettersScraper()
    hostile = b"<?xml version='1.0'?><!DOCTYPE foo [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]><rss>&xxe;</rss>"
    monkeypatch.setattr(
        "app.scrapers.fda_warning_letters.fetch_with_retry",
        _fetch_rss_then_api(hostile),
    )

    _assert_api_fallback(scraper.scrape())


def test_import_alert_parser_drops_non_http_urls_and_keeps_real_rows():
    html = (
        "<table>"
        '<tr><td>16-120</td><td><a href="javascript:alert(1)">Bad</a></td></tr>'
        '<tr><td>16-120</td><td><a href="https://www.accessdata.fda.gov/cms_ia/importalert_120.html">Later real</a></td></tr>'
        '<tr><td>16-121</td><td><a href="file:///etc/passwd">Secret</a></td></tr>'
        '<tr><td>16-122</td><td><a href="data:text/html,hi">Data</a></td></tr>'
        '<tr><td>16-123</td><td><a href="ok.html">Real alert</a></td></tr>'
        '<tr><td>16-124</td><td><a href="https://www.accessdata.fda.gov/cms_ia/importalert_9.html">Absolute</a></td></tr>'
        "</table>" + _PAD
    )
    items, _warnings = FDAImportAlertsScraper().parse_html(html)
    urls = {item.raw_data["alert_number"]: item.url for item in items}

    assert urls["16-120"] == "https://www.accessdata.fda.gov/cms_ia/importalert_120.html"
    assert "16-121" not in urls
    assert "16-122" not in urls
    assert urls["16-123"].startswith("https://")
    assert urls["16-123"].endswith("ok.html")
    assert urls["16-124"] == "https://www.accessdata.fda.gov/cms_ia/importalert_9.html"
    for url in urls.values():
        assert url.startswith("https://") or url.startswith("http://")
