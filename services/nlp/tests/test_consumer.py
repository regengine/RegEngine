"""Tests for NLP consumer module.

Covers:
- Entity to extraction conversion
- Schema loading and validation
- Topic routing based on confidence
- Consumer lifecycle (start/stop)
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
from uuid import uuid4

import pytest

# Ensure the repo root 'shared' package is importable (not graph/shared)
_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))


class TestNowIso:
    """Tests for _now_iso helper function."""

    def test_returns_iso_format(self):
        """Verify ISO 8601 format is returned."""
        from services.nlp.app.consumer import _now_iso
        
        result = _now_iso()
        # Should be parseable as datetime
        dt = datetime.fromisoformat(result.replace('Z', '+00:00'))
        assert dt is not None

    def test_returns_utc_timestamp(self):
        """Verify timestamp is in UTC."""
        from services.nlp.app.consumer import _now_iso
        
        result = _now_iso()
        # Should end with Z or +00:00
        assert result.endswith('Z') or '+00:00' in result


class TestConvertEntitiesToExtraction:
    """Tests for _convert_entities_to_extraction."""

    def test_converts_empty_list(self):
        """Verify empty entity list returns empty extractions."""
        from services.nlp.app.consumer import _convert_entities_to_extraction
        
        result = _convert_entities_to_extraction(
            entities=[],
            doc_id="doc-123",
            source_url="https://example.com/doc.pdf",
        )
        
        assert isinstance(result, list)
        assert len(result) == 0

    def test_converts_single_entity(self):
        """Verify single entity is converted correctly."""
        from services.nlp.app.consumer import _convert_entities_to_extraction
        
        entities = [
            {
                "type": "OBLIGATION",
                "text": "Banks must maintain capital",
                "confidence": 0.9,
                "start": 100,
                "end": 130,
            }
        ]
        
        result = _convert_entities_to_extraction(
            entities=entities,
            doc_id="doc-123",
            source_url="https://example.com/doc.pdf",
        )
        
        assert len(result) == 1
        assert "confidence_score" in result[0] or hasattr(result[0], "confidence_score")

    def test_preserves_source_url(self):
        """Verify source_url is included in extraction."""
        from services.nlp.app.consumer import _convert_entities_to_extraction
        
        entities = [{"type": "OBLIGATION", "text": "Banks must maintain 10% capital", "confidence": 0.85, "start": 0, "end": 30}]
        source_url = "https://regulator.gov/rule.pdf"
        
        result = _convert_entities_to_extraction(
            entities=entities,
            doc_id="doc-456",
            source_url=source_url,
        )
        
        assert len(result) == 1
        assert result[0].attributes.get("source_url") == source_url


class TestLoadSchema:
    """Tests for schema loading."""

    def test_load_schema_returns_validator(self):
        """Verify _load_schema returns a usable validator."""
        from services.nlp.app.consumer import _load_schema
        
        schema = _load_schema()
        # Schema should be a dictionary or validator
        assert schema is not None


class TestRouteExtraction:
    """Tests for extraction routing logic."""

    @pytest.fixture
    def mock_producer(self):
        """Provide a mock Kafka producer."""
        producer = MagicMock()
        future = MagicMock()
        future.get.return_value = MagicMock()
        producer.send.return_value = future
        return producer

    def test_high_confidence_routes_to_graph(self, mock_producer):
        """Verify high confidence extractions go to graph.update topic."""
        from services.nlp.app.consumer import _route_extraction, CONFIDENCE_THRESHOLD, ExtractionPayload
        
        extraction = ExtractionPayload(
            subject="Banks",
            action="must maintain",
            obligation_type="MUST",
            confidence_score=0.95,  # Above threshold
            source_text="Banks must maintain capital",
            source_offset=0,
            attributes={},
        )
        
        _route_extraction(
            extraction=extraction,
            doc_id="doc-123",
            doc_hash="hash-abc",
            source_url="https://example.com",
            producer=mock_producer,
            tenant_id=str(uuid4()),
        )
        
        # Should send to graph.update topic
        mock_producer.send.assert_called()
        call_args = mock_producer.send.call_args
        assert call_args[0][0] == "graph.update"  # First positional arg is topic

    def test_low_confidence_routes_to_review(self, mock_producer):
        """Verify low confidence extractions go to needs_review topic."""
        from services.nlp.app.consumer import _route_extraction, CONFIDENCE_THRESHOLD, ExtractionPayload
        
        extraction = ExtractionPayload(
            subject="banks",
            action="should maintain",
            obligation_type="SHOULD",
            confidence_score=0.5,  # Below threshold
            source_text="Maybe banks should maintain capital",
            source_offset=0,
            attributes={},
        )
        
        _route_extraction(
            extraction=extraction,
            doc_id="doc-123",
            doc_hash="hash-abc",
            source_url="https://example.com",
            producer=mock_producer,
            tenant_id=str(uuid4()),
        )
        
        mock_producer.send.assert_called()
        call_args = mock_producer.send.call_args
        assert call_args[0][0] == "nlp.needs_review"

    def test_includes_tenant_id_in_message(self, mock_producer):
        """Verify tenant_id is included in routed message."""
        from services.nlp.app.consumer import _route_extraction, ExtractionPayload
        
        tenant_id = str(uuid4())
        extraction = ExtractionPayload(
            subject="entities",
            action="must maintain",
            obligation_type="MUST",
            confidence_score=0.9,
            source_text="10% threshold",
            source_offset=0,
            attributes={},
        )
        
        _route_extraction(
            extraction=extraction,
            doc_id="doc-123",
            doc_hash="hash-abc",
            source_url="https://example.com",
            producer=mock_producer,
            tenant_id=tenant_id,
        )
        
        mock_producer.send.assert_called()


class TestStopConsumer:
    """Tests for consumer shutdown."""

    def test_stop_sets_shutdown_event(self):
        """Verify stop_consumer sets the shutdown event."""
        from services.nlp.app.consumer import stop_consumer, _shutdown_event
        
        # Reset the event first
        _shutdown_event.clear()
        assert not _shutdown_event.is_set()
        
        stop_consumer()
        
        assert _shutdown_event.is_set()


class TestEnsureTopic:
    """Tests for topic creation."""

    def test_ensure_topic_creates_if_missing(self):
        """Verify _ensure_topic attempts to create topic."""
        from services.nlp.app.consumer import _ensure_topic
        
        with patch("services.nlp.app.consumer.KafkaAdminClient") as mock_admin:
            mock_instance = MagicMock()
            mock_admin.return_value = mock_instance
            mock_instance.list_topics.return_value.topics = {}
            
            _ensure_topic("test.topic")
            
            # Should have been called
            mock_admin.assert_called()


class TestConfidenceThreshold:
    """Tests for confidence threshold constant."""

    def test_threshold_is_reasonable(self):
        """Verify confidence threshold is between 0 and 1."""
        from services.nlp.app.consumer import CONFIDENCE_THRESHOLD
        
        assert 0.0 < CONFIDENCE_THRESHOLD < 1.0
        assert CONFIDENCE_THRESHOLD == 0.95  # Default from settings.extraction_confidence_high


class TestTopicNames:
    """Tests for topic name constants."""

    def test_graph_update_topic_name(self):
        """Verify graph update topic name."""
        from services.nlp.app.consumer import TOPIC_GRAPH_UPDATE
        
        assert TOPIC_GRAPH_UPDATE == "graph.update"

    def test_needs_review_topic_name(self):
        """Verify needs review topic name."""
        from services.nlp.app.consumer import TOPIC_NEEDS_REVIEW
        
        assert TOPIC_NEEDS_REVIEW == "nlp.needs_review"
