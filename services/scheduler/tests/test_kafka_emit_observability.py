"""Regression tests for #1147 — Kafka emit failures must be observable.

Before the fix, `_process_new_items` caught Kafka errors with
``except (ConnectionError, ...) as e: logger.error(...)`` and moved on.
Partial per-item failures (``success=8, failures=2``) were logged at
INFO with no alerting. Those 2 lost items could be Class I recalls no
one ever sees.

The fix keeps the emit-then-ack invariant (#1136) and adds:
  - Prometheus counter ``scheduler_kafka_emit_failures_total{source_type, failure_mode}``
  - Counter is bumped on both ``hard_exception`` and ``partial_batch``
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.models import EnforcementItem, EnforcementSeverity, SourceType


def _item(source_id: str = "fda_recall:x") -> EnforcementItem:
    return EnforcementItem(
        source_type=SourceType.FDA_RECALL,
        source_id=source_id,
        title="Test",
        url="https://x",
        published_date=datetime(2026, 4, 17, tzinfo=timezone.utc),
        severity=EnforcementSeverity.HIGH,
    )


def _svc():
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


class TestKafkaEmitFailureMetric:
    def test_hard_exception_bumps_counter(self):
        import main as scheduler_main

        svc = _svc()
        svc.kafka_producer.emit_batch.side_effect = ConnectionError("broker down")
        svc.kafka_producer.emit_fsma_batch.return_value = (0, 0)
        svc.notifier.notify.return_value = []

        with patch.object(
            scheduler_main.metrics, "record_kafka_emit_failure"
        ) as record:
            svc._process_new_items([_item("a"), _item("b")], SourceType.FDA_RECALL)

        record.assert_called()
        kwargs = record.call_args.kwargs
        assert kwargs["failure_mode"] == "hard_exception"
        # Two items lost when the batch raised → count should reflect that.
        assert kwargs["count"] == 2

    def test_partial_failure_bumps_counter_with_failure_count(self):
        import main as scheduler_main

        svc = _svc()
        svc.kafka_producer.emit_batch.return_value = (8, 2)
        svc.kafka_producer.emit_fsma_batch.return_value = (0, 0)
        svc.notifier.notify.return_value = []

        with patch.object(
            scheduler_main.metrics, "record_kafka_emit_failure"
        ) as record:
            items = [_item(f"r-{i}") for i in range(10)]
            svc._process_new_items(items, SourceType.FDA_RECALL)

        record.assert_called()
        kwargs = record.call_args.kwargs
        assert kwargs["failure_mode"] == "partial_batch"
        assert kwargs["count"] == 2

    def test_successful_emit_does_not_bump_counter(self):
        import main as scheduler_main

        svc = _svc()
        svc.kafka_producer.emit_batch.return_value = (2, 0)
        svc.kafka_producer.emit_fsma_batch.return_value = (2, 0)
        svc.notifier.notify.return_value = []

        with patch.object(
            scheduler_main.metrics, "record_kafka_emit_failure"
        ) as record:
            svc._process_new_items([_item("a"), _item("b")], SourceType.FDA_RECALL)

        assert record.call_count == 0


class TestKafkaProducerRetryConfig:
    """Producer must be configured with aggressive retries (#1147)."""

    def test_producer_config_has_high_retries(self):
        from app.kafka_producer import KafkaEventProducer

        # Inspect the configured values on the instance rather than open a
        # real connection.
        prod = KafkaEventProducer()
        with patch("app.kafka_producer.KafkaProducerLib") as KP:
            prod._producer = None  # force rebuild
            prod._get_producer()

        call_kwargs = KP.call_args.kwargs
        assert call_kwargs["retries"] >= 10, (
            "#1147: producer retries default was 3 — transient 5xx dropped "
            "recalls; must be at least 10"
        )
        assert call_kwargs["acks"] == "all"
