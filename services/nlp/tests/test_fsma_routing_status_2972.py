"""#2972 — the consumer must act on ``_run_fsma_extractor``'s error status.

``_run_fsma_extractor`` catches its own routing (flush timeout / connection
error) and signing (``KafkaAuthError``) failures and returns
``{"status": "error", ...}`` instead of raising. The caller only ever read
``high_confidence``, and only to gate the LLM fallback — so a record whose
extracted CTEs never reached the FSMA topic still reached
``consumer.commit()``, was counted in ``MESSAGES_COUNTER(status="success")``
and never reached the FSMA DLQ. Because the extractor swallows the
exception, the outer ``except (ValidationError, KafkaTimeoutError)`` handler
never saw it either, so neither the retry counter nor the DLQ escalation
engaged: the traceability output was dropped with a log line and nothing
else.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID

import pytest

_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

TENANT = str(UUID("11111111-1111-1111-1111-111111111111"))
SIGNING_KEY = "test-signing-key-for-nlp-consumer-2972"


def _signed_record(monkeypatch, *, offset: int = 5):
    """Build a signed, schema-valid ingest.normalized record."""
    monkeypatch.setenv("KAFKA_EVENT_SIGNING_KEY", SIGNING_KEY)
    from shared.kafka_auth import sign_event

    evt = {
        "event_id": "evt-2972",
        "document_id": "doc-2972",
        "document_hash": "hash-2972",
        "tenant_id": TENANT,
        "text_clean": "Lot 42 shipped from Farm A on 2026-01-02.",
    }
    signed_payload, signed_headers = sign_event(evt, producer_service="ingestion-service")

    record = MagicMock()
    record.value = json.dumps(signed_payload).encode("utf-8")
    record.offset = offset
    record.topic = "ingest.normalized"
    record.partition = 0
    record.headers = signed_headers
    return record


def _drive_loop(monkeypatch, *, records, fsma_status):
    """Run one poll batch through the real consumer loop with fake infra."""
    from services.nlp.app import consumer as consumer_mod

    consumer_mod._shutdown_event.clear()
    if hasattr(consumer_mod._retry_counts, "clear"):
        consumer_mod._retry_counts.clear()

    consumer = MagicMock(name="KafkaConsumer")
    tp = MagicMock(name="TopicPartition")
    calls = {"n": 0}

    def _poll(*_a, **_kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return {tp: records}
        consumer_mod._shutdown_event.set()
        return {}

    consumer.poll.side_effect = _poll

    producer = MagicMock(name="KafkaProducer")
    producer.flush.return_value = None

    fsma_calls: list[dict] = []

    def _fake_extractor(**kwargs):
        fsma_calls.append(kwargs)
        return {
            "status": fsma_status,
            "cte_count": 2,
            "routed": "graph.update",
            "review_required": False,
            "high_confidence": True,
        }

    dlq = MagicMock(name="_send_to_fsma_dlq")

    monkeypatch.setattr(consumer_mod, "KafkaConsumer", MagicMock(return_value=consumer))
    monkeypatch.setattr(consumer_mod, "KafkaProducer", MagicMock(return_value=producer))
    monkeypatch.setattr(consumer_mod, "_ensure_topic", MagicMock())
    monkeypatch.setattr(consumer_mod, "_run_fsma_extractor", _fake_extractor)
    monkeypatch.setattr(consumer_mod, "_send_to_fsma_dlq", dlq)
    monkeypatch.setattr(consumer_mod, "NLP_ENABLE_FSMA_EXTRACTOR", True)

    consumer_mod.run_consumer()
    return consumer, producer, dlq, fsma_calls


def _counter(status: str) -> float:
    from services.nlp.app.consumer import MESSAGES_COUNTER

    return MESSAGES_COUNTER.labels(status=status)._value.get()


class TestRoutingErrorIsActedOn:
    def test_error_status_does_not_commit_the_source_offset(self, monkeypatch):
        record = _signed_record(monkeypatch)
        consumer, _producer, _dlq, fsma_calls = _drive_loop(
            monkeypatch, records=[record], fsma_status="error"
        )

        assert fsma_calls, "the FSMA extractor must have run for this record"
        assert not consumer.commit.called, (
            "the source offset was committed for a record whose CTEs never "
            "reached the FSMA topic — permanently lost with no DLQ entry and "
            "no retry (#2972)"
        )

    def test_error_status_is_not_counted_as_success(self, monkeypatch):
        before_success = _counter("success")
        before_error = _counter("error")

        record = _signed_record(monkeypatch)
        _drive_loop(monkeypatch, records=[record], fsma_status="error")

        assert _counter("success") == before_success, (
            "a record whose FSMA routing failed was reported as a successful "
            "extraction (#2972)"
        )
        assert _counter("error") > before_error, (
            "the failure must be visible in MESSAGES_COUNTER(status='error')"
        )

    def test_error_status_escalates_to_the_dlq_after_max_retries(self, monkeypatch):
        from services.nlp.app.consumer import MAX_RETRIES

        records = [_signed_record(monkeypatch, offset=5) for _ in range(MAX_RETRIES)]
        consumer, _producer, dlq, _calls = _drive_loop(
            monkeypatch, records=records, fsma_status="error"
        )

        assert dlq.called, (
            "after MAX_RETRIES redeliveries the record must reach the FSMA "
            "DLQ, exactly like the sibling failure paths (#2972)"
        )
        assert consumer.commit.call_count == 1, (
            "only the final, dead-lettered attempt may commit"
        )

    def test_ok_status_still_commits(self, monkeypatch):
        """Control case: a healthy record must not be held back."""
        record = _signed_record(monkeypatch)
        consumer, _producer, dlq, _calls = _drive_loop(
            monkeypatch, records=[record], fsma_status="ok"
        )

        assert consumer.commit.called
        assert not dlq.called


class TestExtractorStillReportsErrorStatus:
    """The contract the caller now depends on, pinned at the source."""

    def test_sign_failure_returns_error_status(self, monkeypatch):
        from shared.kafka_auth import KafkaAuthError
        from services.nlp.app import consumer as consumer_mod

        extractor = MagicMock()
        result = MagicMock()
        result.ctes = [object()]
        result.review_required = False
        extractor.extract.return_value = result
        extractor.route_extraction.return_value = {
            "topic": "graph.update",
            "payload": {"ctes": []},
        }
        monkeypatch.setattr(consumer_mod, "_get_fsma_extractor", lambda: extractor)

        def _boom(*_a, **_kw):
            raise KafkaAuthError("signing_key_missing", topic="graph.update")

        monkeypatch.setattr(consumer_mod, "sign_event", _boom)

        summary = consumer_mod._run_fsma_extractor(
            text="t",
            doc_id="doc-1",
            doc_hash="h",
            producer=MagicMock(),
            tenant_id=TENANT,
            kafka_headers=[],
        )
        assert summary["status"] == "error"

    def test_routing_failure_returns_error_status(self, monkeypatch):
        from shared.kafka_compat import KafkaTimeoutError
        from services.nlp.app import consumer as consumer_mod

        extractor = MagicMock()
        result = MagicMock()
        result.ctes = [object()]
        result.review_required = False
        extractor.extract.return_value = result
        extractor.route_extraction.return_value = {
            "topic": "graph.update",
            "payload": {"ctes": []},
        }
        monkeypatch.setattr(consumer_mod, "_get_fsma_extractor", lambda: extractor)
        monkeypatch.setattr(
            consumer_mod, "sign_event", lambda payload, **_kw: (payload, [])
        )

        producer = MagicMock()
        producer.flush.side_effect = KafkaTimeoutError("flush timed out")

        summary = consumer_mod._run_fsma_extractor(
            text="t",
            doc_id="doc-1",
            doc_hash="h",
            producer=producer,
            tenant_id=TENANT,
            kafka_headers=[],
        )
        assert summary["status"] == "error"
