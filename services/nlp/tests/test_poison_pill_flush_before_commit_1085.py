"""Regression tests for #1085 — DLQ producer must flush before offset commit.

Problem
-------
``services/nlp/app/consumer.py`` routes poison-pill / schema-invalid /
auth-failed / tenant-missing / max-retries messages to the DLQ via
``producer.send()`` and then immediately calls ``consumer.commit()``.

``producer.send()`` returns a ``Future`` and only buffers the record
internally. The broker has not yet acked it. If the consumer process
crashes (OOM, SIGKILL, broker reject) between the send and the buffered
flush, the committed offset advances past the inbound message **while the
DLQ record is still in the producer buffer and will never reach the
broker**. That breaks the "every dropped message is recoverable from the
DLQ" FSMA 204 audit invariant.

Fix
---
Between ``_send_to_dlq(...)`` / ``_send_to_fsma_dlq(...)`` and
``consumer.commit()`` the consumer now calls ``producer.flush(timeout=5.0)``.
On ``KafkaTimeoutError`` the consumer logs ``dlq_flush_timeout`` and skips
the commit so Kafka redelivers the message on the next poll.

These tests drive the run_consumer loop with a mock Kafka stack and assert
that when ``producer.flush`` raises ``KafkaTimeoutError`` the consumer
does NOT commit the offset.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

# Make the repo root importable so `services.nlp...` works inside pytest
_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(value: bytes, *, offset: int = 0, topic: str = "ingest.normalized"):
    """Build a minimal kafka.consumer.fetcher.ConsumerRecord-shaped object."""
    rec = MagicMock()
    rec.value = value
    rec.offset = offset
    rec.topic = topic
    rec.headers = []
    return rec


def _install_run_consumer_mocks(
    monkeypatch: pytest.MonkeyPatch,
    *,
    inbound_records: list,
    flush_raises: bool,
) -> tuple[MagicMock, MagicMock]:
    """Patch run_consumer's infra dependencies and return (consumer, producer) mocks."""
    from kafka.errors import KafkaTimeoutError as _KafkaTimeoutError

    # Reset shutdown so other tests that may have flipped it don't prevent us
    # from running the loop even once.
    from services.nlp.app import consumer as consumer_mod
    consumer_mod._shutdown_event.clear()

    consumer = MagicMock(name="KafkaConsumer")
    # First poll returns one batch; subsequent polls return {} after we
    # flip the shutdown flag from inside the poll side effect.
    poll_calls = {"n": 0}
    tp = MagicMock(name="TopicPartition")

    def _poll(*_args, **_kwargs):
        poll_calls["n"] += 1
        if poll_calls["n"] == 1:
            return {tp: inbound_records}
        # After the first (and only) batch, signal shutdown so the while
        # loop exits cleanly.
        consumer_mod._shutdown_event.set()
        return {}

    consumer.poll.side_effect = _poll

    producer = MagicMock(name="KafkaProducer")
    if flush_raises:
        producer.flush.side_effect = _KafkaTimeoutError("simulated flush timeout")
    else:
        producer.flush.return_value = None

    # Patch the constructors that run_consumer calls so that no real network
    # I/O happens.
    monkeypatch.setattr(consumer_mod, "KafkaConsumer", MagicMock(return_value=consumer))
    monkeypatch.setattr(consumer_mod, "KafkaProducer", MagicMock(return_value=producer))
    # Topic creation should be a no-op for tests.
    monkeypatch.setattr(consumer_mod, "_ensure_topic", MagicMock())

    return consumer, producer


# ---------------------------------------------------------------------------
# Poison-pill path (the headline case)
# ---------------------------------------------------------------------------


def test_poison_pill_flush_timeout_does_not_commit(monkeypatch: pytest.MonkeyPatch):
    """When producer.flush times out on the poison-pill DLQ path, consumer.commit
    must NOT be called. Force-redelivery is the only safe recovery."""
    # Poison pill: bytes that are not valid JSON.
    rec = _make_record(b"\xff\xfe not json {\x00\x00", offset=42)

    consumer, producer = _install_run_consumer_mocks(
        monkeypatch,
        inbound_records=[rec],
        flush_raises=True,
    )

    from services.nlp.app.consumer import run_consumer
    run_consumer()

    # DLQ send happened (send() was called on the DLQ topic).
    assert producer.send.called, "DLQ send must still happen even when flush fails"
    # And a flush attempt was made (that's the bug-fix — without this, the
    # FSMA invariant can't be enforced).
    assert producer.flush.called, "producer.flush must be invoked before commit"
    # The key assertion: commit was NOT called because flush timed out.
    assert not consumer.commit.called, (
        "consumer.commit must NOT be called when producer.flush times out — "
        "the offset must stay behind so Kafka redelivers the poison pill."
    )


def test_poison_pill_successful_flush_does_commit(monkeypatch: pytest.MonkeyPatch):
    """Control case: when flush succeeds, commit must proceed normally."""
    rec = _make_record(b"not valid json at all", offset=7)

    consumer, producer = _install_run_consumer_mocks(
        monkeypatch,
        inbound_records=[rec],
        flush_raises=False,
    )

    from services.nlp.app.consumer import run_consumer
    run_consumer()

    assert producer.send.called, "DLQ send must happen"
    assert producer.flush.called, "producer.flush must happen before commit"
    assert consumer.commit.called, (
        "consumer.commit MUST be called when flush succeeds — otherwise the "
        "partition stalls on every malformed message."
    )


# ---------------------------------------------------------------------------
# Module-level sanity: the fix is actually present in the source
# ---------------------------------------------------------------------------


def test_every_dlq_call_is_followed_by_flush_before_commit():
    """Source-level invariant: every ``_send_to_dlq`` / ``_send_to_fsma_dlq``
    call inside the main consumer loop must be paired with a
    ``producer.flush(timeout=5.0)`` before the next ``consumer.commit()``.

    This is a regression guard so a future refactor can't accidentally
    reintroduce the #1085 gap without the test suite catching it.
    """
    from services.nlp.app import consumer as consumer_mod
    source = Path(consumer_mod.__file__).read_text(encoding="utf-8")
    lines = source.splitlines()

    dlq_call_re = ("_send_to_dlq(", "_send_to_fsma_dlq(")

    # Skip the helper function bodies themselves (they contain the call
    # names but that's the definition site, not a caller).
    def _in_helper_body(idx: int) -> bool:
        # Walk backward until we hit a top-level def or EOF; if the nearest
        # def is one of the helpers, this line is inside its body.
        for j in range(idx, -1, -1):
            line = lines[j]
            if line.startswith("def _send_to_dlq(") or line.startswith(
                "def _send_to_fsma_dlq("
            ):
                return True
            if line.startswith("def ") and j < idx:
                return False
        return False

    violations: list[str] = []
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if not any(stripped.startswith(t) for t in dlq_call_re):
            continue
        if _in_helper_body(i):
            continue
        # Look in the next 30 lines for commit() — it's the trigger we care
        # about. If we see producer.flush(timeout=5.0) before the commit,
        # we're good. If we see commit() first, that's a #1085 regression.
        window = lines[i : i + 30]
        saw_flush_5s = False
        for w in window:
            if "producer.flush(timeout=5.0)" in w:
                saw_flush_5s = True
            if "consumer.commit(" in w:
                if not saw_flush_5s:
                    violations.append(
                        f"line {i+1}: DLQ call not followed by "
                        f"producer.flush(timeout=5.0) before consumer.commit()"
                    )
                break

    assert not violations, (
        "#1085 regression — at least one DLQ call in the consumer loop is not "
        "followed by producer.flush(timeout=5.0) before consumer.commit():\n  "
        + "\n  ".join(violations)
    )
