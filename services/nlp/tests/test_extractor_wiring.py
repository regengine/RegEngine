"""
Tests that the structured extractors (FSMAExtractor, LLMGenerativeExtractor)
are actually wired into the Kafka consumer pipeline.

Context (#1194):
Before this wiring landed, both classes were imported by the package but
never instantiated from the consumer loop — every document fell through
to the regex-only path and bypassed the FSMA KDE-minimum gate entirely.

These tests use mocked Kafka + extractor classes to assert:
  1. FSMAExtractor is invoked per document when the feature flag is on.
  2. Its routing helper is called, and the event goes to the topic
     it returned.
  3. The flag defaults cover (on for FSMA, off for LLM).
  4. LLM fallback only fires when high-confidence extractions were not
     produced by the regex/FSMA pass AND the flag is on.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _env_setup(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    # Ensure repo root is on sys.path so `services.nlp.app.*` resolves.
    _repo_root = Path(__file__).resolve().parents[3]
    if str(_repo_root) not in sys.path:
        sys.path.insert(0, str(_repo_root))
    yield


def _reload_consumer():
    """Import or reimport services.nlp.app.consumer so env changes stick."""
    from services.nlp.app import consumer as consumer_mod

    return importlib.reload(consumer_mod)


class TestFlagDefaults:
    def test_fsma_flag_default_on(self, monkeypatch):
        """
        #1194: FSMA extractor should default ON so every document passes
        through KDE gating unless an operator explicitly opts out.
        """
        monkeypatch.delenv("NLP_ENABLE_FSMA_EXTRACTOR", raising=False)
        consumer = _reload_consumer()
        assert consumer.NLP_ENABLE_FSMA_EXTRACTOR is True

    def test_llm_flag_default_off(self, monkeypatch):
        """
        #1194: LLM extractor defaults OFF because the path has per-token
        cost. Operators must opt in explicitly via NLP_ENABLE_LLM_EXTRACTOR=true.
        """
        monkeypatch.delenv("NLP_ENABLE_LLM_EXTRACTOR", raising=False)
        consumer = _reload_consumer()
        assert consumer.NLP_ENABLE_LLM_EXTRACTOR is False

    def test_fsma_flag_honored_when_off(self, monkeypatch):
        monkeypatch.setenv("NLP_ENABLE_FSMA_EXTRACTOR", "false")
        consumer = _reload_consumer()
        assert consumer.NLP_ENABLE_FSMA_EXTRACTOR is False

    def test_llm_flag_honored_when_on(self, monkeypatch):
        monkeypatch.setenv("NLP_ENABLE_LLM_EXTRACTOR", "true")
        consumer = _reload_consumer()
        assert consumer.NLP_ENABLE_LLM_EXTRACTOR is True


class TestFSMAExtractorIsWired:
    def test_run_fsma_extractor_invokes_extract_and_route(self):
        """
        _run_fsma_extractor must call FSMAExtractor.extract and
        FSMAExtractor.route_extraction, and must forward the resulting
        topic to the producer.
        """
        consumer = _reload_consumer()

        mock_extractor = MagicMock()
        result = MagicMock()
        result.ctes = [MagicMock(), MagicMock()]
        result.review_required = False
        mock_extractor.extract.return_value = result
        mock_extractor.route_extraction.return_value = {
            "topic": "graph.update",
            "payload": {"event_type": "fsma.extraction"},
            "routed_at": "2026-04-17T00:00:00Z",
        }

        mock_producer = MagicMock()

        with patch.object(consumer, "_get_fsma_extractor", return_value=mock_extractor):
            summary = consumer._run_fsma_extractor(
                text="sample document text",
                doc_id="doc-1",
                doc_hash="hash-1",
                producer=mock_producer,
                tenant_id="tenant-a",
                kafka_headers=[],
            )

        mock_extractor.extract.assert_called_once_with("sample document text", "doc-1", tenant_id="tenant-a")
        mock_extractor.route_extraction.assert_called_once_with(result)
        mock_producer.send.assert_called_once()
        send_kwargs = mock_producer.send.call_args
        assert send_kwargs.args[0] == "graph.update"
        assert summary["status"] == "ok"
        assert summary["routed"] == "graph.update"
        assert summary["cte_count"] == 2

    def test_run_fsma_extractor_routes_low_confidence_to_review(self):
        """Routing must respect FSMAExtractor's review_required flag."""
        consumer = _reload_consumer()

        mock_extractor = MagicMock()
        result = MagicMock()
        result.ctes = [MagicMock()]
        result.review_required = True
        mock_extractor.extract.return_value = result
        mock_extractor.route_extraction.return_value = {
            "topic": "nlp.needs_review",
            "payload": {"event_type": "fsma.extraction"},
            "routed_at": "2026-04-17T00:00:00Z",
        }

        mock_producer = MagicMock()

        with patch.object(consumer, "_get_fsma_extractor", return_value=mock_extractor):
            summary = consumer._run_fsma_extractor(
                text="low confidence doc",
                doc_id="doc-2",
                doc_hash="hash-2",
                producer=mock_producer,
                tenant_id="tenant-a",
                kafka_headers=[],
            )
        assert summary["routed"] == "nlp.needs_review"
        assert summary["high_confidence"] is False

    def test_run_fsma_extractor_swallows_errors(self):
        """Extractor failures must not crash the consumer loop."""
        consumer = _reload_consumer()

        mock_extractor = MagicMock()
        mock_extractor.extract.side_effect = RuntimeError("model exploded")

        mock_producer = MagicMock()
        with patch.object(consumer, "_get_fsma_extractor", return_value=mock_extractor):
            summary = consumer._run_fsma_extractor(
                text="boom",
                doc_id="doc-3",
                doc_hash="hash-3",
                producer=mock_producer,
                tenant_id="tenant-a",
                kafka_headers=[],
            )
        assert summary["status"] == "error"
        mock_producer.send.assert_not_called()


class TestLLMExtractorIsWired:
    def test_run_llm_extractor_invokes_extract(self):
        """_run_llm_extractor must forward doc_id as correlation_id."""
        consumer = _reload_consumer()

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = [{"provision_text": "must report"}]

        with patch.object(consumer, "_get_llm_extractor", return_value=mock_extractor):
            out = consumer._run_llm_extractor(
                text="some regulation",
                doc_id="doc-xyz",
                jurisdiction="US-FDA",
            )
        mock_extractor.extract.assert_called_once_with(
            text="some regulation",
            jurisdiction="US-FDA",
            correlation_id="doc-xyz",
        )
        assert out == [{"provision_text": "must report"}]

    def test_run_llm_extractor_swallows_errors(self):
        """LLM failures must not crash the consumer loop."""
        consumer = _reload_consumer()

        mock_extractor = MagicMock()
        mock_extractor.extract.side_effect = RuntimeError("inference failed")

        with patch.object(consumer, "_get_llm_extractor", return_value=mock_extractor):
            out = consumer._run_llm_extractor(
                text="boom",
                doc_id="doc-err",
                jurisdiction="unknown",
            )
        assert out == []


class TestExtractorClassesImportable:
    def test_fsma_extractor_imported(self):
        """Defense against regressions that re-orphan the class (#1194)."""
        consumer = _reload_consumer()

        assert consumer.FSMAExtractor is not None
        from services.nlp.app.extractors import FSMAExtractor as CanonicalFSMA

        assert consumer.FSMAExtractor is CanonicalFSMA

    def test_llm_extractor_imported(self):
        consumer = _reload_consumer()

        assert consumer.LLMGenerativeExtractor is not None
        from services.nlp.app.extractors import LLMGenerativeExtractor as CanonicalLLM

        assert consumer.LLMGenerativeExtractor is CanonicalLLM


# ----------------------------------------------------------------------
# #2947 — the LLM extractor's output must reach the review queue
# ----------------------------------------------------------------------
#
# `_run_llm_extractor` was called, counted into a log line, and discarded: the
# routing loop below it iterates `extractions`, which only the regex path fed.
# Enabling NLP_ENABLE_LLM_EXTRACTOR paid a third-party provider for output
# nothing read. These tests pin the bridge, and pin it as fail-closed: nothing
# from a generative extractor may auto-publish on its own confidence.


def _llm_item(**overrides):
    """Build a real LLMExtraction; overrides replace defaults."""
    from services.nlp.app.extractors.llm_extractor import LLMExtraction

    fields = {
        "provision_text": "Covered entities shall maintain traceability records.",
        "obligation_type": "REQUIREMENT",
        "confidence": 0.91,
        "source_document_id": "doc-llm",
        "source_span_start": 120,
        "source_span_end": 172,
    }
    fields.update(overrides)
    return LLMExtraction(**fields)


def _bridge(items):
    from services.nlp.app.consumer import _convert_llm_results_to_extractions

    return _convert_llm_results_to_extractions(
        items, doc_id="doc-llm", source_url="https://example.gov/rule.pdf"
    )


class TestLLMResultsReachTheReviewQueue:
    def test_results_are_converted_into_extractions(self):
        extractions = _bridge([_llm_item()])
        assert len(extractions) == 1
        extraction = extractions[0]
        assert extraction.source_text == (
            "Covered entities shall maintain traceability records."
        )
        assert extraction.source_offset == 120
        assert extraction.obligation_type.value == "MUST"
        assert extraction.attributes["extractor"] == "llm_generative_v1"
        assert extraction.attributes["document_id"] == "doc-llm"

    def test_prohibition_maps_to_must_not(self):
        extraction = _bridge(
            [_llm_item(obligation_type="PROHIBITION", provision_text="No person shall adulterate food.")]
        )[0]
        assert extraction.obligation_type.value == "MUST_NOT"

    def test_exemption_does_not_become_a_mandate(self):
        extraction = _bridge([_llm_item(obligation_type="EXEMPTION")])[0]
        assert extraction.obligation_type.value == "MAY"

    def test_reporting_is_preserved(self):
        extraction = _bridge([_llm_item(obligation_type="REPORTING")])[0]
        assert extraction.obligation_type.value == "REPORTING"

    def test_self_reported_confidence_cannot_unlock_auto_approval(self):
        from services.nlp.app.consumer import _current_thresholds

        extraction = _bridge([_llm_item(confidence=1.0)])[0]
        _high, medium = _current_thresholds()
        assert extraction.confidence_score < medium
        assert extraction.attributes["llm_reported_confidence"] == 1.0

    def test_needs_review_item_routes_to_review_not_graph(self):
        from unittest.mock import MagicMock as _MagicMock

        from services.nlp.app.consumer import (
            TOPIC_GRAPH_UPDATE,
            TOPIC_NEEDS_REVIEW,
            _route_extraction,
        )

        extraction = _bridge(
            [_llm_item(confidence=1.0, needs_review=True, review_reason="output_injection_marker")]
        )[0]
        producer = _MagicMock()
        _route_extraction(
            extraction,
            doc_id="doc-llm",
            doc_hash="hash-llm",
            source_url="https://example.gov/rule.pdf",
            producer=producer,
            tenant_id="tenant-a",
        )
        producer.send.assert_called_once()
        assert producer.send.call_args.args[0] == TOPIC_NEEDS_REVIEW
        assert producer.send.call_args.args[0] != TOPIC_GRAPH_UPDATE

    def test_guardrail_flags_are_surfaced_to_the_reviewer(self):
        from services.nlp.app.consumer import _build_review_reasons

        extraction = _bridge(
            [
                _llm_item(
                    needs_review=True,
                    review_reason="output_injection_marker",
                    truncated_input=True,
                )
            ]
        )[0]
        codes = {r["reason_code"] for r in _build_review_reasons(extraction, "low")}
        assert "llm_flagged_for_review" in codes
        assert "llm_truncated_input" in codes

    def test_item_without_a_provenance_span_is_not_routed(self):
        """Fail closed: an item with no quote cannot be checked against source."""
        assert _bridge([{"obligation_type": "REQUIREMENT", "confidence": 0.9}]) == []

    def test_every_llm_extraction_field_is_read_by_the_bridge(self):
        """#2947 acceptance: no LLMExtraction field may be write-only."""
        import inspect

        from services.nlp.app.consumer import _convert_llm_results_to_extractions
        from services.nlp.app.extractors.llm_extractor import LLMExtraction

        bridge_source = inspect.getsource(_convert_llm_results_to_extractions)
        unread = [
            name for name in LLMExtraction.model_fields if name not in bridge_source
        ]
        assert not unread, f"LLMExtraction fields with no non-test reader: {unread}"


class TestConsumerLoopDoesNotDiscardLLMResults:
    def test_llm_results_is_consumed_not_just_counted(self):
        """The defect in source form: `llm_results` used only by `len()`."""
        import ast

        consumer = _reload_consumer()
        tree = ast.parse(Path(consumer.__file__).read_text())

        counted = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "len"
            ):
                counted.update(id(arg) for arg in node.args)

        real_uses = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Name)
            and node.id == "llm_results"
            and isinstance(node.ctx, ast.Load)
            and id(node) not in counted
        ]
        assert real_uses, (
            "llm_results is only counted into a log line — the paid LLM call "
            "produces nothing any consumer reads (#2947)"
        )
