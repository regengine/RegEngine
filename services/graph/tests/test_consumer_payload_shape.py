"""Regression tests for graph consumer payload-shape gating (Sig RE-SEC-006).

Before the fix, a non-dict payload (or non-list headers) reached
``verify_event`` substituted as ``{}`` / ``None``, which then raised
``missing_producer_service_in_body`` and DLQ'd with reason
``kafka_auth_failed``. That is the wrong root cause for on-call: the
real failure is a malformed payload shape, not an auth failure.

The fix short-circuits non-dict payloads BEFORE ``verify_event`` and
DLQs them with reason ``payload_not_dict`` (or ``headers_not_list``).
These tests pin that contract without spinning up the full async
consumer loop — they exercise the relevant branch by driving a single
poll iteration.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))


def _make_record(value, headers=None, topic="graph.update"):
    """Build a minimal confluent-kafka record stub."""
    rec = MagicMock()
    rec.value.return_value = value
    rec.headers.return_value = headers
    rec.topic.return_value = topic
    rec.error.return_value = None
    return rec


@pytest.mark.parametrize(
    "bad_value, expected_reason",
    [
        (["not", "a", "dict"], "payload_not_dict"),
        ("string-payload", "payload_not_dict"),
        (12345, "payload_not_dict"),
    ],
)
def test_non_dict_payload_routes_to_payload_not_dict_dlq(
    bad_value, expected_reason, monkeypatch
):
    """Non-dict payloads must DLQ with shape-specific reason, not kafka_auth_failed."""
    from services.graph.app import consumer as consumer_mod

    sent = []

    def fake_dlq(event, error, reason="processing_error", doc_id=None):
        sent.append({"event": event, "error": error, "reason": reason})

    # Drive one iteration of the consumer loop with a stubbed
    # DeserializingConsumer that returns our bad-shape record once and
    # then triggers shutdown.
    record = _make_record(bad_value, headers=[])
    fake_consumer = MagicMock()
    poll_calls = {"n": 0}

    def fake_poll(timeout):
        poll_calls["n"] += 1
        if poll_calls["n"] == 1:
            return record
        consumer_mod._shutdown_event.set()
        return None

    fake_consumer.poll.side_effect = fake_poll
    fake_consumer.commit.return_value = None

    consumer_mod._shutdown_event.clear()

    with patch.object(consumer_mod, "_send_to_dlq", side_effect=fake_dlq), patch.object(
        consumer_mod, "DeserializingConsumer", return_value=fake_consumer
    ), patch.object(consumer_mod, "_init_dlq_producer"), patch.object(
        consumer_mod, "SchemaRegistryClient"
    ), patch.object(
        consumer_mod, "AvroDeserializer"
    ), patch.object(
        consumer_mod, "load_schema", return_value="{}"
    ):
        try:
            asyncio.run(consumer_mod.run_consumer())
        finally:
            consumer_mod._shutdown_event.clear()

    assert sent, "expected a DLQ send for malformed payload"
    assert sent[0]["reason"] == expected_reason
    # Ensure we did NOT mask the shape error as a kafka_auth_failed.
    assert all(s["reason"] != "kafka_auth_failed" for s in sent)


def test_non_list_headers_routes_to_headers_not_list_dlq(monkeypatch):
    """When headers is not a list (e.g. a dict), DLQ with headers_not_list."""
    from services.graph.app import consumer as consumer_mod

    sent = []

    def fake_dlq(event, error, reason="processing_error", doc_id=None):
        sent.append({"reason": reason, "error": error})

    # record.headers() returning a dict — not a list of tuples — should
    # be classified as headers_not_list, not as a downstream auth fail.
    record = _make_record({"tenant_id": "t1"}, headers={"x": "y"})
    fake_consumer = MagicMock()
    poll_calls = {"n": 0}

    def fake_poll(timeout):
        poll_calls["n"] += 1
        if poll_calls["n"] == 1:
            return record
        consumer_mod._shutdown_event.set()
        return None

    fake_consumer.poll.side_effect = fake_poll
    fake_consumer.commit.return_value = None
    consumer_mod._shutdown_event.clear()

    with patch.object(consumer_mod, "_send_to_dlq", side_effect=fake_dlq), patch.object(
        consumer_mod, "DeserializingConsumer", return_value=fake_consumer
    ), patch.object(consumer_mod, "_init_dlq_producer"), patch.object(
        consumer_mod, "SchemaRegistryClient"
    ), patch.object(
        consumer_mod, "AvroDeserializer"
    ), patch.object(
        consumer_mod, "load_schema", return_value="{}"
    ):
        try:
            asyncio.run(consumer_mod.run_consumer())
        finally:
            consumer_mod._shutdown_event.clear()

    # The first DLQ send must be the shape-specific reason. (Subsequent
    # DLQs from any later branch are out of scope for this test.)
    assert sent, "expected a DLQ send"
    assert sent[0]["reason"] == "headers_not_list"
