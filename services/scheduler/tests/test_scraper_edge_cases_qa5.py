"""QA edge cases for the scheduler scrapers module.

Covers real failure modes found by probe:

1. Malformed RSS XML must fail closed as a ScrapeResult (success=False),
   not escape as an exception (xml ParseError is a SyntaxError, which the
   old narrow except tuple did not catch).
2. get_by_classification must skip a single malformed row and keep the
   valid rows, matching _fetch_recalls behavior (one bad row used to fail
   the whole result).
3. Warning-letters API rows missing recall_number must be skipped with a
   log trace: without this every such row shared source_id "fda_enf:",
   and the state manager dedupes on source_id only, so distinct actions
   were silently dropped after the first.
4. Empty product/company strings must not pollute item lists.
5. RSS dates without a timezone must come back timezone aware (UTC), so
   downstream code never mixes naive and aware datetimes.
6. Unexpected errors (non-dict JSON, random RuntimeError) must surface as
   failure ScrapeResults, never raise out of scrape().
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.models import EnforcementSeverity
from app.scrapers.fda_recalls import FDARecallsScraper
from app.scrapers.fda_warning_letters import FDAWarningLettersScraper


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        content: bytes = b"",
        json_payload: Any = None,
    ) -> None:
        self.status_code = status_code
        self.content = content
        self._json_payload = json_payload if json_payload is not None else {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._json_payload


_GOOD_RECALL = {
    "recall_number": "F-1111-2026",
    "classification": "Class II",
    "report_date": "20260419",
    "recalling_firm": "Grower One",
    "product_description": "Spinach",
}


@pytest.fixture
def recalls_scraper():
    scraper = FDARecallsScraper()
    try:
        yield scraper
    finally:
        scraper.close()


@pytest.fixture
def wl_scraper():
    scraper = FDAWarningLettersScraper()
    try:
        yield scraper
    finally:
        scraper.close()


class TestMalformedRSSFailsClosed:
    def test_garbage_xml_returns_failure_result(self, wl_scraper, monkeypatch):
        monkeypatch.setattr(
            "app.scrapers.fda_warning_letters.fetch_with_retry",
            lambda *args, **kwargs: _FakeResponse(content=b"<rss><channel><item><title>truncated garbage"),
        )
        result = wl_scraper.scrape()
        assert result.success is False
        assert result.items == []
        assert result.error_message

    def test_well_formed_holding_page_stays_success_with_zero_items(self, wl_scraper, monkeypatch):
        # A 200 holding page is well-formed XML with no items. That is not
        # a scrape failure; the scheduler stale-coverage alert owns that
        # case after N consecutive zero-item runs.
        monkeypatch.setattr(
            "app.scrapers.fda_warning_letters.fetch_with_retry",
            lambda *args, **kwargs: _FakeResponse(content=b"<html><body>CDN holding page</body></html>"),
        )
        monkeypatch.setattr(wl_scraper, "_scrape_api", lambda: [])
        result = wl_scraper.scrape()
        assert result.success is True
        assert result.items == []


class TestGetByClassificationSkipsBadRows:
    def test_one_bad_row_keeps_good_row(self, recalls_scraper, monkeypatch):
        bad_row = {
            "recall_number": "X-BAD",
            "classification": "Class I",
            "report_date": {"not": "a string"},
        }
        recalls_scraper.session.get = lambda *args, **kwargs: _FakeResponse(
            json_payload={"results": [_GOOD_RECALL, bad_row]}
        )
        result = recalls_scraper.get_by_classification("Class II")
        assert result.success is True
        assert result.items_found == 1
        assert result.items[0].source_id.endswith("F-1111-2026")

    def test_all_bad_rows_returns_empty_success(self, recalls_scraper, monkeypatch):
        bad_row = {"recall_number": "X-BAD", "report_date": {"not": "a string"}}
        recalls_scraper.session.get = lambda *args, **kwargs: _FakeResponse(json_payload={"results": [bad_row]})
        result = recalls_scraper.get_by_classification("Class II")
        assert result.success is True
        assert result.items_found == 0

    def test_bad_row_leaves_log_trace(self, recalls_scraper, monkeypatch):
        from app.scrapers import fda_recalls

        fake_logger = MagicMock()
        monkeypatch.setattr(fda_recalls, "logger", fake_logger)
        bad_row = {"recall_number": "X-BAD", "report_date": {"not": "a string"}}
        recalls_scraper.session.get = lambda *args, **kwargs: _FakeResponse(
            json_payload={"results": [_GOOD_RECALL, bad_row]}
        )
        recalls_scraper.get_by_classification("Class II")
        drop_calls = [c for c in fake_logger.warning.call_args_list if c.args and c.args[0] == "recall_parse_error"]
        assert len(drop_calls) == 1


class TestWarningLettersApiRowHygiene:
    def test_rows_missing_recall_number_are_skipped(self, wl_scraper, monkeypatch):
        from app.scrapers import fda_warning_letters

        fake_logger = MagicMock()
        monkeypatch.setattr(fda_warning_letters, "logger", fake_logger)
        monkeypatch.setattr(
            "app.scrapers.fda_warning_letters.fetch_with_retry",
            lambda *args, **kwargs: _FakeResponse(
                json_payload={
                    "results": [
                        {
                            "classification": "Class I",
                            "report_date": "20260420",
                            "recalling_firm": "Firm A",
                            "product_description": "Salad",
                        },
                        {
                            "classification": "Class II",
                            "report_date": "20260420",
                            "recalling_firm": "Firm B",
                            "product_description": "Soup",
                        },
                    ]
                }
            ),
        )
        items = wl_scraper._scrape_api()
        assert items == []
        drop_calls = [
            c
            for c in fake_logger.warning.call_args_list
            if c.args and c.args[0] == "warning_letter_row_missing_recall_number_dropped"
        ]
        assert len(drop_calls) == 2

    def test_source_ids_are_unique_per_recall_number(self, wl_scraper, monkeypatch):
        monkeypatch.setattr(
            "app.scrapers.fda_warning_letters.fetch_with_retry",
            lambda *args, **kwargs: _FakeResponse(
                json_payload={
                    "results": [
                        {
                            "recall_number": "W-2026-0001",
                            "classification": "Class I",
                            "report_date": "20260420",
                            "recalling_firm": "Firm A",
                            "product_description": "Salad",
                        },
                        {
                            "recall_number": "W-2026-0002",
                            "classification": "Class II",
                            "report_date": "20260420",
                            "recalling_firm": "Firm B",
                            "product_description": "Soup",
                        },
                    ]
                }
            ),
        )
        items = wl_scraper._scrape_api()
        assert len(items) == 2
        assert len({i.source_id for i in items}) == 2

    def test_empty_product_and_company_do_not_pollute_lists(self, wl_scraper, monkeypatch):
        monkeypatch.setattr(
            "app.scrapers.fda_warning_letters.fetch_with_retry",
            lambda *args, **kwargs: _FakeResponse(
                json_payload={
                    "results": [
                        {
                            "recall_number": "W-2026-0009",
                            "classification": "Class III",
                            "report_date": "20260420",
                        }
                    ]
                }
            ),
        )
        items = wl_scraper._scrape_api()
        assert len(items) == 1
        assert items[0].affected_products == []
        assert "" not in items[0].affected_companies


class TestRSSDateTimezone:
    def test_date_without_timezone_is_utc_aware(self, wl_scraper):
        parsed = wl_scraper._parse_rss_date("15 Jan 2026 12:00:00")
        assert isinstance(parsed, datetime)
        assert parsed.tzinfo is not None
        assert parsed.utcoffset() == timezone.utc.utcoffset(None)

    def test_date_with_timezone_preserved(self, wl_scraper):
        parsed = wl_scraper._parse_rss_date("Wed, 15 Jan 2026 12:00:00 -0500")
        assert parsed.tzinfo is not None
        assert isinstance(parsed, datetime)


class TestScrapeNeverRaises:
    def test_recalls_non_dict_json_returns_failure(self, recalls_scraper, monkeypatch):
        monkeypatch.setattr(
            "app.scrapers.fda_recalls.fetch_with_retry",
            lambda *args, **kwargs: _FakeResponse(json_payload=["not", "a", "dict"]),
        )
        result = recalls_scraper.scrape()
        assert result.success is False
        assert result.items == []
        assert result.error_message

    def test_recalls_unexpected_error_returns_failure(self, recalls_scraper, monkeypatch):
        monkeypatch.setattr(
            recalls_scraper,
            "_fetch_recalls",
            lambda: (_ for _ in ()).throw(RuntimeError("odd failure")),
        )
        result = recalls_scraper.scrape()
        assert result.success is False
        assert result.error_message == "odd failure"

    def test_get_by_classification_unexpected_error_returns_failure(self, recalls_scraper, monkeypatch):
        def _boom(*args, **kwargs):
            raise RuntimeError("odd failure")

        monkeypatch.setattr(recalls_scraper.session, "get", _boom)
        result = recalls_scraper.get_by_classification("Class I")
        assert result.success is False
        assert result.error_message == "odd failure"

    def test_warning_letters_severity_mapping_intact(self, wl_scraper, monkeypatch):
        monkeypatch.setattr(
            "app.scrapers.fda_warning_letters.fetch_with_retry",
            lambda *args, **kwargs: _FakeResponse(
                json_payload={
                    "results": [
                        {
                            "recall_number": "W-2026-0001",
                            "classification": "Class I",
                            "report_date": "20260420",
                            "recalling_firm": "Cutter Foods",
                            "product_description": "Bagged salad kits",
                        }
                    ]
                }
            ),
        )
        items = wl_scraper._scrape_api()
        assert len(items) == 1
        assert items[0].severity == EnforcementSeverity.CRITICAL
