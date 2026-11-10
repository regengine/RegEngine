"""#2711: kafka producer counts ASYNC delivery failures, not just enqueues.

Pre-fix, ``_send`` returned True on local enqueue and the batch emitters
acked on that — async delivery failures only surfaced in flush() logs.
Send futures now carry an errback; the batch emitters reconcile the
observed failures into (success, failures) after flush.

NOTE (#2969): the tests below drive a ``MagicMock`` whose ``send`` returns a
future the test itself supplies, so they stayed green for the whole period
in which ``KafkaProducerCompat.send()`` returned ``None`` and the errback was
never registered at all. They are kept as coverage of the batch
reconciliation arithmetic; the end-to-end guarantee is pinned by
``test_kafka_producer_delivery_handle_2969.py``, which drives the real
``KafkaProducerCompat`` against a fake confluent ``Producer``.
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


class TestSendRegistersErrback:
    def test_send_attaches_errback_to_future(self):
        producer = _producer_with_mock_lib()
        future = MagicMock()
        lib = MagicMock()
        lib.send.return_value = future
        producer._producer = lib
        producer._initialized = True
        producer._get_producer = lambda: lib

        assert producer._send(topic="t", key="k", value={"a": 1}) is True
        future.add_errback.assert_called_once()

        # Invoking the registered errback counts a delivery failure.
        errback = future.add_errback.call_args.args[0]
        errback(RuntimeError("broker rejected"))
        assert producer.take_delivery_failures() == 1
        # take() resets the counter.
        assert producer.take_delivery_failures() == 0


class TestBatchReconciliation:
    def test_emit_fsma_batch_reconciles_async_failures(self, monkeypatch):
        producer = _producer_with_mock_lib()
        monkeypatch.setattr(producer, "emit_fsma_event", lambda e: True)

        def _flush(timeout=30):
            # Delivery of one message fails asynchronously during flush.
            producer._note_delivery_failure("fsma.events.extracted", RuntimeError("timeout"))

        monkeypatch.setattr(producer, "flush", _flush)

        success, failures = producer.emit_fsma_batch([{"event_id": "e1"}, {"event_id": "e2"}])
        assert (success, failures) == (1, 1)

    def test_emit_fsma_batch_clean_flush_unchanged(self, monkeypatch):
        producer = _producer_with_mock_lib()
        monkeypatch.setattr(producer, "emit_fsma_event", lambda e: True)
        monkeypatch.setattr(producer, "flush", lambda timeout=30: None)

        assert producer.emit_fsma_batch([{"event_id": "e1"}]) == (1, 0)
