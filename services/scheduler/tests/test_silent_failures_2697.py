"""#2697: scheduler & probe silent-failure follow-ups.

Covers:
* run_fsma_nightly_sync / drain_remediation_notifications RE-RAISE after
  logging, so APScheduler fires EVENT_JOB_ERROR and the #1144 listener
  records the failure (pre-fix: swallowed → scheduler_job_runs said success).
* Stale-coverage alert: N consecutive successful-but-zero-item scrapes of
  the same source log an error instead of staying silent forever.
* Webhook outbox: corrupt JSONL lines are QUARANTINED, not destroyed by the
  retry pass's rewrite.
* FDA recalls: a row missing recall_number leaves a log trace when dropped.
"""

from __future__ import annotations

import json
import sys
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _make_scheduler_service():
    """Build a SchedulerService with all heavy dependencies mocked out."""
    from services.scheduler import service as scheduler_service

    with (
        patch.object(scheduler_service, "get_settings") as mock_settings,
        patch.object(scheduler_service, "StateManager"),
        patch.object(scheduler_service, "WebhookNotifier"),
        patch.object(scheduler_service, "get_kafka_producer"),
        patch.object(scheduler_service, "DistributedContext"),
        patch.object(scheduler_service, "circuit_registry"),
        patch.object(scheduler_service, "FDAWarningLettersScraper"),
        patch.object(scheduler_service, "FDAImportAlertsScraper"),
        patch.object(scheduler_service, "FDARecallsScraper"),
    ):
        settings = MagicMock()
        settings.webhook_outbox_path = None
        settings.fda_warning_letters_interval = 60
        settings.fda_import_alerts_interval = 120
        settings.fda_recalls_interval = 30
        settings.circuit_breaker_failure_threshold = 3
        settings.circuit_breaker_recovery_timeout = 300
        mock_settings.return_value = settings

        return scheduler_service.SchedulerService()


# ---------------------------------------------------------------------------
# Job failures must re-raise (EVENT_JOB_ERROR / #1144 listener)
# ---------------------------------------------------------------------------


class TestJobFailuresReRaise:
    def test_fsma_nightly_sync_reraises_on_crash(self, monkeypatch):
        svc = _make_scheduler_service()

        async def _boom():
            raise RuntimeError("sync exploded")

        fake_mod = SimpleNamespace(run_all_regulations_ingest=_boom)
        monkeypatch.setitem(sys.modules, "services.ingestion.app.routes_scraping", fake_mod)

        with pytest.raises(RuntimeError, match="sync exploded"):
            svc.run_fsma_nightly_sync()

    def test_remediation_drain_reraises_on_crash(self, monkeypatch):
        svc = _make_scheduler_service()

        db_mod = SimpleNamespace(SessionLocal=MagicMock())

        def _boom(_db):
            raise RuntimeError("drain exploded")

        delivery_mod = SimpleNamespace(drain_all_tenants=_boom)
        monkeypatch.setitem(sys.modules, "shared.database", db_mod)
        monkeypatch.setitem(sys.modules, "services.ingestion.app.remediation.delivery", delivery_mod)

        with pytest.raises(RuntimeError, match="drain exploded"):
            svc.drain_remediation_notifications()


# ---------------------------------------------------------------------------
# Stale-coverage alert (#2697 item 6)
# ---------------------------------------------------------------------------


class TestStaleCoverageAlert:
    def _run_zero_scrape(self, svc, source_type):
        from services.scheduler.app.models import ScrapeResult

        scraper = MagicMock()
        scraper.name = "stub"
        scraper.scrape.return_value = ScrapeResult(
            source_type=source_type,
            success=True,
            items_found=0,
            items_new=0,
            items=[],
        )
        breaker = MagicMock()
        breaker.can_execute.return_value = True
        svc._run_scraper_inner(source_type, scraper, breaker, MagicMock())

    def test_consecutive_zero_runs_trigger_alert(self, monkeypatch):
        from services.scheduler import service as scheduler_service
        from services.scheduler.app.models import SourceType

        svc = _make_scheduler_service()
        fake_logger = MagicMock()
        monkeypatch.setattr(scheduler_service, "logger", fake_logger)

        for _ in range(scheduler_service._STALE_COVERAGE_ZERO_RUNS):
            self._run_zero_scrape(svc, SourceType.FDA_WARNING_LETTER)

        stale_calls = [c for c in fake_logger.error.call_args_list if c.args and c.args[0] == "scrape_coverage_stale"]
        assert len(stale_calls) == 1
        assert stale_calls[0].kwargs["consecutive_zero_item_runs"] == scheduler_service._STALE_COVERAGE_ZERO_RUNS

    def test_nonzero_scrape_resets_streak(self, monkeypatch):
        from services.scheduler import service as scheduler_service
        from services.scheduler.app.models import ScrapeResult, SourceType

        svc = _make_scheduler_service()
        fake_logger = MagicMock()
        monkeypatch.setattr(scheduler_service, "logger", fake_logger)

        src = SourceType.FDA_WARNING_LETTER
        for _ in range(scheduler_service._STALE_COVERAGE_ZERO_RUNS - 1):
            self._run_zero_scrape(svc, src)
        assert svc._consecutive_zero_scrapes[src] == scheduler_service._STALE_COVERAGE_ZERO_RUNS - 1

        # A run with items resets the streak; note the scraper returns items
        # but _filter_new_items is driven by mocked state, so route through
        # the counter directly via a non-empty ScrapeResult.
        scraper = MagicMock()
        scraper.name = "stub"
        scraper.scrape.return_value = ScrapeResult(
            source_type=src,
            success=True,
            items_found=3,
            items_new=0,
            items=[],
        )
        breaker = MagicMock()
        breaker.can_execute.return_value = True
        svc._run_scraper_inner(src, scraper, breaker, MagicMock())

        assert svc._consecutive_zero_scrapes[src] == 0
        stale_calls = [c for c in fake_logger.error.call_args_list if c.args and c.args[0] == "scrape_coverage_stale"]
        assert not stale_calls


# ---------------------------------------------------------------------------
# Outbox quarantine (#2697 item 3)
# ---------------------------------------------------------------------------


class TestOutboxQuarantine:
    def _notifier(self, outbox_path):
        from services.scheduler.app.notifications import WebhookNotifier

        return WebhookNotifier(urls=["https://hook.example.com"], outbox_path=str(outbox_path))

    def test_corrupt_line_is_quarantined_not_destroyed(self, tmp_path):
        from services.scheduler.app.notifications import OutboxEntry

        outbox = tmp_path / "outbox.jsonl"
        valid = OutboxEntry(
            url="https://hook.example.com",
            payload={"k": "v"},
            next_retry_at=time.time() + 1000,  # not due — no HTTP attempted
        )
        corrupt_raw = '{"url": "https://hook.example.com", "payload": TRUNCATED'
        outbox.write_text(json.dumps(valid.to_dict()) + "\n" + corrupt_raw + "\n")

        n = self._notifier(outbox)
        try:
            n.retry_outbox_once()
        finally:
            n.close()

        quarantine = tmp_path / "outbox.jsonl.quarantine"
        assert quarantine.exists(), "corrupt line must be preserved in quarantine"
        assert corrupt_raw in quarantine.read_text()

        # The rewritten outbox keeps the valid entry and drops the corrupt
        # line (it lives in quarantine now).
        remaining = [json.loads(line) for line in outbox.read_text().splitlines() if line.strip()]
        assert len(remaining) == 1
        assert remaining[0]["url"] == "https://hook.example.com"

    def test_valid_outbox_produces_no_quarantine(self, tmp_path):
        from services.scheduler.app.notifications import OutboxEntry

        outbox = tmp_path / "outbox.jsonl"
        valid = OutboxEntry(
            url="https://hook.example.com",
            payload={"k": "v"},
            next_retry_at=time.time() + 1000,
        )
        outbox.write_text(json.dumps(valid.to_dict()) + "\n")

        n = self._notifier(outbox)
        try:
            n.retry_outbox_once()
        finally:
            n.close()

        assert not (tmp_path / "outbox.jsonl.quarantine").exists()


# ---------------------------------------------------------------------------
# FDA recalls: dropped rows leave a trace (#2697 item 7)
# ---------------------------------------------------------------------------


class TestRecallDropLogging:
    def test_missing_recall_number_logs_warning(self, monkeypatch):
        from services.scheduler.app.scrapers import fda_recalls

        fake_logger = MagicMock()
        monkeypatch.setattr(fda_recalls, "logger", fake_logger)

        scraper = fda_recalls.FDARecallsScraper()
        assert scraper._parse_recall({"report_date": "20260101", "classification": "Class I"}) is None

        drop_calls = [
            c
            for c in fake_logger.warning.call_args_list
            if c.args and c.args[0] == "recall_row_missing_recall_number_dropped"
        ]
        assert len(drop_calls) == 1
        assert drop_calls[0].kwargs["report_date"] == "20260101"
