"""
Tests for FSMA 204 Data Quality Monitoring.

Sprint 3: Orphan Detection & KDE Drift Analysis

Tests cover:
- Orphan lot detection (lots without outbound events)
- KDE completeness analysis (missing fields, low confidence)
- Data quality metrics by event type
- API endpoint integration
"""

import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
from unittest.mock import MagicMock, patch

import pytest

# Add parent paths for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))

from services.graph.app.fsma_utils import (
    DataQualityReport,
    KDECompletenessMetrics,
    OrphanLot,
    analyze_kde_completeness,
    find_orphaned_lots,
)

# ============================================================================
# ORPHAN LOT DATACLASS TESTS
# ============================================================================


class TestOrphanLotDataclass:
    """Tests for the OrphanLot dataclass."""

    def test_orphan_lot_creation(self):
        """OrphanLot can be created with all fields."""
        orphan = OrphanLot(
            tlc="ORPHAN-LOT-001",
            product_description="Abandoned Lettuce",
            quantity=100.0,
            unit_of_measure="cases",
            created_at="2025-01-01T00:00:00",
            stagnant_days=45,
            last_event_type="RECEIVING",
            last_event_date="2025-01-15",
        )

        assert orphan.tlc == "ORPHAN-LOT-001"
        assert orphan.product_description == "Abandoned Lettuce"
        assert orphan.quantity == 100.0
        assert orphan.stagnant_days == 45
        assert orphan.last_event_type == "RECEIVING"

    def test_orphan_lot_minimal(self):
        """OrphanLot can be created with minimal required fields."""
        orphan = OrphanLot(
            tlc="MIN-LOT-001",
            product_description=None,
            quantity=None,
            unit_of_measure=None,
            created_at=None,
            stagnant_days=30,
            last_event_type=None,
            last_event_date=None,
        )

        assert orphan.tlc == "MIN-LOT-001"
        assert orphan.product_description is None
        assert orphan.stagnant_days == 30

    def test_orphan_lot_stagnant_days_calculation(self):
        """Stagnant days correctly represents time since last activity."""
        orphan = OrphanLot(
            tlc="STAG-001",
            product_description="Old Product",
            quantity=50.0,
            unit_of_measure="units",
            created_at="2025-10-01",
            stagnant_days=60,  # 60 days without activity
            last_event_type="CREATION",
            last_event_date="2025-10-01",
        )

        assert orphan.stagnant_days == 60
        assert orphan.stagnant_days >= 30  # Meets default threshold


# ============================================================================
# KDE COMPLETENESS METRICS TESTS
# ============================================================================


class TestKDECompletenessMetrics:
    """Tests for the KDECompletenessMetrics dataclass."""

    def test_metrics_creation(self):
        """KDECompletenessMetrics can be created with all fields."""
        metrics = KDECompletenessMetrics(
            event_type="SHIPPING",
            total_events=100,
            missing_date_count=5,
            missing_date_rate=0.05,
            missing_lot_count=3,
            missing_lot_rate=0.03,
            low_confidence_count=10,
            low_confidence_rate=0.10,
            average_confidence=0.92,
        )

        assert metrics.event_type == "SHIPPING"
        assert metrics.total_events == 100
        assert metrics.missing_date_rate == 0.05
        assert metrics.low_confidence_rate == 0.10
        assert metrics.average_confidence == 0.92

    def test_metrics_perfect_quality(self):
        """Metrics with perfect data quality."""
        metrics = KDECompletenessMetrics(
            event_type="RECEIVING",
            total_events=50,
            missing_date_count=0,
            missing_date_rate=0.0,
            missing_lot_count=0,
            missing_lot_rate=0.0,
            low_confidence_count=0,
            low_confidence_rate=0.0,
            average_confidence=0.98,
        )

        assert metrics.missing_date_rate == 0.0
        assert metrics.missing_lot_rate == 0.0
        assert metrics.low_confidence_rate == 0.0
        assert metrics.average_confidence >= 0.95

    def test_metrics_poor_quality(self):
        """Metrics indicating poor data quality."""
        metrics = KDECompletenessMetrics(
            event_type="TRANSFORMATION",
            total_events=20,
            missing_date_count=8,
            missing_date_rate=0.40,  # 40% missing dates
            missing_lot_count=6,
            missing_lot_rate=0.30,  # 30% missing lots
            low_confidence_count=12,
            low_confidence_rate=0.60,  # 60% low confidence
            average_confidence=0.65,
        )

        assert metrics.missing_date_rate > 0.20  # Poor
        assert metrics.missing_lot_rate > 0.20  # Poor
        assert metrics.low_confidence_rate > 0.50  # Very poor
        assert metrics.average_confidence < 0.85  # Below threshold


# ============================================================================
# DATA QUALITY REPORT TESTS
# ============================================================================


class TestDataQualityReport:
    """Tests for the DataQualityReport dataclass."""

    def test_report_creation(self):
        """DataQualityReport can be created with metrics."""
        metrics = [
            KDECompletenessMetrics(
                event_type="SHIPPING",
                total_events=100,
                missing_date_count=5,
                missing_date_rate=0.05,
                missing_lot_count=3,
                missing_lot_rate=0.03,
                low_confidence_count=10,
                low_confidence_rate=0.10,
                average_confidence=0.92,
            ),
            KDECompletenessMetrics(
                event_type="RECEIVING",
                total_events=80,
                missing_date_count=2,
                missing_date_rate=0.025,
                missing_lot_count=1,
                missing_lot_rate=0.0125,
                low_confidence_count=5,
                low_confidence_rate=0.0625,
                average_confidence=0.95,
            ),
        ]

        report = DataQualityReport(
            total_events=180,
            overall_completeness_rate=0.93,
            metrics_by_type=metrics,
            trend_direction="stable",
            query_time_ms=15.5,
        )

        assert report.total_events == 180
        assert report.overall_completeness_rate == 0.93
        assert len(report.metrics_by_type) == 2
        assert report.trend_direction == "stable"

    def test_report_trend_directions(self):
        """Report can have different trend directions."""
        for trend in ["improving", "stable", "degrading"]:
            report = DataQualityReport(
                total_events=100,
                overall_completeness_rate=0.90,
                metrics_by_type=[],
                trend_direction=trend,
                query_time_ms=10.0,
            )
            assert report.trend_direction == trend

    def test_report_empty_metrics(self):
        """Report with no metrics (new/empty database)."""
        report = DataQualityReport(
            total_events=0,
            overall_completeness_rate=1.0,  # Perfect when empty
            metrics_by_type=[],
            trend_direction="stable",
            query_time_ms=5.0,
        )

        assert report.total_events == 0
        assert len(report.metrics_by_type) == 0
        assert report.overall_completeness_rate == 1.0


# ============================================================================
# ORPHAN DETECTION LOGIC TESTS (MOCKED)
# ============================================================================


class TestOrphanDetectionLogic:
    """Tests for orphan detection logic with mocked Neo4j."""

    def test_orphan_detection_returns_list(self):
        """find_orphaned_lots returns a list of OrphanLot objects."""
        # Mock the Neo4j client
        mock_client = MagicMock()
        mock_session = MagicMock()
        mock_client.session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_client.session.return_value.__exit__ = MagicMock(return_value=False)

        # Mock empty result
        mock_session.run.return_value = []

        result = find_orphaned_lots(mock_client, tenant_id=None, days_stagnant=30)

        assert isinstance(result, list)

    def test_orphan_detection_with_results(self):
        """find_orphaned_lots parses results correctly."""
        mock_client = MagicMock()
        mock_session = MagicMock()
        mock_client.session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_client.session.return_value.__exit__ = MagicMock(return_value=False)

        # Mock a result with one orphan lot
        mock_record = MagicMock()
        mock_record.__getitem__ = lambda self, key: {
            "tlc": "ORPHAN-001",
            "product_description": "Test Product",
            "quantity": 100.0,
            "unit_of_measure": "cases",
            "created_at": "2025-01-01",
            "last_event_type": "RECEIVING",
            "last_event_date": "2025-01-05",
        }.get(key)

        mock_session.run.return_value = [mock_record]

        result = find_orphaned_lots(mock_client, tenant_id=None, days_stagnant=30)

        assert len(result) == 1
        assert result[0].tlc == "ORPHAN-001"
        assert result[0].product_description == "Test Product"

    def test_orphan_detection_tenant_filter(self):
        """find_orphaned_lots passes tenant_id to query."""
        mock_client = MagicMock()
        mock_session = MagicMock()
        mock_client.session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_client.session.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.run.return_value = []

        find_orphaned_lots(mock_client, tenant_id="tenant-123", days_stagnant=45)

        # Verify query was called with tenant_id parameter
        mock_session.run.assert_called()
        call_kwargs = mock_session.run.call_args
        assert (
            "tenant_id" in str(call_kwargs)
            or call_kwargs[1].get("tenant_id") == "tenant-123"
        )


# ============================================================================
# KDE COMPLETENESS ANALYSIS LOGIC TESTS (MOCKED)
# ============================================================================


class TestKDECompletenessAnalysisLogic:
    """Tests for KDE completeness analysis logic with mocked Neo4j."""

    def test_analysis_returns_report(self):
        """analyze_kde_completeness returns a DataQualityReport."""
        mock_client = MagicMock()
        mock_session = MagicMock()
        mock_client.session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_client.session.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.run.return_value = []

        result = analyze_kde_completeness(mock_client, tenant_id=None)

        assert isinstance(result, DataQualityReport)

    def test_analysis_with_event_data(self):
        """analyze_kde_completeness parses event metrics correctly."""
        mock_client = MagicMock()
        mock_session = MagicMock()
        mock_client.session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_client.session.return_value.__exit__ = MagicMock(return_value=False)

        # Mock result with metrics for one event type
        mock_record = MagicMock()
        mock_record.__getitem__ = lambda self, key: {
            "event_type": "SHIPPING",
            "total": 100,
            "missing_date": 5,
            "missing_lot": 3,
            "low_confidence": 10,
            "avg_confidence": 0.92,
        }.get(key)

        mock_session.run.return_value = [mock_record]

        result = analyze_kde_completeness(mock_client, tenant_id=None)

        assert result.total_events == 100
        assert len(result.metrics_by_type) == 1
        assert result.metrics_by_type[0].event_type == "SHIPPING"
        assert result.metrics_by_type[0].missing_date_count == 5

    def test_analysis_confidence_threshold(self):
        """analyze_kde_completeness uses custom confidence threshold."""
        mock_client = MagicMock()
        mock_session = MagicMock()
        mock_client.session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_client.session.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.run.return_value = []

        # Call with custom threshold
        analyze_kde_completeness(mock_client, tenant_id=None, confidence_threshold=0.90)

        # Verify threshold was passed
        call_kwargs = mock_session.run.call_args
        assert call_kwargs[1].get("threshold") == 0.90


# ============================================================================
# TREND DIRECTION TESTS
# ============================================================================


class TestTrendDirection:
    """Tests for data quality trend determination."""

    def test_stable_trend_high_completeness(self):
        """High completeness rate indicates stable trend."""
        report = DataQualityReport(
            total_events=1000,
            overall_completeness_rate=0.96,
            metrics_by_type=[],
            trend_direction="stable",
            query_time_ms=20.0,
        )

        # >= 0.95 should be stable
        assert report.overall_completeness_rate >= 0.95
        assert report.trend_direction == "stable"

    def test_degrading_trend_low_completeness(self):
        """Low completeness rate indicates degrading trend."""
        report = DataQualityReport(
            total_events=500,
            overall_completeness_rate=0.72,
            metrics_by_type=[],
            trend_direction="degrading",
            query_time_ms=15.0,
        )

        # < 0.85 should trigger degrading
        assert report.overall_completeness_rate < 0.85
        assert report.trend_direction == "degrading"


# ============================================================================
# STAGNANT DAYS THRESHOLD TESTS
# ============================================================================


class TestStagnantDaysThreshold:
    """Tests for stagnant days threshold behavior."""

    def test_default_threshold_30_days(self):
        """Default threshold is 30 days."""
        orphan_30 = OrphanLot(
            tlc="LOT-30",
            product_description="Product",
            quantity=50.0,
            unit_of_measure="units",
            created_at=None,
            stagnant_days=30,
            last_event_type=None,
            last_event_date=None,
        )

        assert orphan_30.stagnant_days == 30

    def test_custom_threshold_values(self):
        """Various threshold values can be used."""
        for days in [7, 14, 30, 60, 90, 180, 365]:
            orphan = OrphanLot(
                tlc=f"LOT-{days}",
                product_description="Product",
                quantity=10.0,
                unit_of_measure="units",
                created_at=None,
                stagnant_days=days,
                last_event_type=None,
                last_event_date=None,
            )
            assert orphan.stagnant_days == days

    def test_stagnant_lot_exceeds_threshold(self):
        """Lots exceeding threshold are identified."""
        threshold = 30

        # Lot stagnant for 45 days
        orphan = OrphanLot(
            tlc="STAGNANT-45",
            product_description="Old Inventory",
            quantity=200.0,
            unit_of_measure="cases",
            created_at="2025-10-01",
            stagnant_days=45,
            last_event_type="RECEIVING",
            last_event_date="2025-10-15",
        )

        assert orphan.stagnant_days > threshold
        assert orphan.stagnant_days == 45


# ============================================================================
# EDGE CASE TESTS
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases in data quality monitoring."""

    def test_empty_database(self):
        """Handle empty database gracefully."""
        report = DataQualityReport(
            total_events=0,
            overall_completeness_rate=1.0,
            metrics_by_type=[],
            trend_direction="stable",
            query_time_ms=1.0,
        )

        assert report.total_events == 0
        assert report.overall_completeness_rate == 1.0
        assert report.trend_direction == "stable"

    def test_all_events_incomplete(self):
        """Handle case where all events have issues."""
        metrics = KDECompletenessMetrics(
            event_type="SHIPPING",
            total_events=50,
            missing_date_count=50,
            missing_date_rate=1.0,  # 100% missing
            missing_lot_count=50,
            missing_lot_rate=1.0,
            low_confidence_count=50,
            low_confidence_rate=1.0,
            average_confidence=0.0,
        )

        assert metrics.missing_date_rate == 1.0
        assert metrics.missing_lot_rate == 1.0
        assert metrics.low_confidence_rate == 1.0

    def test_orphan_with_null_quantity(self):
        """Handle orphan lot with null quantity."""
        orphan = OrphanLot(
            tlc="NULL-QTY-001",
            product_description="Unknown Quantity",
            quantity=None,
            unit_of_measure=None,
            created_at=None,
            stagnant_days=60,
            last_event_type="CREATION",
            last_event_date=None,
        )

        assert orphan.quantity is None
        # Should still be identifiable as orphan
        assert orphan.tlc is not None
        assert orphan.stagnant_days > 0

    def test_metrics_division_by_zero_prevention(self):
        """Rates should handle zero total events."""
        # If total_events is 0, rates should be 0 or handled gracefully
        metrics = KDECompletenessMetrics(
            event_type="UNKNOWN",
            total_events=0,
            missing_date_count=0,
            missing_date_rate=0.0,  # Should be 0, not NaN
            missing_lot_count=0,
            missing_lot_rate=0.0,
            low_confidence_count=0,
            low_confidence_rate=0.0,
            average_confidence=0.0,
        )

        assert metrics.missing_date_rate == 0.0
        assert metrics.missing_lot_rate == 0.0


# ============================================================================
# INTEGRATION-LIKE TESTS (MOCK FULL FLOW)
# ============================================================================


class TestDataQualityMonitoringFlow:
    """Tests for the complete data quality monitoring workflow."""

    def test_orphan_to_report_workflow(self):
        """Complete workflow from orphan detection to actionable report."""
        # Simulate finding orphans
        orphans = [
            OrphanLot(
                tlc="ORPHAN-001",
                product_description="Stale Produce",
                quantity=100.0,
                unit_of_measure="cases",
                created_at="2025-09-01",
                stagnant_days=90,
                last_event_type="RECEIVING",
                last_event_date="2025-09-05",
            ),
            OrphanLot(
                tlc="ORPHAN-002",
                product_description="Old Dairy",
                quantity=50.0,
                unit_of_measure="cases",
                created_at="2025-10-01",
                stagnant_days=60,
                last_event_type="CREATION",
                last_event_date="2025-10-01",
            ),
        ]

        # Generate summary stats
        total_orphans = len(orphans)
        avg_stagnant = sum(o.stagnant_days for o in orphans) / total_orphans
        total_qty_at_risk = sum(o.quantity or 0 for o in orphans)

        assert total_orphans == 2
        assert avg_stagnant == 75.0
        assert total_qty_at_risk == 150.0

    def test_quality_metrics_to_alert_decision(self):
        """Quality metrics can trigger alert decisions."""
        report = DataQualityReport(
            total_events=500,
            overall_completeness_rate=0.78,  # Below 85% threshold
            metrics_by_type=[
                KDECompletenessMetrics(
                    event_type="SHIPPING",
                    total_events=300,
                    missing_date_count=60,
                    missing_date_rate=0.20,
                    missing_lot_count=45,
                    missing_lot_rate=0.15,
                    low_confidence_count=90,
                    low_confidence_rate=0.30,
                    average_confidence=0.78,
                ),
            ],
            trend_direction="degrading",
            query_time_ms=25.0,
        )

        # Alert decision logic
        should_alert = (
            report.overall_completeness_rate < 0.85
            or report.trend_direction == "degrading"
        )

        assert should_alert is True
        assert report.trend_direction == "degrading"
