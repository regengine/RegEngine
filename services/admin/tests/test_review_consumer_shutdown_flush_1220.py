"""Regression tests for DLQ producer flush on shutdown (#1220).

The admin review consumer holds a lazily-initialized, module-global
``_dlq_producer``. librdkafka buffers ``send()`` calls asynchronously,
so calling ``close()`` without an explicit ``flush()`` can drop
in-flight dead-letter messages when SIGTERM fires. The same risk exists
if the main loop raises an unhandled exception. This suite asserts that
``_cleanup_dlq_producer`` flushes before close AND that the consumer
loop invokes ``_cleanup_dlq_producer`` via ``finally`` on every exit
path.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestCleanupDlqProducer:
    """Tests for _cleanup_dlq_producer shutdown semantics."""

    def test_flush_called_before_close(self):
        """flush() must run before close() so buffered DLQ msgs land."""
        from services.admin.app import review_consumer

        producer = MagicMock()
        call_order: list[str] = []
        producer.flush.side_effect = lambda **_: call_order.append("flush")
        producer.close.side_effect = lambda **_: call_order.append("close")

        with patch.object(review_consumer, "_dlq_producer", producer):
            review_consumer._cleanup_dlq_producer()

        assert call_order == ["flush", "close"], (
            f"Expected flush before close; got {call_order}"
        )
        # Flush timeout must be a positive drain window -- matches the
        # graph consumer pattern (#1220).
        flush_kwargs = producer.flush.call_args.kwargs
        assert flush_kwargs.get("timeout", 0) >= 1.0
        producer.flush.assert_called_once()
        producer.close.assert_called_once()

    def test_close_still_runs_if_flush_raises(self):
        """A broker outage during flush must not block close()."""
        from services.admin.app import review_consumer

        producer = MagicMock()
        producer.flush.side_effect = RuntimeError("broker unreachable")

        with patch.object(review_consumer, "_dlq_producer", producer):
            # Must not raise -- shutdown path is best-effort.
            review_consumer._cleanup_dlq_producer()

        producer.flush.assert_called_once()
        producer.close.assert_called_once()

    def test_no_op_when_producer_never_initialized(self):
        """Shutting down before the first DLQ send is a clean no-op."""
        from services.admin.app import review_consumer

        with patch.object(review_consumer, "_dlq_producer", None):
            # Should not raise.
            review_consumer._cleanup_dlq_producer()


class TestRunConsumerShutdownFlush:
    """End-to-end: run_consumer must call _cleanup_dlq_producer in finally."""

    def test_shutdown_invokes_cleanup(self):
        """Normal shutdown (shutdown_event set) runs cleanup."""
        from services.admin.app import review_consumer

        mock_consumer = MagicMock()
        mock_consumer.poll.return_value = {}
        mock_settings = MagicMock()
        mock_settings.kafka_bootstrap = "redpanda:9092"
        mock_settings.consumer_group_id = "admin-review"

        review_consumer._shutdown_event.clear()
        review_consumer._shutdown_event.set()

        with patch.object(review_consumer, "_ensure_topic"), \
             patch.object(review_consumer, "KafkaConsumer", return_value=mock_consumer), \
             patch.object(review_consumer, "get_settings", return_value=mock_settings), \
             patch.object(review_consumer, "get_hallucination_tracker"), \
             patch.object(review_consumer, "_cleanup_dlq_producer") as mock_cleanup:
            try:
                review_consumer.run_consumer()
            finally:
                review_consumer._shutdown_event.clear()

        mock_cleanup.assert_called_once()
        mock_consumer.close.assert_called_once()

    def test_cleanup_runs_even_if_loop_raises(self):
        """Unhandled exception in loop must not skip DLQ flush (#1220)."""
        from services.admin.app import review_consumer

        mock_consumer = MagicMock()
        mock_consumer.poll.side_effect = RuntimeError("kafka down")
        mock_settings = MagicMock()
        mock_settings.kafka_bootstrap = "redpanda:9092"
        mock_settings.consumer_group_id = "admin-review"

        review_consumer._shutdown_event.clear()

        with patch.object(review_consumer, "_ensure_topic"), \
             patch.object(review_consumer, "KafkaConsumer", return_value=mock_consumer), \
             patch.object(review_consumer, "get_settings", return_value=mock_settings), \
             patch.object(review_consumer, "get_hallucination_tracker"), \
             patch.object(review_consumer, "_cleanup_dlq_producer") as mock_cleanup:
            try:
                with pytest.raises(RuntimeError, match="kafka down"):
                    review_consumer.run_consumer()
            finally:
                review_consumer._shutdown_event.set()
                review_consumer._shutdown_event.clear()

        # This is the core of the fix: the DLQ producer MUST be
        # flushed/closed via finally even when the loop blows up.
        mock_cleanup.assert_called_once()
