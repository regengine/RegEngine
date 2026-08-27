"""
Tests for FSMA 204 Prometheus Metrics.

Sprint 5: FSMA Health Dashboard Metrics

#2879: 22 of the 35 assertions here could not fail -- 20 were
``is not None`` against module-level ``prometheus_client`` collectors
(and the child objects ``.labels()`` returns), neither of which is ever
``None``, and 2 were bare ``assert True``. Proof: gutting every
recording helper in ``app/fsma_metrics.py`` so it recorded NOTHING left
all 27 tests passing. The tests verified only that the functions did
not raise.

They now read the RECORDED VALUE back out of the registry through the
public ``REGISTRY.get_sample_value`` API. Counters and histograms are
asserted as before/after deltas so the file stays order-independent;
gauges are absolute because ``.set()`` is.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from prometheus_client import REGISTRY

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


def _sample(name: str, **labels) -> float:
    """Current value of one metric sample, or 0.0 if it has no value yet.

    ``REGISTRY.get_sample_value`` is prometheus_client's public read API:
    it resolves the exported sample names (``_total`` for counters,
    ``_count``/``_sum`` for histograms) rather than reaching into the
    private ``._value`` of a child. Returning 0.0 for an absent sample
    makes "never recorded" and "recorded zero" compare equal, which is
    what the delta assertions below need.
    """
    value = REGISTRY.get_sample_value(name, labels or None)
    return 0.0 if value is None else value


# ============================================================================
# TRACE QUERY METRICS TESTS
# ============================================================================


class TestTraceQueryMetrics:
    """Tests for trace query metrics recording."""

    def test_record_trace_query_success(self):
        """Test recording successful trace query."""
        before_count = _sample("fsma_trace_queries_total", direction="forward", status="success")
        before_observations = _sample("fsma_trace_query_seconds_count", direction="forward", status="success")
        before_seconds = _sample("fsma_trace_query_seconds_sum", direction="forward", status="success")
        before_facilities = _sample("fsma_trace_facilities_total", direction="forward")

        record_trace_query(
            direction="forward",
            duration_seconds=0.5,
            status="success",
            hop_count=3,
            facility_count=5,
        )

        # The counter counts the query, the histogram observes its duration,
        # the depth gauge takes the hop count, the facility counter adds the
        # facility count. Each is a distinct wiring mistake.
        assert _sample("fsma_trace_queries_total", direction="forward", status="success") == before_count + 1
        assert (
            _sample("fsma_trace_query_seconds_count", direction="forward", status="success") == before_observations + 1
        )
        assert _sample("fsma_trace_query_seconds_sum", direction="forward", status="success") == pytest.approx(
            before_seconds + 0.5
        )
        assert _sample("fsma_trace_max_depth", direction="forward") == 3
        assert _sample("fsma_trace_facilities_total", direction="forward") == before_facilities + 5

    def test_record_trace_query_error(self):
        """Test recording failed trace query."""
        before_errors = _sample("fsma_trace_queries_total", direction="backward", status="error")
        before_successes = _sample("fsma_trace_queries_total", direction="backward", status="success")

        record_trace_query(
            direction="backward",
            duration_seconds=1.0,
            status="error",
            hop_count=0,
            facility_count=0,
        )

        assert _sample("fsma_trace_queries_total", direction="backward", status="error") == before_errors + 1
        # ...and the status label is not ignored: the success series is untouched.
        assert _sample("fsma_trace_queries_total", direction="backward", status="success") == before_successes

    def test_record_trace_query_both_directions(self):
        """Test both forward and backward trace metrics."""
        record_trace_query("forward", 0.3, "success", 2, 4)
        record_trace_query("backward", 0.4, "success", 5, 8)

        # Both directions are tracked, and each keeps its OWN hop count --
        # the bug a shared/overwritten label would hide.
        assert _sample("fsma_trace_max_depth", direction="forward") == 2
        assert _sample("fsma_trace_max_depth", direction="backward") == 5


# ============================================================================
# RECALL SLA METRICS TESTS
# ============================================================================


class TestRecallSLAMetrics:
    """Tests for recall SLA metrics."""

    def test_record_recall_export_csv(self):
        """Test recording CSV export timing."""
        before_observations = _sample("fsma_recall_sla_seconds_count", export_type="csv")
        before_seconds = _sample("fsma_recall_sla_seconds_sum", export_type="csv")
        before_exports = _sample("fsma_recall_exports_total", export_type="csv", status="success")

        record_recall_export(export_type="csv", duration_seconds=5.0, status="success")

        assert _sample("fsma_recall_sla_seconds_count", export_type="csv") == before_observations + 1
        assert _sample("fsma_recall_sla_seconds_sum", export_type="csv") == pytest.approx(before_seconds + 5.0)
        assert _sample("fsma_recall_exports_total", export_type="csv", status="success") == before_exports + 1

    def test_record_recall_export_full_package(self):
        """Test recording full package export."""
        before_observations = _sample("fsma_recall_sla_seconds_count", export_type="full_package")
        before_seconds = _sample("fsma_recall_sla_seconds_sum", export_type="full_package")
        before_csv = _sample("fsma_recall_sla_seconds_count", export_type="csv")

        record_recall_export(export_type="full_package", duration_seconds=30.0, status="success")

        assert _sample("fsma_recall_sla_seconds_count", export_type="full_package") == before_observations + 1
        assert _sample("fsma_recall_sla_seconds_sum", export_type="full_package") == pytest.approx(
            before_seconds + 30.0
        )
        # The export_type label routes the observation; csv must not move.
        assert _sample("fsma_recall_sla_seconds_count", export_type="csv") == before_csv

    def test_record_recall_sla_helper(self):
        """Test simplified recall SLA recording."""
        before_observations = _sample("fsma_recall_sla_seconds_count", export_type="csv")
        before_seconds = _sample("fsma_recall_sla_seconds_sum", export_type="csv")
        before_exports = _sample("fsma_recall_exports_total", export_type="csv", status="success")

        record_recall_sla(duration_seconds=10.0, export_type="csv")

        assert _sample("fsma_recall_sla_seconds_count", export_type="csv") == before_observations + 1
        assert _sample("fsma_recall_sla_seconds_sum", export_type="csv") == pytest.approx(before_seconds + 10.0)
        # This helper times the SLA only -- unlike record_recall_export it
        # must NOT also count an export.
        assert _sample("fsma_recall_exports_total", export_type="csv", status="success") == before_exports


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

        # Gauges, so absolute: the two gap types must not be swapped or merged.
        assert _sample("fsma_gaps_total", gap_type="missing_date") == 5
        assert _sample("fsma_gaps_total", gap_type="missing_lot") == 3
        assert _sample("fsma_gap_rate", event_type="SHIPPING") == pytest.approx(0.05)
        assert _sample("fsma_gap_rate", event_type="RECEIVING") == pytest.approx(0.03)

    def test_update_orphan_metrics(self):
        """Test updating orphan metrics."""
        update_orphan_metrics(
            orphan_count=10,
            total_quantity=500.0,
            avg_stagnant_days=15.0,
            quantity_by_unit={"kg": 300.0, "lbs": 200.0},
        )

        assert _sample("fsma_orphans_total") == 10
        assert _sample("fsma_orphan_avg_stagnant_days") == pytest.approx(15.0)
        assert _sample("fsma_orphan_quantity_at_risk", unit_of_measure="kg") == pytest.approx(300.0)
        assert _sample("fsma_orphan_quantity_at_risk", unit_of_measure="lbs") == pytest.approx(200.0)

    def test_record_gap_detection(self):
        """Test simplified gap detection recording."""
        record_gap_detection(gap_count=7, gap_type="missing_lot")

        assert _sample("fsma_gaps_total", gap_type="missing_lot") == 7

    def test_record_orphan_detection(self):
        """Test simplified orphan detection recording."""
        record_orphan_detection(orphan_count=5, quantity_at_risk=100.0)

        assert _sample("fsma_orphans_total") == 5
        assert _sample("fsma_orphan_quantity_at_risk", unit_of_measure="units") == pytest.approx(100.0)


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

        assert _sample("fsma_kde_completeness_rate") == pytest.approx(0.92)
        assert _sample("fsma_kde_completeness_by_type", event_type="SHIPPING") == pytest.approx(0.95)
        assert _sample("fsma_kde_completeness_by_type", event_type="RECEIVING") == pytest.approx(0.90)
        # completeness and confidence are different gauges; crossing them
        # would silently report confidence as completeness.
        assert _sample("fsma_extraction_confidence_avg", event_type="SHIPPING") == pytest.approx(0.88)
        assert _sample("fsma_extraction_confidence_avg", event_type="RECEIVING") == pytest.approx(0.85)

    def test_update_data_quality_score(self):
        """Test simplified data quality score update."""
        update_data_quality_score(score=0.95)

        # Should set the gauge
        assert _sample("fsma_kde_completeness_rate") == pytest.approx(0.95)

    def test_record_extraction_confidence_high(self):
        """Test recording high confidence extraction."""
        before_low = _sample("fsma_low_confidence_extractions_total", event_type="SHIPPING")

        record_extraction_confidence(confidence=0.92, event_type="SHIPPING")

        assert _sample("fsma_extraction_confidence_avg", event_type="SHIPPING") == pytest.approx(0.92)
        # 0.92 is above the 0.85 threshold, so the low-confidence counter
        # must NOT move -- the half of the branch the low test can't see.
        assert _sample("fsma_low_confidence_extractions_total", event_type="SHIPPING") == before_low

    def test_record_extraction_confidence_low(self):
        """Test recording low confidence triggers counter."""
        before_low = _sample("fsma_low_confidence_extractions_total", event_type="RECEIVING")

        record_extraction_confidence(confidence=0.50, event_type="RECEIVING")

        assert _sample("fsma_extraction_confidence_avg", event_type="RECEIVING") == pytest.approx(0.50)
        # Should increment low confidence counter
        assert _sample("fsma_low_confidence_extractions_total", event_type="RECEIVING") == before_low + 1


# ============================================================================
# API METRICS TESTS
# ============================================================================


class TestAPIMetrics:
    """Tests for API call metrics."""

    def test_record_api_call(self):
        """Test recording API call metrics."""
        labels = {"endpoint": "/v1/fsma/trace/forward", "method": "GET", "status": "success"}
        before_calls = _sample("fsma_api_calls_total", **labels)
        before_latency_count = _sample("fsma_api_latency_seconds_count", endpoint=labels["endpoint"])
        before_latency_sum = _sample("fsma_api_latency_seconds_sum", endpoint=labels["endpoint"])

        record_api_call(
            endpoint="/v1/fsma/trace/forward",
            method="GET",
            status="success",
            duration=0.25,
        )

        assert _sample("fsma_api_calls_total", **labels) == before_calls + 1
        assert _sample("fsma_api_latency_seconds_count", endpoint=labels["endpoint"]) == before_latency_count + 1
        assert _sample("fsma_api_latency_seconds_sum", endpoint=labels["endpoint"]) == pytest.approx(
            before_latency_sum + 0.25
        )


# ============================================================================
# VALIDATION METRICS TESTS
# ============================================================================


class TestValidationMetrics:
    """Tests for identifier validation metrics."""

    def test_record_tlc_validation_valid(self):
        """Test recording valid TLC."""
        before_valid = _sample("fsma_tlc_validations_total", result="valid")
        before_invalid = _sample("fsma_tlc_validations_total", result="invalid")

        record_validation(identifier_type="TLC", is_valid=True)

        assert _sample("fsma_tlc_validations_total", result="valid") == before_valid + 1
        # is_valid=True must not land on the invalid series.
        assert _sample("fsma_tlc_validations_total", result="invalid") == before_invalid

    def test_record_tlc_validation_invalid(self):
        """Test recording invalid TLC."""
        before_invalid = _sample("fsma_tlc_validations_total", result="invalid")
        before_valid = _sample("fsma_tlc_validations_total", result="valid")

        record_validation(identifier_type="TLC", is_valid=False)

        assert _sample("fsma_tlc_validations_total", result="invalid") == before_invalid + 1
        assert _sample("fsma_tlc_validations_total", result="valid") == before_valid

    def test_record_gtin_validation(self):
        """Test recording GTIN validation."""
        before_gs1 = _sample("fsma_gs1_validations_total", identifier_type="GTIN", result="valid")
        before_tlc = _sample("fsma_tlc_validations_total", result="valid")

        record_validation(identifier_type="GTIN", is_valid=True)

        assert _sample("fsma_gs1_validations_total", identifier_type="GTIN", result="valid") == before_gs1 + 1
        # Non-TLC identifiers take the GS1 branch, not the TLC one.
        assert _sample("fsma_tlc_validations_total", result="valid") == before_tlc

    def test_record_gln_validation(self):
        """Test recording GLN validation."""
        before_gln = _sample("fsma_gs1_validations_total", identifier_type="GLN", result="invalid")
        before_gtin = _sample("fsma_gs1_validations_total", identifier_type="GTIN", result="invalid")

        record_validation(identifier_type="GLN", is_valid=False)

        assert _sample("fsma_gs1_validations_total", identifier_type="GLN", result="invalid") == before_gln + 1
        # identifier_type is a real label, not a constant.
        assert _sample("fsma_gs1_validations_total", identifier_type="GTIN", result="invalid") == before_gtin


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
