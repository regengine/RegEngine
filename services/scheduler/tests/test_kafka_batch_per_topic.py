"""Per-topic delivery reconciliation in ``KafkaEventProducer.emit_batch``.

``emit_batch`` enqueues enforcement sends AND high-priority alert sends,
then performs a single shared ``flush()``. Async delivery failures that
surface during that flush must be reconciled per topic: an alerts-topic
failure must not move the enforcement (success, failures) counts that
gate the seen-ack in ``services/scheduler/service.py``.

Pre-fix, ``emit_batch`` drained one global counter and subtracted every
failure from the enforcement success count, so a failing alert send
withheld the ack for enforcement items that delivered fine (forcing a
duplicate re-emit next tick) while the alert failure itself stayed
invisible as an alert problem.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.scheduler.app.kafka_producer import KafkaEventProducer


def _producer_with_mock_lib():
    with patch("services.scheduler.app.kafka_producer.get_settings") as settings:
        s = MagicMock()
        s.kafka_bootstrap_servers = "localhost:9092"
        s.kafka_topic_enforcement = "enforcement.changes"
        s.kafka_topic_alerts = "alerts"
        s.kafka_topic_fsma = "fsma.events.extracted"
        settings.return_value = s
        producer = KafkaEventProducer()
    return producer


def _critical_item(source_id="r-1"):
    item = MagicMock()
    item.source_id = source_id
    item.severity.value = "critical"
    return item


def _batch_producer(monkeypatch, flush_effect):
    """Producer with enqueue stubbed out and flush running ``flush_effect``."""
    producer = _producer_with_mock_lib()
    monkeypatch.setattr(producer, "emit_enforcement_change", lambda item: True)
    monkeypatch.setattr(producer, "emit_high_priority_alert", lambda item: True)
    monkeypatch.setattr(producer, "flush", flush_effect)
    return producer


class TestAlertFailuresDoNotMoveEnforcementCounts:
    def test_alert_delivery_failure_leaves_enforcement_counts_whole(self, monkeypatch):
        def _flush(timeout=30):
            # Only the alerts-topic send fails during the shared flush.
            producer._note_delivery_failure(producer.topic_alerts, RuntimeError("alert broker rejected"))

        producer = _batch_producer(monkeypatch, _flush)
        items = [_critical_item("r-1"), _critical_item("r-2")]

        success, failures = producer.emit_batch(items)

        assert (success, failures) == (2, 0)
        # The alert failure was consumed by this batch, not left behind.
        assert producer.take_delivery_failures() == 0

    def test_enforcement_delivery_failure_still_counts(self, monkeypatch):
        def _flush(timeout=30):
            producer._note_delivery_failure(producer.topic_enforcement, RuntimeError("broker rejected"))

        producer = _batch_producer(monkeypatch, _flush)
        items = [_critical_item("r-1"), _critical_item("r-2")]

        success, failures = producer.emit_batch(items)

        assert (success, failures) == (1, 1)

    def test_counts_are_scoped_to_each_topic(self):
        producer = _producer_with_mock_lib()
        producer._note_delivery_failure("enforcement.changes", RuntimeError("x"))
        producer._note_delivery_failure("enforcement.changes", RuntimeError("y"))
        producer._note_delivery_failure("alerts", RuntimeError("z"))

        assert producer.take_delivery_failures("enforcement.changes") == 2
        assert producer.take_delivery_failures("alerts") == 1
        assert producer.take_delivery_failures() == 0
