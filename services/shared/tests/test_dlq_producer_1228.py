"""Tests for shared DLQ producer singleton -- #1228.

Verifies:
1. DLQProducer.send() routes through the underlying Kafka backend.
2. get_dlq_producer() returns the same instance on repeated calls (singleton).
3. All three call-sites (graph/consumer, graph/consumers/fsma_consumer,
   admin/review_consumer) import from shared.observability.dlq_producer.
4. reset_dlq_producer() clears the registry so tests remain isolated.
"""

from __future__ import annotations

import importlib
import json
import threading
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_confluent_producer() -> MagicMock:
    p = MagicMock()
    p.produce = MagicMock()
    p.poll = MagicMock()
    p.flush = MagicMock()
    return p


def _make_mock_kafka_producer() -> MagicMock:
    p = MagicMock()
    p.send = MagicMock()
    p.flush = MagicMock()
    p.close = MagicMock()
    return p


# ---------------------------------------------------------------------------
# Unit tests for DLQProducer
# ---------------------------------------------------------------------------

class TestDLQProducerConfluentBackend:
    """DLQProducer backed by confluent-kafka."""

    def _make_producer(self, mock_confluent: MagicMock) -> "DLQProducer":
        from shared.observability.dlq_producer import DLQProducer
        return DLQProducer(
            bootstrap_servers="kafka:9092",
            topic="test.dlq",
            service_name="test-svc",
        )

    def test_send_calls_produce(self) -> None:
        mock_p = _make_mock_confluent_producer()
        with patch.dict("sys.modules", {"confluent_kafka": MagicMock(Producer=MagicMock(return_value=mock_p))}):
            from shared.observability import dlq_producer as mod
            import importlib
            importlib.reload(mod)
            producer = mod.DLQProducer(
                bootstrap_servers="kafka:9092",
                topic="test.dlq",
                service_name="test-svc",
            )
            producer.send(b"raw-bytes", reason="test_reason", detail="some detail")

        mock_p.produce.assert_called_once()
        args, kwargs = mock_p.produce.call_args
        assert args[0] == "test.dlq"
        assert kwargs["value"] == b"raw-bytes"
        # headers must include error_reason
        header_keys = [k for k, _ in kwargs.get("headers", [])]
        assert "error_reason" in header_keys
        assert "service" in header_keys

    def test_flush_delegates(self) -> None:
        mock_p = _make_mock_confluent_producer()
        with patch.dict("sys.modules", {"confluent_kafka": MagicMock(Producer=MagicMock(return_value=mock_p))}):
            from shared.observability import dlq_producer as mod
            importlib.reload(mod)
            producer = mod.DLQProducer("kafka:9092", "test.dlq")
            producer.flush(timeout=3.0)
        mock_p.flush.assert_called_once_with(3.0)

    def test_send_noop_when_not_initialized(self, caplog: Any) -> None:
        """If producer fails to initialize, send() logs and returns gracefully."""
        import logging
        # Block both confluent-kafka and kafka-python
        with patch.dict("sys.modules", {"confluent_kafka": None, "kafka": None}):
            from shared.observability import dlq_producer as mod
            importlib.reload(mod)
            with caplog.at_level(logging.ERROR):
                producer = mod.DLQProducer("kafka:9092", "test.dlq")
                producer.send(b"data", reason="no_backend")
        # Should not raise; producer._producer is None


class TestDLQProducerKafkaPythonBackend:
    """DLQProducer backed by kafka-python (confluent_kafka absent)."""

    def test_send_calls_send(self) -> None:
        mock_p = _make_mock_kafka_producer()
        confluent_absent = MagicMock(side_effect=ImportError)

        with patch.dict(
            "sys.modules",
            {"confluent_kafka": None, "kafka": MagicMock(KafkaProducer=MagicMock(return_value=mock_p))},
        ):
            from shared.observability import dlq_producer as mod
            importlib.reload(mod)
            producer = mod.DLQProducer("kafka:9092", "kp.dlq", "kp-svc")
            producer.send(b"payload", reason="kp_reason")

        mock_p.send.assert_called_once()
        _, kwargs = mock_p.send.call_args
        assert kwargs["value"] == b"payload"


# ---------------------------------------------------------------------------
# Singleton registry tests
# ---------------------------------------------------------------------------

class TestGetDlqProducerSingleton:
    """get_dlq_producer() returns the same instance on repeated calls."""

    def setup_method(self) -> None:
        from shared.observability import dlq_producer as mod
        mod._instances.clear()

    def teardown_method(self) -> None:
        from shared.observability import dlq_producer as mod
        mod._instances.clear()

    def test_same_instance_returned(self) -> None:
        mock_p = _make_mock_confluent_producer()
        with patch.dict("sys.modules", {"confluent_kafka": MagicMock(Producer=MagicMock(return_value=mock_p))}):
            from shared.observability import dlq_producer as mod
            importlib.reload(mod)
            a = mod.get_dlq_producer(topic="svc.dlq", bootstrap_servers="kafka:9092")
            b = mod.get_dlq_producer(topic="svc.dlq", bootstrap_servers="kafka:9092")
        assert a is b

    def test_different_topics_different_instances(self) -> None:
        mock_p = _make_mock_confluent_producer()
        with patch.dict("sys.modules", {"confluent_kafka": MagicMock(Producer=MagicMock(return_value=mock_p))}):
            from shared.observability import dlq_producer as mod
            importlib.reload(mod)
            a = mod.get_dlq_producer(topic="svc1.dlq", bootstrap_servers="kafka:9092")
            b = mod.get_dlq_producer(topic="svc2.dlq", bootstrap_servers="kafka:9092")
        assert a is not b

    def test_reset_removes_instance(self) -> None:
        mock_p = _make_mock_confluent_producer()
        with patch.dict("sys.modules", {"confluent_kafka": MagicMock(Producer=MagicMock(return_value=mock_p))}):
            from shared.observability import dlq_producer as mod
            importlib.reload(mod)
            a = mod.get_dlq_producer(topic="reset.dlq", bootstrap_servers="kafka:9092")
            mod.reset_dlq_producer(topic="reset.dlq")
            b = mod.get_dlq_producer(topic="reset.dlq", bootstrap_servers="kafka:9092")
        assert a is not b

    def test_thread_safety(self) -> None:
        """Concurrent calls must return the same instance."""
        mock_p = _make_mock_confluent_producer()
        results: list = []

        with patch.dict("sys.modules", {"confluent_kafka": MagicMock(Producer=MagicMock(return_value=mock_p))}):
            from shared.observability import dlq_producer as mod
            importlib.reload(mod)

            def _get() -> None:
                results.append(mod.get_dlq_producer(topic="threaded.dlq", bootstrap_servers="k:9092"))

            threads = [threading.Thread(target=_get) for _ in range(20)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert len(set(id(r) for r in results)) == 1, "All threads must get the same instance"


# ---------------------------------------------------------------------------
# Call-site import verification  (#1228 acceptance criteria)
# ---------------------------------------------------------------------------

class TestCallSitesUseSharedModule:
    """Assert that each service file imports DLQProducer from shared, not a local copy."""

    def _grep_file(self, path: str, pattern: str) -> bool:
        import re
        with open(path) as f:
            return bool(re.search(pattern, f.read()))

    def test_graph_consumer_imports_shared(self) -> None:
        path = "services/graph/app/consumer.py"
        import os
        full = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", path
        )
        assert self._grep_file(full, r"from shared\.observability\.dlq_producer import"), (
            f"{path} must import DLQProducer from shared.observability.dlq_producer"
        )

    def test_graph_consumer_no_local_singleton(self) -> None:
        path = "services/graph/app/consumer.py"
        import os
        full = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", path
        )
        assert not self._grep_file(full, r"confluent_kafka.*Producer"), (
            f"{path} must not import Producer from confluent_kafka directly"
        )

    def test_fsma_consumer_imports_shared(self) -> None:
        path = "services/graph/app/consumers/fsma_consumer.py"
        import os
        full = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", path
        )
        assert self._grep_file(full, r"from shared\.observability\.dlq_producer import"), (
            f"{path} must import DLQProducer from shared.observability.dlq_producer"
        )

    def test_review_consumer_imports_shared(self) -> None:
        path = "services/admin/app/review_consumer.py"
        import os
        full = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", path
        )
        assert self._grep_file(full, r"from shared\.observability\.dlq_producer import"), (
            f"{path} must import DLQProducer from shared.observability.dlq_producer"
        )

    def test_review_consumer_no_local_kafka_producer(self) -> None:
        path = "services/admin/app/review_consumer.py"
        import os
        full = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", path
        )
        assert not self._grep_file(full, r"KafkaProducer"), (
            f"{path} must not use KafkaProducer directly"
        )
