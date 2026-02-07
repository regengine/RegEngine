"""
Tests for FSMA 204 Drift Detection & Alerting.

Sprint 7: Data Quality Drift Detection
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Add service path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.fsma_drift import (  # Enums; Data classes; Main class; Global functions; Convenience functions
    AlertSeverity,
    AlertStatus,
    AlertType,
    DriftAlert,
    DriftAnalysisResult,
    DriftDetector,
    KDESnapshot,
    check_for_drift,
    get_active_drift_alerts,
    get_drift_detector,
    get_drift_status,
    record_ingestion_quality,
    reset_drift_detector,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture(autouse=True)
def reset_detector():
    """Reset the global drift detector before each test."""
    reset_drift_detector()
    yield
    reset_drift_detector()


# ============================================================================
# KDE SNAPSHOT TESTS
# ============================================================================


class TestKDESnapshot:
    """Tests for KDESnapshot data class."""

    def test_snapshot_creation(self):
        """Test basic snapshot creation."""
        snapshot = KDESnapshot(
            total_events=100,
            complete_events=95,
            completeness_rate=0.95,
            supplier_gln="1234567890123",
        )

        assert snapshot.total_events == 100
        assert snapshot.complete_events == 95
        assert snapshot.completeness_rate == 0.95
        assert snapshot.supplier_gln == "1234567890123"

    def test_snapshot_has_timestamp(self):
        """Test that snapshots have ISO timestamps."""
        snapshot = KDESnapshot()

        assert snapshot.timestamp is not None
        # Should be valid ISO format
        datetime.fromisoformat(snapshot.timestamp.replace("Z", "+00:00"))

    def test_snapshot_to_dict(self):
        """Test conversion to dictionary."""
        snapshot = KDESnapshot(
            total_events=50,
            complete_events=45,
            completeness_rate=0.90,
            missing_date_count=3,
            missing_lot_count=2,
        )

        d = snapshot.to_dict()

        assert d["total_events"] == 50
        assert d["completeness_rate"] == 0.90
        assert d["missing_date_count"] == 3


# ============================================================================
# DRIFT ALERT TESTS
# ============================================================================


class TestDriftAlert:
    """Tests for DriftAlert data class."""

    def test_alert_creation(self):
        """Test basic alert creation."""
        alert = DriftAlert(
            alert_type=AlertType.KDE_COMPLETENESS_DROP,
            severity=AlertSeverity.WARNING,
            supplier_gln="1234567890123",
            message="Test alert",
        )

        assert alert.alert_id is not None
        assert alert.alert_type == AlertType.KDE_COMPLETENESS_DROP
        assert alert.severity == AlertSeverity.WARNING
        assert alert.status == AlertStatus.ACTIVE

    def test_alert_to_dict(self):
        """Test conversion to dictionary."""
        alert = DriftAlert(
            alert_type=AlertType.SUPPLIER_FORMAT_CHANGE,
            severity=AlertSeverity.CRITICAL,
            baseline_value=0.95,
            current_value=0.75,
            drift_percentage=-20.0,
        )

        d = alert.to_dict()

        assert d["alert_type"] == "SUPPLIER_FORMAT_CHANGE"
        assert d["severity"] == "CRITICAL"
        assert d["status"] == "ACTIVE"
        assert d["drift_percentage"] == -20.0


# ============================================================================
# DRIFT DETECTOR TESTS
# ============================================================================


class TestDriftDetector:
    """Tests for DriftDetector class."""

    def test_record_snapshot(self):
        """Test recording a snapshot."""
        detector = DriftDetector()

        snapshot = detector.record_snapshot(
            total_events=100,
            complete_events=95,
            supplier_gln="1234567890123",
        )

        assert snapshot.completeness_rate == 0.95
        assert len(detector._snapshots) == 1

    def test_new_supplier_detection(self):
        """Test that new suppliers generate info alerts."""
        detector = DriftDetector()

        detector.record_snapshot(
            total_events=100,
            complete_events=95,
            supplier_gln="NEW-SUPPLIER-001",
        )

        # Should have created a new supplier alert
        alerts = detector.get_alerts(severity=AlertSeverity.INFO)
        assert len(alerts) >= 1

        new_supplier_alerts = [
            a for a in alerts if a.alert_type == AlertType.NEW_SUPPLIER_DETECTED
        ]
        assert len(new_supplier_alerts) == 1
        assert new_supplier_alerts[0].supplier_gln == "NEW-SUPPLIER-001"

    def test_completeness_drop_warning(self):
        """Test that moderate completeness drop generates warning."""
        detector = DriftDetector()

        # Record baseline (high completeness)
        baseline_time = datetime.now(timezone.utc) - timedelta(days=3)
        for i in range(5):
            snapshot = KDESnapshot(
                timestamp=(baseline_time + timedelta(hours=i)).isoformat(),
                total_events=100,
                complete_events=95,
                completeness_rate=0.95,
            )
            detector._snapshots.append(snapshot)

        # Record recent (lower completeness - 7% drop)
        recent_time = datetime.now(timezone.utc) - timedelta(hours=2)
        for i in range(3):
            snapshot = KDESnapshot(
                timestamp=(recent_time + timedelta(hours=i)).isoformat(),
                total_events=100,
                complete_events=88,
                completeness_rate=0.88,
            )
            detector._snapshots.append(snapshot)

        # Analyze
        result = detector.analyze_drift()

        assert result.has_drift is True
        assert result.drift_severity == AlertSeverity.WARNING
        assert len(result.alerts) >= 1

    def test_completeness_drop_critical(self):
        """Test that severe completeness drop generates critical alert."""
        detector = DriftDetector()

        # Record baseline (high completeness)
        baseline_time = datetime.now(timezone.utc) - timedelta(days=3)
        for i in range(5):
            snapshot = KDESnapshot(
                timestamp=(baseline_time + timedelta(hours=i)).isoformat(),
                total_events=100,
                complete_events=95,
                completeness_rate=0.95,
            )
            detector._snapshots.append(snapshot)

        # Record recent (much lower completeness - 20% drop)
        recent_time = datetime.now(timezone.utc) - timedelta(hours=2)
        for i in range(3):
            snapshot = KDESnapshot(
                timestamp=(recent_time + timedelta(hours=i)).isoformat(),
                total_events=100,
                complete_events=75,
                completeness_rate=0.75,
            )
            detector._snapshots.append(snapshot)

        # Analyze
        result = detector.analyze_drift()

        assert result.has_drift is True
        assert result.drift_severity == AlertSeverity.CRITICAL

    def test_no_drift_when_stable(self):
        """Test that stable data doesn't generate drift alerts."""
        detector = DriftDetector()

        # Record consistent data
        base_time = datetime.now(timezone.utc) - timedelta(days=5)
        for i in range(20):
            snapshot = KDESnapshot(
                timestamp=(base_time + timedelta(hours=i * 6)).isoformat(),
                total_events=100,
                complete_events=94 + (i % 3),  # 94-96% (stable)
                completeness_rate=0.94 + ((i % 3) * 0.01),
            )
            detector._snapshots.append(snapshot)

        # Analyze
        result = detector.analyze_drift()

        # Should not have completeness alerts (may have new supplier alerts)
        completeness_alerts = [
            a for a in result.alerts if a.alert_type == AlertType.KDE_COMPLETENESS_DROP
        ]
        assert len(completeness_alerts) == 0

    def test_supplier_specific_analysis(self):
        """Test drift analysis for specific supplier."""
        detector = DriftDetector()

        # Record data for supplier A (stable)
        for i in range(5):
            detector._supplier_snapshots["SUPPLIER-A"].append(
                KDESnapshot(
                    timestamp=(
                        datetime.now(timezone.utc) - timedelta(days=3, hours=i)
                    ).isoformat(),
                    supplier_gln="SUPPLIER-A",
                    completeness_rate=0.95,
                )
            )
            detector._supplier_snapshots["SUPPLIER-A"].append(
                KDESnapshot(
                    timestamp=(
                        datetime.now(timezone.utc) - timedelta(hours=i)
                    ).isoformat(),
                    supplier_gln="SUPPLIER-A",
                    completeness_rate=0.94,
                )
            )

        # Analyze supplier A specifically
        result = detector.analyze_supplier_drift("SUPPLIER-A")

        # Should not have drift (stable)
        completeness_alerts = [
            a
            for a in result.alerts
            if a.alert_type
            in (AlertType.KDE_COMPLETENESS_DROP, AlertType.SUPPLIER_FORMAT_CHANGE)
        ]
        assert len(completeness_alerts) == 0

    def test_acknowledge_alert(self):
        """Test acknowledging an alert."""
        detector = DriftDetector()

        # Create an alert
        alert = DriftAlert(
            alert_type=AlertType.KDE_COMPLETENESS_DROP,
            severity=AlertSeverity.WARNING,
        )
        detector._alerts.append(alert)

        # Acknowledge it
        success = detector.acknowledge_alert(alert.alert_id)

        assert success is True
        assert alert.status == AlertStatus.ACKNOWLEDGED
        assert alert.acknowledged_at is not None

    def test_resolve_alert(self):
        """Test resolving an alert."""
        detector = DriftDetector()

        # Create an alert
        alert = DriftAlert(
            alert_type=AlertType.CONFIDENCE_DROP,
            severity=AlertSeverity.WARNING,
        )
        detector._alerts.append(alert)

        # Resolve it
        success = detector.resolve_alert(alert.alert_id)

        assert success is True
        assert alert.status == AlertStatus.RESOLVED
        assert alert.resolved_at is not None

    def test_get_alerts_filtering(self):
        """Test alert filtering by status and severity."""
        detector = DriftDetector()

        # Add various alerts
        detector._alerts.append(
            DriftAlert(
                severity=AlertSeverity.WARNING,
                status=AlertStatus.ACTIVE,
            )
        )
        detector._alerts.append(
            DriftAlert(
                severity=AlertSeverity.CRITICAL,
                status=AlertStatus.ACTIVE,
            )
        )
        detector._alerts.append(
            DriftAlert(
                severity=AlertSeverity.WARNING,
                status=AlertStatus.RESOLVED,
            )
        )

        # Filter by status
        active = detector.get_alerts(status=AlertStatus.ACTIVE)
        assert len(active) == 2

        # Filter by severity
        critical = detector.get_alerts(severity=AlertSeverity.CRITICAL)
        assert len(critical) == 1

        # Combined filter
        active_warning = detector.get_alerts(
            status=AlertStatus.ACTIVE,
            severity=AlertSeverity.WARNING,
        )
        assert len(active_warning) == 1

    def test_get_drift_summary(self):
        """Test drift summary generation."""
        detector = DriftDetector()

        # Add some alerts
        detector._alerts.append(
            DriftAlert(
                severity=AlertSeverity.CRITICAL,
                status=AlertStatus.ACTIVE,
            )
        )
        detector._alerts.append(
            DriftAlert(
                severity=AlertSeverity.WARNING,
                status=AlertStatus.ACTIVE,
            )
        )

        summary = detector.get_drift_summary()

        assert summary["status"] == "CRITICAL"  # Has critical alerts
        assert summary["active_alerts"] == 2
        assert summary["critical_alerts"] == 1
        assert summary["warning_alerts"] == 1

    def test_get_supplier_health(self):
        """Test supplier health reporting."""
        detector = DriftDetector()

        # Add snapshots for two suppliers
        detector._supplier_snapshots["SUPPLIER-A"].append(
            KDESnapshot(
                supplier_gln="SUPPLIER-A",
                completeness_rate=0.95,
                avg_confidence=0.90,
            )
        )
        detector._supplier_snapshots["SUPPLIER-B"].append(
            KDESnapshot(
                supplier_gln="SUPPLIER-B",
                completeness_rate=0.80,
                avg_confidence=0.75,
            )
        )

        health = detector.get_supplier_health()

        assert len(health) == 2
        # Find supplier A
        supplier_a = next(s for s in health if s["supplier_gln"] == "SUPPLIER-A")
        assert supplier_a["latest_completeness_rate"] == 0.95


# ============================================================================
# CONVENIENCE FUNCTION TESTS
# ============================================================================


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_record_ingestion_quality(self):
        """Test recording ingestion quality."""
        snapshot = record_ingestion_quality(
            total_events=100,
            complete_events=90,
            missing_date=5,
            missing_lot=5,
            avg_confidence=0.88,
            supplier_gln="TEST-SUPPLIER",
        )

        assert snapshot.completeness_rate == 0.90
        assert snapshot.supplier_gln == "TEST-SUPPLIER"

    def test_check_for_drift(self):
        """Test drift checking."""
        # Just verify it runs without error
        result = check_for_drift()

        assert isinstance(result, DriftAnalysisResult)

    def test_get_drift_status(self):
        """Test getting drift status."""
        status = get_drift_status()

        assert "status" in status
        assert "active_alerts" in status
        assert "known_suppliers" in status


# ============================================================================
# GLOBAL DETECTOR TESTS
# ============================================================================


class TestGlobalDetector:
    """Tests for global detector singleton."""

    def test_get_detector_returns_same_instance(self):
        """Test singleton behavior."""
        d1 = get_drift_detector()
        d2 = get_drift_detector()

        assert d1 is d2

    def test_reset_clears_detector(self):
        """Test reset clears all data."""
        detector = get_drift_detector()
        detector.record_snapshot(100, 90)

        reset_drift_detector()
        new_detector = get_drift_detector()

        assert len(new_detector._snapshots) == 0


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestDriftIntegration:
    """Integration tests for drift detection workflow."""

    def test_full_drift_detection_workflow(self):
        """Test complete drift detection workflow."""
        detector = get_drift_detector()

        # 1. Record baseline data (7 days ago)
        baseline_time = datetime.now(timezone.utc) - timedelta(days=7)
        for day in range(5):
            snapshot = KDESnapshot(
                timestamp=(baseline_time + timedelta(days=day)).isoformat(),
                total_events=100,
                complete_events=95,
                completeness_rate=0.95,
                supplier_gln="MAIN-SUPPLIER",
            )
            detector._snapshots.append(snapshot)
            detector._supplier_snapshots["MAIN-SUPPLIER"].append(snapshot)
        detector._known_suppliers.add("MAIN-SUPPLIER")

        # 2. Record degraded recent data
        recent_time = datetime.now(timezone.utc) - timedelta(hours=12)
        for i in range(3):
            snapshot = KDESnapshot(
                timestamp=(recent_time + timedelta(hours=i * 4)).isoformat(),
                total_events=100,
                complete_events=80,  # Significant drop
                completeness_rate=0.80,
                supplier_gln="MAIN-SUPPLIER",
            )
            detector._snapshots.append(snapshot)
            detector._supplier_snapshots["MAIN-SUPPLIER"].append(snapshot)

        # 3. Analyze drift
        result = detector.analyze_drift()

        assert result.has_drift is True
        assert len(result.alerts) > 0

        # 4. Get active alerts
        active = detector.get_active_alerts()
        assert len(active) > 0

        # 5. Acknowledge alert
        first_alert = active[0]
        detector.acknowledge_alert(first_alert.alert_id)

        assert first_alert.status == AlertStatus.ACKNOWLEDGED

        # 6. Resolve alert
        detector.resolve_alert(first_alert.alert_id)

        assert first_alert.status == AlertStatus.RESOLVED

        # 7. Check summary
        summary = detector.get_drift_summary()
        assert "status" in summary

    def test_multi_supplier_monitoring(self):
        """Test monitoring multiple suppliers."""
        detector = get_drift_detector()

        # Record data for 3 suppliers
        for supplier in ["SUPPLIER-A", "SUPPLIER-B", "SUPPLIER-C"]:
            detector.record_snapshot(
                total_events=100,
                complete_events=95,
                supplier_gln=supplier,
            )

        # Check supplier health
        health = detector.get_supplier_health()

        assert len(health) == 3

        # All should have new supplier alerts
        new_supplier_alerts = [
            a
            for a in detector.get_alerts()
            if a.alert_type == AlertType.NEW_SUPPLIER_DETECTED
        ]
        assert len(new_supplier_alerts) == 3
