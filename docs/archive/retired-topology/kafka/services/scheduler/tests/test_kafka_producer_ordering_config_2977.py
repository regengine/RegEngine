"""#2977 — the scheduler producer must configure the ordering it documents.

``_get_producer``'s docstring claimed "with retries>0 and acks=all this is
still ordered per partition". Both halves were false:
``max_in_flight_requests_per_connection=5`` was discarded by the compat
layer's config translation, and librdkafka only preserves produce order
across retries when ``enable.idempotence=true`` — which no producer in the
tree set.

These tests assert the *effective* librdkafka config the scheduler producer
builds, not just the two keys the old compat test checked.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from shared import kafka_compat as kc  # noqa: E402


class _FakeProducer:
    instances: list["_FakeProducer"] = []

    def __init__(self, config):
        self.config = config
        _FakeProducer.instances.append(self)

    def produce(self, topic, **kwargs):
        pass

    def poll(self, timeout):
        return 0

    def flush(self, timeout=None):
        return 0


@pytest.fixture
def scheduler_producer(monkeypatch):
    from services.scheduler.app.kafka_producer import KafkaEventProducer

    _FakeProducer.instances.clear()
    monkeypatch.setattr(kc, "Producer", _FakeProducer)
    with patch("services.scheduler.app.kafka_producer.get_settings") as settings:
        s = MagicMock()
        s.kafka_bootstrap_servers = "localhost:9092"
        s.kafka_topic_enforcement = "enforcement.changes"
        s.kafka_topic_alerts = "alerts"
        s.kafka_topic_fsma = "fsma.events.extracted"
        settings.return_value = s
        producer = KafkaEventProducer()
    producer._get_producer()
    return producer


def _effective_config():
    return _FakeProducer.instances[-1].config


class TestSchedulerProducerOrdering:
    def test_in_flight_limit_reaches_librdkafka(self, scheduler_producer):
        assert _effective_config()["max.in.flight.requests.per.connection"] == 5

    def test_idempotence_is_enabled(self, scheduler_producer):
        assert _effective_config()["enable.idempotence"] is True, (
            "per-partition ordering across retries requires "
            "enable.idempotence=true in librdkafka; without it the "
            "docstring's ordering claim is false (#2977)"
        )

    def test_durability_settings_still_reach_librdkafka(self, scheduler_producer):
        config = _effective_config()
        assert config["acks"] == "all"
        assert config["message.send.max.retries"] == 10
        assert config["retry.backoff.ms"] == 500
        assert config["request.timeout.ms"] == 30000

    def test_docstring_does_not_claim_unconfigured_ordering(self):
        """The docs/code disagreement must be resolved, not left standing."""
        from services.scheduler.app.kafka_producer import KafkaEventProducer

        doc = KafkaEventProducer._get_producer.__doc__ or ""
        if "ordered per partition" in doc:
            assert "idempotence" in doc.lower(), (
                "the docstring asserts per-partition ordering; it must name "
                "enable.idempotence, which is what actually provides it "
                "(#2977)"
            )
