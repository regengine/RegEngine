"""Hardening tests for the scheduler service — emit-then-ack invariant.

Regression tests for #1136: items must not be marked "seen" until the
downstream broker has acknowledged the event. Before the fix,
`_filter_new_items` persisted `mark_seen()` eagerly and a Kafka outage
would silently drop FDA recalls because the state manager thought they
were already processed.

The Kafka-path tests set ``EVENT_BACKBONE=kafka`` because #1159 gates
Kafka emission off in the default (pg) backbone — see
``TestPgBackboneGating`` for the pg-mode contract.

These tests deliberately stub external integrations so they can run
without any of the actual infrastructure (APScheduler, Kafka, Redis,
PostgreSQL, DistributedContext).
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from services.scheduler.app.models import (
    EnforcementItem,
    EnforcementSeverity,
    SourceType,
)


def _make_item(source_id: str = "fda_recall:001") -> EnforcementItem:
    return EnforcementItem(
        source_type=SourceType.FDA_RECALL,
        source_id=source_id,
        title="Recall of Something",
        summary="Class II recall",
        url="https://example.com/recalls/001",
        published_date=datetime(2026, 4, 17, tzinfo=timezone.utc),
        severity=EnforcementSeverity.HIGH,
    )


def _build_scheduler_service_without_init():
    """Construct SchedulerService with all heavy dependencies stubbed.

    APScheduler, Kafka, Redis, DistributedContext, and the DB-backed state
    manager must all be avoidable so these tests can run in CI without
    any of that infrastructure.
    """
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


@pytest.fixture
def kafka_backbone(monkeypatch):
    """Opt the test into the legacy Kafka emission path (#1159)."""
    monkeypatch.setenv("EVENT_BACKBONE", "kafka")


class TestEmitThenAckInvariant:
    """#1136 — items must not be marked seen until emission succeeds."""

    def test_items_not_marked_seen_when_kafka_emit_raises(self, kafka_backbone):
        svc = _build_scheduler_service_without_init()
        svc.state_manager = MagicMock()
        svc.kafka_producer = MagicMock()
        svc.kafka_producer.emit_batch.side_effect = ConnectionError("broker down")
        svc.kafka_producer.emit_fsma_batch.return_value = (0, 0)
        svc.notifier = MagicMock()
        svc.notifier.notify.return_value = []

        item = _make_item()
        svc._process_new_items([item], SourceType.FDA_RECALL)

        # The whole point of the fix — mark_seen MUST NOT be called
        # when Kafka emission fails.
        assert svc.state_manager.mark_seen.call_count == 0

    def test_items_marked_seen_when_kafka_emit_succeeds(self, kafka_backbone):
        svc = _build_scheduler_service_without_init()
        svc.state_manager = MagicMock()
        svc.kafka_producer = MagicMock()
        # emit_batch returns (success_count, failure_count) — zero failures.
        svc.kafka_producer.emit_batch.return_value = (1, 0)
        svc.kafka_producer.emit_fsma_batch.return_value = (1, 0)
        svc.notifier = MagicMock()
        svc.notifier.notify.return_value = []

        item = _make_item()
        # Alerting succeeds — this test pins the Kafka emit/ack contract,
        # and a real (unstubbed) integration failure would withhold the ack.
        with patch(
            "services.scheduler.app.compliance_integration.get_compliance_integration",
            return_value=MagicMock(),
        ):
            svc._process_new_items([item], SourceType.FDA_RECALL)

        svc.state_manager.mark_seen.assert_called_once()
        kwargs = svc.state_manager.mark_seen.call_args.kwargs
        assert kwargs["source_id"] == item.source_id
        assert kwargs["source_type"] == SourceType.FDA_RECALL.value

    def test_partial_kafka_failure_leaves_items_unmarked(self, kafka_backbone):
        """emit_batch reports 1 success + 1 failure → do NOT mark seen.

        If any item fails to emit, the whole batch stays un-marked so the
        next scheduler tick re-discovers and re-emits (downstream is
        idempotent on source_id). This is the safe default.
        """
        svc = _build_scheduler_service_without_init()
        svc.state_manager = MagicMock()
        svc.kafka_producer = MagicMock()
        svc.kafka_producer.emit_batch.return_value = (1, 1)
        svc.kafka_producer.emit_fsma_batch.return_value = (0, 0)
        svc.notifier = MagicMock()
        svc.notifier.notify.return_value = []

        items = [_make_item("a"), _make_item("b")]
        svc._process_new_items(items, SourceType.FDA_RECALL)

        assert svc.state_manager.mark_seen.call_count == 0

    def test_filter_new_items_does_not_mark_seen(self):
        """Regression guard: _filter_new_items must never call mark_seen."""
        svc = _build_scheduler_service_without_init()
        svc.state_manager = MagicMock()
        svc.state_manager.is_new.return_value = True

        items = [_make_item("a"), _make_item("b")]
        result = svc._filter_new_items(items, SourceType.FDA_RECALL)

        assert len(result) == 2
        assert svc.state_manager.mark_seen.call_count == 0

    def test_mark_seen_stops_on_first_failure(self):
        """If mark_seen raises mid-loop, remaining items stay un-marked."""
        svc = _build_scheduler_service_without_init()
        svc.state_manager = MagicMock()
        svc.state_manager.mark_seen.side_effect = [None, RuntimeError("pg down")]

        items = [_make_item("a"), _make_item("b"), _make_item("c")]
        svc._mark_items_seen(items, SourceType.FDA_RECALL)

        # Should have attempted 2 of 3 (stopped after the exception).
        assert svc.state_manager.mark_seen.call_count == 2


class TestPgBackboneGating:
    """#1159 — with EVENT_BACKBONE=pg (the production default) Kafka
    emission is skipped entirely and must not block the seen-ack."""

    def test_pg_mode_skips_kafka_and_marks_seen(self, monkeypatch):
        monkeypatch.delenv("EVENT_BACKBONE", raising=False)

        svc = _build_scheduler_service_without_init()
        svc.state_manager = MagicMock()
        svc.kafka_producer = MagicMock()
        svc.notifier = MagicMock()
        svc.notifier.notify.return_value = []

        item = _make_item()
        # Alerting succeeds — this test pins pg-mode Kafka gating/acking,
        # and a real (unstubbed) integration failure would withhold the ack.
        with patch(
            "services.scheduler.app.compliance_integration.get_compliance_integration",
            return_value=MagicMock(),
        ):
            svc._process_new_items([item], SourceType.FDA_RECALL)

        # No Kafka traffic at all in pg mode...
        svc.kafka_producer.emit_batch.assert_not_called()
        svc.kafka_producer.emit_fsma_batch.assert_not_called()
        # ...and the item is still acked so the next tick doesn't re-alert.
        svc.state_manager.mark_seen.assert_called_once()

    def test_pg_mode_still_delivers_webhooks_and_compliance_alerts(self, monkeypatch):
        monkeypatch.delenv("EVENT_BACKBONE", raising=False)

        svc = _build_scheduler_service_without_init()
        svc.state_manager = MagicMock()
        svc.kafka_producer = MagicMock()
        svc.notifier = MagicMock()
        svc.notifier.notify.return_value = []

        integration = MagicMock()
        with patch(
            "services.scheduler.app.compliance_integration.get_compliance_integration",
            return_value=integration,
        ):
            item = _make_item()
            svc._process_new_items([item], SourceType.FDA_RECALL)

        svc.notifier.notify.assert_called_once()
        integration.process_enforcement_item.assert_called_once_with(item)

    def test_compliance_alert_loop_continues_past_a_failing_item(self, monkeypatch):
        """A single recall raising inside process_enforcement_item must not drop
        alerts for the rest of the batch. Before the per-item guard, one
        exception aborted the loop while the batch was still marked seen (pg
        mode acks unconditionally), permanently losing later tenants' alerts.

        #2689 follow-up: the FAILED item's ack is now withheld so it retries
        next tick — only the succeeded items are marked seen."""
        monkeypatch.delenv("EVENT_BACKBONE", raising=False)

        svc = _build_scheduler_service_without_init()
        svc.state_manager = MagicMock()
        svc.kafka_producer = MagicMock()
        svc.notifier = MagicMock()
        svc.notifier.notify.return_value = []

        items = [_make_item(source_id=f"fda_recall:{i}") for i in range(3)]
        integration = MagicMock()
        # Middle item fails; first and third must still be attempted.
        integration.process_enforcement_item.side_effect = [None, RuntimeError("boom"), None]
        with patch(
            "services.scheduler.app.compliance_integration.get_compliance_integration",
            return_value=integration,
        ):
            svc._process_new_items(items, SourceType.FDA_RECALL)

        assert integration.process_enforcement_item.call_count == 3
        # Succeeded items ack once (no re-storm); the failed one is withheld
        # and will be re-discovered next tick.
        assert svc.state_manager.mark_seen.call_count == 2
        acked = {c.kwargs["source_id"] for c in svc.state_manager.mark_seen.call_args_list}
        assert acked == {"fda_recall:0", "fda_recall:2"}

    def test_compliance_integration_construction_failure_withholds_all_acks(self, monkeypatch):
        """If building the integration fails, no alert was attempted for any
        item — every ack is withheld so the whole batch retries next tick.
        The run must still not raise (#2689 follow-up; previously the batch
        was acked anyway and all alerts were lost permanently)."""
        monkeypatch.delenv("EVENT_BACKBONE", raising=False)

        svc = _build_scheduler_service_without_init()
        svc.state_manager = MagicMock()
        svc.kafka_producer = MagicMock()
        svc.notifier = MagicMock()
        svc.notifier.notify.return_value = []

        with patch(
            "services.scheduler.app.compliance_integration.get_compliance_integration",
            side_effect=RuntimeError("engine init failed"),
        ):
            # Must not raise.
            svc._process_new_items([_make_item()], SourceType.FDA_RECALL)

        svc.state_manager.mark_seen.assert_not_called()

    def test_all_alerts_succeeding_acks_every_item(self, monkeypatch):
        """No alerting failures → every item is acked exactly once."""
        monkeypatch.delenv("EVENT_BACKBONE", raising=False)

        svc = _build_scheduler_service_without_init()
        svc.state_manager = MagicMock()
        svc.kafka_producer = MagicMock()
        svc.notifier = MagicMock()
        svc.notifier.notify.return_value = []

        items = [_make_item(source_id=f"fda_recall:{i}") for i in range(3)]
        integration = MagicMock()
        with patch(
            "services.scheduler.app.compliance_integration.get_compliance_integration",
            return_value=integration,
        ):
            svc._process_new_items(items, SourceType.FDA_RECALL)

        assert svc.state_manager.mark_seen.call_count == 3

    def test_non_recall_sources_ack_normally(self, monkeypatch):
        """The withholding logic is recall-specific — other source types
        never enter the compliance loop and ack the full batch."""
        monkeypatch.delenv("EVENT_BACKBONE", raising=False)

        svc = _build_scheduler_service_without_init()
        svc.state_manager = MagicMock()
        svc.kafka_producer = MagicMock()
        svc.notifier = MagicMock()
        svc.notifier.notify.return_value = []

        item = _make_item(source_id="warning_letter:001")
        svc._process_new_items([item], SourceType.FDA_WARNING_LETTER)

        svc.state_manager.mark_seen.assert_called_once()
