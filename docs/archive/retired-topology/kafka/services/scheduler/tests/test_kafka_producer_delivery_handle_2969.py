"""#2969 — the delivery-ack fix must work against the REAL compat producer.

#2711 (PR #2715) added ``future.add_errback(...)`` in
``KafkaEventProducer._send``. It never ran: ``KafkaProducerCompat.send()``
has no ``return``, so ``producer.send(...)`` evaluated to ``None`` and
``None.add_errback`` raised ``AttributeError`` on every send — swallowed by
a bare ``except Exception: pass``. ``take_delivery_failures()`` therefore
always returned 0 and ``emit_batch``/``emit_fsma_batch`` reported broker
delivery failures as complete success.

WHY THE ORIGINAL REGRESSION TEST COULD NOT CATCH THIS
-----------------------------------------------------
``test_kafka_delivery_ack_2711.py`` does::

    lib = MagicMock()
    lib.send.return_value = future        # <-- the test invents the handle
    producer._get_producer = lambda: lib

The test *supplies* the return value of ``send()``, so it passes whatever
``KafkaProducerCompat.send`` does — including returning ``None``. The
object whose behaviour is in question was replaced by the double.

HOW THESE TESTS AVOID THAT TRAP
-------------------------------
1. ``KafkaProducerCompat`` is the REAL class here. Nothing patches it, and
   nothing supplies the return value of ``send()``.
2. The only test double sits one layer BELOW the code under test — at the
   ``confluent_kafka.Producer`` boundary (``shared.kafka_compat.Producer``).
   Everything between the scheduler and librdkafka is production code.
3. ``test_scheduler_send_uses_the_real_compat_producer`` asserts the object
   under test is a ``KafkaProducerCompat`` and not a mock, so the suite
   fails loudly if someone re-introduces a self-fulfilling double.
4. ``test_send_returning_none_is_not_reported_as_success`` pins the exact
   failure mode #2969 describes: a producer whose ``send()`` yields no
   handle must NOT be reported as a successful send.
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
from shared.kafka_compat import KafkaProducerCompat  # noqa: E402


class _FakeKafkaError:
    """Stands in for a librdkafka error object handed to on_delivery."""

    def __init__(self, message: str):
        self._message = message

    def __str__(self) -> str:
        return self._message


class _FakeDeliveredMessage:
    def __init__(self, topic: str):
        self._topic = topic

    def topic(self) -> str:
        return self._topic


class _FakeConfluentProducer:
    """Test double for ``confluent_kafka.Producer`` — one layer BELOW the
    class under test, so ``KafkaProducerCompat`` itself stays real."""

    instances: list["_FakeConfluentProducer"] = []

    def __init__(self, config):
        self.config = config
        self.pending: list[tuple[str, object]] = []
        self.delivery_error: _FakeKafkaError | None = None
        self.flush_remaining = 0
        _FakeConfluentProducer.instances.append(self)

    def produce(self, topic, key=None, value=None, headers=None, on_delivery=None):
        self.pending.append((topic, on_delivery))

    def poll(self, timeout):
        return 0

    def flush(self, timeout=None):
        """Deliver everything queued, reporting ``delivery_error`` if set."""
        for topic, on_delivery in self.pending:
            if on_delivery is not None:
                on_delivery(self.delivery_error, _FakeDeliveredMessage(topic))
        self.pending = []
        return self.flush_remaining

    def list_topics(self, timeout):
        return object()


@pytest.fixture
def fake_broker(monkeypatch):
    _FakeConfluentProducer.instances.clear()
    monkeypatch.setattr(kc, "Producer", _FakeConfluentProducer)
    return _FakeConfluentProducer


def _scheduler_producer():
    """A real ``KafkaEventProducer`` (only ``get_settings`` is stubbed)."""
    from services.scheduler.app.kafka_producer import KafkaEventProducer

    with patch("services.scheduler.app.kafka_producer.get_settings") as settings:
        s = MagicMock()
        s.kafka_bootstrap_servers = "localhost:9092"
        s.kafka_topic_enforcement = "enforcement.changes"
        s.kafka_topic_alerts = "alerts"
        s.kafka_topic_fsma = "fsma.events.extracted"
        settings.return_value = s
        return KafkaEventProducer()


class TestCompatSendReturnsAHandle:
    def test_send_returns_a_delivery_handle(self, fake_broker):
        producer = KafkaProducerCompat(bootstrap_servers="broker:9092")
        handle = producer.send("t", key="k", value={"a": 1})

        assert handle is not None, (
            "#2969: KafkaProducerCompat.send() returned None, so every "
            "future.add_errback(...) call site is dead code"
        )
        assert hasattr(handle, "add_errback"), (
            "send() must return a handle the legacy call sites can register "
            "a delivery errback on"
        )

    def test_handle_errback_fires_on_broker_delivery_failure(self, fake_broker):
        producer = KafkaProducerCompat(bootstrap_servers="broker:9092")
        handle = producer.send("t", key="k", value={"a": 1})

        seen: list[str] = []
        handle.add_errback(lambda exc: seen.append(str(exc)))

        fake = fake_broker.instances[0]
        fake.delivery_error = _FakeKafkaError("broker rejected")
        producer.flush(timeout=1.0)

        assert seen == ["broker rejected"]

    def test_handle_errback_silent_on_successful_delivery(self, fake_broker):
        producer = KafkaProducerCompat(bootstrap_servers="broker:9092")
        handle = producer.send("t", key="k", value={"a": 1})

        seen: list[str] = []
        handle.add_errback(lambda exc: seen.append(str(exc)))
        producer.flush(timeout=1.0)

        assert seen == []


class TestSchedulerSeesRealDeliveryFailures:
    def test_scheduler_send_uses_the_real_compat_producer(self, fake_broker):
        """Guard against the MagicMock trap #2969 describes."""
        sched = _scheduler_producer()
        lib = sched._get_producer()

        assert isinstance(lib, KafkaProducerCompat), (
            "the producer under test must be the real compat class, not a "
            "double that invents its own send() return value"
        )
        assert not isinstance(lib.send, MagicMock)

    def test_delivery_failure_is_counted(self, fake_broker):
        sched = _scheduler_producer()
        assert sched._send(topic="t", key="k", value={"a": 1}) is True
        assert sched.take_delivery_failures() == 0, "nothing delivered yet"

        fake_broker.instances[0].delivery_error = _FakeKafkaError("broker rejected")
        sched.flush()

        assert sched.take_delivery_failures() == 1, (
            "a broker-reported delivery failure must reach "
            "_note_delivery_failure through the real compat producer"
        )

    def test_emit_fsma_batch_reports_failures_from_the_broker(self, fake_broker, monkeypatch):
        """service.py:388 reads ``failures == 0``; make it observably False."""
        monkeypatch.setenv("KAFKA_EVENT_SIGNING_KEY", "test-signing-key-2969")
        sched = _scheduler_producer()
        # Prime the producer so the fake exists, then arm the broker failure.
        sched._get_producer()
        fake_broker.instances[0].delivery_error = _FakeKafkaError("broker rejected")

        success, failures = sched.emit_fsma_batch([{"event_id": "e1"}])

        assert failures > 0, (
            "emit_fsma_batch reported broker delivery failure as success — "
            "primary_emit_succeeded at services/scheduler/service.py:388 "
            "would be True (#2969)"
        )
        assert success == 0

    def test_flush_timeout_counts_as_a_delivery_failure(self, fake_broker):
        """An unacked flush must not be swallowed by KafkaEventProducer.flush."""
        sched = _scheduler_producer()
        assert sched._send(topic="t", key="k", value={"a": 1}) is True
        fake_broker.instances[0].flush_remaining = 1  # compat raises KafkaTimeoutError

        sched.flush()

        assert sched.take_delivery_failures() >= 1, (
            "flush() discarded the KafkaTimeoutError raised by the compat "
            "layer, so unacknowledged messages counted as delivered (#2969)"
        )


class TestNoSilentSwallowOfAMissingHandle:
    def test_send_returning_none_is_not_reported_as_success(self, fake_broker):
        """The exact #2969 failure mode must be loud, not swallowed."""
        sched = _scheduler_producer()

        class _HandleLessProducer:
            def send(self, *args, **kwargs):
                return None  # what KafkaProducerCompat.send used to do

        sched._producer = _HandleLessProducer()
        sched._get_producer = lambda: sched._producer

        assert sched._send(topic="t", key="k", value={"a": 1}) is False, (
            "a producer that yields no delivery handle must be reported as a "
            "failed send, not swallowed by `except Exception: pass` (#2969)"
        )
