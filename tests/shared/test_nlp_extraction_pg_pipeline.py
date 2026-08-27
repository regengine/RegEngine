"""Tests for the hardened NLP extraction pipeline on the pg task path.

Covers the port of the Kafka-consumer extraction pipeline
(services/nlp/app/consumer) onto :func:`server.workers.task_processor.
_handle_nlp_extraction` — the path that actually runs in production
(EVENT_BACKBONE=pg, Kafka gated off):

* Hardened happy path — FSMA pass + capped-confidence regex conversion +
  three-tier routing, with review-tier results enqueued as ``review_item``
  tasks (the pg replacement for the ``nlp.needs_review`` topic).
* Fallback-on-exception — any pipeline failure falls back to the bare
  legacy regex extractor with a structured warning and never fails the
  task.
* Output-schema compatibility — payloads enqueued by the hardened path
  satisfy the ``_handle_review_item`` consumer, and the legacy 4-key
  payload contract (document_id/entity_type/confidence/text) still works.

Like test_task_queue_hardening.py, these tests stub the database layer
(``task_processor.enqueue_task``) and the FSMA extractor singleton so they
run without PostgreSQL or model downloads. The legacy regex extractor and
the consumer conversion/threshold/review-reason modules run for real.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# Make the repo root importable so `from server.workers.task_processor import ...`
# resolves in a test-only environment.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_SERVICES = _ROOT / "services"
if str(_SERVICES) not in sys.path:
    sys.path.insert(0, str(_SERVICES))

from server.workers import task_processor  # noqa: E402

TENANT_ID = "11111111-2222-3333-4444-555555555555"
OBLIGATION_TEXT = "Food facilities on the FTL shall maintain temperature records for 180 days. FDA requires compliance."


def _fsma_result(review_required: bool = True):
    """Minimal stand-in for FSMAExtractionResult (only the fields the
    task handler reads)."""
    return SimpleNamespace(
        ctes=[],
        review_required=review_required,
        raw_text="redacted snippet",
    )


def _stub_fsma_extractor(review_required: bool = True, topic: str = "nlp.needs_review"):
    extractor = MagicMock()
    extractor.extract.return_value = _fsma_result(review_required=review_required)
    extractor.route_extraction.return_value = {
        "topic": topic,
        "payload": {"event_type": "fsma.extraction", "ctes": []},
        "routed_at": "2026-01-01T00:00:00Z",
    }
    return extractor


def _payload(**overrides):
    base = {
        "document_id": "doc-1",
        "text": OBLIGATION_TEXT,
        "tenant_id": TENANT_ID,
        "source_url": "https://example.com/doc-1",
        "document_hash": "hash-abc",
    }
    base.update(overrides)
    return base


def _review_item_calls(enqueue_mock):
    return [c for c in enqueue_mock.call_args_list if c.args and c.args[0] == "review_item"]


# ---------------------------------------------------------------------------
# Hardened happy path
# ---------------------------------------------------------------------------


class TestHardenedHappyPath:
    def test_review_tier_extractions_enqueued_as_review_items(self):
        extractor = _stub_fsma_extractor(review_required=True)
        enqueue = MagicMock(return_value=1)

        with (
            patch.object(task_processor, "_get_fsma_extractor", return_value=extractor),
            patch.object(task_processor, "enqueue_task", enqueue),
        ):
            task_processor._handle_nlp_extraction(_payload(), TENANT_ID)

        # FSMA pass ran with the required tenant scoping (#1122).
        extractor.extract.assert_called_once()
        assert extractor.extract.call_args.kwargs["tenant_id"] == TENANT_ID

        review_calls = _review_item_calls(enqueue)
        entity_types = [c.args[1]["entity_type"] for c in review_calls]
        # FSMA review_required result + the regex OBLIGATION extraction
        # (confidence capped at 0.60 → low tier → review).
        assert "FSMA_EXTRACTION" in entity_types
        assert "OBLIGATION" in entity_types

    def test_regex_review_payload_shape_and_routing(self):
        extractor = _stub_fsma_extractor(review_required=False, topic="graph.update")
        enqueue = MagicMock(return_value=1)

        with (
            patch.object(task_processor, "_get_fsma_extractor", return_value=extractor),
            patch.object(task_processor, "enqueue_task", enqueue),
        ):
            task_processor._handle_nlp_extraction(_payload(), TENANT_ID)

        review_calls = _review_item_calls(enqueue)
        # FSMA was high-confidence (no review) — only the regex extraction routes.
        assert len(review_calls) == 1
        call = review_calls[0]
        payload = call.args[1]

        # Byte-compatible legacy contract keys.
        assert {"document_id", "entity_type", "confidence", "text"} <= set(payload)
        assert payload["document_id"] == "doc-1"
        assert payload["entity_type"] == "OBLIGATION"
        # #1202 — legacy regex confidence is capped below auto-approval.
        assert payload["confidence"] <= 0.60
        # Low tier → high review priority (#1258), queue priority 1.
        assert payload["confidence_tier"] == "low"
        assert payload["priority"] == "high"
        assert call.kwargs["priority"] == 1
        assert call.kwargs["tenant_id"] == TENANT_ID
        # Provenance contract (#1368).
        assert payload["provenance"]["source_document_id"] == "doc-1"
        assert payload["provenance"]["source_url"] == "https://example.com/doc-1"
        assert payload["doc_hash"] == "hash-abc"
        # Canonical extraction dump rides along for persistence.
        assert payload["extraction"]["confidence_score"] == payload["confidence"]
        assert payload["extraction"]["source_text"] == payload["text"]
        # Idempotency key disambiguates extractions by source offset.
        assert call.kwargs["idempotency_key"].startswith("review_item:doc-1:OBLIGATION:")
        # Structured review reasons present (#1368).
        assert any(r["reason_code"] == "confidence_tier_low" for r in payload["review_reasons"])

    def test_fsma_high_confidence_is_not_sent_to_review(self):
        extractor = _stub_fsma_extractor(review_required=False, topic="graph.update")
        enqueue = MagicMock(return_value=1)

        with (
            patch.object(task_processor, "_get_fsma_extractor", return_value=extractor),
            patch.object(task_processor, "enqueue_task", enqueue),
        ):
            # Text with no obligations → regex pass yields nothing.
            task_processor._handle_nlp_extraction(_payload(text="hello world"), TENANT_ID)

        assert _review_item_calls(enqueue) == []

    def test_fsma_skipped_without_tenant_but_regex_routing_still_runs(self):
        get_extractor = MagicMock()
        enqueue = MagicMock(return_value=1)

        # The payload still carries a tenant_id, but the task ROW has none —
        # the row column is the only tenant authority (EPIC-A #1651), so the
        # payload value must be ignored and the FSMA pass skipped.
        payload = _payload()

        with (
            patch.object(task_processor, "_get_fsma_extractor", get_extractor),
            patch.object(task_processor, "enqueue_task", enqueue),
        ):
            task_processor._handle_nlp_extraction(payload, tenant_id=None)

        # FSMAExtractor requires tenant scoping (#1122) — never invoked.
        get_extractor.assert_not_called()
        review_calls = _review_item_calls(enqueue)
        assert len(review_calls) == 1
        assert review_calls[0].args[1]["entity_type"] == "OBLIGATION"
        assert review_calls[0].kwargs["tenant_id"] is None

    def test_skip_empty_payload_preserved(self):
        enqueue = MagicMock(return_value=1)
        with patch.object(task_processor, "enqueue_task", enqueue):
            task_processor._handle_nlp_extraction({})
        enqueue.assert_not_called()


# ---------------------------------------------------------------------------
# Fallback on pipeline exception
# ---------------------------------------------------------------------------


class TestFallbackOnException:
    def test_pipeline_exception_falls_back_to_legacy_regex(self):
        extractor = MagicMock()
        extractor.extract.side_effect = RuntimeError("fsma pipeline regression")
        enqueue = MagicMock(return_value=1)
        log = MagicMock()

        with (
            patch.object(task_processor, "_get_fsma_extractor", return_value=extractor),
            patch.object(task_processor, "enqueue_task", enqueue),
            patch.object(task_processor, "logger", log),
        ):
            # Must NOT raise — the task must not fail on a pipeline regression.
            task_processor._handle_nlp_extraction(_payload(), TENANT_ID)

        # Structured warning emitted for the fallback.
        warning_events = [c.args[0] for c in log.warning.call_args_list if c.args]
        assert "nlp_hardened_pipeline_failed" in warning_events
        warn_call = next(
            c for c in log.warning.call_args_list if c.args and c.args[0] == "nlp_hardened_pipeline_failed"
        )
        assert warn_call.kwargs["fallback"] == "legacy_regex"
        assert warn_call.kwargs["error_type"] == "RuntimeError"
        assert warn_call.kwargs["document_id"] == "doc-1"

        # Legacy regex completion log, no review items enqueued.
        info_calls = [c for c in log.info.call_args_list if c.args and c.args[0] == "nlp_extraction_complete"]
        assert len(info_calls) == 1
        assert info_calls[0].kwargs["pipeline"] == "legacy_regex_fallback"
        # The fallback ran the real regex extractor over obligation text.
        assert info_calls[0].kwargs["entities"] >= 1
        assert _review_item_calls(enqueue) == []

    def test_fallback_failure_still_fails_the_task(self):
        # If the LEGACY extractor itself breaks, that is a real failure —
        # the task must raise so the worker retry/dead-letter path engages.
        with patch(
            "services.nlp.app.extractor.extract_entities",
            side_effect=TypeError("regex extractor broken"),
        ):
            with pytest.raises(TypeError):
                task_processor._handle_nlp_extraction(_payload(), TENANT_ID)


# ---------------------------------------------------------------------------
# Output-schema compatibility with the review_item consumer
# ---------------------------------------------------------------------------


def _stub_admin_metrics():
    """Stub services.admin.app.metrics so _handle_review_item does not pull
    the admin DB engine; text_sanitize is imported for real (stdlib-only)."""
    tracker = MagicMock()
    fake_metrics = ModuleType("services.admin.app.metrics")
    fake_metrics.get_hallucination_tracker = lambda: tracker
    return tracker, fake_metrics


class TestReviewItemSchemaCompatibility:
    def test_hardened_payload_satisfies_review_item_handler(self):
        extractor = _stub_fsma_extractor(review_required=False, topic="graph.update")
        enqueue = MagicMock(return_value=1)

        with (
            patch.object(task_processor, "_get_fsma_extractor", return_value=extractor),
            patch.object(task_processor, "enqueue_task", enqueue),
        ):
            task_processor._handle_nlp_extraction(_payload(), TENANT_ID)

        review_call = _review_item_calls(enqueue)[0]
        review_payload = review_call.args[1]

        tracker, fake_metrics = _stub_admin_metrics()
        with patch.dict(sys.modules, {"services.admin.app.metrics": fake_metrics}):
            # The worker passes the claimed row's tenant_id column — mirror
            # that here with the tenant the enqueue call stamped on the row.
            task_processor._handle_review_item(review_payload, review_call.kwargs["tenant_id"])

        tracker.record_hallucination.assert_called_once()
        kwargs = tracker.record_hallucination.call_args.kwargs
        assert kwargs["tenant_id"] == TENANT_ID
        assert kwargs["document_id"] == "doc-1"
        assert kwargs["doc_hash"] == "hash-abc"
        assert kwargs["confidence_score"] == review_payload["confidence"]
        assert kwargs["extractor"] == "legacy_regex_v1"
        assert kwargs["provenance"]["source_document_id"] == "doc-1"
        # Sanitized span recorded for both text_raw and the extraction dict.
        assert kwargs["text_raw"]
        assert kwargs["extraction"]["source_text"] == kwargs["text_raw"]

    def test_legacy_minimal_payload_still_supported(self):
        # The pre-existing 4-key contract must keep working byte-for-byte.
        tracker, fake_metrics = _stub_admin_metrics()
        with patch.dict(sys.modules, {"services.admin.app.metrics": fake_metrics}):
            task_processor._handle_review_item(
                {
                    "document_id": "doc-9",
                    "entity_type": "THRESHOLD",
                    "confidence": 0.42,
                    "text": "at least 4 degrees",
                }
            )

        tracker.record_hallucination.assert_called_once()
        kwargs = tracker.record_hallucination.call_args.kwargs
        assert kwargs["tenant_id"] is None
        assert kwargs["document_id"] == "doc-9"
        assert kwargs["doc_hash"] == "doc-9"
        assert kwargs["confidence_score"] == 0.42
        assert kwargs["extractor"] == "unknown"
        assert kwargs["text_raw"] == "at least 4 degrees"
        assert kwargs["extraction"]["attributes"]["entity_type"] == "THRESHOLD"

    def test_source_text_sanitized_before_store(self):
        # #1390 — stored-XSS hardening must apply on the pg path too.
        tracker, fake_metrics = _stub_admin_metrics()
        with patch.dict(sys.modules, {"services.admin.app.metrics": fake_metrics}):
            task_processor._handle_review_item(
                {
                    "document_id": "doc-x",
                    "entity_type": "OBLIGATION",
                    "confidence": 0.5,
                    "text": "<script>alert(1)</script>must report",
                }
            )

        kwargs = tracker.record_hallucination.call_args.kwargs
        assert "<script>" not in kwargs["text_raw"]
        assert "must report" in kwargs["text_raw"]


# ---------------------------------------------------------------------------
# FSMA review envelope contents (#2932)
# ---------------------------------------------------------------------------


# A BOL with a lot code but no ship date — the KDE-minimum gate fires, so the
# extraction is routed to review and its single CTE is the one the reviewer
# has to complete.
BOL_MISSING_EVENT_DATE = """
BILL OF LADING
Shipper: Fresh Farms Inc.
GLN: 1234567890123

Ship To: Metro Distribution Center

ITEM DETAILS:
Product: Romaine Lettuce Hearts 12ct
Lot: L-2025-1105-A
Quantity: 50 cases
GTIN: 00012345678901
"""


class TestFSMAReviewEnvelope:
    """The enqueued ``review_item`` must carry the CTEs that triggered review.

    Runs the REAL FSMAExtractor (not the stub used above) because the defect
    lived in the extractor's own choice of serializer: ``route_extraction``
    built the HITL payload with ``to_graph_event``, which drops exactly the
    KDE-deficient CTEs that caused the routing decision (#2932).
    """

    def _enqueued_fsma_envelope(self):
        from services.nlp.app.extractors.fsma_extractor import FSMAExtractor

        enqueue = MagicMock(return_value=1)
        with (
            patch.object(task_processor, "_get_fsma_extractor", return_value=FSMAExtractor()),
            patch.object(task_processor, "enqueue_task", enqueue),
        ):
            task_processor._handle_nlp_extraction(
                _payload(text=BOL_MISSING_EVENT_DATE), TENANT_ID
            )

        fsma_calls = [c for c in _review_item_calls(enqueue) if c.args[1]["entity_type"] == "FSMA_EXTRACTION"]
        assert len(fsma_calls) == 1
        return fsma_calls[0].args[1]["extraction"]["attributes"]["fsma_envelope"]

    def test_review_item_envelope_carries_the_deficient_cte(self):
        envelope = self._enqueued_fsma_envelope()

        assert envelope["risk_assessment"]["review_required"] is True
        # Pre-fix this was [] — the reviewer saw only warnings and a
        # 1000-char redacted snippet, and the partial KDEs were discarded.
        assert len(envelope["ctes"]) == 1
        assert envelope["ctes"][0]["kdes"]["traceability_lot_code"] == "L-2025-1105-A"
        assert envelope["ctes"][0]["kdes"]["quantity"] == 50.0

    def test_review_item_envelope_lists_missing_kdes(self):
        envelope = self._enqueued_fsma_envelope()

        assert envelope["ctes"][0]["missing_kdes"] == ["event_date"]
