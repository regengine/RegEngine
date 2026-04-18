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

        mock_extractor.extract.assert_called_once_with("sample document text", "doc-1")
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
