"""Hardening tests for the scheduler service — emit-then-ack invariant.

Regression tests for #1136: items must not be marked "seen" until the
downstream broker has acknowledged the event. Before the fix,
`_filter_new_items` persisted `mark_seen()` eagerly and a Kafka outage
would silently drop FDA recalls because the state manager thought they
were already processed.

These tests deliberately stub external integrations so they can run
without any of the actual infrastructure (APScheduler, Kafka, Redis,
PostgreSQL, DistributedContext).
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.models import (
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


class TestEmitThenAckInvariant:
    """#1136 — items must not be marked seen until emission succeeds."""

    def test_items_not_marked_seen_when_kafka_emit_raises(self):
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

    def test_items_marked_seen_when_kafka_emit_succeeds(self):
        svc = _build_scheduler_service_without_init()
        svc.state_manager = MagicMock()
        svc.kafka_producer = MagicMock()
        # emit_batch returns (success_count, failure_count) — zero failures.
        svc.kafka_producer.emit_batch.return_value = (1, 0)
        svc.kafka_producer.emit_fsma_batch.return_value = (1, 0)
        svc.notifier = MagicMock()
        svc.notifier.notify.return_value = []

        item = _make_item()
        svc._process_new_items([item], SourceType.FDA_RECALL)

        svc.state_manager.mark_seen.assert_called_once()
        kwargs = svc.state_manager.mark_seen.call_args.kwargs
        assert kwargs["source_id"] == item.source_id
        assert kwargs["source_type"] == SourceType.FDA_RECALL.value

    def test_partial_kafka_failure_leaves_items_unmarked(self):
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
