"""#2971 — KafkaConsumerCompat must not advance past records it never acked.

``KafkaConsumerCompat`` built the confluent ``Consumer`` with four config
keys and discarded the rest, so ``enable.auto.offset.store`` kept
librdkafka's default of ``true``: the offset is stored the instant
``poll()`` hands the message to the application, independently of
``enable.auto.commit=False``. ``commit()`` then called
``self._consumer.commit(asynchronous=False)`` with neither ``message=``
nor ``offsets=``, which commits the whole assignment's *stored* offsets.

Every ``continue  # do NOT commit — force redelivery`` site in the NLP
consumer therefore only deferred the commit by one record: the next
successful record's ``commit()`` swept up the stored offset of the record
that was deliberately skipped, so it was never redelivered and never
retried — silently dropped.

The fake below models the two librdkafka behaviours the defect depends on:
auto-store at poll time, and "commit with no argument commits the stored
offsets".
"""

from __future__ import annotations

import pytest
from shared import kafka_compat as kc


class _FakeMessage:
    def __init__(self, offset: int, *, topic: str = "ingest.normalized", partition: int = 0):
        self._offset = offset
        self._topic = topic
        self._partition = partition

    def error(self):
        return None

    def topic(self):
        return self._topic

    def partition(self):
        return self._partition

    def offset(self):
        return self._offset

    def key(self):
        return f"k{self._offset}".encode()

    def value(self):
        return f"v{self._offset}".encode()

    def headers(self):
        return []


class _FakeConfluentConsumer:
    """Models librdkafka's offset-store / commit / seek semantics.

    * ``enable.auto.offset.store`` defaults to ``true``; when on, the offset
      is stored as soon as ``poll()`` returns the message.
    * ``commit()`` with neither ``message=`` nor ``offsets=`` commits the
      assignment's stored offsets.
    * ``seek()`` repositions the fetch pointer, so the next ``poll()``
      re-delivers from that offset.
    """

    instances: list["_FakeConfluentConsumer"] = []

    def __init__(self, config, log=None):
        self.config = config
        self._log = log if log is not None else []
        self._position = 0
        self.stored_offset: int | None = None
        self.committed_offset: int | None = None
        self.commit_calls: list[dict] = []
        self.seeks: list[int] = []
        self.subscribed: list[str] = []
        self.closed = False
        _FakeConfluentConsumer.instances.append(self)

    # -- confluent Consumer surface -----------------------------------
    def subscribe(self, topics):
        self.subscribed = list(topics)

    def poll(self, timeout):
        if self._position >= len(self._log):
            return None
        msg = self._log[self._position]
        self._position += 1
        if self.config.get("enable.auto.offset.store", True):
            # librdkafka stores the offset the moment the message is handed
            # to the application — this is the root of #2971.
            self.stored_offset = msg.offset() + 1
        return msg

    def store_offsets(self, message=None, offsets=None):
        if message is not None:
            self.stored_offset = message.offset() + 1
        elif offsets:
            self.stored_offset = offsets[0].offset

    def commit(self, message=None, offsets=None, asynchronous=True):
        self.commit_calls.append(
            {"message": message, "offsets": offsets, "asynchronous": asynchronous}
        )
        if message is not None:
            self.committed_offset = message.offset() + 1
        elif offsets:
            self.committed_offset = offsets[0].offset
        else:
            # Assignment-wide commit of whatever librdkafka has stored.
            self.committed_offset = self.stored_offset

    def seek(self, partition):
        self.seeks.append(partition.offset)
        for index, msg in enumerate(self._log):
            if msg.offset() >= partition.offset:
                self._position = index
                return
        self._position = len(self._log)

    def assignment(self):
        return []

    def close(self):
        self.closed = True


def _install(monkeypatch, log):
    _FakeConfluentConsumer.instances.clear()

    def _make(config):
        return _FakeConfluentConsumer(config, log=log)

    monkeypatch.setattr(kc, "Consumer", _make)


def _manual_consumer(**kwargs):
    return kc.KafkaConsumerCompat(
        "ingest.normalized",
        bootstrap_servers="broker:9092",
        group_id="nlp-consumer",
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        **kwargs,
    )


def _only_record(batch):
    assert batch, "expected the poll batch to contain a record"
    return list(batch.values())[0][0]


class TestOffsetStoreConfig:
    def test_manual_commit_mode_disables_librdkafka_auto_offset_store(self, monkeypatch):
        """Manual offset control requires enable.auto.offset.store=False."""
        _install(monkeypatch, [_FakeMessage(10)])
        _manual_consumer()

        config = _FakeConfluentConsumer.instances[0].config
        assert config.get("enable.auto.offset.store") is False, (
            "with enable.auto.commit=False the offset must NOT be stored at "
            "poll time, or a later commit() sweeps up records the caller "
            "deliberately skipped (#2971)"
        )

    def test_auto_commit_mode_leaves_offset_store_enabled(self, monkeypatch):
        """Auto-commit commits *stored* offsets — don't break that mode."""
        _install(monkeypatch, [_FakeMessage(10)])
        kc.KafkaConsumerCompat(
            "t",
            bootstrap_servers="broker:9092",
            group_id="g",
            enable_auto_commit=True,
        )
        config = _FakeConfluentConsumer.instances[0].config
        assert config.get("enable.auto.offset.store", True) is True


class TestPerMessageCommit:
    def test_commit_acks_the_polled_message_not_the_assignment(self, monkeypatch):
        _install(monkeypatch, [_FakeMessage(10)])
        consumer = _manual_consumer()

        record = _only_record(consumer.poll(timeout_ms=500))
        assert record.offset == 10
        consumer.commit()

        fake = _FakeConfluentConsumer.instances[0]
        call = fake.commit_calls[-1]
        assert call["asynchronous"] is False
        assert call["message"] is not None or call["offsets"], (
            "commit() must name the record being acknowledged; a bare "
            "commit() commits the assignment's stored offsets (#2971)"
        )
        assert fake.committed_offset == 11


class TestRedeliveryOfSkippedRecords:
    def test_skipped_record_is_redelivered_not_swept_up_by_next_commit(self, monkeypatch):
        """The headline #2971 data-loss case.

        Record 10 hits a ``do NOT commit — force redelivery`` path; record 11
        is then processed successfully and committed. Pre-fix the commit of
        record 11 also committed record 10's auto-stored offset, so record 10
        was never redelivered and never retried.
        """
        _install(monkeypatch, [_FakeMessage(10), _FakeMessage(11)])
        consumer = _manual_consumer()

        first = _only_record(consumer.poll(timeout_ms=500))
        assert first.offset == 10
        # Caller declines to commit — the "force redelivery" contract.

        second = _only_record(consumer.poll(timeout_ms=500))
        assert second.offset == 10, (
            "a record that was polled but never committed must be REDELIVERED, "
            "not skipped in favour of the next offset (#2971)"
        )

        consumer.commit()
        fake = _FakeConfluentConsumer.instances[0]
        assert fake.committed_offset == 11, (
            "committing the redelivered record must ack exactly it (offset+1), "
            "never an offset beyond a record the caller never acked"
        )

    def test_uncommitted_offset_is_never_committed(self, monkeypatch):
        """Even if the caller keeps consuming, the skipped offset is not acked."""
        _install(monkeypatch, [_FakeMessage(10), _FakeMessage(11)])
        consumer = _manual_consumer()

        _only_record(consumer.poll(timeout_ms=500))  # offset 10, never acked
        consumer.poll(timeout_ms=500)

        fake = _FakeConfluentConsumer.instances[0]
        assert fake.committed_offset is None
        assert (fake.stored_offset or 0) <= 10, (
            "offset 11 must never be stored while offset 10 is unacknowledged "
            "— that is the silent skip #2971 describes"
        )


class TestKwargsAreNotSilentlyDiscarded:
    def test_unknown_consumer_kwarg_raises(self, monkeypatch):
        _install(monkeypatch, [])
        with pytest.raises(TypeError) as exc:
            kc.KafkaConsumerCompat(
                "t",
                bootstrap_servers="broker:9092",
                group_id="g",
                enable_auto_commit=False,
                enabel_auto_offset_store=False,  # typo — must not vanish
            )
        assert "enabel_auto_offset_store" in str(exc.value)

    def test_explicit_offset_store_kwarg_is_honoured(self, monkeypatch):
        _install(monkeypatch, [])
        kc.KafkaConsumerCompat(
            "t",
            bootstrap_servers="broker:9092",
            group_id="g",
            enable_auto_commit=False,
            enable_auto_offset_store=True,
        )
        assert _FakeConfluentConsumer.instances[0].config["enable.auto.offset.store"] is True
