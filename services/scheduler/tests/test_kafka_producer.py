"""Tests for KafkaEventProducer.

Covers:
- Single event emission
- High-priority alert filtering
- Batch emission with success/failure counts
- FSMA event emission
- Error handling when Kafka is unavailable
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, PropertyMock

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")

_SERVICES_DIR = Path(__file__).resolve().parent.parent.parent
if str(_SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICES_DIR))

from shared.paths import ensure_shared_importable
ensure_shared_importable()

import pytest
from unittest.mock import ANY

from app.models import EnforcementItem, EnforcementSeverity, SourceType


def _make_item(severity=EnforcementSeverity.MEDIUM, source_type=SourceType.FDA_RECALL, **kw) -> EnforcementItem:
    return EnforcementItem(
        source_type=source_type,
        source_id=kw.get("source_id", "test-recall-001"),
        title=kw.get("title", "Test Recall"),
        url="https://fda.gov/recalls/test",
        published_date=datetime(2026, 3, 15, tzinfo=timezone.utc),
        severity=severity,
    )


@pytest.fixture
def mock_kafka():
    """Patch KafkaProducerLib to avoid real Kafka connections."""
    with patch("app.kafka_producer.KafkaProducerLib") as MockKafka:
        mock_instance = MagicMock()
        mock_instance.send.return_value = MagicMock()  # Future
        mock_instance.bootstrap_connected.return_value = True
        MockKafka.return_value = mock_instance
        yield mock_instance, MockKafka


@pytest.fixture
def producer(mock_kafka):
    """Create a KafkaEventProducer with mocked Kafka."""
    from app.kafka_producer import KafkaEventProducer
    p = KafkaEventProducer(bootstrap_servers="localhost:9092")
    return p


# ─── emit_enforcement_change ─────────────────────────────────────────────


class TestEmitEnforcementChange:
    def test_sends_to_enforcement_topic(self, producer, mock_kafka):
        mock_instance, _ = mock_kafka
        item = _make_item()
        result = producer.emit_enforcement_change(item)
        assert result is True
        mock_instance.send.assert_called_once()
        call_args = mock_instance.send.call_args
        # send(topic, key=..., value=...) — topic is positional
        topic = call_args[0][0] if call_args[0] else call_args[1].get("topic")
        assert topic == producer.topic_enforcement

    def test_uses_source_id_as_key(self, producer, mock_kafka):
        mock_instance, _ = mock_kafka
        item = _make_item(source_id="recall-xyz")
        producer.emit_enforcement_change(item)
        call_args = mock_instance.send.call_args
        key = call_args[1].get("key") if "key" in (call_args[1] or {}) else call_args[0][1] if len(call_args[0]) > 1 else None
        assert key == "recall-xyz"

    def test_returns_false_on_kafka_error(self, producer, mock_kafka):
        mock_instance, _ = mock_kafka
        from shared.kafka_compat import KafkaError
        mock_instance.send.side_effect = KafkaError("Broker down")
        result = producer.emit_enforcement_change(_make_item())
        assert result is False


# ─── emit_high_priority_alert ────────────────────────────────────────────


class TestEmitHighPriorityAlert:
    def test_sends_to_alerts_topic(self, producer, mock_kafka):
        mock_instance, _ = mock_kafka
        item = _make_item(severity=EnforcementSeverity.CRITICAL)
        result = producer.emit_high_priority_alert(item)
        assert result is True
        call_args = mock_instance.send.call_args
        topic = call_args[1].get("topic") or call_args[0][0]
        assert topic == producer.topic_alerts

    def test_event_type_is_high_priority(self, producer, mock_kafka):
        mock_instance, _ = mock_kafka
        item = _make_item(severity=EnforcementSeverity.CRITICAL)
        producer.emit_high_priority_alert(item)
        call_args = mock_instance.send.call_args
        value = call_args[1].get("value") or call_args[0][2]
        assert value["event_type"] == "alert.high_priority"


# ─── emit_batch ──────────────────────────────────────────────────────────


class TestEmitBatch:
    def test_returns_success_failure_counts(self, producer, mock_kafka):
        items = [_make_item(source_id=f"r-{i}") for i in range(3)]
        success, failures = producer.emit_batch(items)
        assert success == 3
        assert failures == 0

    def test_counts_failures(self, producer, mock_kafka):
        mock_instance, _ = mock_kafka
        # Fail on second call
        mock_instance.send.side_effect = [
            MagicMock(),  # success
            Exception("fail"),  # failure
            MagicMock(),  # success
        ]
        items = [_make_item(source_id=f"r-{i}") for i in range(3)]
        success, failures = producer.emit_batch(items)
        assert failures >= 1

    def test_critical_items_also_emit_alert(self, producer, mock_kafka):
        mock_instance, _ = mock_kafka
        items = [_make_item(severity=EnforcementSeverity.CRITICAL)]
        producer.emit_batch(items)
        # Should have calls to both enforcement and alerts topics
        assert mock_instance.send.call_count >= 2

    def test_medium_items_skip_alert(self, producer, mock_kafka):
        mock_instance, _ = mock_kafka
        items = [_make_item(severity=EnforcementSeverity.MEDIUM)]
        producer.emit_batch(items)
        # Only enforcement topic, no alert
        assert mock_instance.send.call_count == 1

    def test_flushes_after_batch(self, producer, mock_kafka):
        mock_instance, _ = mock_kafka
        producer.emit_batch([_make_item()])
        mock_instance.flush.assert_called_once()


# ─── emit_fsma_event ─────────────────────────────────────────────────────


class TestEmitFSMAEvent:
    def test_sends_fsma_event(self, producer, mock_kafka):
        mock_instance, _ = mock_kafka
        fsma = {"event_id": "fsma-001", "event_type": "FSMA_RECALL_ALERT"}
        result = producer.emit_fsma_event(fsma)
        assert result is True
        call_args = mock_instance.send.call_args
        topic = call_args[1].get("topic") or call_args[0][0]
        assert topic == producer.topic_fsma

    def test_uses_event_id_as_key(self, producer, mock_kafka):
        mock_instance, _ = mock_kafka
        fsma = {"event_id": "fsma-001"}
        producer.emit_fsma_event(fsma)
        call_args = mock_instance.send.call_args
        key = call_args[1].get("key") or call_args[0][1]
        assert key == "fsma-001"

    def test_missing_event_id_uses_unknown(self, producer, mock_kafka):
        mock_instance, _ = mock_kafka
        fsma = {"event_type": "FSMA_RECALL_ALERT"}
        producer.emit_fsma_event(fsma)
        call_args = mock_instance.send.call_args
        key = call_args[1].get("key") or call_args[0][1]
        assert key == "unknown"


# ─── emit_fsma_batch ─────────────────────────────────────────────────────


class TestEmitFSMABatch:
    def test_batch_returns_counts(self, producer, mock_kafka):
        events = [{"event_id": f"fsma-{i}"} for i in range(3)]
        success, failures = producer.emit_fsma_batch(events)
        assert success == 3
        assert failures == 0

    def test_batch_flushes(self, producer, mock_kafka):
        mock_instance, _ = mock_kafka
        producer.emit_fsma_batch([{"event_id": "x"}])
        mock_instance.flush.assert_called()


# ─── Health check ────────────────────────────────────────────────────────


class TestHealthCheck:
    def test_healthy_when_connected(self, producer, mock_kafka):
        assert producer.is_healthy() is True

    def test_unhealthy_when_not_connected(self, producer, mock_kafka):
        mock_instance, _ = mock_kafka
        mock_instance.bootstrap_connected.return_value = False
        assert producer.is_healthy() is False

    def test_unhealthy_on_exception(self, producer, mock_kafka):
        mock_instance, _ = mock_kafka
        mock_instance.bootstrap_connected.side_effect = Exception("connection lost")
        assert producer.is_healthy() is False


# ─── Close / Flush ───────────────────────────────────────────────────────


class TestLifecycle:
    def test_close_flushes_and_closes(self, producer, mock_kafka):
        mock_instance, _ = mock_kafka
        # Force producer init
        producer._get_producer()
        producer.close()
        mock_instance.flush.assert_called()
        mock_instance.close.assert_called()
        assert producer._producer is None

    def test_flush_no_op_when_not_initialized(self, producer, mock_kafka):
        producer._producer = None
        producer.flush()  # Should not raise
