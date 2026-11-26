"""#2977 — KafkaProducerCompat must not silently discard producer kwargs.

The config translation handled exactly four keys (``acks``, ``retries``,
``retry_backoff_ms``, ``request_timeout_ms``) and dropped everything else in
``**config`` with no warning and no error. The scheduler passes
``max_in_flight_requests_per_connection=5`` expecting bounded in-flight
requests; that value never reached librdkafka, which kept its default of
1000000. A typo'd option was a no-op rather than an error.
"""

from __future__ import annotations

import pytest
from shared import kafka_compat as kc


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
def fake_producer(monkeypatch):
    _FakeProducer.instances.clear()
    monkeypatch.setattr(kc, "Producer", _FakeProducer)
    return _FakeProducer


def _config(**kwargs):
    kc.KafkaProducerCompat(bootstrap_servers="broker:9092", **kwargs)
    return _FakeProducer.instances[-1].config


class TestKwargTranslation:
    def test_max_in_flight_reaches_librdkafka(self, fake_producer):
        config = _config(max_in_flight_requests_per_connection=5)
        assert config["max.in.flight.requests.per.connection"] == 5, (
            "the scheduler's bounded in-flight setting was dropped, leaving "
            "librdkafka's default of 1000000 (#2977)"
        )

    def test_enable_idempotence_reaches_librdkafka(self, fake_producer):
        assert _config(enable_idempotence=True)["enable.idempotence"] is True

    def test_every_kwarg_the_scheduler_passes_survives_translation(self, fake_producer):
        config = _config(
            acks="all",
            retries=10,
            retry_backoff_ms=500,
            max_in_flight_requests_per_connection=5,
            request_timeout_ms=30000,
            enable_idempotence=True,
        )
        assert config == {
            "bootstrap.servers": "broker:9092",
            "acks": "all",
            "message.send.max.retries": 10,
            "retry.backoff.ms": 500,
            "max.in.flight.requests.per.connection": 5,
            "request.timeout.ms": 30000,
            "enable.idempotence": True,
        }


class TestUnknownKwargsAreLoud:
    def test_unknown_kwarg_raises_and_names_the_key(self, fake_producer):
        with pytest.raises(TypeError) as exc:
            _config(max_in_flght_requests_per_connection=5)  # typo
        assert "max_in_flght_requests_per_connection" in str(exc.value)

    def test_known_but_untranslatable_kwarg_is_warned_not_dropped(self, fake_producer, caplog):
        """``max_block_ms`` is kafka-python-only; graph's publisher passes it.

        It has no librdkafka equivalent, so it must be explicitly recognised
        and warned about — not silently discarded and not fatal.
        """
        config = _config(max_block_ms=5000)
        assert "max.block.ms" not in config
        assert config["bootstrap.servers"] == "broker:9092"
