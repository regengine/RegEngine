"""Tests for the hardened NLP extraction pipeline on the pg task path.

Covers the port of the Kafka-consumer extraction pipeline
(services/nlp/app/consumer) onto :func:`server.workers.task_processor.
_handle_nlp_extraction` — the path that actually runs in production
(EVENT_BACKBONE=pg, Kafka gated off):

* Hardened happy path — FSMA pass + capped-confidence regex conversion +
  three-tier routing, with review-tier results enqueued as ``review_item``
  tasks (the pg replacement for the ``nlp.needs_review`` topic).
* Fail-closed completion — missing input, extraction failures, and failed
  review enqueues enter the worker's retry/dead-letter path.
* Output-schema compatibility — payloads enqueued by the hardened path
  satisfy the ``_handle_review_item`` consumer, and the legacy 4-key
  payload contract (document_id/entity_type/confidence/text) still works.

Like test_task_queue_hardening.py, these tests stub the database layer
(``task_processor.enqueue_task``) and the FSMA extractor singleton so they
run without PostgreSQL or model downloads. The legacy regex extractor and
the consumer conversion/threshold/review-reason modules run for real.
"""

from __future__ import annotations

import builtins
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

    def test_empty_payload_fails(self):
        enqueue = MagicMock(return_value=1)
        with patch.object(task_processor, "enqueue_task", enqueue):
            with pytest.raises(ValueError):
                task_processor._handle_nlp_extraction({})
        enqueue.assert_not_called()


# ---------------------------------------------------------------------------
# Failures must reach the worker's retry/dead-letter path
# ---------------------------------------------------------------------------


class TestExtractionFailures:
    @pytest.mark.parametrize("field", ["document_id", "text"])
    @pytest.mark.parametrize("value", [" \t\n", 17, ["text"], {"text": "value"}])
    def test_invalid_input_fails_before_extraction(self, field, value):
        with patch.object(task_processor, "_run_hardened_extraction", return_value={}) as extract:
            with pytest.raises(ValueError):
                task_processor._handle_nlp_extraction(_payload(**{field: value}), TENANT_ID)
        extract.assert_not_called()

    def test_nonblank_text_is_not_stripped(self):
        original_text = " \nhello world\t "
        extractor = _stub_fsma_extractor(review_required=False)
        with (
            patch.object(task_processor, "_get_fsma_extractor", return_value=extractor),
            patch.object(task_processor, "enqueue_task") as enqueue,
        ):
            task_processor._handle_nlp_extraction(_payload(text=original_text), TENANT_ID)
        extractor.extract.assert_called_once_with(original_text, "doc-1", tenant_id=TENANT_ID)
        enqueue.assert_not_called()

    def test_pipeline_exception_propagates_without_regex_fallback(self):
        extractor = MagicMock()
        extractor.extract.side_effect = RuntimeError("fsma pipeline regression")
        enqueue = MagicMock(return_value=1)
        log = MagicMock()

        with (
            patch.object(task_processor, "_get_fsma_extractor", return_value=extractor),
            patch.object(task_processor, "enqueue_task", enqueue),
            patch.object(task_processor, "logger", log),
            patch("services.nlp.app.extractor.extract_entities") as regex,
        ):
            with pytest.raises(RuntimeError, match="fsma pipeline regression"):
                task_processor._handle_nlp_extraction(_payload(), TENANT_ID)

        regex.assert_not_called()
        enqueue.assert_not_called()
        assert not any(c.args[0] == "nlp_extraction_complete" for c in log.info.call_args_list)

    def test_regex_failure_fails_the_task(self):
        with (
            patch.object(task_processor, "_get_fsma_extractor", return_value=_stub_fsma_extractor(False)),
            patch.object(task_processor, "enqueue_task", return_value=1),
            patch(
                "services.nlp.app.extractor.extract_entities",
                side_effect=TypeError("regex extractor broken"),
            ),
        ):
            with pytest.raises(TypeError):
                task_processor._handle_nlp_extraction(_payload(), TENANT_ID)

    @pytest.mark.parametrize("attempts", [1, 3], ids=["retry", "dead"])
    @pytest.mark.parametrize(
        "failure",
        [
            "empty_payload",
            "missing_text",
            "missing_document_id",
            "extractor_import",
            "hardened_runtime",
            "hardened_import",
            "fsma_enqueue",
            "regex_enqueue",
            "fsma_no_graph_sink",
            "fsma_mixed_no_graph_sink",
            "fsma_mixed_regex_enqueue",
        ],
    )
    def test_worker_does_not_complete_failed_extraction(self, monkeypatch, failure, attempts):
        payload = _payload()
        extractor = _stub_fsma_extractor(review_required=failure == "fsma_enqueue")
        enqueue = MagicMock(return_value=None if failure.endswith("enqueue") else 1)
        if failure == "empty_payload":
            payload = {}
        elif failure == "missing_text":
            payload.pop("text")
        elif failure == "missing_document_id":
            payload.pop("document_id")
        elif failure == "hardened_runtime":
            extractor.extract.side_effect = RuntimeError("extraction failed")
        elif failure == "hardened_import":
            extractor.extract.side_effect = ImportError("extraction dependency missing")
        elif failure == "fsma_enqueue":
            payload["text"] = "hello world"
        elif failure in {"fsma_no_graph_sink", "fsma_mixed_no_graph_sink", "fsma_mixed_regex_enqueue"}:
            from services.nlp.app.extractors.fsma_extractor import FSMAExtractor

            extractor = FSMAExtractor()
            payload["text"] = BOL_WITH_EVENT_DATE if failure == "fsma_no_graph_sink" else MIXED_FSMA_AND_OBLIGATION_TEXT
        elif failure == "extractor_import":
            original_import = builtins.__import__

            def missing_extractor(name, *args, **kwargs):
                if name == "services.nlp.app.extractor":
                    raise ImportError("extractor unavailable")
                return original_import(name, *args, **kwargs)

            monkeypatch.setattr(builtins, "__import__", missing_extractor)

        original_payload = dict(payload)
        db = MagicMock()
        db.execute.return_value.rowcount = 1
        fake_database = ModuleType("services.admin.app.database")
        fake_database.SessionLocal = lambda: db
        fake_database.arm_global_admin_context = lambda session: None
        monkeypatch.setitem(sys.modules, "services.admin.app.database", fake_database)
        task = {
            "id": 71,
            "task_type": "nlp_extraction",
            "payload": payload,
            "tenant_id": TENANT_ID,
            "attempts": attempts,
            "max_attempts": 3,
        }
        with (
            patch.object(task_processor, "_shutdown_event") as shutdown,
            patch.object(task_processor, "_claim_task", return_value=task),
            patch.object(task_processor, "_get_fsma_extractor", return_value=extractor),
            patch.object(task_processor, "enqueue_task", enqueue),
            patch.object(task_processor, "_complete_task") as complete,
        ):
            shutdown.is_set.side_effect = [False, True]
            task_processor._worker_loop()

        complete.assert_not_called()
        db.execute.assert_called_once()
        sql, params = db.execute.call_args.args
        assert f"status = '{'pending' if attempts < 3 else 'dead'}'" in str(sql)
        assert params["id"] == 71
        assert params["error"]
        assert task["payload"] == original_payload
        if failure == "fsma_no_graph_sink":
            assert "graph sink unavailable" in params["error"]
            enqueue.assert_not_called()
        elif failure.startswith("fsma_mixed"):
            review_calls = _review_item_calls(enqueue)
            assert len(review_calls) == 1
            assert review_calls[0].args[1]["entity_type"] == "OBLIGATION"
            assert review_calls[0].kwargs["tenant_id"] == TENANT_ID
            assert review_calls[0].kwargs["idempotency_key"] == "review_item:doc-1:OBLIGATION:0"
            expected_error = (
                "Failed to enqueue NLP extraction review" if failure.endswith("enqueue") else "graph sink unavailable"
            )
            assert expected_error in params["error"]
        if attempts < 3:
            assert params["delay_seconds"] == 60
        db.commit.assert_called_once()

    @pytest.mark.parametrize("tenant_id", [TENANT_ID, None])
    def test_partial_retry_preserves_review_keys_and_row_tenant(self, tenant_id):
        extractor = _stub_fsma_extractor(review_required=True)
        payload = _payload(text=OBLIGATION_TEXT + " Records must be available for inspection.")
        enqueue = MagicMock(side_effect=[17, None, 18])
        with (
            patch.object(task_processor, "_get_fsma_extractor", return_value=extractor),
            patch.object(task_processor, "enqueue_task", enqueue),
        ):
            with pytest.raises(RuntimeError):
                task_processor._handle_nlp_extraction(payload, tenant_id)
            first_calls = enqueue.call_args_list[:]
            enqueue.reset_mock()
            enqueue.side_effect = None
            enqueue.return_value = 17
            task_processor._handle_nlp_extraction(payload, tenant_id)

        assert enqueue.call_args_list[:2] == first_calls
        assert all(c.kwargs["tenant_id"] == tenant_id for c in enqueue.call_args_list)
        keys = [c.kwargs["idempotency_key"] for c in enqueue.call_args_list]
        assert len(keys) == len(set(keys))


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
BOL_WITH_EVENT_DATE = BOL_MISSING_EVENT_DATE + "\nShip Date: 11/05/2025\n"
MIXED_FSMA_AND_OBLIGATION_TEXT = OBLIGATION_TEXT + "\n" + BOL_WITH_EVENT_DATE


def test_high_confidence_fsma_failure_preserves_independent_review_routing_on_retry():
    from services.nlp.app.extractors.fsma_extractor import FSMAExtractor

    extractor = FSMAExtractor()
    result = extractor.extract(MIXED_FSMA_AND_OBLIGATION_TEXT, "doc-1", tenant_id=TENANT_ID)
    assert len(result.ctes) == 1
    assert result.ctes[0].confidence == 1.0
    assert result.review_required is False
    payload = _payload(text=MIXED_FSMA_AND_OBLIGATION_TEXT, tenant_id="untrusted-payload-tenant")
    enqueue = MagicMock(return_value=17)

    with (
        patch.object(task_processor, "_get_fsma_extractor", return_value=extractor),
        patch.object(task_processor, "enqueue_task", enqueue),
    ):
        for _ in range(2):
            with pytest.raises(RuntimeError, match="graph sink unavailable"):
                task_processor._handle_nlp_extraction(payload, TENANT_ID)

    review_calls = _review_item_calls(enqueue)
    assert len(review_calls) == 2
    for call in review_calls:
        assert call.args[1]["entity_type"] == "OBLIGATION"
        assert call.args[1]["text"] == "Food facilities on the FTL shall maintain temperature records for 180 days"
        assert call.args[1]["confidence"] <= 0.60
        assert call.args[1]["tenant_id"] == TENANT_ID
        assert call.kwargs["tenant_id"] == TENANT_ID
        assert call.kwargs["idempotency_key"] == "review_item:doc-1:OBLIGATION:0"


def test_real_high_confidence_fsma_result_fails_without_graph_sink():
    from services.nlp.app.extractors.fsma_extractor import FSMAExtractor

    extractor = FSMAExtractor()
    result = extractor.extract(BOL_WITH_EVENT_DATE, "doc-1", tenant_id=TENANT_ID)
    assert len(result.ctes) == 1
    assert result.ctes[0].confidence == 1.0
    assert result.review_required is False
    assert extractor.route_extraction(result)["topic"] == "graph.update"

    with (
        patch.object(task_processor, "_get_fsma_extractor", return_value=extractor),
        patch.object(task_processor, "enqueue_task") as enqueue,
    ):
        with pytest.raises(RuntimeError, match="graph sink unavailable"):
            task_processor._handle_nlp_extraction(_payload(text=BOL_WITH_EVENT_DATE), TENANT_ID)
    enqueue.assert_not_called()


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
            task_processor._handle_nlp_extraction(_payload(text=BOL_MISSING_EVENT_DATE), TENANT_ID)

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
