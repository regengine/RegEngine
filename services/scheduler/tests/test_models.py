"""
Tests for scheduler data models.

Validates Pydantic model construction, defaults, serialization,
and enum values.
"""

from datetime import datetime, timezone
from uuid import UUID

import pytest

from app.models import (
    AlertEvent,
    EnforcementItem,
    EnforcementSeverity,
    JobExecution,
    ScrapeResult,
    SourceType,
    WebhookPayload,
)


class TestSourceType:
    """Test SourceType enum."""

    def test_all_expected_types_exist(self):
        assert SourceType.FDA_WARNING_LETTER == "fda_warning_letter"
        assert SourceType.FDA_IMPORT_ALERT == "fda_import_alert"
        assert SourceType.FDA_RECALL == "fda_recall"
        assert SourceType.STATE_REGISTRY == "state_registry"
        assert SourceType.FEDERAL_REGISTER == "federal_register"
        assert SourceType.REGULATORY_DISCOVERY == "regulatory_discovery"


class TestEnforcementItem:
    """Test EnforcementItem model."""

    def _make_item(self, **overrides):
        defaults = {
            "source_type": SourceType.FDA_RECALL,
            "source_id": "FDA-2024-001",
            "title": "Romaine Lettuce Recall",
            "url": "https://fda.gov/recalls/001",
            "published_date": datetime(2024, 1, 15, tzinfo=timezone.utc),
        }
        defaults.update(overrides)
        return EnforcementItem(**defaults)

    def test_creation_with_required_fields(self):
        item = self._make_item()
        assert item.title == "Romaine Lettuce Recall"
        assert item.source_type == SourceType.FDA_RECALL

    def test_auto_generates_id(self):
        item = self._make_item()
        assert item.id  # non-empty
        UUID(item.id)  # validates as UUID

    def test_auto_sets_detected_at(self):
        item = self._make_item()
        assert item.detected_at is not None
        assert item.detected_at.tzinfo is not None

    def test_default_severity_is_medium(self):
        item = self._make_item()
        assert item.severity == EnforcementSeverity.MEDIUM

    def test_default_jurisdiction(self):
        item = self._make_item()
        assert item.jurisdiction == "US-FDA"

    def test_empty_lists_by_default(self):
        item = self._make_item()
        assert item.affected_products == []
        assert item.affected_companies == []

    def test_serialization_to_dict(self):
        item = self._make_item()
        d = item.model_dump(mode="json")
        assert d["source_type"] == "fda_recall"
        assert isinstance(d["published_date"], str)


class TestScrapeResult:
    """Test ScrapeResult model."""

    def test_successful_result(self):
        result = ScrapeResult(
            source_type=SourceType.FDA_RECALL,
            success=True,
            items_found=5,
            items_new=2,
        )
        assert result.success is True
        assert result.items_found == 5

    def test_failed_result(self):
        result = ScrapeResult(
            source_type=SourceType.FDA_RECALL,
            success=False,
            error_message="Connection timeout",
        )
        assert result.success is False
        assert result.error_message == "Connection timeout"

    def test_default_values(self):
        result = ScrapeResult(source_type=SourceType.FDA_RECALL, success=True)
        assert result.items_found == 0
        assert result.items_new == 0
        assert result.items == []
        assert result.duration_ms == 0


class TestJobExecution:
    """Test JobExecution model."""

    def test_default_values(self):
        job = JobExecution(
            job_id="job-001",
            source_type=SourceType.STATE_REGISTRY,
        )
        assert job.success is False
        assert job.completed_at is None
        assert job.items_processed == 0
        assert job.error_message is None

    def test_auto_generated_id(self):
        job = JobExecution(
            job_id="job-001",
            source_type=SourceType.STATE_REGISTRY,
        )
        UUID(job.id)  # should be valid UUID


class TestWebhookPayload:
    """Test WebhookPayload model."""

    def _make_item(self):
        return EnforcementItem(
            source_type=SourceType.FDA_RECALL,
            source_id="FDA-001",
            title="Test Recall",
            url="https://fda.gov/r/1",
            published_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

    def test_to_dict(self):
        payload = WebhookPayload(
            items=[self._make_item()],
            summary="1 new recall detected",
        )
        d = payload.to_dict()
        assert d["event_type"] == "enforcement.detected"
        assert d["item_count"] == 1
        assert isinstance(d["timestamp"], str)

    def test_default_source(self):
        payload = WebhookPayload(items=[], summary="empty")
        assert payload.source == "regengine-scheduler"


class TestAlertEvent:
    """Test AlertEvent model."""

    def _make_item(self):
        return EnforcementItem(
            source_type=SourceType.FDA_RECALL,
            source_id="FDA-001",
            title="Test",
            url="https://fda.gov/r/1",
            published_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

    def test_to_kafka_dict(self):
        event = AlertEvent(
            source_type=SourceType.FDA_RECALL,
            item=self._make_item(),
        )
        d = event.to_kafka_dict()
        assert d["event_type"] == "enforcement.detected"
        assert d["source_type"] == "fda_recall"
        assert d["tenant_id"] is None  # No tenant by default
        assert "item" in d

    def test_with_tenant_id(self):
        tid = UUID("12345678-1234-5678-1234-567812345678")
        event = AlertEvent(
            source_type=SourceType.FDA_RECALL,
            item=self._make_item(),
            tenant_id=tid,
        )
        d = event.to_kafka_dict()
        assert d["tenant_id"] == str(tid)
