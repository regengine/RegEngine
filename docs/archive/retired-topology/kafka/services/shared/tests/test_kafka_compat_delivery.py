"""Delivery handles, admin mapping and consumer edges.

The compat layer's core send/poll/commit paths are covered elsewhere
(``test_kafka_compat_1884``, ``test_kafka_consumer_offset_commit_2971``,
``test_kafka_producer_config_2977``). This file pins the remaining
contracts: late-registered delivery callbacks, error mapping that keeps
legacy ``except KafkaError`` handlers working, admin topic-creation
mapping, and the consumer's no-record / error-message paths.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from shared import kafka_compat as kc


class _FakeProducer:
    instances: list["_FakeProducer"] = []

    def __init__(self, config):
        self.config = config
        self.produce_calls: list = []
        _FakeProducer.instances.append(self)

    def produce(self, topic, **kwargs):
        self.produce_calls.append((topic, kwargs))

    def poll(self, timeout):
        return 0

    def flush(self, timeout=None):
        return 0

    def list_topics(self, timeout=None):
        return SimpleNamespace(brokers={1: object()})


@pytest.fixture
def fake_producer(monkeypatch):
    _FakeProducer.instances.clear()
    monkeypatch.setattr(kc, "Producer", _FakeProducer)
    return _FakeProducer


class TestDeliveryHandle:
    def test_errback_registered_before_failure_is_called(self):
        handle = kc.DeliveryHandle("topic")
        seen: list = []
        handle.add_errback(seen.append)
        handle._on_delivery("boom", None)
        assert len(seen) == 1
        assert isinstance(seen[0], kc.KafkaError)

    def test_errback_registered_after_failure_fires_immediately(self):
        handle = kc.DeliveryHandle("topic")
        handle._on_delivery("boom", None)
        seen: list = []
        result = handle.add_errback(seen.append)
        assert result is handle
        assert len(seen) == 1

    def test_callback_registered_before_success_receives_message(self):
        handle = kc.DeliveryHandle("topic")
        seen: list = []
        handle.add_callback(seen.append)
        handle._on_delivery(None, "msg")
        assert seen == ["msg"]

    def test_callback_registered_after_success_receives_message(self):
        # #3296: a late callback replays the delivery message, matching what
        # an early callback receives (it used to get the topic name).
        handle = kc.DeliveryHandle("topic")
        handle._on_delivery(None, "msg")
        seen: list = []
        handle.add_callback(seen.append)
        assert seen == ["msg"]

class TestProducerErrorMapping:
    def test_buffer_error_becomes_kafka_error(self, fake_producer, monkeypatch):
        def _full(topic, **kwargs):
            raise BufferError("queue full")

        producer = kc.KafkaProducerCompat(bootstrap_servers="broker:9092")
        fake = _FakeProducer.instances[0]
        monkeypatch.setattr(fake, "produce", _full)
        monkeypatch.setattr(fake, "poll", lambda timeout: 0)
        with pytest.raises(kc.KafkaError):
            producer.send("topic", value="v")

    def test_kafka_exception_becomes_kafka_error(self, fake_producer, monkeypatch):
        producer = kc.KafkaProducerCompat(bootstrap_servers="broker:9092")
        fake = _FakeProducer.instances[0]

        def _down(topic, **kwargs):
            raise kc.KafkaException("broker down")

        monkeypatch.setattr(fake, "produce", _down)
        monkeypatch.setattr(fake, "poll", lambda timeout: 0)
        with pytest.raises(kc.KafkaError):
            producer.send("topic", value="v")

class _FakeFuture:
    def __init__(self, exc=None):
        self._exc = exc

    def result(self):
        if self._exc is not None:
            raise self._exc


class _FakeAdmin:
    instances: list["_FakeAdmin"] = []
    futures: dict = {}

    def __init__(self, config):
        self.config = config
        _FakeAdmin.instances.append(self)

    def create_topics(self, topics):
        return _FakeAdmin.futures


def _already_exists_exc():
    return Exception(
        SimpleNamespace(code=lambda: kc.ConfluentKafkaError.TOPIC_ALREADY_EXISTS)
    )


class TestAdminClient:
    def test_create_topics_success(self, monkeypatch):
        _FakeAdmin.instances.clear()
        _FakeAdmin.futures = {"t": _FakeFuture()}
        monkeypatch.setattr(kc, "AdminClient", _FakeAdmin)
        admin = kc.KafkaAdminClientCompat(bootstrap_servers=["a:9092"])
        assert _FakeAdmin.instances[0].config["bootstrap.servers"] == "a:9092"
        admin.create_topics(["t"])
        assert admin.close() is None

    def test_topic_already_exists_maps(self, monkeypatch):
        _FakeAdmin.instances.clear()
        _FakeAdmin.futures = {"t": _FakeFuture(exc=_already_exists_exc())}
        monkeypatch.setattr(kc, "AdminClient", _FakeAdmin)
        admin = kc.KafkaAdminClientCompat(bootstrap_servers="b:9092")
        with pytest.raises(kc.TopicAlreadyExistsError):
            admin.create_topics(["t"])

    def test_other_admin_error_maps_to_kafka_error(self, monkeypatch):
        _FakeAdmin.instances.clear()
        _FakeAdmin.futures = {"t": _FakeFuture(exc=RuntimeError("denied"))}
        monkeypatch.setattr(kc, "AdminClient", _FakeAdmin)
        admin = kc.KafkaAdminClientCompat(bootstrap_servers="b:9092")
        with pytest.raises(kc.KafkaError):
            admin.create_topics(["t"])


class _FakeMessage:
    def __init__(self, offset=7, err=None):
        self._offset = offset
        self._err = err

    def error(self):
        return self._err

    def topic(self):
        return "t"

    def partition(self):
        return 0

    def offset(self):
        return self._offset

    def key(self):
        return None

    def value(self):
        return b"v"

    def headers(self):
        return []


class _FakeConsumer:
    def __init__(self, config, messages=None):
        self.config = config
        self.messages = list(messages or [])
        self.commit_calls: list = []
        self.seeks: list = []
        self.closed = False

    def subscribe(self, topics):
        self.subscribed = topics

    def poll(self, timeout):
        if not self.messages:
            return None
        return self.messages.pop(0)

    def commit(self, message=None, offsets=None, asynchronous=True):
        self.commit_calls.append(
            {"message": message, "offsets": offsets, "asynchronous": asynchronous}
        )

    def seek(self, partition):
        self.seeks.append(partition)

    def close(self):
        self.closed = True


def _manual_consumer(monkeypatch, messages):
    holder: dict = {}

    def _make(config):
        holder["consumer"] = _FakeConsumer(config, messages)
        return holder["consumer"]

    monkeypatch.setattr(kc, "Consumer", _make)
    consumer = kc.KafkaConsumerCompat(
        "t",
        bootstrap_servers="broker:9092",
        group_id="g",
        enable_auto_commit=False,
    )
    return consumer, holder


class TestConsumerEdges:
    def test_poll_empty_returns_empty_batch(self, monkeypatch):
        consumer, _ = _manual_consumer(monkeypatch, [])
        assert consumer.poll(timeout_ms=100) == {}

    def test_poll_message_error_raises_kafka_error(self, monkeypatch):
        consumer, _ = _manual_consumer(monkeypatch, [_FakeMessage(err="NOT_LEADER")])
        with pytest.raises(kc.KafkaError, match="NOT_LEADER"):
            consumer.poll(timeout_ms=100)

    def test_commit_without_record_does_not_touch_broker(self, monkeypatch):
        from structlog.testing import capture_logs

        consumer, holder = _manual_consumer(monkeypatch, [])
        with capture_logs() as logs:
            consumer.commit()
        assert holder["consumer"].commit_calls == []
        assert any(entry.get("event") == "kafka_commit_without_record" for entry in logs)

    def test_commit_explicit_record_acks_that_record(self, monkeypatch):
        consumer, holder = _manual_consumer(
            monkeypatch, [_FakeMessage(offset=3), _FakeMessage(offset=4)]
        )
        batch = consumer.poll(timeout_ms=100)
        record = list(batch.values())[0][0]
        assert record.offset == 3
        other = kc.ConsumerRecord(
            topic="t", partition=0, offset=9, key=None, value=None, headers=[]
        )
        consumer.commit(record=other)
        call = holder["consumer"].commit_calls[-1]
        assert call["offsets"][0].offset == 10
        assert call["asynchronous"] is False

class TestDlqManager:
    def test_dlq_send_counts_success(self, monkeypatch):
        import shared.kafka_consumer_base as kcb_module

        sent: list = []

        class _Producer:
            def send(self, topic, value=None, **kwargs):
                sent.append((topic, value))

            def flush(self, timeout=None):
                return 0

            def close(self, timeout=None):
                return None

        monkeypatch.setattr(
            "shared.kafka_compat.KafkaProducerCompat", lambda **kwargs: _Producer()
        )
        dlq = kcb_module.DLQManager(bootstrap_servers="broker:9092", dlq_topic="dlq")
        dlq.send({"id": "doc-1"}, error="bad row", doc_id="doc-1")
        assert len(sent) == 1
        assert sent[0][0] == "dlq"
        assert sent[0][1]["error"] == "bad row"
        dlq.close()
