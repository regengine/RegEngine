"""Regression tests for #2510 — webhook dead-letter queue durability.

The scheduler's webhook DLQ persists to disk only when WEBHOOK_OUTBOX_PATH is
set, and that variable defaults to "" (in-memory only). The embedded scheduler
runs inside the ephemeral Railway monolith container, so once an operator
enables WEBHOOK_URLS without also setting WEBHOOK_OUTBOX_PATH, failed deliveries
of HIGH/CRITICAL alerts are silently dropped on the next restart and the drain
job that would retry them never registers.

These tests assert the loud-default guard and the job-registration gating on
the real SchedulerService.schedule_jobs() path with the heavy dependencies
stubbed (mirrors test_fsma_nightly_sync_wired.py).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import services.scheduler.app.notifications as notifications_mod  # noqa: F401  (ensures package import path)


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


def _scheduled_job_ids(svc) -> list[str]:
    return [call.kwargs.get("id") for call in svc.scheduler.add_job.call_args_list]


class TestWebhookOutboxDrainRegistration:
    def test_drain_job_registered_when_outbox_path_set(self):
        svc = _build_scheduler_service_without_init()
        svc.scheduler = MagicMock()
        svc.settings.webhook_outbox_path = "/data/webhook_outbox.jsonl"

        svc.schedule_jobs()

        assert "webhook_outbox_drain" in _scheduled_job_ids(svc)

    def test_drain_job_not_registered_when_outbox_path_empty(self):
        svc = _build_scheduler_service_without_init()
        svc.scheduler = MagicMock()
        svc.settings.webhook_outbox_path = ""

        svc.schedule_jobs()

        assert "webhook_outbox_drain" not in _scheduled_job_ids(svc)


class TestWebhookDlqLoudDefault:
    def test_warns_when_webhooks_enabled_without_durable_outbox(self):
        """WEBHOOK_URLS set + WEBHOOK_OUTBOX_PATH empty -> startup WARNING so the
        in-memory-only footgun is not silent (#2510)."""
        svc = _build_scheduler_service_without_init()
        svc.scheduler = MagicMock()
        svc.settings.webhook_urls = "https://hook.example.com/alerts"
        svc.settings.webhook_outbox_path = ""

        from services.scheduler import service as scheduler_service

        with patch.object(scheduler_service.logger, "warning") as warn:
            svc.schedule_jobs()

        warned_events = [call.args[0] for call in warn.call_args_list if call.args]
        assert "webhook_dlq_persistence_disabled" in warned_events

    def test_no_warning_when_outbox_path_configured(self):
        svc = _build_scheduler_service_without_init()
        svc.scheduler = MagicMock()
        svc.settings.webhook_urls = "https://hook.example.com/alerts"
        svc.settings.webhook_outbox_path = "/data/webhook_outbox.jsonl"

        from services.scheduler import service as scheduler_service

        with patch.object(scheduler_service.logger, "warning") as warn:
            svc.schedule_jobs()

        warned_events = [call.args[0] for call in warn.call_args_list if call.args]
        assert "webhook_dlq_persistence_disabled" not in warned_events

    def test_no_warning_when_webhooks_disabled(self):
        svc = _build_scheduler_service_without_init()
        svc.scheduler = MagicMock()
        svc.settings.webhook_urls = ""
        svc.settings.webhook_outbox_path = ""

        from services.scheduler import service as scheduler_service

        with patch.object(scheduler_service.logger, "warning") as warn:
            svc.schedule_jobs()

        warned_events = [call.args[0] for call in warn.call_args_list if call.args]
        assert "webhook_dlq_persistence_disabled" not in warned_events
