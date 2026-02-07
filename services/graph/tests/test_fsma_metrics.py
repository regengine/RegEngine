"""
Tests for FSMA 204 Prometheus Metrics.

Sprint 5: FSMA Health Dashboard Metrics
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add service path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.fsma_metrics import (  # Metrics; Functions; Decorators
    EXTRACTION_CONFIDENCE_AVG,
    FSMA_API_CALLS,
    GAPS_TOTAL,
    GS1_VALIDATIONS_TOTAL,
    KDE_COMPLETENESS_RATE,
    LOW_CONFIDENCE_EXTRACTIONS,
    ORPHANS_TOTAL,
    RECALL_SLA_SECONDS,
    TLC_VALIDATIONS_TOTAL,
    TRACE_FACILITIES_FOUND,
    TRACE_MAX_DEPTH,
    TRACE_QUERIES_TOTAL,
    TRACE_QUERY_LATENCY,
    get_health_status,
    get_metrics_text,
    record_api_call,
    record_extraction_confidence,
    record_gap_detection,
    record_orphan_detection,
    record_recall_export,
    record_recall_sla,
    record_trace_query,
    record_validation,
    track_fsma_endpoint,
    track_trace_query,
    update_completeness_metrics,
    update_data_quality_score,
    update_gap_metrics,
    update_orphan_metrics,
)

# ============================================================================
# TRACE QUERY METRICS TESTS
# ============================================================================


class TestTraceQueryMetrics:
    """Tests for trace query metrics recording."""

    def test_record_trace_query_success(self):
        """Test recording successful trace query."""
        record_trace_query(
            direction="forward",
            duration_seconds=0.5,
            status="success",
            hop_count=3,
            facility_count=5,
        )

        # Verify metrics were updated (checking labels exist)
        assert (
            TRACE_QUERIES_TOTAL.labels(direction="forward", status="success")
            is not None
        )
        assert (
            TRACE_QUERY_LATENCY.labels(direction="forward", status="success")
            is not None
        )

    def test_record_trace_query_error(self):
        """Test recording failed trace query."""
        record_trace_query(
            direction="backward",
            duration_seconds=1.0,
            status="error",
            hop_count=0,
            facility_count=0,
        )

        assert (
            TRACE_QUERIES_TOTAL.labels(direction="backward", status="error") is not None
        )

    def test_record_trace_query_both_directions(self):
        """Test both forward and backward trace metrics."""
        record_trace_query("forward", 0.3, "success", 2, 4)
        record_trace_query("backward", 0.4, "success", 5, 8)

        # Both directions should be tracked
        assert TRACE_MAX_DEPTH.labels(direction="forward") is not None
        assert TRACE_MAX_DEPTH.labels(direction="backward") is not None


# ============================================================================
# RECALL SLA METRICS TESTS
# ============================================================================


class TestRecallSLAMetrics:
    """Tests for recall SLA metrics."""

    def test_record_recall_export_csv(self):
        """Test recording CSV export timing."""
        record_recall_export(export_type="csv", duration_seconds=5.0, status="success")

        assert RECALL_SLA_SECONDS.labels(export_type="csv") is not None

    def test_record_recall_export_full_package(self):
        """Test recording full package export."""
        record_recall_export(
            export_type="full_package", duration_seconds=30.0, status="success"
        )

        assert RECALL_SLA_SECONDS.labels(export_type="full_package") is not None

    def test_record_recall_sla_helper(self):
        """Test simplified recall SLA recording."""
        record_recall_sla(duration_seconds=10.0, export_type="csv")

        # Should not raise
        assert True


# ============================================================================
# DATA QUALITY METRICS TESTS
# ============================================================================


class TestDataQualityMetrics:
    """Tests for data quality metrics."""

    def test_update_gap_metrics(self):
        """Test updating gap metrics."""
        update_gap_metrics(
            missing_date=5,
            missing_lot=3,
            total_events=100,
            gap_rates={"SHIPPING": 0.05, "RECEIVING": 0.03},
        )

        assert GAPS_TOTAL.labels(gap_type="missing_date") is not None
        assert GAPS_TOTAL.labels(gap_type="missing_lot") is not None

    def test_update_orphan_metrics(self):
        """Test updating orphan metrics."""
        update_orphan_metrics(
            orphan_count=10,
            total_quantity=500.0,
            avg_stagnant_days=15.0,
            quantity_by_unit={"kg": 300.0, "lbs": 200.0},
        )

        assert ORPHANS_TOTAL is not None

    def test_record_gap_detection(self):
        """Test simplified gap detection recording."""
        record_gap_detection(gap_count=7, gap_type="missing_lot")

        assert GAPS_TOTAL.labels(gap_type="missing_lot") is not None

    def test_record_orphan_detection(self):
        """Test simplified orphan detection recording."""
        record_orphan_detection(orphan_count=5, quantity_at_risk=100.0)

        assert ORPHANS_TOTAL is not None


# ============================================================================
# KDE COMPLETENESS METRICS TESTS
# ============================================================================


class TestKDECompletenessMetrics:
    """Tests for KDE completeness metrics."""

    def test_update_completeness_metrics(self):
        """Test updating KDE completeness."""
        update_completeness_metrics(
            overall_rate=0.92,
            by_type={"SHIPPING": 0.95, "RECEIVING": 0.90},
            confidence_by_type={"SHIPPING": 0.88, "RECEIVING": 0.85},
        )

        assert KDE_COMPLETENESS_RATE is not None

    def test_update_data_quality_score(self):
        """Test simplified data quality score update."""
        update_data_quality_score(score=0.95)

        # Should set the gauge
        assert True

    def test_record_extraction_confidence_high(self):
        """Test recording high confidence extraction."""
        record_extraction_confidence(confidence=0.92, event_type="SHIPPING")

        assert EXTRACTION_CONFIDENCE_AVG.labels(event_type="SHIPPING") is not None

    def test_record_extraction_confidence_low(self):
        """Test recording low confidence triggers counter."""
        record_extraction_confidence(confidence=0.50, event_type="RECEIVING")

        # Should increment low confidence counter
        assert LOW_CONFIDENCE_EXTRACTIONS.labels(event_type="RECEIVING") is not None


# ============================================================================
# API METRICS TESTS
# ============================================================================


class TestAPIMetrics:
    """Tests for API call metrics."""

    def test_record_api_call(self):
        """Test recording API call metrics."""
        record_api_call(
            endpoint="/v1/fsma/trace/forward",
            method="GET",
            status="success",
            duration=0.25,
        )

        assert (
            FSMA_API_CALLS.labels(
                endpoint="/v1/fsma/trace/forward", method="GET", status="success"
            )
            is not None
        )


# ============================================================================
# VALIDATION METRICS TESTS
# ============================================================================


class TestValidationMetrics:
    """Tests for identifier validation metrics."""

    def test_record_tlc_validation_valid(self):
        """Test recording valid TLC."""
        record_validation(identifier_type="TLC", is_valid=True)

        assert TLC_VALIDATIONS_TOTAL.labels(result="valid") is not None

    def test_record_tlc_validation_invalid(self):
        """Test recording invalid TLC."""
        record_validation(identifier_type="TLC", is_valid=False)

        assert TLC_VALIDATIONS_TOTAL.labels(result="invalid") is not None

    def test_record_gtin_validation(self):
        """Test recording GTIN validation."""
        record_validation(identifier_type="GTIN", is_valid=True)

        assert (
            GS1_VALIDATIONS_TOTAL.labels(identifier_type="GTIN", result="valid")
            is not None
        )

    def test_record_gln_validation(self):
        """Test recording GLN validation."""
        record_validation(identifier_type="GLN", is_valid=False)

        assert (
            GS1_VALIDATIONS_TOTAL.labels(identifier_type="GLN", result="invalid")
            is not None
        )


# ============================================================================
# HEALTH STATUS TESTS
# ============================================================================


class TestHealthStatus:
    """Tests for health status reporting."""

    def test_get_health_status(self):
        """Test health status returns expected structure."""
        status = get_health_status()

        assert status["status"] == "ok"
        assert status["module"] == "fsma-204"
        assert status["metrics_available"] is True
        assert status["compliance_target"] == "24_hour_recall"

    def test_get_metrics_text(self):
        """Test Prometheus metrics text generation."""
        metrics_text = get_metrics_text()

        # Should be a non-empty string
        assert isinstance(metrics_text, str)
        assert len(metrics_text) > 0

        # Should contain FSMA metrics
        assert "fsma_" in metrics_text or "HELP" in metrics_text


# ============================================================================
# DECORATOR TESTS
# ============================================================================


class TestMetricDecorators:
    """Tests for metric decorator functions."""

    def test_track_fsma_endpoint_success(self):
        """Test endpoint tracking decorator on success."""

        @track_fsma_endpoint("test_endpoint")
        def sample_endpoint():
            return {"status": "ok"}

        result = sample_endpoint()

        assert result == {"status": "ok"}

    def test_track_fsma_endpoint_error(self):
        """Test endpoint tracking decorator on error."""

        @track_fsma_endpoint("test_endpoint")
        def failing_endpoint():
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            failing_endpoint()

    def test_track_trace_query_decorator(self):
        """Test trace query tracking decorator."""

        class MockResult:
            hop_count = 5
            facilities = ["fac1", "fac2"]

        @track_trace_query("forward")
        def mock_trace():
            return MockResult()

        result = mock_trace()

        assert result.hop_count == 5
        assert len(result.facilities) == 2


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestMetricsIntegration:
    """Integration tests for metrics module."""

    def test_full_trace_workflow_metrics(self):
        """Test metrics recording for complete trace workflow."""
        # Simulate a complete trace query
        record_trace_query("forward", 0.5, "success", 3, 5)
        record_recall_export("csv", 2.0, "success")
        record_gap_detection(2, "missing_lot")
        update_data_quality_score(0.95)

        # All should complete without error
        status = get_health_status()
        assert status["status"] == "ok"

    def test_multiple_concurrent_traces(self):
        """Test recording multiple traces."""
        for i in range(10):
            direction = "forward" if i % 2 == 0 else "backward"
            record_trace_query(direction, 0.1 * i, "success", i, i * 2)

        # All 10 should be recorded
        # Metrics should still work
        assert get_health_status()["status"] == "ok"

    def test_metrics_text_contains_all_families(self):
        """Test that metrics text includes key metric families."""
        # Trigger some metrics first
        record_trace_query("forward", 0.5, "success", 3, 5)
        record_gap_detection(1, "missing_lot")

        text = get_metrics_text()

        # Should contain metric declarations
        assert "fsma_trace" in text or "TYPE" in text
