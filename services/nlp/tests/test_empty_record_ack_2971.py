"""#2971 follow-on — an empty record must be acked, not redelivered forever.

Once ``KafkaConsumerCompat`` really redelivers records the loop declines to
commit, every un-annotated "skip without committing" becomes an infinite
redelivery. ``if not evt: continue`` was the only such site: an empty payload
(a tombstone, or a null value) carries nothing to process, so skipping it
lost nothing — but under the corrected offset semantics it would spin on that
record forever and block the partition.

Acking it is the correct choice precisely because there is no data to lose;
this is the opposite case to the deliberate ``do NOT commit — force
redelivery`` paths, where the record still holds unprocessed work.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))


def _run_with(monkeypatch, value: bytes):
    from services.nlp.app import consumer as consumer_mod

    consumer_mod._shutdown_event.clear()

    record = MagicMock()
    record.value = value
    record.offset = 17
    record.topic = "ingest.normalized"
    record.partition = 0
    record.headers = []

    consumer = MagicMock(name="KafkaConsumer")
    calls = {"n": 0}
    tp = MagicMock()

    def _poll(*_a, **_kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return {tp: [record]}
        consumer_mod._shutdown_event.set()
        return {}

    consumer.poll.side_effect = _poll
    producer = MagicMock(name="KafkaProducer")
    producer.flush.return_value = None

    monkeypatch.setattr(consumer_mod, "KafkaConsumer", MagicMock(return_value=consumer))
    monkeypatch.setattr(consumer_mod, "KafkaProducer", MagicMock(return_value=producer))
    monkeypatch.setattr(consumer_mod, "_ensure_topic", MagicMock())
    monkeypatch.setattr(consumer_mod, "_start_health_server", MagicMock())

    consumer_mod.run_consumer()
    return consumer, producer


def test_tombstone_record_is_committed(monkeypatch):
    consumer, _producer = _run_with(monkeypatch, b"")

    assert consumer.commit.called, (
        "an empty record was skipped without acking — with #2971's real "
        "redelivery that spins the same record forever and blocks the "
        "partition"
    )


def test_empty_json_object_is_committed(monkeypatch):
    consumer, _producer = _run_with(monkeypatch, b"{}")

    assert consumer.commit.called
