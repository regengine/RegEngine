"""Regression tests for DLQ producer flush on shutdown (#1220).

The NLP consumer shares a single KafkaProducer for both routing events
and DLQ writes. librdkafka buffers ``send()`` calls asynchronously, so
``producer.close()`` alone can drop in-flight DLQ messages when SIGTERM
fires mid-batch. This suite asserts that ``producer.flush()`` is called
before ``close()`` on every shutdown path, including when the consumer
loop raises an unhandled exception.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure the repo root 'shared' package is importable (mirrors test_consumer.py)
_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))


class TestGracefulProducerShutdown:
    """Tests for the _graceful_producer_shutdown helper."""

    def test_flush_called_before_close(self):
        """flush() must run before close() so buffered DLQ msgs land."""
        from services.nlp.app.consumer import _graceful_producer_shutdown

        producer = MagicMock()
        call_order: list[str] = []
        producer.flush.side_effect = lambda **_: call_order.append("flush")
        producer.close.side_effect = lambda **_: call_order.append("close")

        _graceful_producer_shutdown(producer)

        assert call_order == ["flush", "close"], (
            f"Expected flush before close; got {call_order}"
        )
        producer.flush.assert_called_once()
        # flush timeout must be a positive number so drain has time to
        # finish; 5s matches the graph consumer pattern (#1220).
        flush_kwargs = producer.flush.call_args.kwargs
        assert flush_kwargs.get("timeout", 0) >= 1.0

    def test_close_still_runs_if_flush_raises(self):
        """A broker outage during flush must not block close()."""
        from services.nlp.app.consumer import _graceful_producer_shutdown

        producer = MagicMock()
        producer.flush.side_effect = RuntimeError("broker unreachable")

        # Must not raise -- shutdown path is best-effort.
        _graceful_producer_shutdown(producer)

        producer.flush.assert_called_once()
        producer.close.assert_called_once()


class TestRunConsumerShutdownFlush:
    """End-to-end: run_consumer must flush the producer in finally."""

    def test_shutdown_flushes_producer(self):
        """Normal shutdown (shutdown_event set) flushes before close."""
        from services.nlp.app import consumer as consumer_module

        mock_consumer = MagicMock()
        # Empty poll → loop exits on shutdown_event check.
        mock_consumer.poll.return_value = {}
        mock_producer = MagicMock()

        call_order: list[str] = []
        mock_producer.flush.side_effect = lambda **_: call_order.append("flush")
        mock_producer.close.side_effect = lambda **_: call_order.append("close")

        # Reset shutdown event and pre-set it so the loop exits on entry.
        consumer_module._shutdown_event.clear()
        consumer_module._shutdown_event.set()

        with patch.object(consumer_module, "_ensure_topic"), \
             patch.object(consumer_module, "KafkaConsumer", return_value=mock_consumer), \
             patch.object(consumer_module, "KafkaProducer", return_value=mock_producer):
            try:
                consumer_module.run_consumer()
            finally:
                consumer_module._shutdown_event.clear()

        mock_producer.flush.assert_called_once()
        mock_producer.close.assert_called_once()
        mock_consumer.close.assert_called_once()
        assert call_order.index("flush") < call_order.index("close")

    def test_flush_runs_even_if_loop_raises(self):
        """Unhandled exception in loop must not skip flush (#1220)."""
        from services.nlp.app import consumer as consumer_module

        mock_consumer = MagicMock()
        mock_consumer.poll.side_effect = RuntimeError("kafka down")
        mock_producer = MagicMock()

        consumer_module._shutdown_event.clear()

        with patch.object(consumer_module, "_ensure_topic"), \
             patch.object(consumer_module, "KafkaConsumer", return_value=mock_consumer), \
             patch.object(consumer_module, "KafkaProducer", return_value=mock_producer):
            try:
                with pytest.raises(RuntimeError, match="kafka down"):
                    consumer_module.run_consumer()
            finally:
                consumer_module._shutdown_event.set()
                consumer_module._shutdown_event.clear()

        # The whole point of the fix: flush must run via finally even
        # when the loop blows up.
        mock_producer.flush.assert_called_once()
        mock_producer.close.assert_called_once()
