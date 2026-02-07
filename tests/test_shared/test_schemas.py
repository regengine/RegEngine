"""Unit tests for shared/schemas.py canonical data models."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from uuid import UUID

from shared.schemas import (
    ObligationType,
    Threshold,
    ExtractionPayload,
    GraphEvent,
    ReviewItem,
)


class TestThreshold:
    """Tests for Threshold model."""

    def test_valid_threshold(self):
        """Test creating a valid threshold."""
        threshold = Threshold(
            value=5.0,
            unit="percent",
            operator="gte",
            context="capital requirement",
        )
        assert threshold.value == 5.0
        assert threshold.unit == "percent"
        assert threshold.operator == "gte"
        assert threshold.context == "capital requirement"

    def test_threshold_operators(self):
        """Test all valid threshold operators."""
        valid_operators = ["gt", "lt", "eq", "gte", "lte"]
        for op in valid_operators:
            threshold = Threshold(value=10.0, unit="USD", operator=op)
            assert threshold.operator == op

    def test_invalid_operator(self):
        """Test that invalid operators are rejected."""
        with pytest.raises(ValueError):
            Threshold(value=10.0, unit="USD", operator="invalid")


class TestExtractionPayload:
    """Tests for ExtractionPayload model."""

    def test_valid_extraction(self):
        """Test creating a valid extraction payload."""
        extraction = ExtractionPayload(
            subject="financial institutions",
            action="must maintain",
            object="capital reserves",
            obligation_type=ObligationType.MUST,
            thresholds=[
                Threshold(value=8.0, unit="percent", operator="gte")
            ],
            confidence_score=0.92,
            source_text="Financial institutions must maintain capital reserves of at least 8%",
            source_offset=1024,
            jurisdiction="US-SEC",
        )
        assert extraction.subject == "financial institutions"
        assert extraction.obligation_type == ObligationType.MUST
        assert extraction.confidence_score == 0.92
        assert len(extraction.thresholds) == 1

    def test_confidence_score_validation(self):
        """Test that confidence score is validated to 0-1 range."""
        # Valid scores
        for score in [0.0, 0.5, 1.0]:
            extraction = ExtractionPayload(
                subject="test",
                action="must",
                obligation_type=ObligationType.MUST,
                confidence_score=score,
                source_text="test",
                source_offset=0,
            )
            assert extraction.confidence_score == score

        # Invalid scores
        with pytest.raises(ValueError):
            ExtractionPayload(
                subject="test",
                action="must",
                obligation_type=ObligationType.MUST,
                confidence_score=1.5,  # > 1.0
                source_text="test",
                source_offset=0,
            )

        with pytest.raises(ValueError):
            ExtractionPayload(
                subject="test",
                action="must",
                obligation_type=ObligationType.MUST,
                confidence_score=-0.1,  # < 0.0
                source_text="test",
                source_offset=0,
            )

    def test_optional_fields(self):
        """Test that optional fields default correctly."""
        extraction = ExtractionPayload(
            subject="test",
            action="must",
            obligation_type=ObligationType.MUST,
            confidence_score=0.85,
            source_text="test text",
            source_offset=100,
        )
        assert extraction.provision_id is None
        assert extraction.object is None
        assert extraction.effective_date is None
        assert extraction.jurisdiction is None
        assert extraction.thresholds == []
        assert extraction.attributes == {}


class TestGraphEvent:
    """Tests for GraphEvent model."""

    def test_valid_graph_event(self):
        """Test creating a valid graph event."""
        extraction = ExtractionPayload(
            subject="financial institutions",
            action="must maintain",
            obligation_type=ObligationType.MUST,
            confidence_score=0.92,
            source_text="Financial institutions must maintain capital reserves",
            source_offset=1024,
        )

        event = GraphEvent(
            event_type="approve_provision",
            doc_hash="abc123",
            document_id="doc_001",
            text_clean="Financial institutions must maintain capital reserves",
            extraction=extraction,
            provenance={"source_url": "https://example.com/reg.pdf", "page": 5},
            status="APPROVED",
        )

        assert event.event_type == "approve_provision"
        assert event.doc_hash == "abc123"
        assert event.document_id == "doc_001"
        assert event.status == "APPROVED"
        assert event.extraction.confidence_score == 0.92

    def test_embedding_dimension_validation(self):
        """Test that embedding dimension is validated to 768."""
        extraction = ExtractionPayload(
            subject="test",
            action="must",
            obligation_type=ObligationType.MUST,
            confidence_score=0.9,
            source_text="test",
            source_offset=0,
        )

        # Valid 768-dimensional embedding
        valid_embedding = [0.1] * 768
        event = GraphEvent(
            event_type="create_provision",
            doc_hash="abc123",
            document_id="doc_001",
            text_clean="test",
            extraction=extraction,
            embedding=valid_embedding,
        )
        assert len(event.embedding) == 768

        # Invalid embedding dimension
        with pytest.raises(ValueError, match="must be 768-dimensional"):
            GraphEvent(
                event_type="create_provision",
                doc_hash="abc123",
                document_id="doc_001",
                text_clean="test",
                extraction=extraction,
                embedding=[0.1] * 500,  # Wrong dimension
            )

    def test_event_id_auto_generation(self):
        """Test that event_id is auto-generated if not provided."""
        extraction = ExtractionPayload(
            subject="test",
            action="must",
            obligation_type=ObligationType.MUST,
            confidence_score=0.9,
            source_text="test",
            source_offset=0,
        )

        event = GraphEvent(
            event_type="create_provision",
            doc_hash="abc123",
            document_id="doc_001",
            text_clean="test",
            extraction=extraction,
        )

        assert event.event_id is not None
        assert isinstance(event.event_id, str)

    def test_timestamp_auto_generation(self):
        """Test that timestamp is auto-generated if not provided."""
        extraction = ExtractionPayload(
            subject="test",
            action="must",
            obligation_type=ObligationType.MUST,
            confidence_score=0.9,
            source_text="test",
            source_offset=0,
        )

        event = GraphEvent(
            event_type="create_provision",
            doc_hash="abc123",
            document_id="doc_001",
            text_clean="test",
            extraction=extraction,
        )

        assert event.timestamp is not None
        assert isinstance(event.timestamp, datetime)


class TestReviewItem:
    """Tests for ReviewItem model."""

    def test_valid_review_item(self):
        """Test creating a valid review item."""
        extraction = ExtractionPayload(
            subject="financial institutions",
            action="must maintain",
            obligation_type=ObligationType.MUST,
            confidence_score=0.72,  # Low confidence -> needs review
            source_text="Financial institutions must maintain capital reserves",
            source_offset=1024,
        )

        review = ReviewItem(
            document_id="doc_001",
            extraction=extraction,
            status="pending",
        )

        assert review.document_id == "doc_001"
        assert review.status == "pending"
        assert review.extraction.confidence_score == 0.72
        assert review.reviewer_id is None
        assert review.reviewed_at is None

    def test_review_statuses(self):
        """Test all valid review statuses."""
        extraction = ExtractionPayload(
            subject="test",
            action="must",
            obligation_type=ObligationType.MUST,
            confidence_score=0.7,
            source_text="test",
            source_offset=0,
        )

        valid_statuses = ["pending", "approved", "rejected"]
        for status in valid_statuses:
            review = ReviewItem(
                document_id="doc_001",
                extraction=extraction,
                status=status,
            )
            assert review.status == status

    def test_id_auto_generation(self):
        """Test that review item ID is auto-generated."""
        extraction = ExtractionPayload(
            subject="test",
            action="must",
            obligation_type=ObligationType.MUST,
            confidence_score=0.7,
            source_text="test",
            source_offset=0,
        )

        review = ReviewItem(
            document_id="doc_001",
            extraction=extraction,
        )

        assert review.id is not None
        assert isinstance(review.id, UUID)


class TestObligationType:
    """Tests for ObligationType enum."""

    def test_obligation_types(self):
        """Test all obligation type values."""
        assert ObligationType.MUST.value == "MUST"
        assert ObligationType.MUST_NOT.value == "MUST_NOT"
        assert ObligationType.SHOULD.value == "SHOULD"
        assert ObligationType.MAY.value == "MAY"

    def test_obligation_type_usage(self):
        """Test using obligation types in ExtractionPayload."""
        for obl_type in ObligationType:
            extraction = ExtractionPayload(
                subject="test",
                action="test",
                obligation_type=obl_type,
                confidence_score=0.8,
                source_text="test",
                source_offset=0,
            )
            assert extraction.obligation_type == obl_type
