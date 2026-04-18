"""Regression tests for #1135 — FSMA nightly sync must run in production.

Before the fix, `services/scheduler/app/jobs.py` defined
`fsma_nightly_sync_job` (02:00 UTC daily) on its own module-level
`BlockingScheduler()` that was never started. The entry point
`main.py` instantiated its own scheduler and never imported
`app.jobs`, so the job fired nowhere — despite being documented as a
"Phase 29" compliance feature.

The fix re-homes the job onto the real scheduler via
`SchedulerService.run_fsma_nightly_sync` and a `CronTrigger(hour=2)`
registered in `schedule_jobs`.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _build_scheduler_service_without_init():
    """Construct SchedulerService with heavy dependencies stubbed."""
    import main as scheduler_main

    with patch.object(scheduler_main, "get_kafka_producer", return_value=MagicMock()), \
         patch.object(scheduler_main, "WebhookNotifier", return_value=MagicMock()), \
         patch.object(scheduler_main, "DistributedContext", return_value=MagicMock()), \
         patch.object(scheduler_main, "StateManager", return_value=MagicMock()), \
         patch.object(scheduler_main, "FDAImportAlertsScraper", return_value=MagicMock()), \
         patch.object(scheduler_main, "FDARecallsScraper", return_value=MagicMock()), \
         patch.object(scheduler_main, "FDAWarningLettersScraper", return_value=MagicMock()), \
         patch.object(scheduler_main, "InternalDiscoveryScraper", return_value=MagicMock()), \
         patch.object(scheduler_main, "BlockingScheduler", return_value=MagicMock()):
        svc = scheduler_main.SchedulerService()
    return svc


class TestNightlyFsmaSyncRegistered:
    """#1135 — `fsma_nightly_sync` must be reachable from the running scheduler."""

    def test_fsma_nightly_sync_job_is_scheduled(self):
        svc = _build_scheduler_service_without_init()
        svc.scheduler = MagicMock()
        svc.schedule_jobs()

        scheduled_ids = [
            call.kwargs.get("id")
            for call in svc.scheduler.add_job.call_args_list
        ]
        assert "fsma_nightly_sync" in scheduled_ids, (
            "FSMA nightly sync must be registered on the running "
            "BlockingScheduler — see #1135. Scheduled: %s" % scheduled_ids
        )

    def test_fsma_nightly_sync_fires_on_cron_trigger(self):
        svc = _build_scheduler_service_without_init()
        svc.scheduler = MagicMock()
        svc.schedule_jobs()

        from apscheduler.triggers.cron import CronTrigger
        for call in svc.scheduler.add_job.call_args_list:
            if call.kwargs.get("id") == "fsma_nightly_sync":
                trigger = call.kwargs.get("trigger")
                assert isinstance(trigger, CronTrigger), (
                    "fsma_nightly_sync must use CronTrigger(hour=2) not "
                    "IntervalTrigger — exact cadence matters for the audit trail"
                )
                return
        pytest.fail("fsma_nightly_sync job not found in schedule_jobs()")


class TestNightlyFsmaSyncExecution:
    """The sync method itself — auth, endpoint, error paths."""

    def test_run_fsma_nightly_sync_skips_on_missing_secret(self, monkeypatch):
        """#1063 — do not POST an empty API key; log and return."""
        monkeypatch.delenv("REGENGINE_INTERNAL_SECRET", raising=False)

        svc = _build_scheduler_service_without_init()

        with patch("httpx.post") as post:
            svc.run_fsma_nightly_sync()

        post.assert_not_called()

    def test_run_fsma_nightly_sync_skips_on_empty_secret(self, monkeypatch):
        monkeypatch.setenv("REGENGINE_INTERNAL_SECRET", "   ")

        svc = _build_scheduler_service_without_init()

        with patch("httpx.post") as post:
            svc.run_fsma_nightly_sync()

        post.assert_not_called()

    def test_run_fsma_nightly_sync_posts_when_secret_set(self, monkeypatch):
        monkeypatch.setenv("REGENGINE_INTERNAL_SECRET", "secret-123")
        monkeypatch.setenv("INGESTION_SERVICE_URL", "http://ingestion.test")

        svc = _build_scheduler_service_without_init()

        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.content = b'{"sources_attempted": 5}'
        fake_response.json.return_value = {
            "sources_attempted": 5,
            "ingested": 2,
            "unchanged": 3,
            "failed": 0,
        }

        with patch("httpx.post", return_value=fake_response) as post:
            svc.run_fsma_nightly_sync()

        post.assert_called_once()
        call_kwargs = post.call_args.kwargs
        assert call_kwargs["headers"]["X-RegEngine-API-Key"] == "secret-123"
        assert post.call_args.args[0].endswith("/v1/ingest/all-regulations")
