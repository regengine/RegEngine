"""Break tests: Kafka failure injection with a fake broker.

Two batch emits share one producer. Delivery failures used to land in one
process-wide counter. Whichever batch called take_delivery_failures first
consumed the other batch's failures, and that other batch reported success.
service.py then marks those items seen.

A high-priority alert send that fails before enqueue was also ignored, so
the batch could report zero failures.
"""

from __future__ import annotations

import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from shared import kafka_compat as kc  # noqa: E402
from shared.kafka_compat import KafkaError  # noqa: E402


class _FakeKafkaError:
    def __init__(self, message: str):
        self._message = message

    def __str__(self) -> str:
        return self._message


class _BarrierProducer:
    """confluent stand-in.

    The first flush delivers every stored callback. The second flush waits
    until that batch has already taken the shared failure counter. On the
    old producer that means one batch observes every failure and the other
    observes zero.
    """

    first_take_done = threading.Event()

    def __init__(self, _config):
        self.pending: list = []
        self.sent = 0
        self.both_sent = threading.Event()
        self._lock = threading.Lock()
        self._flush_gate = threading.Lock()
        self._delivered = False

    def produce(self, topic, key=None, value=None, headers=None, on_delivery=None):
        with self._lock:
            self.pending.append(on_delivery)
            self.sent += 1
            if self.sent >= 2:
                self.both_sent.set()

    def poll(self, _timeout):
        return 0

    def flush(self, timeout=None):
        assert self.both_sent.wait(timeout=3), "second batch never produced"
        with self._flush_gate:
            if not self._delivered:
                with self._lock:
                    pending = list(self.pending)
                    self.pending.clear()
                for callback in pending:
                    if callback is not None:
                        callback(_FakeKafkaError("broker rejected"), None)
                self._delivered = True
                return 0
        assert type(self).first_take_done.wait(timeout=3), "first batch never reconciled"
        return 0

    def list_topics(self, timeout):
        return object()


def _producer():
    from services.scheduler.app.kafka_producer import KafkaEventProducer

    with patch("services.scheduler.app.kafka_producer.get_settings") as settings:
        stub = MagicMock()
        stub.kafka_bootstrap_servers = "localhost:9092"
        stub.kafka_topic_enforcement = "enforcement.changes"
        stub.kafka_topic_alerts = "alerts"
        stub.kafka_topic_fsma = "fsma.events.extracted"
        settings.return_value = stub
        return KafkaEventProducer()


def _item(severity: str = "medium"):
    from services.scheduler.app.models import EnforcementItem, EnforcementSeverity, SourceType

    return EnforcementItem(
        source_type=SourceType.FDA_RECALL,
        source_id=f"recall-{severity}-{threading.get_ident()}",
        title="Test recall",
        url="https://www.fda.gov/recalls/test",
        published_date=datetime(2026, 3, 15, tzinfo=timezone.utc),
        severity=EnforcementSeverity(severity),
    )


def test_concurrent_batches_each_see_their_own_delivery_failure(monkeypatch):
    monkeypatch.setenv("KAFKA_EVENT_SIGNING_KEY", "break-test-signing-key")
    _BarrierProducer.first_take_done = threading.Event()
    monkeypatch.setattr(kc, "Producer", _BarrierProducer)
    producer = _producer()
    original_take = producer.take_delivery_failures

    def _take_and_signal():
        try:
            return original_take()
        finally:
            _BarrierProducer.first_take_done.set()

    producer.take_delivery_failures = _take_and_signal
    results: list[tuple[int, int]] = []
    errors: list[BaseException] = []
    gate = threading.Barrier(2)

    def run_batch():
        try:
            gate.wait(timeout=3)
            results.append(producer.emit_batch([_item("medium")]))
        except BaseException as exc:  # noqa: BLE001 - surface worker failures
            errors.append(exc)

    threads = [threading.Thread(target=run_batch) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert errors == []
    assert len(results) == 2
    assert all(failures > 0 for _success, failures in results), (
        f"one batch reported success after the other batch consumed its delivery failure: {results}"
    )


def test_high_priority_alert_send_failure_counts_as_batch_failure(monkeypatch):
    monkeypatch.setenv("KAFKA_EVENT_SIGNING_KEY", "break-test-signing-key")
    producer = _producer()
    future = MagicMock()
    lib = MagicMock()
    lib.send.side_effect = [future, KafkaError("alerts topic down")]
    producer._get_producer = lambda: lib

    _success, failures = producer.emit_batch([_item("critical")])

    assert failures >= 1, "a failed high-priority alert send was reported as a clean batch"
