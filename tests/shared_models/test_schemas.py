"""Tests for shared schemas module.

Covers:
- ObligationType enum
- JurisdictionScope enum
- Jurisdiction model
- Threshold model
- ExtractionPayload model
- GraphEvent model
- ReviewItem model
- FSMA 204 models (CTEType, Location, ProductDescription, KDE)
"""

from __future__ import annotations

from uuid import UUID, uuid4
from datetime import datetime, timezone

import pytest


class TestObligationType:
    """Tests for ObligationType enum."""

    def test_all_obligation_types_defined(self):
        """Verify all expected obligation types exist."""
        from shared.schemas import ObligationType
        
        expected = ["MUST", "MUST_NOT", "SHOULD", "MAY", "CONDUCT", 
                    "RECORDKEEPING", "REPORTING", "DISCLOSURE"]
        
        for obligation in expected:
            assert hasattr(ObligationType, obligation)

    def test_obligation_type_values(self):
        """Verify obligation type string values."""
        from shared.schemas import ObligationType
        
        assert ObligationType.MUST.value == "MUST"
        assert ObligationType.MUST_NOT.value == "MUST_NOT"


class TestJurisdictionScope:
    """Tests for JurisdictionScope enum."""

    def test_all_scopes_defined(self):
        """Verify all jurisdiction scopes exist."""
        from shared.schemas import JurisdictionScope
        
        assert hasattr(JurisdictionScope, "FEDERAL")
        assert hasattr(JurisdictionScope, "STATE")
        assert hasattr(JurisdictionScope, "MUNICIPAL")

    def test_scope_values(self):
        """Verify scope string values."""
        from shared.schemas import JurisdictionScope
        
        assert JurisdictionScope.FEDERAL.value == "federal"
        assert JurisdictionScope.STATE.value == "state"
        assert JurisdictionScope.MUNICIPAL.value == "municipal"


class TestJurisdiction:
    """Tests for Jurisdiction model."""

    def test_create_federal_jurisdiction(self):
        """Verify federal jurisdiction creation."""
        from shared.schemas import Jurisdiction, JurisdictionScope
        
        j = Jurisdiction(
            code="US",
            name="United States",
            scope=JurisdictionScope.FEDERAL,
        )
        
        assert j.code == "US"
        assert j.name == "United States"
        assert j.scope == JurisdictionScope.FEDERAL
        assert j.parent_code is None

    def test_create_state_jurisdiction_with_parent(self):
        """Verify state jurisdiction with parent."""
        from shared.schemas import Jurisdiction, JurisdictionScope
        
        j = Jurisdiction(
            code="US-NY",
            name="New York",
            scope=JurisdictionScope.STATE,
            parent_code="US",
        )
        
        assert j.code == "US-NY"
        assert j.name == "New York"
        assert j.parent_code == "US"

    def test_create_municipal_jurisdiction(self):
        """Verify municipal jurisdiction."""
        from shared.schemas import Jurisdiction, JurisdictionScope
        
        j = Jurisdiction(
            code="US-TX-AUS",
            name="Austin",
            scope=JurisdictionScope.MUNICIPAL,
            parent_code="US-TX",
        )
        
        assert j.code == "US-TX-AUS"
        assert j.name == "Austin"
        assert j.scope == JurisdictionScope.MUNICIPAL


class TestThreshold:
    """Tests for Threshold model."""

    def test_create_percentage_threshold(self):
        """Verify percentage threshold creation."""
        from shared.schemas import Threshold
        
        t = Threshold(value=8.0, unit="percent", operator="gte")
        
        assert t.value == 8.0
        assert t.unit == "percent"
        assert t.operator == "gte"

    def test_create_threshold_with_operator(self):
        """Verify threshold with comparison operator."""
        from shared.schemas import Threshold
        
        t = Threshold(value=5.0, unit="percent", operator="gte")
        
        assert t.operator == "gte"

    def test_threshold_with_context(self):
        """Verify threshold with context description."""
        from shared.schemas import Threshold
        
        t = Threshold(
            value=72,
            unit="hours",
            operator="lte",
            context="notification deadline",
        )
        
        assert t.context == "notification deadline"


class TestExtractionPayload:
    """Tests for ExtractionPayload model."""

    def _base_extraction_data(self):
        """Return minimal valid extraction data."""
        return {
            "subject": "financial institutions",
            "action": "must maintain",
            "obligation_type": "MUST",
            "confidence_score": 0.92,
            "source_text": "Banks must maintain capital",
            "source_offset": 0,
        }

    def test_create_basic_extraction(self):
        """Verify basic extraction creation."""
        from shared.schemas import ExtractionPayload
        
        e = ExtractionPayload(**self._base_extraction_data())
        
        assert e.source_text == "Banks must maintain capital"
        assert e.source_offset == 0

    def test_extraction_with_obligation_type(self):
        """Verify extraction with obligation type."""
        from shared.schemas import ExtractionPayload, ObligationType
        
        data = self._base_extraction_data()
        data["obligation_type"] = ObligationType.MUST
        
        e = ExtractionPayload(**data)
        
        assert e.obligation_type == ObligationType.MUST

    def test_extraction_with_confidence_score(self):
        """Verify extraction with confidence score."""
        from shared.schemas import ExtractionPayload
        
        data = self._base_extraction_data()
        data["confidence_score"] = 0.95
        
        e = ExtractionPayload(**data)
        
        assert e.confidence_score == 0.95

    def test_extraction_with_thresholds(self):
        """Verify extraction with threshold list."""
        from shared.schemas import ExtractionPayload, Threshold
        
        data = self._base_extraction_data()
        data["thresholds"] = [Threshold(value=8.0, unit="percent", operator="gte")]
        
        e = ExtractionPayload(**data)
        
        assert len(e.thresholds) == 1
        assert e.thresholds[0].value == 8.0


class TestGraphEvent:
    """Tests for GraphEvent model."""

    def _base_extraction(self):
        """Return a valid ExtractionPayload."""
        from shared.schemas import ExtractionPayload
        
        return ExtractionPayload(
            subject="financial institutions",
            action="must maintain",
            obligation_type="MUST",
            confidence_score=0.92,
            source_text="Test text",
            source_offset=0,
        )

    def test_create_graph_event(self):
        """Verify GraphEvent creation."""
        from shared.schemas import GraphEvent
        
        event = GraphEvent(
            event_type="create_provision",
            document_id="doc-123",
            doc_hash="hash-abc",
            extraction=self._base_extraction(),
            text_clean="Test text",
        )
        
        assert event.document_id == "doc-123"
        assert event.doc_hash == "hash-abc"

    def test_graph_event_auto_generates_event_id(self):
        """Verify event_id is auto-generated."""
        from shared.schemas import GraphEvent
        
        event = GraphEvent(
            event_type="create_provision",
            document_id="doc",
            doc_hash="hash",
            extraction=self._base_extraction(),
            text_clean="text",
        )
        
        assert event.event_id is not None
        assert len(event.event_id) > 0

    def test_graph_event_embedding_validation(self):
        """Verify embedding dimension validation."""
        from shared.schemas import GraphEvent
        
        # 768-dimensional embedding for sentence-transformers
        embedding = [0.0] * 768
        
        event = GraphEvent(
            event_type="create_provision",
            document_id="doc",
            doc_hash="hash",
            extraction=self._base_extraction(),
            text_clean="text",
            embedding=embedding,
        )
        
        assert len(event.embedding) == 768


class TestReviewItem:
    """Tests for ReviewItem model."""

    def _base_extraction(self):
        """Return a valid ExtractionPayload."""
        from shared.schemas import ExtractionPayload
        
        return ExtractionPayload(
            subject="financial institutions",
            action="must maintain",
            obligation_type="MUST",
            confidence_score=0.72,
            source_text="Banks must",
            source_offset=0,
        )

    def test_create_review_item(self):
        """Verify ReviewItem creation."""
        from shared.schemas import ReviewItem
        
        item = ReviewItem(
            document_id="doc-123",
            extraction=self._base_extraction(),
        )
        
        assert item.document_id == "doc-123"
        assert item.status == "pending"  # Default

    def test_review_item_auto_generates_id(self):
        """Verify id is auto-generated as UUID."""
        from shared.schemas import ReviewItem
        
        item = ReviewItem(
            document_id="doc",
            extraction=self._base_extraction(),
        )
        
        assert item.id is not None
        assert isinstance(item.id, UUID)


class TestCTEType:
    """Tests for FSMA CTEType enum."""

    def test_all_cte_types_defined(self):
        """Verify all CTE types exist."""
        from shared.schemas import CTEType
        
        expected = ["SHIPPING", "RECEIVING", "TRANSFORMATION", 
                    "CREATION", "INITIAL_PACKING"]
        
        for cte in expected:
            assert hasattr(CTEType, cte)


class TestLocation:
    """Tests for FSMA Location model."""

    def test_create_location(self):
        """Verify Location creation."""
        from shared.schemas import Location
        
        loc = Location(
            gln="1234567890123",
            name="Distribution Center",
            address="123 Main St",
        )
        
        assert loc.gln == "1234567890123"
        assert loc.name == "Distribution Center"

    def test_location_optional_fields(self):
        """Verify Location with optional fields."""
        from shared.schemas import Location
        
        loc = Location(name="Warehouse")
        
        assert loc.gln is None
        assert loc.address is None


class TestProductDescription:
    """Tests for FSMA ProductDescription model."""

    def test_create_product_description(self):
        """Verify ProductDescription creation."""
        from shared.schemas import ProductDescription
        
        prod = ProductDescription(text="Romaine Lettuce 12ct")
        
        assert prod.text == "Romaine Lettuce 12ct"

    def test_product_with_identifiers(self):
        """Verify ProductDescription with SKU and GTIN."""
        from shared.schemas import ProductDescription
        
        prod = ProductDescription(
            text="Romaine Lettuce",
            sku="ROM-12CT",
            gtin="00012345678901",
        )
        
        assert prod.sku == "ROM-12CT"
        assert prod.gtin == "00012345678901"


class TestKDE:
    """Tests for FSMA Key Data Element model."""

    def test_create_kde(self):
        """Verify KDE creation."""
        from shared.schemas import KDE
        
        kde = KDE(
            name="traceability_lot_code",
            value="LOT-2025-001",
        )
        
        assert kde.name == "traceability_lot_code"
        assert kde.value == "LOT-2025-001"

    def test_kde_with_confidence(self):
        """Verify KDE with confidence score."""
        from shared.schemas import KDE
        
        kde = KDE(
            name="lot_code",
            value="ABC123",
            confidence=0.92,
        )
        
        assert kde.confidence == 0.92
