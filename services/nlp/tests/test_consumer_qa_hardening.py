"""QA hardening tests for services/nlp/app/consumer/.

Covers four real bugs found in a deep QA pass:

* Bug A (dlq.py): ``_send_to_fsma_dlq`` did not catch ``KafkaTimeoutError``
  (or the base ``KafkaError``), so a transient broker stall while
  dead-lettering escaped ``_run_consumer_loop`` and killed the whole
  consumer thread, halting all processing with health 503.
* Bug B (consumer loop retry path): the retry handler caught
  ``KafkaTimeoutError`` but not the base ``KafkaError`` that
  ``producer.send()`` raises on produce-time failures, so transient send
  failures went straight to the DLQ with no retry and no retry-budget
  accounting.
* Bug C (conversion.py): a garbage ``source_span_start`` in one LLM result
  raised ``ValueError``/``TypeError`` and discarded every valid extraction
  from the same document to the DLQ.
* Bug D (health.py): ``SO_REUSEADDR`` was set after ``bind()``, which has
  no effect, so a fast restart could hit ``EADDRINUSE`` and come up with
  no liveness endpoint.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID

import pytest

_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))


TENANT = str(UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))


@pytest.fixture()
def retry_counts_clean():
    """Isolate the global retry-count cache per test."""
    from services.nlp.app.consumer import _retry_counts

    _retry_counts.clear()
    try:
        yield _retry_counts
    finally:
        _retry_counts.clear()


# ---------------------------------------------------------------------------
# Bug A: _send_to_fsma_dlq must swallow Kafka delivery failures
# ---------------------------------------------------------------------------


class TestFsmaDlqSwallowsKafkaFailures:
    def test_flush_timeout_does_not_propagate(self):
        """A slow-broker flush timeout inside the FSMA DLQ send must be
        logged, not raised: every loop call site invokes this helper
        outside any KafkaTimeoutError handler, so a raise kills the
        consumer thread and halts all processing."""
        from shared.kafka_compat import KafkaTimeoutError

        from services.nlp.app.consumer import _send_to_fsma_dlq

        producer = MagicMock(name="KafkaProducer")
        producer.flush.side_effect = KafkaTimeoutError("3 message(s) still buffered")

        # Must not raise.
        _send_to_fsma_dlq(
            producer,
            {"document_id": "doc-1", "source_url": "https://example.com/x"},
            "boom",
            doc_id="doc-1",
            tenant_id=TENANT,
        )
        assert producer.send.called

    def test_produce_time_kafka_error_does_not_propagate(self):
        """produce() raises base KafkaError (buffer full, unknown topic),
        which is not a TimeoutError/OSError: it must also be swallowed."""
        from shared.kafka_compat import KafkaError

        from services.nlp.app.consumer import _send_to_fsma_dlq

        producer = MagicMock(name="KafkaProducer")
        producer.send.side_effect = KafkaError("buffer full")

        _send_to_fsma_dlq(
            producer,
            {"document_id": "doc-1"},
            "boom",
            doc_id="doc-1",
            tenant_id=TENANT,
        )
        assert producer.send.called

    def test_poison_pill_sibling_still_swallows_timeout(self):
        """Parity lock: the non-FSMA sibling already caught this; both
        DLQ helpers must survive a stalled broker."""
        from shared.kafka_compat import KafkaTimeoutError

        from services.nlp.app.consumer import _send_to_dlq

        producer = MagicMock(name="KafkaProducer")
        producer.flush.side_effect = KafkaTimeoutError("slow broker")

        _send_to_dlq(producer, b"\xff\xfe", "deser failed")
        assert producer.send.called


# ---------------------------------------------------------------------------
# Bug B: transient producer.send KafkaError must use the retry budget
# ---------------------------------------------------------------------------


def _run_loop_once(monkeypatch, evt: dict):
    """Drive one record through run_consumer with a controllable routing step."""
    from services.nlp.app import consumer as consumer_mod

    consumer_mod._shutdown_event.clear()

    record = MagicMock()
    import json

    record.value = json.dumps(evt).encode("utf-8")
    record.offset = 5
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
    monkeypatch.setattr(consumer_mod, "NLP_ENABLE_FSMA_EXTRACTOR", False)
    monkeypatch.setattr(consumer_mod, "NLP_ENABLE_LLM_EXTRACTOR", False)
    monkeypatch.setattr(
        consumer_mod,
        "verify_event",
        lambda e, headers, **kw: (e, "test-producer"),
    )
    _validator = MagicMock(name="InboundValidator")
    _validator.iter_errors.return_value = []
    monkeypatch.setattr(consumer_mod, "_INBOUND_VALIDATOR", _validator)
    monkeypatch.setattr(
        consumer_mod,
        "extract_entities",
        lambda _text: [
            {
                "type": "OBLIGATION",
                "text": "Operators shall file receiving reports",
                "start": 0,
                "attrs": {},
            }
        ],
    )
    consumer_mod.run_consumer()
    return consumer, producer


def _doc_event() -> dict:
    return {
        "document_id": "doc-1",
        "tenant_id": TENANT,
        "text_clean": "Operators shall file receiving reports.",
    }


class TestSendKafkaErrorUsesRetryBudget:
    def test_transient_send_error_retries_without_dlq(
        self, monkeypatch, retry_counts_clean
    ):
        """A base-KafkaError from the routing send must increment the
        tenant-scoped retry counter and must NOT emit a DLQ record or
        commit on the first failure."""
        from shared.kafka_compat import KafkaError

        from services.nlp.app import consumer as consumer_mod
        from services.nlp.app.consumer import TOPIC_DLQ, TOPIC_FSMA_DLQ

        monkeypatch.setattr(
            consumer_mod,
            "_route_extraction",
            MagicMock(side_effect=KafkaError("buffer full")),
        )

        consumer, producer = _run_loop_once(monkeypatch, _doc_event())

        assert retry_counts_clean.get(f"{TENANT}:doc-1") == 1
        dlq_topics = [
            c.kwargs.get("topic", c.args[0] if c.args else None)
            for c in producer.send.call_args_list
        ]
        assert not any(t in (TOPIC_DLQ, TOPIC_FSMA_DLQ) for t in dlq_topics), (
            "transient send failure went straight to the DLQ without "
            "touching the retry budget"
        )
        assert consumer.commit.call_count == 0

    def test_send_error_escalates_to_dlq_at_max_retries(
        self, monkeypatch, retry_counts_clean
    ):
        """Once the tenant-scoped budget is exhausted the message must land
        on the DLQ keyed by tenant, the counter must reset, and the offset
        must commit so the partition is not blocked."""
        from shared.kafka_compat import KafkaError

        from services.nlp.app import consumer as consumer_mod
        from services.nlp.app.consumer import (
            MAX_RETRIES,
            TOPIC_DLQ,
            _retry_key_for,
        )

        retry_counts_clean[_retry_key_for(TENANT, "doc-1")] = MAX_RETRIES - 1
        monkeypatch.setattr(
            consumer_mod,
            "_route_extraction",
            MagicMock(side_effect=KafkaError("buffer full")),
        )

        consumer, producer = _run_loop_once(monkeypatch, _doc_event())

        sent_topics = [
            c.args[0] if c.args else c.kwargs.get("topic")
            for c in producer.send.call_args_list
        ]
        assert TOPIC_DLQ in sent_topics
        sent_keys = [c.kwargs.get("key") for c in producer.send.call_args_list]
        assert f"{TENANT}:doc-1" in sent_keys
        assert _retry_key_for(TENANT, "doc-1") not in retry_counts_clean
        assert consumer.commit.called

    def test_auth_failure_still_skips_retry(self, monkeypatch, retry_counts_clean):
        """KafkaAuthError (bad signature) must keep going straight to the
        DLQ: widening the retry tuple must not make deterministic auth
        failures retryable."""
        from shared.kafka_auth import KafkaAuthError

        from services.nlp.app import consumer as consumer_mod
        from services.nlp.app.consumer import TOPIC_DLQ

        monkeypatch.setattr(
            consumer_mod,
            "_route_extraction",
            MagicMock(side_effect=KafkaAuthError("bad-signature")),
        )

        consumer, producer = _run_loop_once(monkeypatch, _doc_event())

        assert retry_counts_clean.get(f"{TENANT}:doc-1", 0) == 0
        sent_topics = [
            c.args[0] if c.args else c.kwargs.get("topic")
            for c in producer.send.call_args_list
        ]
        assert TOPIC_DLQ in sent_topics
        assert consumer.commit.called


# ---------------------------------------------------------------------------
# Bug C: garbage LLM source_span_start must not discard the document
# ---------------------------------------------------------------------------


class TestLlmSpanStartCoercion:
    def _item(self, **overrides):
        base = {
            "provision_text": "Operators must retain shipping records.",
            "obligation_type": "REQUIREMENT",
            "confidence": 0.9,
            "source_span_start": 0,
        }
        base.update(overrides)
        return base

    def test_garbage_span_defaults_to_zero(self):
        from services.nlp.app.consumer import _convert_llm_results_to_extractions

        out = _convert_llm_results_to_extractions(
            [self._item(source_span_start="abc")], "doc-1", "https://example.com"
        )
        assert len(out) == 1
        assert out[0].source_offset == 0

    def test_garbage_span_does_not_discard_sibling_items(self):
        from services.nlp.app.consumer import _convert_llm_results_to_extractions

        out = _convert_llm_results_to_extractions(
            [
                self._item(
                    provision_text="First duty to retain.",
                    source_span_start="not-a-number",
                ),
                self._item(
                    provision_text="Second duty to retain.",
                    source_span_start=41,
                ),
            ],
            "doc-1",
            "https://example.com",
        )
        assert len(out) == 2
        assert [e.source_offset for e in out] == [0, 41]

    def test_confidence_still_capped_on_coerced_item(self):
        from services.nlp.app.consumer import _LLM_EXTRACTION_CONFIDENCE_CAP, _convert_llm_results_to_extractions

        out = _convert_llm_results_to_extractions(
            [self._item(source_span_start="abc", confidence=0.99)],
            "doc-1",
            "https://example.com",
        )
        assert out[0].confidence_score <= _LLM_EXTRACTION_CONFIDENCE_CAP

    def test_none_and_numeric_string_spans(self):
        from services.nlp.app.consumer import _convert_llm_results_to_extractions

        out = _convert_llm_results_to_extractions(
            [
                self._item(provision_text="Duty one.", source_span_start=None),
                self._item(provision_text="Duty two.", source_span_start="42"),
            ],
            "doc-1",
            "https://example.com",
        )
        assert [e.source_offset for e in out] == [0, 42]


# ---------------------------------------------------------------------------
# Bug D: health server must set SO_REUSEADDR before bind
# ---------------------------------------------------------------------------


class TestHealthServerReuseAddress:
    def test_reusable_server_sets_allow_reuse_address(self):
        import services.nlp.app.consumer.health as health_mod

        assert health_mod._ReusableHTTPServer.allow_reuse_address is True

    def test_start_health_server_binds_reusable_server(self, monkeypatch):
        import services.nlp.app.consumer.health as health_mod

        seen: dict = {}
        real_cls = health_mod._ReusableHTTPServer

        class SpyServer(real_cls):
            def __init__(self, addr, handler):
                seen["addr"] = addr
                seen["handler"] = handler
                seen["constructed"] = True

            def serve_forever(self, *a, **k):
                return None

        monkeypatch.setattr(health_mod, "_ReusableHTTPServer", SpyServer)
        monkeypatch.setattr(health_mod, "_HEALTH_PORT", 18099)

        stopped_threads = []

        class NoopThread:
            def __init__(self, *a, **k):
                pass

            def start(self):
                stopped_threads.append(True)

        monkeypatch.setattr(health_mod.threading, "Thread", NoopThread)

        health_mod._start_health_server()

        assert seen.get("constructed") is True
        assert seen["addr"] == ("0.0.0.0", 18099)
        assert seen["handler"] is health_mod._HealthHandler
