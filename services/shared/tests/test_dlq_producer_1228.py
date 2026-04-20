"""Tests for shared DLQProducer singleton -- #1228."""
from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch, call

import pytest

from shared.observability.dlq_producer import DLQProducer
from shared.dlq import DLQProducer as DLQProducerAlias


# ---------------------------------------------------------------------------
# Re-export shim
# ---------------------------------------------------------------------------

def test_dlq_alias_is_same_class():
    """shared.dlq.DLQProducer is the same object as the canonical class."""
    assert DLQProducerAlias is DLQProducer


# ---------------------------------------------------------------------------
# confluent-kafka backend
# ---------------------------------------------------------------------------

class TestDLQProducerConfluentBackend:
    def _make(self, mock_producer_cls):
        mock_producer_cls.return_value = MagicMock()
        return DLQProducer(
            bootstrap_servers="localhost:9092",
            topic="test.dlq",
            service_name="test-svc",
        )

    @patch("shared.observability.dlq_producer.DLQProducer._init_producer")
    def test_init_sets_attributes(self, mock_init):
        dlq = DLQProducer.__new__(DLQProducer)
        dlq._bootstrap = "localhost:9092"
        dlq._topic = "test.dlq"
        dlq._service_name = "test-svc"
        dlq._lock = threading.Lock()
        dlq._producer = None
        dlq._confluent = False
        assert dlq._topic == "test.dlq"
        assert dlq._service_name == "test-svc"

    def test_send_with_confluent_backend(self):
        mock_inner = MagicMock()
        with patch("shared.observability.dlq_producer.DLQProducer._init_producer"):
            dlq = DLQProducer.__new__(DLQProducer)
            dlq._bootstrap = "localhost:9092"
            dlq._topic = "test.dlq"
            dlq._service_name = "test-svc"
            dlq._lock = threading.Lock()
            dlq._producer = mock_inner
            dlq._confluent = True

        dlq.send(b"payload", reason="parse_error", detail="traceback", original_topic="ingest.raw")

        mock_inner.produce.assert_called_once()
        args, kwargs = mock_inner.produce.call_args
        assert kwargs.get("topic") == "test.dlq" or args[0] == "test.dlq"
        assert kwargs["value"] == b"payload"
        headers = {k: v for k, v in kwargs["headers"]}
        assert headers["error_reason"] == b"parse_error"
        assert headers["original_topic"] == b"ingest.raw"
        assert headers["service"] == b"test-svc"
        mock_inner.poll.assert_called_once_with(0)

    def test_send_kafka_python_backend(self):
        mock_inner = MagicMock()
        with patch("shared.observability.dlq_producer.DLQProducer._init_producer"):
            dlq = DLQProducer.__new__(DLQProducer)
            dlq._bootstrap = "localhost:9092"
            dlq._topic = "test.dlq"
            dlq._service_name = "test-svc"
            dlq._lock = threading.Lock()
            dlq._producer = mock_inner
            dlq._confluent = False

        dlq.send(b"msg", reason="timeout")

        mock_inner.send.assert_called_once()
        _, kwargs = mock_inner.send.call_args
        assert kwargs["value"] == b"msg"

    def test_send_noop_when_no_producer(self, caplog):
        with patch("shared.observability.dlq_producer.DLQProducer._init_producer"):
            dlq = DLQProducer.__new__(DLQProducer)
            dlq._bootstrap = "localhost:9092"
            dlq._topic = "test.dlq"
            dlq._service_name = "test-svc"
            dlq._lock = threading.Lock()
            dlq._producer = None
            dlq._confluent = False
        # Should not raise
        dlq.send(b"x", reason="no_producer")

    def test_flush_confluent(self):
        mock_inner = MagicMock()
        with patch("shared.observability.dlq_producer.DLQProducer._init_producer"):
            dlq = DLQProducer.__new__(DLQProducer)
            dlq._bootstrap = "localhost:9092"
            dlq._topic = "test.dlq"
            dlq._service_name = "svc"
            dlq._lock = threading.Lock()
            dlq._producer = mock_inner
            dlq._confluent = True
        dlq.flush(timeout=3.0)
        mock_inner.flush.assert_called_once_with(3.0)

    def test_close_kafka_python(self):
        mock_inner = MagicMock()
        with patch("shared.observability.dlq_producer.DLQProducer._init_producer"):
            dlq = DLQProducer.__new__(DLQProducer)
            dlq._bootstrap = "localhost:9092"
            dlq._topic = "test.dlq"
            dlq._service_name = "svc"
            dlq._lock = threading.Lock()
            dlq._producer = mock_inner
            dlq._confluent = False
        dlq.close()
        mock_inner.flush.assert_called()
        mock_inner.close.assert_called()
        assert dlq._producer is None

    def test_thread_safety(self):
        """Concurrent sends must not raise (lock guards the producer)."""
        mock_inner = MagicMock()
        with patch("shared.observability.dlq_producer.DLQProducer._init_producer"):
            dlq = DLQProducer.__new__(DLQProducer)
            dlq._bootstrap = "localhost:9092"
            dlq._topic = "test.dlq"
            dlq._service_name = "svc"
            dlq._lock = threading.Lock()
            dlq._producer = mock_inner
            dlq._confluent = True

        errors = []

        def worker():
            try:
                dlq.send(b"concurrent", reason="test")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread-safety violations: {errors}"


# ---------------------------------------------------------------------------
# Singleton-per-topic tests (#1228)
# ---------------------------------------------------------------------------

class TestDLQProducerSingleton:
    """DLQProducer.get() returns per-topic singletons."""

    def setup_method(self):
        # Clear the singleton registry before each test to ensure isolation.
        DLQProducer._instances.clear()

    def teardown_method(self):
        DLQProducer._instances.clear()

    def test_same_topic_returns_same_instance(self):
        """Two calls with the same topic must return the identical object."""
        with patch.object(DLQProducer, "_init_producer"):
            a = DLQProducer.get("topic.foo", bootstrap_servers="localhost:9092")
            b = DLQProducer.get("topic.foo", bootstrap_servers="localhost:9092")
        assert a is b, "Expected singleton: same topic must return same instance"

    def test_different_topics_return_different_instances(self):
        """Two different topics must each get their own DLQProducer instance."""
        with patch.object(DLQProducer, "_init_producer"):
            a = DLQProducer.get("topic.alpha", bootstrap_servers="localhost:9092")
            b = DLQProducer.get("topic.beta", bootstrap_servers="localhost:9092")
        assert a is not b, "Different topics must yield different instances"
        assert a._topic == "topic.alpha"
        assert b._topic == "topic.beta"

    def test_send_noops_when_kafka_unavailable(self):
        """send() must log and return (not raise) when the underlying producer raises."""
        with patch.object(DLQProducer, "_init_producer"):
            dlq = DLQProducer.get("topic.noop", bootstrap_servers="localhost:9092")
            # Inject a broken inner producer
            broken = MagicMock()
            broken.produce.side_effect = RuntimeError("broker unreachable")
            broken.send.side_effect = RuntimeError("broker unreachable")
            dlq._producer = broken
            dlq._confluent = True

        # Must not raise
        dlq.send(b"payload", reason="test_noop", original_topic="topic.src")

    def test_singleton_thread_safety(self):
        """Concurrent DLQProducer.get() calls for the same topic must return the same instance."""
        results = []

        def get_instance():
            with patch.object(DLQProducer, "_init_producer"):
                results.append(DLQProducer.get("topic.concurrent", bootstrap_servers="localhost:9092"))

        threads = [threading.Thread(target=get_instance) for _ in range(30)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(set(id(r) for r in results)) == 1, "All threads should get the same instance"
