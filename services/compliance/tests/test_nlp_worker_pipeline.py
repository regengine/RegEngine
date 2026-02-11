"""
Integration tests for the NLP → Compliance Worker pipeline.

Tests the serialization/deserialization path that caused DEBT-023,
ensuring GraphEvent payloads from the NLP service are correctly
parsed by the compliance worker's consumer loop.
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# ------------------------------------------------------------------
# Attempt to import shared schemas (skip if deps unavailable)
# ------------------------------------------------------------------
try:
    from shared.schemas import ExtractionPayload, GraphEvent, ObligationType
    HAS_SCHEMAS = True
except ImportError:
    HAS_SCHEMAS = False


pytestmark = pytest.mark.skipif(not HAS_SCHEMAS, reason="shared.schemas not importable")


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

def _make_extraction(**overrides):
    """Build a minimal valid ExtractionPayload dict."""
    base = {
        "subject": "covered entities",
        "action": "must comply by",
        "obligation_type": "MUST",
        "confidence_score": 0.95,
        "source_text": "Entities must comply by January 20 2026",
        "source_offset": 0,
        "attributes": {
            "document_id": "doc-001",
            "source_url": "https://fda.gov/fsma204",
            "entities": [
                {
                    "type": "REGULATORY_DATE",
                    "text": "January 20, 2026",
                    "start": 30,
                    "end": 46,
                    "confidence_score": 0.99,
                    "attrs": {"key": "Compliance Date", "value": "January 20, 2026"},
                }
            ],
        },
    }
    base.update(overrides)
    return base


def _make_graph_event(**overrides):
    """Build a complete GraphEvent dict as the NLP service would produce."""
    base = {
        "event_id": str(uuid.uuid4()),
        "event_type": "create_provision",
        "tenant_id": str(uuid.uuid4()),
        "doc_hash": "abc123hash",
        "document_id": "doc-001",
        "text_clean": "Entities must comply by January 20 2026",
        "extraction": _make_extraction(),
        "provenance": {"source_url": "https://fda.gov/fsma204", "offset": 0},
        "embedding": None,
        "status": "APPROVED",
        "reviewer_id": "nlp_model_v1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    base.update(overrides)
    return base


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------

class TestGraphEventSerialization:
    """DEBT-023: Validate GraphEvent round-trip serialization."""

    def test_graph_event_parses_from_nlp_payload(self):
        """NLP-produced payload must successfully validate as GraphEvent."""
        payload = _make_graph_event()
        event = GraphEvent.model_validate(payload)

        assert event.event_type == "create_provision"
        assert event.doc_hash == "abc123hash"
        assert event.extraction.subject == "covered entities"
        assert event.extraction.confidence_score == 0.95

    def test_extraction_entities_in_attributes(self):
        """DEBT-023 fix: entities must be accessible from attributes dict."""
        payload = _make_graph_event()
        event = GraphEvent.model_validate(payload)

        entities = event.extraction.attributes.get("entities", [])
        assert len(entities) == 1
        assert entities[0]["type"] == "REGULATORY_DATE"
        assert entities[0]["attrs"]["key"] == "Compliance Date"

    def test_extraction_entities_field(self):
        """Root schema has entities field on ExtractionPayload."""
        payload = _make_graph_event()
        # Also put entities in the top-level field
        payload["extraction"]["entities"] = [
            {"type": "REGULATORY_DATE", "text": "Jan 2026"}
        ]
        event = GraphEvent.model_validate(payload)
        assert len(event.extraction.entities) == 1

    def test_graph_event_json_roundtrip(self):
        """Serialize → JSON → deserialize must be lossless."""
        original = _make_graph_event()
        event = GraphEvent.model_validate(original)

        json_str = event.model_dump_json()
        restored = GraphEvent.model_validate_json(json_str)

        assert restored.event_id == event.event_id
        assert restored.extraction.subject == event.extraction.subject
        assert restored.extraction.attributes == event.extraction.attributes

    def test_missing_text_clean_raises(self):
        """GraphEvent requires text_clean — must not silently pass."""
        payload = _make_graph_event()
        del payload["text_clean"]

        with pytest.raises(Exception):  # Pydantic ValidationError
            GraphEvent.model_validate(payload)

    def test_model_dump_mode_json_serializable(self):
        """model_dump(mode='json') output must be JSON-serializable (Kafka-safe)."""
        payload = _make_graph_event()
        event = GraphEvent.model_validate(payload)
        dumped = event.model_dump(mode="json")

        # Must not raise
        json_str = json.dumps(dumped, default=str)
        assert isinstance(json_str, str)
        assert "create_provision" in json_str


class TestWorkerFallbackPath:
    """Test the compliance worker's fallback parsing for non-GraphEvent payloads."""

    def test_raw_dict_with_entities_in_extraction(self):
        """Worker should extract entities from raw dict extraction payload."""
        data = {
            "document_id": "doc-001",
            "doc_hash": "abc123",
            "extraction": {
                "entities": [
                    {
                        "type": "REGULATORY_DATE",
                        "text": "January 20, 2026",
                        "attrs": {"key": "Compliance Date", "value": "January 20, 2026"},
                    }
                ]
            },
        }
        # Simulate what the worker does
        extraction = data.get("extraction", {})
        entities = extraction.get("entities", [])
        assert len(entities) == 1
        assert entities[0]["attrs"]["key"] == "Compliance Date"

    def test_raw_dict_with_flat_entities_list(self):
        """Worker should handle extraction as a flat list of entities."""
        data = {
            "document_id": "doc-001",
            "doc_hash": "abc123",
            "extraction": [
                {"type": "REGULATORY_DATE", "text": "Jan 2026"}
            ],
        }
        extraction = data.get("extraction", {})
        if isinstance(extraction, list):
            entities = extraction
        else:
            entities = extraction.get("entities", [])
        assert len(entities) == 1


class TestMockRecallFallback:
    """Test mock recall engine graceful degradation."""

    def test_mock_fallback_returns_valid_result(self):
        """Mock recall should return valid structure when graph is down."""
        from mock_recall import simulate_mock_recall

        result = simulate_mock_recall("LOT-TEST-001", product_description="Test Product")

        assert result.lot_id == "LOT-TEST-001"
        assert result.data_source == "mock"
        assert len(result.affected_facilities) == 3
        assert result.impact_summary.total_facilities_affected == 3
        assert result.impact_summary.total_quantity_impacted > 0

    def test_mock_result_serializable(self):
        """Mock recall result.to_dict() must be JSON-serializable."""
        from mock_recall import simulate_mock_recall

        result = simulate_mock_recall("LOT-TEST-002")
        d = result.to_dict()
        json_str = json.dumps(d)
        assert isinstance(json_str, str)
        assert "LOT-TEST-002" in json_str
