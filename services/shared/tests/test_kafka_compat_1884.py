"""Coverage for confluent-backed Kafka compatibility helpers (#1884)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from shared import kafka_compat as kc


class _FakeProducer:
    instances: list["_FakeProducer"] = []

    def __init__(self, config):
        self.config = config
        self.produce_calls = []
        self.poll_calls = []
        self.flush_remaining = 0
        _FakeProducer.instances.append(self)

    def produce(self, topic, **kwargs):
        self.produce_calls.append((topic, kwargs))

    def poll(self, timeout):
        self.poll_calls.append(timeout)

    def flush(self, timeout):
        return self.flush_remaining

    def list_topics(self, timeout):
        return SimpleNamespace(brokers={1: object()})


def test_producer_uses_confluent_config_and_serializes(monkeypatch):
    _FakeProducer.instances.clear()
    monkeypatch.setattr(kc, "Producer", _FakeProducer)

    producer = kc.KafkaProducerCompat(
        bootstrap_servers=["a:9092", "b:9092"],
        value_serializer=lambda value: f"v:{value}".encode(),
        key_serializer=lambda key: f"k:{key}".encode(),
        retries=7,
    )

    producer.send("topic", key="id", value="body", headers=[("h", b"v")])

    fake = _FakeProducer.instances[0]
    assert fake.config["bootstrap.servers"] == "a:9092,b:9092"
    assert fake.config["message.send.max.retries"] == 7
    assert fake.produce_calls == [
        (
            "topic",
            {
                "key": b"k:id",
                "value": b"v:body",
                "headers": [("h", b"v")],
            },
        )
    ]
    assert fake.poll_calls == [0]
    assert producer.bootstrap_connected() is True


def test_flush_raises_timeout_when_confluent_leaves_messages(monkeypatch):
    _FakeProducer.instances.clear()
    monkeypatch.setattr(kc, "Producer", _FakeProducer)
    producer = kc.KafkaProducerCompat(bootstrap_servers="broker:9092")
    _FakeProducer.instances[0].flush_remaining = 2

    with pytest.raises(kc.KafkaTimeoutError):
        producer.flush(timeout=1.0)


class _FakeMessage:
    def error(self):
        return None

    def topic(self):
        return "events"

    def partition(self):
        return 1

    def offset(self):
        return 42

    def key(self):
        return b"k"

    def value(self):
        return b"v"

    def headers(self):
        return [("x", b"y")]


class _FakeConsumer:
    def __init__(self, config):
        self.config = config
        self.subscribed = []
        self.committed = False
        self.closed = False

    def subscribe(self, topics):
        self.subscribed = topics

    def poll(self, timeout):
        return _FakeMessage()

    def commit(self, asynchronous):
        self.committed = not asynchronous

    def close(self):
        self.closed = True


def test_consumer_poll_returns_legacy_batch_shape(monkeypatch):
    holder = {}

    def _make(config):
        holder["consumer"] = _FakeConsumer(config)
        return holder["consumer"]

    monkeypatch.setattr(kc, "Consumer", _make)

    consumer = kc.KafkaConsumerCompat(
        "topic-a",
        bootstrap_servers="broker:9092",
        group_id="group",
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    batch = consumer.poll(timeout_ms=500)
    records = list(batch.values())[0]

    assert holder["consumer"].config["bootstrap.servers"] == "broker:9092"
    assert holder["consumer"].subscribed == ["topic-a"]
    assert records[0].topic == "events"
    assert records[0].offset == 42
    assert records[0].headers == [("x", b"y")]

    consumer.commit()
    consumer.close()
    assert holder["consumer"].committed is True
    assert holder["consumer"].closed is True

