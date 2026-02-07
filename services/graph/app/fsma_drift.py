"""
FSMA 204 Drift Detection & Alerting.

Sprint 7: Data Quality Drift Detection

Monitors KDE completeness over time to detect:
- Supplier format changes (sudden increase in missing KDEs)
- Extraction quality degradation
- Document type drift

Per FSMA 204 Section 8.1:
"Alert if % of missing KDEs increases (indicates supplier format change)"
"""

from __future__ import annotations

import statistics
import threading
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger("fsma-drift")


# ============================================================================
# ALERT SEVERITY LEVELS
# ============================================================================


class AlertSeverity(str, Enum):
    """Alert severity levels."""

    INFO = "INFO"  # Informational, no action needed
    WARNING = "WARNING"  # Attention needed, not critical
    CRITICAL = "CRITICAL"  # Immediate action required


class AlertType(str, Enum):
    """Types of drift alerts."""

    KDE_COMPLETENESS_DROP = "KDE_COMPLETENESS_DROP"
    SUPPLIER_FORMAT_CHANGE = "SUPPLIER_FORMAT_CHANGE"
    EXTRACTION_DEGRADATION = "EXTRACTION_DEGRADATION"
    CONFIDENCE_DROP = "CONFIDENCE_DROP"
    VOLUME_ANOMALY = "VOLUME_ANOMALY"
    NEW_SUPPLIER_DETECTED = "NEW_SUPPLIER_DETECTED"


class AlertStatus(str, Enum):
    """Alert lifecycle status."""

    ACTIVE = "ACTIVE"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


# ============================================================================
# DATA MODELS
# ============================================================================


@dataclass
class KDESnapshot:
    """Point-in-time snapshot of KDE completeness metrics."""

    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    supplier_gln: Optional[str] = None
    document_type: Optional[str] = None

    # Completeness metrics
    total_events: int = 0
    complete_events: int = 0
    completeness_rate: float = 0.0

    # Missing field counts
    missing_date_count: int = 0
    missing_lot_count: int = 0
    missing_quantity_count: int = 0
    missing_location_count: int = 0

    # Confidence metrics
    avg_confidence: float = 0.0
    low_confidence_count: int = 0  # < 0.85 threshold

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "supplier_gln": self.supplier_gln,
            "document_type": self.document_type,
            "total_events": self.total_events,
            "complete_events": self.complete_events,
            "completeness_rate": self.completeness_rate,
            "missing_date_count": self.missing_date_count,
            "missing_lot_count": self.missing_lot_count,
            "missing_quantity_count": self.missing_quantity_count,
            "missing_location_count": self.missing_location_count,
            "avg_confidence": self.avg_confidence,
            "low_confidence_count": self.low_confidence_count,
        }


@dataclass
class DriftAlert:
    """Alert generated when drift is detected."""

    alert_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    alert_type: AlertType = AlertType.KDE_COMPLETENESS_DROP
    severity: AlertSeverity = AlertSeverity.WARNING
    status: AlertStatus = AlertStatus.ACTIVE

    # Context
    supplier_gln: Optional[str] = None
    document_type: Optional[str] = None
    tenant_id: Optional[str] = None

    # Drift details
    metric_name: str = ""
    baseline_value: float = 0.0
    current_value: float = 0.0
    drift_percentage: float = 0.0  # Negative = degradation

    # Timestamps
    detected_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    acknowledged_at: Optional[str] = None
    resolved_at: Optional[str] = None

    # Recommendations
    message: str = ""
    recommended_action: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "status": self.status.value,
            "supplier_gln": self.supplier_gln,
            "document_type": self.document_type,
            "tenant_id": self.tenant_id,
            "metric_name": self.metric_name,
            "baseline_value": self.baseline_value,
            "current_value": self.current_value,
            "drift_percentage": self.drift_percentage,
            "detected_at": self.detected_at,
            "acknowledged_at": self.acknowledged_at,
            "resolved_at": self.resolved_at,
            "message": self.message,
            "recommended_action": self.recommended_action,
        }


@dataclass
class DriftAnalysisResult:
    """Result of drift analysis."""

    has_drift: bool = False
    drift_severity: AlertSeverity = AlertSeverity.INFO
    alerts: List[DriftAlert] = field(default_factory=list)

    # Overall health
    overall_health_score: float = 1.0  # 0.0 = critical, 1.0 = healthy

    # Analysis metadata
    analysis_window_hours: int = 24
    baseline_window_hours: int = 168  # 7 days
    snapshots_analyzed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_drift": self.has_drift,
            "drift_severity": self.drift_severity.value,
            "alerts": [a.to_dict() for a in self.alerts],
            "overall_health_score": self.overall_health_score,
            "analysis_window_hours": self.analysis_window_hours,
            "baseline_window_hours": self.baseline_window_hours,
            "snapshots_analyzed": self.snapshots_analyzed,
        }


# ============================================================================
# DRIFT DETECTION ENGINE
# ============================================================================


class DriftDetector:
    """
    Detects drift in KDE completeness and data quality.

    Monitors:
    - KDE completeness rate changes
    - Per-supplier quality degradation
    - Extraction confidence drops
    - Volume anomalies
    """

    # Thresholds for alert generation
    COMPLETENESS_DROP_WARNING = 0.05  # 5% drop = warning
    COMPLETENESS_DROP_CRITICAL = 0.15  # 15% drop = critical
    CONFIDENCE_DROP_WARNING = 0.10  # 10% confidence drop = warning
    VOLUME_ANOMALY_THRESHOLD = 2.0  # 2x standard deviation = anomaly

    def __init__(self):
        self._lock = threading.RLock()
        self._snapshots: List[KDESnapshot] = []
        self._supplier_snapshots: Dict[str, List[KDESnapshot]] = defaultdict(list)
        self._alerts: List[DriftAlert] = []
        self._known_suppliers: set = set()

    def record_snapshot(
        self,
        total_events: int,
        complete_events: int,
        missing_date: int = 0,
        missing_lot: int = 0,
        missing_quantity: int = 0,
        missing_location: int = 0,
        avg_confidence: float = 1.0,
        low_confidence_count: int = 0,
        supplier_gln: Optional[str] = None,
        document_type: Optional[str] = None,
    ) -> KDESnapshot:
        """
        Record a KDE completeness snapshot.

        Call this periodically (e.g., hourly) or after batch ingestion.
        """
        completeness_rate = complete_events / total_events if total_events > 0 else 1.0

        snapshot = KDESnapshot(
            supplier_gln=supplier_gln,
            document_type=document_type,
            total_events=total_events,
            complete_events=complete_events,
            completeness_rate=completeness_rate,
            missing_date_count=missing_date,
            missing_lot_count=missing_lot,
            missing_quantity_count=missing_quantity,
            missing_location_count=missing_location,
            avg_confidence=avg_confidence,
            low_confidence_count=low_confidence_count,
        )

        with self._lock:
            self._snapshots.append(snapshot)

            if supplier_gln:
                # Check for new supplier
                if supplier_gln not in self._known_suppliers:
                    self._known_suppliers.add(supplier_gln)
                    self._create_new_supplier_alert(supplier_gln)

                self._supplier_snapshots[supplier_gln].append(snapshot)

            logger.debug(
                "snapshot_recorded",
                completeness_rate=completeness_rate,
                supplier_gln=supplier_gln,
            )

        return snapshot

    def analyze_drift(
        self,
        analysis_window_hours: int = 24,
        baseline_window_hours: int = 168,  # 7 days
        supplier_gln: Optional[str] = None,
    ) -> DriftAnalysisResult:
        """
        Analyze drift by comparing recent data to historical baseline.

        Args:
            analysis_window_hours: Recent window to analyze (default 24h)
            baseline_window_hours: Historical baseline window (default 7 days)
            supplier_gln: Optional supplier filter

        Returns:
            DriftAnalysisResult with any detected drift alerts
        """
        with self._lock:
            now = datetime.now(timezone.utc)
            analysis_cutoff = now - timedelta(hours=analysis_window_hours)
            baseline_cutoff = now - timedelta(hours=baseline_window_hours)

            # Select snapshots to analyze
            if supplier_gln:
                all_snapshots = self._supplier_snapshots.get(supplier_gln, [])
            else:
                all_snapshots = self._snapshots

            # Split into baseline and recent
            baseline_snapshots = []
            recent_snapshots = []

            for s in all_snapshots:
                snap_time = datetime.fromisoformat(s.timestamp.replace("Z", "+00:00"))
                if snap_time >= analysis_cutoff:
                    recent_snapshots.append(s)
                elif snap_time >= baseline_cutoff:
                    baseline_snapshots.append(s)

            result = DriftAnalysisResult(
                analysis_window_hours=analysis_window_hours,
                baseline_window_hours=baseline_window_hours,
                snapshots_analyzed=len(recent_snapshots) + len(baseline_snapshots),
            )

            if not baseline_snapshots or not recent_snapshots:
                # Not enough data for comparison
                return result

            # Calculate baseline metrics
            baseline_completeness = statistics.mean(
                s.completeness_rate for s in baseline_snapshots
            )
            baseline_confidence = statistics.mean(
                s.avg_confidence for s in baseline_snapshots
            )

            # Calculate recent metrics
            recent_completeness = statistics.mean(
                s.completeness_rate for s in recent_snapshots
            )
            recent_confidence = statistics.mean(
                s.avg_confidence for s in recent_snapshots
            )

            # Detect completeness drift
            completeness_drift = recent_completeness - baseline_completeness
            if completeness_drift < -self.COMPLETENESS_DROP_CRITICAL:
                alert = self._create_completeness_alert(
                    baseline_completeness,
                    recent_completeness,
                    completeness_drift,
                    AlertSeverity.CRITICAL,
                    supplier_gln,
                )
                result.alerts.append(alert)
                result.has_drift = True
                result.drift_severity = AlertSeverity.CRITICAL
            elif completeness_drift < -self.COMPLETENESS_DROP_WARNING:
                alert = self._create_completeness_alert(
                    baseline_completeness,
                    recent_completeness,
                    completeness_drift,
                    AlertSeverity.WARNING,
                    supplier_gln,
                )
                result.alerts.append(alert)
                result.has_drift = True
                if result.drift_severity != AlertSeverity.CRITICAL:
                    result.drift_severity = AlertSeverity.WARNING

            # Detect confidence drift
            confidence_drift = recent_confidence - baseline_confidence
            if confidence_drift < -self.CONFIDENCE_DROP_WARNING:
                alert = self._create_confidence_alert(
                    baseline_confidence,
                    recent_confidence,
                    confidence_drift,
                    supplier_gln,
                )
                result.alerts.append(alert)
                result.has_drift = True

            # Calculate overall health score
            # Score decreases with drift magnitude
            health_factors = [
                1.0 + completeness_drift,  # Drift is negative, so this decreases
                1.0 + (confidence_drift * 0.5),  # Weight confidence less
            ]
            result.overall_health_score = max(
                0.0, min(1.0, statistics.mean(health_factors))
            )

            # Store new alerts
            self._alerts.extend(result.alerts)

            return result

    def analyze_supplier_drift(
        self,
        supplier_gln: str,
        analysis_window_hours: int = 24,
    ) -> DriftAnalysisResult:
        """Analyze drift for a specific supplier."""
        return self.analyze_drift(
            analysis_window_hours=analysis_window_hours,
            supplier_gln=supplier_gln,
        )

    def get_alerts(
        self,
        status: Optional[AlertStatus] = None,
        severity: Optional[AlertSeverity] = None,
        supplier_gln: Optional[str] = None,
        limit: int = 100,
    ) -> List[DriftAlert]:
        """Get alerts with optional filtering."""
        with self._lock:
            alerts = self._alerts

            if status:
                alerts = [a for a in alerts if a.status == status]
            if severity:
                alerts = [a for a in alerts if a.severity == severity]
            if supplier_gln:
                alerts = [a for a in alerts if a.supplier_gln == supplier_gln]

            # Sort by detection time, most recent first
            alerts = sorted(alerts, key=lambda a: a.detected_at, reverse=True)

            return alerts[:limit]

    def get_active_alerts(self) -> List[DriftAlert]:
        """Get all active (unresolved) alerts."""
        return self.get_alerts(status=AlertStatus.ACTIVE)

    def acknowledge_alert(self, alert_id: str, actor: str = "system") -> bool:
        """Acknowledge an alert."""
        with self._lock:
            for alert in self._alerts:
                if alert.alert_id == alert_id:
                    alert.status = AlertStatus.ACKNOWLEDGED
                    alert.acknowledged_at = datetime.now(timezone.utc).isoformat()
                    logger.info(
                        "alert_acknowledged",
                        alert_id=alert_id,
                        actor=actor,
                    )
                    return True
            return False

    def resolve_alert(self, alert_id: str, actor: str = "system") -> bool:
        """Resolve an alert."""
        with self._lock:
            for alert in self._alerts:
                if alert.alert_id == alert_id:
                    alert.status = AlertStatus.RESOLVED
                    alert.resolved_at = datetime.now(timezone.utc).isoformat()
                    logger.info(
                        "alert_resolved",
                        alert_id=alert_id,
                        actor=actor,
                    )
                    return True
            return False

    def get_drift_summary(self) -> Dict[str, Any]:
        """Get summary of current drift status."""
        with self._lock:
            active_alerts = self.get_active_alerts()
            critical_count = sum(
                1 for a in active_alerts if a.severity == AlertSeverity.CRITICAL
            )
            warning_count = sum(
                1 for a in active_alerts if a.severity == AlertSeverity.WARNING
            )

            # Determine overall status
            if critical_count > 0:
                status = "CRITICAL"
            elif warning_count > 0:
                status = "WARNING"
            else:
                status = "HEALTHY"

            return {
                "status": status,
                "active_alerts": len(active_alerts),
                "critical_alerts": critical_count,
                "warning_alerts": warning_count,
                "known_suppliers": len(self._known_suppliers),
                "total_snapshots": len(self._snapshots),
                "last_analysis": datetime.now(timezone.utc).isoformat(),
            }

    def get_supplier_health(self) -> List[Dict[str, Any]]:
        """Get health status per supplier."""
        with self._lock:
            results = []

            for gln, snapshots in self._supplier_snapshots.items():
                if not snapshots:
                    continue

                # Get most recent snapshot
                recent = max(snapshots, key=lambda s: s.timestamp)

                # Get supplier alerts
                supplier_alerts = [
                    a
                    for a in self._alerts
                    if a.supplier_gln == gln and a.status == AlertStatus.ACTIVE
                ]

                results.append(
                    {
                        "supplier_gln": gln,
                        "latest_completeness_rate": recent.completeness_rate,
                        "latest_confidence": recent.avg_confidence,
                        "total_snapshots": len(snapshots),
                        "active_alerts": len(supplier_alerts),
                        "last_seen": recent.timestamp,
                    }
                )

            return sorted(results, key=lambda r: r["active_alerts"], reverse=True)

    def clear(self) -> None:
        """Clear all data (for testing)."""
        with self._lock:
            self._snapshots.clear()
            self._supplier_snapshots.clear()
            self._alerts.clear()
            self._known_suppliers.clear()

    # ========================================================================
    # PRIVATE METHODS
    # ========================================================================

    def _create_completeness_alert(
        self,
        baseline: float,
        current: float,
        drift: float,
        severity: AlertSeverity,
        supplier_gln: Optional[str],
    ) -> DriftAlert:
        """Create a KDE completeness drop alert."""
        drift_pct = drift * 100

        if supplier_gln:
            message = (
                f"Supplier {supplier_gln}: KDE completeness dropped from "
                f"{baseline:.1%} to {current:.1%} ({drift_pct:+.1f}%)"
            )
            recommended = (
                "Review recent documents from this supplier for format changes. "
                "Check if extraction rules need updating."
            )
            alert_type = AlertType.SUPPLIER_FORMAT_CHANGE
        else:
            message = (
                f"Overall KDE completeness dropped from "
                f"{baseline:.1%} to {current:.1%} ({drift_pct:+.1f}%)"
            )
            recommended = (
                "Review recent ingestion batches for quality issues. "
                "Check extraction pipeline health."
            )
            alert_type = AlertType.KDE_COMPLETENESS_DROP

        return DriftAlert(
            alert_type=alert_type,
            severity=severity,
            supplier_gln=supplier_gln,
            metric_name="kde_completeness_rate",
            baseline_value=baseline,
            current_value=current,
            drift_percentage=drift_pct,
            message=message,
            recommended_action=recommended,
        )

    def _create_confidence_alert(
        self,
        baseline: float,
        current: float,
        drift: float,
        supplier_gln: Optional[str],
    ) -> DriftAlert:
        """Create an extraction confidence drop alert."""
        drift_pct = drift * 100

        message = (
            f"Extraction confidence dropped from "
            f"{baseline:.1%} to {current:.1%} ({drift_pct:+.1f}%)"
        )
        if supplier_gln:
            message = f"Supplier {supplier_gln}: " + message

        return DriftAlert(
            alert_type=AlertType.CONFIDENCE_DROP,
            severity=AlertSeverity.WARNING,
            supplier_gln=supplier_gln,
            metric_name="avg_extraction_confidence",
            baseline_value=baseline,
            current_value=current,
            drift_percentage=drift_pct,
            message=message,
            recommended_action=(
                "Review NLP extraction quality. Consider retraining models "
                "or updating extraction patterns for changed document formats."
            ),
        )

    def _create_new_supplier_alert(self, supplier_gln: str) -> DriftAlert:
        """Create alert for new supplier detection."""
        alert = DriftAlert(
            alert_type=AlertType.NEW_SUPPLIER_DETECTED,
            severity=AlertSeverity.INFO,
            supplier_gln=supplier_gln,
            metric_name="new_supplier",
            message=f"New supplier detected: {supplier_gln}",
            recommended_action=(
                "Verify supplier information and monitor initial document "
                "quality to establish baseline."
            ),
        )

        with self._lock:
            self._alerts.append(alert)

        logger.info("new_supplier_detected", supplier_gln=supplier_gln)
        return alert


# ============================================================================
# GLOBAL DRIFT DETECTOR INSTANCE
# ============================================================================

_global_detector: Optional[DriftDetector] = None
_global_lock = threading.Lock()


def get_drift_detector() -> DriftDetector:
    """Get the global drift detector instance."""
    global _global_detector
    with _global_lock:
        if _global_detector is None:
            _global_detector = DriftDetector()
        return _global_detector


def reset_drift_detector() -> None:
    """Reset the global drift detector (for testing)."""
    global _global_detector
    with _global_lock:
        _global_detector = DriftDetector()


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================


def record_ingestion_quality(
    total_events: int,
    complete_events: int,
    missing_date: int = 0,
    missing_lot: int = 0,
    avg_confidence: float = 1.0,
    supplier_gln: Optional[str] = None,
    document_type: Optional[str] = None,
) -> KDESnapshot:
    """Record quality metrics after batch ingestion."""
    return get_drift_detector().record_snapshot(
        total_events=total_events,
        complete_events=complete_events,
        missing_date=missing_date,
        missing_lot=missing_lot,
        avg_confidence=avg_confidence,
        supplier_gln=supplier_gln,
        document_type=document_type,
    )


def check_for_drift(
    analysis_window_hours: int = 24,
    supplier_gln: Optional[str] = None,
) -> DriftAnalysisResult:
    """Check for drift in recent data."""
    return get_drift_detector().analyze_drift(
        analysis_window_hours=analysis_window_hours,
        supplier_gln=supplier_gln,
    )


def get_active_drift_alerts() -> List[DriftAlert]:
    """Get all active drift alerts."""
    return get_drift_detector().get_active_alerts()


def get_drift_status() -> Dict[str, Any]:
    """Get current drift monitoring status."""
    return get_drift_detector().get_drift_summary()
