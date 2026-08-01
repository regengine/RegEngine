"""Regression tests for #1135 — FSMA nightly sync must run in production.

Before the fix, `services/scheduler/app/jobs.py` defined
`fsma_nightly_sync_job` (02:00 UTC daily) on its own module-level
`BlockingScheduler()` that was never started, so the job fired nowhere —
despite being documented as a "Phase 29" compliance feature.

The job now lives on the real scheduler via
`SchedulerService.run_fsma_nightly_sync` and a `CronTrigger(hour=2)`
registered in `schedule_jobs`. It runs the ingestion sweep IN-PROCESS
(``services.ingestion.app.routes_scraping.run_all_regulations_ingest``):
the old HTTP POST authenticated with ``REGENGINE_INTERNAL_SECRET``, which
``shared.auth.require_api_key`` never accepted, so it could only 401.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _build_scheduler_service_without_init():
    """Construct SchedulerService with heavy dependencies stubbed."""
    from services.scheduler import service as scheduler_service

    with (
        patch.object(scheduler_service, "get_kafka_producer", return_value=MagicMock()),
        patch.object(scheduler_service, "WebhookNotifier", return_value=MagicMock()),
        patch.object(scheduler_service, "DistributedContext", return_value=MagicMock()),
        patch.object(scheduler_service, "StateManager", return_value=MagicMock()),
        patch.object(scheduler_service, "FDAImportAlertsScraper", return_value=MagicMock()),
        patch.object(scheduler_service, "FDARecallsScraper", return_value=MagicMock()),
        patch.object(scheduler_service, "FDAWarningLettersScraper", return_value=MagicMock()),
        patch.object(scheduler_service, "BlockingScheduler", return_value=MagicMock()),
    ):
        svc = scheduler_service.SchedulerService()
    return svc


class TestNightlyFsmaSyncRegistered:
    """#1135 — `fsma_nightly_sync` must be reachable from the running scheduler."""

    def test_fsma_nightly_sync_job_is_scheduled(self):
        svc = _build_scheduler_service_without_init()
        svc.scheduler = MagicMock()
        svc.schedule_jobs()

        scheduled_ids = [call.kwargs.get("id") for call in svc.scheduler.add_job.call_args_list]
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

    def test_regulatory_discovery_duplicate_is_gone(self):
        """The old regulatory_discovery job POSTed the same
        /v1/ingest/all-regulations sweep with credentials require_api_key
        never accepted. fsma_nightly_sync is the single daily sync."""
        svc = _build_scheduler_service_without_init()
        svc.scheduler = MagicMock()
        svc.schedule_jobs()

        scheduled_ids = [call.kwargs.get("id") for call in svc.scheduler.add_job.call_args_list]
        assert "regulatory_discovery" not in scheduled_ids


class TestNightlyFsmaSyncExecution:
    """The sync method itself — in-process invocation and error paths."""

    def test_run_fsma_nightly_sync_calls_ingestion_in_process(self):
        svc = _build_scheduler_service_without_init()

        async def _fake_ingest():
            return {
                "sources_attempted": 5,
                "ingested": 2,
                "unchanged": 3,
                "failed": 0,
            }

        with patch(
            "services.ingestion.app.routes_scraping.run_all_regulations_ingest",
            side_effect=_fake_ingest,
        ) as ingest:
            svc.run_fsma_nightly_sync()

        ingest.assert_called_once_with()

    def test_run_fsma_nightly_sync_reraises_ingest_errors(self):
        """#2697: a failing sweep RE-RAISES after logging so APScheduler
        fires EVENT_JOB_ERROR and the #1144 listener records the failure
        (an exception in a job never crashes the scheduler thread — the
        executor catches it and dispatches the error event)."""
        svc = _build_scheduler_service_without_init()

        async def _boom():
            raise RuntimeError("source exploded")

        with patch(
            "services.ingestion.app.routes_scraping.run_all_regulations_ingest",
            side_effect=_boom,
        ):
            with pytest.raises(RuntimeError, match="source exploded"):
                svc.run_fsma_nightly_sync()

    def test_run_fsma_nightly_sync_does_not_use_http(self):
        """The HTTP-to-self path is gone — no POST, no internal secret."""
        svc = _build_scheduler_service_without_init()

        async def _fake_ingest():
            return {"sources_attempted": 0, "ingested": 0, "unchanged": 0, "failed": 0}

        with (
            patch(
                "services.ingestion.app.routes_scraping.run_all_regulations_ingest",
                side_effect=_fake_ingest,
            ),
            patch("shared.safe_http.safe_httpx_post_sync") as post,
        ):
            svc.run_fsma_nightly_sync()

        post.assert_not_called()


class TestNightlyFsmaSyncAllFailedAlerting:
    """#2505 — a sync where every source failed (e.g. Redis unreachable for the
    ETag/content-hash dedup layer) must escalate to error/alert, not pass
    silently at info level."""

    def _run_with_summary(self, summary):
        from services.scheduler import service as scheduler_service

        svc = _build_scheduler_service_without_init()

        async def _fake_ingest():
            return summary

        with (
            patch(
                "services.ingestion.app.routes_scraping.run_all_regulations_ingest",
                side_effect=_fake_ingest,
            ),
            patch.object(scheduler_service.logger, "error") as err,
            patch.object(scheduler_service.logger, "info") as info,
        ):
            svc.run_fsma_nightly_sync()

        err_events = [c.args[0] for c in err.call_args_list if c.args]
        info_events = [c.args[0] for c in info.call_args_list if c.args]
        return err_events, info_events

    def test_all_sources_failed_logs_error(self):
        err_events, info_events = self._run_with_summary(
            {"sources_attempted": 5, "ingested": 0, "unchanged": 0, "failed": 5}
        )
        assert "fsma_nightly_sync_all_failed" in err_events
        assert "fsma_nightly_sync_complete" not in info_events

    def test_partial_failure_logs_info_complete(self):
        err_events, info_events = self._run_with_summary(
            {"sources_attempted": 5, "ingested": 2, "unchanged": 2, "failed": 1}
        )
        assert "fsma_nightly_sync_complete" in info_events
        assert "fsma_nightly_sync_all_failed" not in err_events

    def test_all_success_logs_info_complete(self):
        err_events, info_events = self._run_with_summary(
            {"sources_attempted": 5, "ingested": 5, "unchanged": 0, "failed": 0}
        )
        assert "fsma_nightly_sync_complete" in info_events
        assert "fsma_nightly_sync_all_failed" not in err_events

    def test_zero_sources_attempted_does_not_alert(self):
        """0/0 is not an all-failed condition — must not page."""
        err_events, info_events = self._run_with_summary(
            {"sources_attempted": 0, "ingested": 0, "unchanged": 0, "failed": 0}
        )
        assert "fsma_nightly_sync_all_failed" not in err_events
        assert "fsma_nightly_sync_complete" in info_events
