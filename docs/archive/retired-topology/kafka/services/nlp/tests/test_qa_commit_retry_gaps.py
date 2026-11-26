"""Gap tests from the services/nlp QA pass.

Covers four defects/gaps in consumer commit/retry semantics and extractors:

1. ``_send_to_fsma_dlq`` did not catch ``KafkaTimeoutError`` (its sibling
   ``_send_to_dlq`` does). ``KafkaTimeoutError`` derives from ``KafkaError``,
   not from ``TimeoutError``/``OSError``, so a DLQ flush timeout escaped the
   handler, propagated out of the per-record loop and killed the consumer
   thread. The offset was never committed and no orchestrator-visible
   signal distinguished this from a healthy loop until the liveness probe
   work in #2979.
2. ``_detect_intent`` classified "where did lot X go" as ``trace_backward``:
   the bare phrase "where did" sits in ``_BACKWARD_KEYWORDS``, so the
   forward special-case ("where did" + " go") could never win. A downstream
   recall trace answered with upstream sources is a data integrity issue.
3. ``_resolve_tenant_id`` rejected a valid signed payload when the
   unsigned header carried a sentinel ("default", "none", "null"). The
   header is advisory-only, so a non-claim must not trigger the hostile
   mismatch path and DLQ a healthy message.
4. ``_convert_llm_results_to_extractions`` called ``int()`` on
   ``source_span_start`` with no coercion, so one malformed item aborted
   the whole batch (all valid LLM extractions dropped). Confidence in the
   same function already coerces defensively to 0.0.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from shared.kafka_compat import KafkaTimeoutError

from services.nlp.app.consumer import (
    _convert_llm_results_to_extractions,
    _resolve_tenant_id,
    _send_to_dlq,
    _send_to_fsma_dlq,
)
from services.nlp.app.query_planner import parse_query

TENANT_A = str(uuid.UUID("11111111-1111-1111-1111-111111111111"))
TENANT_B = str(uuid.UUID("22222222-2222-2222-2222-222222222222"))


def _mock_producer() -> MagicMock:
    producer = MagicMock()
    producer.send.return_value = None
    producer.flush.return_value = None
    return producer


class TestFsmaDlqFlushTimeout:
    """A DLQ flush/send timeout must never escape the DLQ helper."""

    def test_flush_timeout_is_swallowed_not_raised(self):
        producer = _mock_producer()
        producer.flush.side_effect = KafkaTimeoutError("1 message still buffered")
        event = {"source_url": "https://example.gov/fsma-rule", "document_id": "d1"}
        # Must not raise: the caller has no handler for this around DLQ sends.
        _send_to_fsma_dlq(producer, event, "boom", "d1", tenant_id=TENANT_A)
        producer.send.assert_called_once()

    def test_send_timeout_is_swallowed_not_raised(self):
        producer = _mock_producer()
        producer.send.side_effect = KafkaTimeoutError("buffer full")
        event = {"source_url": "https://example.gov/fsma-rule", "document_id": "d1"}
        _send_to_fsma_dlq(producer, event, "boom", "d1", tenant_id=TENANT_A)

    def test_standard_dlq_already_swallow_flush_timeout(self):
        """Pin the sibling behavior ``_send_to_fsma_dlq`` was aligned to."""
        producer = _mock_producer()
        producer.flush.side_effect = KafkaTimeoutError("1 message still buffered")
        _send_to_dlq(
            producer, {"document_id": "d1"}, "boom", "d1", tenant_id=TENANT_A
        )


class TestWhereDidIntent:
    """Trace direction must follow the verb, not the bare "where did" prefix."""

    def test_where_did_go_is_forward(self):
        plan = parse_query("where did lot LOT-2026-001 go")
        assert plan.intent == "trace_forward"
        assert plan.tlc == "LOT-2026-001"

    def test_where_did_come_from_is_backward(self):
        plan = parse_query("where did lot LOT-2026-001 come from")
        assert plan.intent == "trace_backward"
        assert plan.tlc == "LOT-2026-001"

    def test_explicit_trace_back_still_backward(self):
        plan = parse_query("trace back lot LOT-2026-001")
        assert plan.intent == "trace_backward"

    def test_explicit_trace_forward_still_forward(self):
        plan = parse_query("trace forward lot LOT-2026-001")
        assert plan.intent == "trace_forward"


class TestSentinelHeaderIsNotAClaim:
    """Sentinel header values must be treated as absent, like the payload."""

    def test_default_header_does_not_reject_valid_payload(self):
        resolved, reason = _resolve_tenant_id(
            header_tenant_id="default", payload_tenant_id=TENANT_A
        )
        assert resolved == TENANT_A
        assert reason is None

    def test_none_and_null_headers_do_not_reject_valid_payload(self):
        for sentinel in ("None", "none", "null", "NULL"):
            resolved, reason = _resolve_tenant_id(
                header_tenant_id=sentinel, payload_tenant_id=TENANT_A
            )
            assert resolved == TENANT_A, sentinel
            assert reason is None, sentinel

    def test_real_uuid_mismatch_still_rejected(self):
        """The hostile-mismatch path must survive the sentinel fix."""
        resolved, reason = _resolve_tenant_id(
            header_tenant_id=TENANT_A, payload_tenant_id=TENANT_B
        )
        assert resolved is None
        assert reason is not None and "mismatch" in reason


class TestLlmBridgeSpanCoercion:
    """One malformed span must not drop the whole LLM batch."""

    def _item(self, **overrides):
        base = {
            "provision_text": "Covered entities shall keep traceability records.",
            "obligation_type": "REQUIREMENT",
            "confidence": 0.9,
            "source_span_start": 12,
        }
        base.update(overrides)
        return base

    def test_non_numeric_span_defaults_to_zero(self):
        extractions = _convert_llm_results_to_extractions(
            [self._item(source_span_start="not-a-number")],
            doc_id="doc-llm",
            source_url="https://example.gov/rule.pdf",
        )
        assert len(extractions) == 1
        assert extractions[0].source_offset == 0

    def test_bad_span_does_not_kill_sibling_items(self):
        extractions = _convert_llm_results_to_extractions(
            [
                self._item(source_span_start=12),
                self._item(source_span_start="not-a-number"),
                self._item(source_span_start=None),
            ],
            doc_id="doc-llm",
            source_url="https://example.gov/rule.pdf",
        )
        assert len(extractions) == 3
        assert [e.source_offset for e in extractions] == [12, 0, 0]

    def test_capped_confidence_still_holds_for_coerced_items(self):
        from services.nlp.app.consumer import _current_thresholds

        _, medium = _current_thresholds()
        extractions = _convert_llm_results_to_extractions(
            [self._item(source_span_start="bogus", confidence=1.0)],
            doc_id="doc-llm",
            source_url="https://example.gov/rule.pdf",
        )
        assert extractions[0].confidence_score < medium
