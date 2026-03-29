"""Tests for scheduler data models and metrics collector."""

import time
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


class TestEnforcementItem:
    """Test EnforcementItem model."""

    def test_defaults(self):
        item = EnforcementItem(
            source_type=SourceType.FDA_RECALL,
            source_id="FDA-2026-001",
            title="Recall of Leafy Greens",
            url="https://fda.gov/recalls/001",
            published_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
        )
        assert item.source_type == SourceType.FDA_RECALL
        assert item.severity == EnforcementSeverity.MEDIUM
        assert item.jurisdiction == "US-FDA"
        assert item.affected_products == []
        assert item.affected_companies == []
        assert item.raw_data == {}
        assert item.id  # auto-generated UUID string

    def test_all_fields(self):
        item = EnforcementItem(
            source_type=SourceType.FDA_WARNING_LETTER,
            source_id="WL-2026-100",
            title="Warning Letter to XYZ Foods",
            summary="Inadequate HACCP plan",
            url="https://fda.gov/wl/100",
            published_date=datetime(2026, 2, 15, tzinfo=timezone.utc),
            severity=EnforcementSeverity.HIGH,
            affected_products=["Fresh Spinach"],
            affected_companies=["XYZ Foods Inc"],
        )
        assert item.severity == EnforcementSeverity.HIGH
        assert "Fresh Spinach" in item.affected_products


class TestScrapeResult:
    """Test ScrapeResult model."""

    def test_success_result(self):
        result = ScrapeResult(
            source_type=SourceType.FDA_RECALL,
            success=True,
            items_found=5,
            items_new=2,
        )
        assert result.success is True
        assert result.items_found == 5
        assert result.items == []

    def test_failure_result(self):
        result = ScrapeResult(
            source_type=SourceType.FDA_IMPORT_ALERT,
            success=False,
            error_message="Connection timeout",
        )
        assert result.success is False
        assert result.error_message == "Connection timeout"
        assert result.items_found == 0


class TestJobExecution:
    """Test JobExecution model."""

    def test_defaults(self):
        job = JobExecution(
            job_id="fda_recalls",
            source_type=SourceType.FDA_RECALL,
        )
        assert job.success is False
        assert job.items_processed == 0
        assert job.completed_at is None
        assert job.id  # auto-generated


class TestWebhookPayload:
    """Test WebhookPayload model."""

    def test_to_dict(self):
        item = EnforcementItem(
            source_type=SourceType.FDA_RECALL,
            source_id="R-001",
            title="Test Recall",
            url="https://fda.gov/r/001",
            published_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
        )
        payload = WebhookPayload(
            items=[item],
            summary="1 new enforcement action detected",
        )
        d = payload.to_dict()
        assert d["event_type"] == "enforcement.detected"
        assert d["source"] == "regengine-scheduler"
        assert d["item_count"] == 1
        assert len(d["items"]) == 1
        assert d["summary"] == "1 new enforcement action detected"


class TestAlertEvent:
    """Test AlertEvent model."""

    def test_to_kafka_dict(self):
        item = EnforcementItem(
            source_type=SourceType.FDA_WARNING_LETTER,
            source_id="WL-001",
            title="Warning Letter",
            url="https://fda.gov/wl/001",
            published_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        event = AlertEvent(
            source_type=SourceType.FDA_WARNING_LETTER,
            item=item,
            tenant_id=UUID("00000000-0000-0000-0000-000000000001"),
        )
        d = event.to_kafka_dict()
        assert d["event_type"] == "enforcement.detected"
        assert d["source_type"] == "fda_warning_letter"
        assert d["tenant_id"] == "00000000-0000-0000-0000-000000000001"
        assert d["item"]["source_id"] == "WL-001"

    def test_no_tenant(self):
        item = EnforcementItem(
            source_type=SourceType.FDA_RECALL,
            source_id="R-002",
            title="Recall",
            url="https://fda.gov/r/002",
            published_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
        )
        event = AlertEvent(
            source_type=SourceType.FDA_RECALL,
            item=item,
        )
        d = event.to_kafka_dict()
        assert d["tenant_id"] is None


class TestSourceType:
    """Test SourceType enum values."""

    def test_all_types(self):
        assert SourceType.FDA_WARNING_LETTER.value == "fda_warning_letter"
        assert SourceType.FDA_IMPORT_ALERT.value == "fda_import_alert"
        assert SourceType.FDA_RECALL.value == "fda_recall"
        assert SourceType.STATE_REGISTRY.value == "state_registry"
        assert SourceType.FEDERAL_REGISTER.value == "federal_register"
        assert SourceType.REGULATORY_DISCOVERY.value == "regulatory_discovery"


class TestMetricsCollector:
    """Test MetricsCollector without requiring prometheus_client."""

    def test_collector_init(self):
        from app.metrics import MetricsCollector
        collector = MetricsCollector()
        assert hasattr(collector, "enabled")

    def test_record_scrape_no_error(self):
        from app.metrics import MetricsCollector
        collector = MetricsCollector()
        # Should not raise even if prometheus is available or not
        collector.record_scrape(
            source_type="fda_recall",
            success=True,
            duration_seconds=1.5,
            items_found=10,
            items_new=3,
        )

    def test_record_webhook_no_error(self):
        from app.metrics import MetricsCollector
        collector = MetricsCollector()
        collector.record_webhook(
            url="https://example.com/hook",
            success=True,
            duration_seconds=0.2,
        )

    def test_record_kafka_event_no_error(self):
        from app.metrics import MetricsCollector
        collector = MetricsCollector()
        collector.record_kafka_event(topic="alerts.regulatory", success=True)

    def test_record_circuit_state_no_error(self):
        from app.metrics import MetricsCollector
        collector = MetricsCollector()
        collector.record_circuit_state(name="fda_scraper", state="closed")
        collector.record_circuit_state(name="fda_scraper", state="open")
        collector.record_circuit_state(name="fda_scraper", state="half_open")

    def test_set_info_no_error(self):
        from app.metrics import MetricsCollector
        collector = MetricsCollector()
        collector.set_info(version="1.0.0", environment="test")

    def test_get_metrics_returns_bytes(self):
        from app.metrics import MetricsCollector
        collector = MetricsCollector()
        result = collector.get_metrics()
        assert isinstance(result, bytes)


class TestStateManagerHash:
    """Test StateManager.compute_hash (static method, no DB needed)."""

    def test_compute_hash_deterministic(self):
        from app.state import StateManager
        h1 = StateManager.compute_hash("hello world")
        h2 = StateManager.compute_hash("hello world")
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_compute_hash_different_input(self):
        from app.state import StateManager
        h1 = StateManager.compute_hash("hello")
        h2 = StateManager.compute_hash("world")
        assert h1 != h2
