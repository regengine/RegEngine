# ============================================================
# FSMA 204 Recall — data models (enums + dataclasses)
# Split from monolithic fsma_recall.py — zero logic changes.
# ============================================================
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class RecallStatus(str, Enum):
    """Status of a recall drill."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RecallType(str, Enum):
    """Type of recall drill."""

    FORWARD_TRACE = "forward_trace"  # From raw material to consumer
    BACKWARD_TRACE = "backward_trace"  # From consumer to source
    FULL_TRACE = "full_trace"  # Both directions
    TARGETED = "targeted"  # Specific facility/lot
    MASS_BALANCE = "mass_balance"  # Quantity reconciliation


class RecallSeverity(str, Enum):
    """Simulated recall severity (FDA classification)."""

    CLASS_I = "class_i"  # Serious health consequences or death
    CLASS_II = "class_ii"  # Temporary/reversible health consequences
    CLASS_III = "class_iii"  # Not likely to cause adverse health


class SLAStatus(str, Enum):
    """SLA compliance status for 24-hour mandate."""

    MET = "met"  # Completed within 24 hours
    AT_RISK = "at_risk"  # Approaching deadline
    BREACHED = "breached"  # Exceeded 24 hours


@dataclass
class AffectedFacility:
    """Facility identified in a recall trace."""

    gln: str
    name: str
    facility_type: str  # grower, processor, distributor, retailer
    lots_affected: List[str]
    quantity_affected: float
    unit_of_measure: str = "cases"
    contact_info: Optional[Dict[str, str]] = None
    notification_status: str = "pending"  # pending, notified, acknowledged


@dataclass
class RecallDrill:
    """
    Represents a single mock recall exercise.

    Captures all parameters needed to execute and audit a recall drill.
    """

    drill_id: str
    tenant_id: str
    created_at: datetime
    drill_type: RecallType
    severity: RecallSeverity

    # Target identification
    target_lot: Optional[str] = None
    target_gtin: Optional[str] = None
    target_facility_gln: Optional[str] = None

    # Drill metadata
    initiated_by: str = "system"
    reason: str = "scheduled_drill"
    description: Optional[str] = None

    # Execution tracking
    status: RecallStatus = RecallStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Results placeholder
    result: Optional[RecallResult] = None

    def __post_init__(self):
        if not self.drill_id:
            self.drill_id = f"drill_{uuid.uuid4().hex[:12]}"

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate drill duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        elif self.started_at:
            return (datetime.now(timezone.utc) - self.started_at).total_seconds()
        return None

    @property
    def sla_status(self) -> SLAStatus:
        """Determine SLA compliance status."""
        if not self.started_at:
            return SLAStatus.MET

        elapsed = (datetime.now(timezone.utc) - self.started_at).total_seconds()
        sla_limit = 24 * 3600  # 24 hours in seconds

        if self.status == RecallStatus.COMPLETED:
            if self.duration_seconds and self.duration_seconds <= sla_limit:
                return SLAStatus.MET
            return SLAStatus.BREACHED

        # Still in progress
        if elapsed > sla_limit:
            return SLAStatus.BREACHED
        elif elapsed > sla_limit * 0.75:  # 75% of deadline
            return SLAStatus.AT_RISK
        return SLAStatus.MET

    def to_dict(self) -> Dict[str, Any]:
        """Serialize drill for API response."""
        return {
            "drill_id": self.drill_id,
            "tenant_id": self.tenant_id,
            "created_at": self.created_at.isoformat(),
            "drill_type": self.drill_type.value,
            "severity": self.severity.value,
            "target_lot": self.target_lot,
            "target_gtin": self.target_gtin,
            "target_facility_gln": self.target_facility_gln,
            "initiated_by": self.initiated_by,
            "reason": self.reason,
            "description": self.description,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "duration_seconds": self.duration_seconds,
            "sla_status": self.sla_status.value,
            "result": self.result.to_dict() if self.result else None,
        }


@dataclass
class RecallResult:
    """
    Results of a recall drill execution.

    Captures metrics, affected parties, and SLA compliance data.
    """

    drill_id: str
    success: bool

    # Trace metrics
    lots_traced: int = 0
    facilities_identified: int = 0
    total_quantity_affected: float = 0.0
    unit_of_measure: str = "cases"

    # Trace depth
    max_depth_forward: int = 0
    max_depth_backward: int = 0

    # SLA metrics
    trace_time_seconds: float = 0.0
    export_time_seconds: float = 0.0
    total_time_seconds: float = 0.0
    sla_compliant: bool = True

    # Data quality
    gaps_found: int = 0
    orphans_found: int = 0
    data_completeness_pct: float = 100.0

    # Affected facilities
    affected_facilities: List[AffectedFacility] = field(default_factory=list)

    # Export artifacts
    csv_export_path: Optional[str] = None
    contact_list_path: Optional[str] = None

    # Error tracking
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize result for API response."""
        return {
            "drill_id": self.drill_id,
            "success": self.success,
            "lots_traced": self.lots_traced,
            "facilities_identified": self.facilities_identified,
            "total_quantity_affected": self.total_quantity_affected,
            "unit_of_measure": self.unit_of_measure,
            "max_depth_forward": self.max_depth_forward,
            "max_depth_backward": self.max_depth_backward,
            "trace_time_seconds": self.trace_time_seconds,
            "export_time_seconds": self.export_time_seconds,
            "total_time_seconds": self.total_time_seconds,
            "sla_compliant": self.sla_compliant,
            "gaps_found": self.gaps_found,
            "orphans_found": self.orphans_found,
            "data_completeness_pct": self.data_completeness_pct,
            "affected_facilities": [
                {
                    "gln": f.gln,
                    "name": f.name,
                    "facility_type": f.facility_type,
                    "lots_affected": f.lots_affected,
                    "quantity_affected": f.quantity_affected,
                    "unit_of_measure": f.unit_of_measure,
                    "notification_status": f.notification_status,
                }
                for f in self.affected_facilities
            ],
            "csv_export_path": self.csv_export_path,
            "contact_list_path": self.contact_list_path,
            "errors": self.errors,
            "warnings": self.warnings,
        }

    def get_summary(self) -> Dict[str, Any]:
        """Get abbreviated summary for dashboards."""
        return {
            "drill_id": self.drill_id,
            "success": self.success,
            "lots_traced": self.lots_traced,
            "facilities_identified": self.facilities_identified,
            "total_time_seconds": self.total_time_seconds,
            "sla_compliant": self.sla_compliant,
            "data_completeness_pct": self.data_completeness_pct,
        }


@dataclass
class ScheduledDrill:
    """A scheduled recurring mock recall drill."""

    schedule_id: str
    tenant_id: str
    drill_type: RecallType
    severity: RecallSeverity
    frequency_days: int  # How often to run (e.g., 90 = quarterly)
    next_run: datetime
    enabled: bool = True
    last_run: Optional[datetime] = None
    last_result: Optional[str] = None  # drill_id of last execution

    # Target selection strategy
    target_strategy: str = "random"  # random, rotating, specific
    specific_targets: Optional[List[str]] = None  # For specific strategy

    def to_dict(self) -> Dict[str, Any]:
        """Serialize schedule for API response."""
        return {
            "schedule_id": self.schedule_id,
            "tenant_id": self.tenant_id,
            "drill_type": self.drill_type.value,
            "severity": self.severity.value,
            "frequency_days": self.frequency_days,
            "next_run": self.next_run.isoformat(),
            "enabled": self.enabled,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "last_result": self.last_result,
            "target_strategy": self.target_strategy,
            "specific_targets": self.specific_targets,
        }
