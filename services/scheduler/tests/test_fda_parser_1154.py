"""Focused FDA scraper parser regressions for #1154."""

from __future__ import annotations

from datetime import datetime

import httpx

from app.models import EnforcementItem, EnforcementSeverity, SourceType
from app.scrapers.fda_recalls import FDARecallsScraper
from app.scrapers.fda_warning_letters import FDAWarningLettersScraper


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        json_payload: dict | None = None,
        content: bytes = b"",
    ) -> None:
        self.status_code = status_code
        self._json_payload = json_payload or {}
        self.content = content

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://example.test")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError(
                f"http {self.status_code}",
                request=request,
                response=response,
            )

    def json(self) -> dict:
        return self._json_payload


class TestFDARecallsParser_Issue1154:
    def test_scrape_returns_success_result(self, monkeypatch):
        scraper = FDARecallsScraper()
        expected_item = scraper._parse_recall(
            {
                "recall_number": "F-2222-2026",
                "classification": "Class I",
                "report_date": "20260420",
                "recalling_firm": "Alert Farms",
            }
        )
        monkeypatch.setattr(scraper, "_fetch_recalls", lambda: [expected_item])

        result = scraper.scrape()

        assert result.success is True
        assert result.items_found == 1
        assert result.items[0].source_id == expected_item.source_id

    def test_scrape_surfaces_fetch_errors(self, monkeypatch):
        scraper = FDARecallsScraper()
        monkeypatch.setattr(scraper, "_fetch_recalls", lambda: (_ for _ in ()).throw(ValueError("boom")))

        result = scraper.scrape()

        assert result.success is False
        assert result.error_message == "boom"

    def test_parse_recall_maps_critical_severity_and_fields(self):
        scraper = FDARecallsScraper()

        item = scraper._parse_recall(
            {
                "recall_number": "F-1234-2026",
                "classification": "Class I",
                "report_date": "20260420",
                "recalling_firm": "Fresh Farms",
                "product_description": "Romaine Lettuce Hearts",
                "reason_for_recall": "Potential listeria contamination",
                "code_info": "LOT-A",
            }
        )

        assert item is not None
        assert item.severity == EnforcementSeverity.CRITICAL
        assert item.affected_companies == ["Fresh Farms"]
        assert item.affected_products == ["Romaine Lettuce Hearts"]
        assert item.raw_data["code_info"] == "LOT-A"
        assert "F-1234-2026" in item.url

    def test_fetch_recalls_skips_malformed_rows_but_keeps_valid_ones(self, monkeypatch):
        scraper = FDARecallsScraper()

        def _fake_fetch(*_args, **_kwargs):
            return _FakeResponse(
                json_payload={
                    "results": [
                        {
                            "recall_number": "F-1111-2026",
                            "classification": "Class II",
                            "report_date": "20260419",
                            "recalling_firm": "Grower One",
                            "product_description": "Spinach",
                        },
                        {
                            "classification": "Class I",
                            "report_date": "20260420",
                            "recalling_firm": "Missing Recall Number Co",
                        },
                    ]
                }
            )

        monkeypatch.setattr("app.scrapers.fda_recalls.fetch_with_retry", _fake_fetch)

        items = scraper._fetch_recalls()

        assert len(items) == 1
        assert items[0].source_id.endswith("F-1111-2026")
        assert items[0].severity == EnforcementSeverity.HIGH

    def test_fetch_recalls_skips_rows_that_raise_during_parse(self, monkeypatch):
        scraper = FDARecallsScraper()
        original_parse = scraper._parse_recall

        monkeypatch.setattr(
            "app.scrapers.fda_recalls.fetch_with_retry",
            lambda *_args, **_kwargs: _FakeResponse(
                json_payload={"results": [{"recall_number": "X"}, {"recall_number": "Y"}]}
            ),
        )

        def _fake_parse(result):
            if result["recall_number"] == "X":
                raise ValueError("bad row")
            return original_parse(
                {
                    "recall_number": "Y",
                    "classification": "Class III",
                    "report_date": "",
                    "recalling_firm": "Fallback Foods",
                }
            )

        monkeypatch.setattr(scraper, "_parse_recall", _fake_parse)

        items = scraper._fetch_recalls()

        assert len(items) == 1
        assert items[0].severity == EnforcementSeverity.MEDIUM

    def test_parse_recall_uses_fallback_timestamp_and_medium_severity(self):
        scraper = FDARecallsScraper()

        item = scraper._parse_recall(
            {
                "recall_number": "F-3333-2026",
                "classification": "Class III",
                "report_date": "bad-date",
                "recalling_firm": "General Foods",
            }
        )

        assert item is not None
        assert item.severity == EnforcementSeverity.MEDIUM
        assert item.affected_products == []
        assert isinstance(item.published_date, datetime)

    def test_get_by_classification_returns_filtered_result(self):
        scraper = FDARecallsScraper()
        scraper.session.get = lambda *_args, **_kwargs: _FakeResponse(
            json_payload={
                "results": [
                    {
                        "recall_number": "F-4444-2026",
                        "classification": "Class II",
                        "report_date": "20260420",
                        "recalling_firm": "Filtered Farms",
                    }
                ]
            }
        )

        result = scraper.get_by_classification("Class II")

        assert result.success is True
        assert result.items_found == 1
        assert result.items[0].severity == EnforcementSeverity.HIGH

    def test_close_closes_http_session(self):
        scraper = FDARecallsScraper()
        scraper.session = type("S", (), {"closed": False, "close": lambda self: setattr(self, "closed", True)})()

        scraper.close()

        assert scraper.session.closed is True


class TestFDAWarningLettersParser_Issue1154:
    def test_scrape_falls_back_to_api_when_rss_is_empty(self, monkeypatch):
        scraper = FDAWarningLettersScraper()
        api_item = EnforcementItem(
            source_type=SourceType.FDA_WARNING_LETTER,
            source_id="api-1",
            title="API fallback item",
            url="https://example.test/wl/api-1",
            published_date=datetime.now(),
            severity=EnforcementSeverity.HIGH,
        )
        monkeypatch.setattr(scraper, "_scrape_rss", lambda: [])
        monkeypatch.setattr(scraper, "_scrape_api", lambda: [api_item])

        result = scraper.scrape()

        assert result.success is True
        assert result.items_found == 1
        assert result.items[0].source_id == "api-1"

    def test_scrape_surfaces_errors(self, monkeypatch):
        scraper = FDAWarningLettersScraper()
        monkeypatch.setattr(
            scraper,
            "_scrape_rss",
            lambda: (_ for _ in ()).throw(ValueError("rss boom")),
        )

        result = scraper.scrape()

        assert result.success is False
        assert result.error_message == "rss boom"

    def test_scrape_rss_404_returns_empty_for_api_fallback(self, monkeypatch):
        scraper = FDAWarningLettersScraper()
        monkeypatch.setattr(
            "app.scrapers.fda_warning_letters.fetch_with_retry",
            lambda *_args, **_kwargs: _FakeResponse(status_code=404),
        )

        assert scraper._scrape_rss() == []

    def test_scrape_rss_parses_items_from_feed(self, monkeypatch):
        scraper = FDAWarningLettersScraper()
        rss = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Fresh Foods LLC - Warning Letter</title>
      <link>https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/warning-letters/fresh-foods-llc-123</link>
      <description>FDA observed sanitation violations.</description>
      <pubDate>Wed, 15 Jan 2026 12:00:00 -0500</pubDate>
    </item>
  </channel>
</rss>
"""

        monkeypatch.setattr(
            "app.scrapers.fda_warning_letters.fetch_with_retry",
            lambda *_args, **_kwargs: _FakeResponse(content=rss),
        )

        items = scraper._scrape_rss()

        assert len(items) == 1
        assert items[0].severity == EnforcementSeverity.HIGH
        assert items[0].affected_companies == ["Fresh Foods LLC"]
        assert "sanitation violations" in (items[0].summary or "")

    def test_scrape_rss_skips_items_missing_required_fields(self, monkeypatch):
        scraper = FDAWarningLettersScraper()
        rss = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title></title>
      <link>https://www.fda.gov/warning-letters/missing-title</link>
      <description>Ignored</description>
    </item>
  </channel>
</rss>
"""
        monkeypatch.setattr(
            "app.scrapers.fda_warning_letters.fetch_with_retry",
            lambda *_args, **_kwargs: _FakeResponse(content=rss),
        )

        assert scraper._scrape_rss() == []

    def test_scrape_api_maps_severity_and_skips_bad_rows(self, monkeypatch):
        scraper = FDAWarningLettersScraper()

        monkeypatch.setattr(
            "app.scrapers.fda_warning_letters.fetch_with_retry",
            lambda *_args, **_kwargs: _FakeResponse(
                json_payload={
                    "results": [
                        {
                            "recall_number": "W-2026-0001",
                            "classification": "Class I",
                            "report_date": "20260420",
                            "recalling_firm": "Cutter Foods",
                            "product_description": "Bagged salad kits",
                            "reason_for_recall": "Undeclared allergen",
                        },
                        {
                            "recall_number": "W-2026-0002",
                            "classification": "Class II",
                            "report_date": "bad-date",
                            "recalling_firm": "Broken Date Co",
                        },
                    ]
                }
            ),
        )

        items = scraper._scrape_api()

        assert len(items) == 1
        assert items[0].severity == EnforcementSeverity.CRITICAL
        assert items[0].affected_products == ["Bagged salad kits"]
        assert isinstance(items[0].published_date, datetime)

    def test_scrape_api_keeps_class_ii_high_not_critical(self, monkeypatch):
        scraper = FDAWarningLettersScraper()
        monkeypatch.setattr(
            "app.scrapers.fda_warning_letters.fetch_with_retry",
            lambda *_args, **_kwargs: _FakeResponse(
                json_payload={
                    "results": [
                        {
                            "recall_number": "W-2026-0003",
                            "classification": "Class II",
                            "report_date": "20260420",
                            "recalling_firm": "Label Foods",
                            "product_description": "Soup cans",
                        }
                    ]
                }
            ),
        )

        items = scraper._scrape_api()

        assert len(items) == 1
        assert items[0].severity == EnforcementSeverity.HIGH

    def test_parse_rss_date_invalid_input_falls_back(self):
        scraper = FDAWarningLettersScraper()

        parsed = scraper._parse_rss_date("not-a-date")

        assert isinstance(parsed, datetime)

    def test_close_closes_http_session(self):
        scraper = FDAWarningLettersScraper()
        scraper.session = type("S", (), {"closed": False, "close": lambda self: setattr(self, "closed", True)})()

        scraper.close()

        assert scraper.session.closed is True
