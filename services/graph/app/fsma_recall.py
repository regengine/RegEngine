"""
FSMA 204 Mock Recall Automation Engine.

Sprint 8: Programmatic recall drill execution, tracking, and FDA compliance.

Per FSMA 204 requirements:
- Organizations must be able to produce traceability records within 24 hours of FDA request
- Regular mock recalls validate recall readiness
- All drill results must be auditable

This module provides:
- MockRecallEngine: Orchestrates recall drill execution
- RecallDrill: Represents a single mock recall exercise
- RecallResult: Captures drill outcomes with SLA metrics
- RecallSchedule: Manages periodic recall drill scheduling
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import inspect


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
            return (datetime.utcnow() - self.started_at).total_seconds()
        return None

    @property
    def sla_status(self) -> SLAStatus:
        """Determine SLA compliance status."""
        if not self.started_at:
            return SLAStatus.MET

        elapsed = (datetime.utcnow() - self.started_at).total_seconds()
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


class MockRecallEngine:
    """
    Mock Recall Automation Engine.

    Orchestrates recall drill execution, tracks history, and maintains
    SLA compliance metrics for FDA audit readiness.
    """

    # 24-hour SLA limit in seconds
    SLA_LIMIT_SECONDS = 24 * 3600

    def __init__(
        self,
        trace_forward_fn: Optional[Callable] = None,
        trace_backward_fn: Optional[Callable] = None,
        export_fn: Optional[Callable] = None,
    ):
        """
        Initialize the recall engine.

        Args:
            trace_forward_fn: Function to execute forward traces
            trace_backward_fn: Function to execute backward traces
            export_fn: Function to generate FDA exports
        """
        self._trace_forward = trace_forward_fn
        self._trace_backward = trace_backward_fn
        self._export_fn = export_fn

        # Drill history by tenant
        self._drills: Dict[str, List[RecallDrill]] = {}

        # Scheduled drills by tenant
        self._schedules: Dict[str, List[ScheduledDrill]] = {}

        # SLA metrics cache
        self._sla_metrics: Dict[str, Dict[str, Any]] = {}

    def create_drill(
        self,
        tenant_id: str,
        drill_type: RecallType,
        severity: RecallSeverity = RecallSeverity.CLASS_II,
        target_lot: Optional[str] = None,
        target_gtin: Optional[str] = None,
        target_facility_gln: Optional[str] = None,
        initiated_by: str = "system",
        reason: str = "manual_drill",
        description: Optional[str] = None,
    ) -> RecallDrill:
        """
        Create a new mock recall drill.

        Args:
            tenant_id: Tenant identifier
            drill_type: Type of recall (forward, backward, full)
            severity: FDA recall classification
            target_lot: Starting lot code for trace
            target_gtin: Product identifier
            target_facility_gln: Facility identifier
            initiated_by: User or system identifier
            reason: Reason for drill
            description: Optional description

        Returns:
            Created RecallDrill instance
        """
        drill = RecallDrill(
            drill_id=f"drill_{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            created_at=datetime.utcnow(),
            drill_type=drill_type,
            severity=severity,
            target_lot=target_lot,
            target_gtin=target_gtin,
            target_facility_gln=target_facility_gln,
            initiated_by=initiated_by,
            reason=reason,
            description=description,
        )

        if tenant_id not in self._drills:
            self._drills[tenant_id] = []
        self._drills[tenant_id].append(drill)

        return drill

    async def execute_drill(self, drill: RecallDrill) -> RecallResult:
        """
        Execute a mock recall drill.

        Performs trace queries, calculates metrics, and generates exports.

        Args:
            drill: The drill to execute

        Returns:
            RecallResult with execution metrics
        """
        import time

        drill.status = RecallStatus.IN_PROGRESS
        drill.started_at = datetime.utcnow()

        start_time = time.time()
        errors: List[str] = []
        warnings: List[str] = []

        # Initialize result metrics
        lots_traced = 0
        facilities: List[AffectedFacility] = []
        max_forward = 0
        max_backward = 0
        trace_time = 0.0

        try:
            # Execute traces based on drill type
            trace_start = time.time()

            if drill.drill_type in (RecallType.FORWARD_TRACE, RecallType.FULL_TRACE):
                if self._trace_forward and drill.target_lot:
                    if inspect.iscoroutinefunction(self._trace_forward):
                        result = await self._trace_forward(drill.target_lot, tenant_id=drill.tenant_id)
                    else:
                        result = self._trace_forward(drill.target_lot, tenant_id=drill.tenant_id)
                    
                    if result:
                        lots_traced += result.get("lots_count", 0)
                        max_forward = result.get("max_depth", 0)
                        facilities.extend(
                            self._extract_facilities(result, "downstream")
                        )
                else:
                    # Simulate trace for testing
                    lots_traced += 5
                    max_forward = 3
                    facilities.append(
                        AffectedFacility(
                            gln="1234567890123",
                            name="Demo Processor",
                            facility_type="processor",
                            lots_affected=[drill.target_lot or "DEMO-001"],
                            quantity_affected=100.0,
                        )
                    )

            if drill.drill_type in (RecallType.BACKWARD_TRACE, RecallType.FULL_TRACE):
                if self._trace_backward and drill.target_lot:
                    if inspect.iscoroutinefunction(self._trace_backward):
                        result = await self._trace_backward(drill.target_lot, tenant_id=drill.tenant_id)
                    else:
                        result = self._trace_backward(drill.target_lot, tenant_id=drill.tenant_id)
                    
                    if result:
                        lots_traced += result.get("lots_count", 0)
                        max_backward = result.get("max_depth", 0)
                        facilities.extend(self._extract_facilities(result, "upstream"))
                else:
                    # Simulate trace for testing
                    lots_traced += 3
                    max_backward = 2
                    facilities.append(
                        AffectedFacility(
                            gln="9876543210987",
                            name="Demo Grower",
                            facility_type="grower",
                            lots_affected=[drill.target_lot or "RAW-001"],
                            quantity_affected=200.0,
                        )
                    )

            if drill.drill_type == RecallType.MASS_BALANCE:
                # Quantity reconciliation check
                warnings.append("Mass balance drill - verify quantities manually")
                lots_traced = 1

            if drill.drill_type == RecallType.TARGETED:
                # Single facility targeted drill
                if drill.target_facility_gln:
                    facilities.append(
                        AffectedFacility(
                            gln=drill.target_facility_gln,
                            name="Targeted Facility",
                            facility_type="unknown",
                            lots_affected=(
                                [drill.target_lot] if drill.target_lot else []
                            ),
                            quantity_affected=0.0,
                        )
                    )
                    lots_traced = 1

            trace_time = time.time() - trace_start

            # Generate exports if export function available
            export_time = 0.0
            csv_path = None
            contact_path = None

            if self._export_fn:
                export_start = time.time()
                try:
                    if inspect.iscoroutinefunction(self._export_fn):
                        export_result = await self._export_fn(drill, facilities, tenant_id=drill.tenant_id)
                    else:
                        export_result = self._export_fn(drill, facilities, tenant_id=drill.tenant_id)
                    
                    csv_path = export_result.get("csv_path")
                    contact_path = export_result.get("contact_path")
                except Exception as e:
                    warnings.append(f"Export warning: {str(e)}")
                export_time = time.time() - export_start

            # Calculate total time
            total_time = time.time() - start_time

            # Determine SLA compliance
            sla_compliant = total_time < self.SLA_LIMIT_SECONDS

            # Calculate data completeness
            total_quantity = sum(f.quantity_affected for f in facilities)
            gaps = len([f for f in facilities if not f.lots_affected])
            completeness = (
                100.0
                if not facilities
                else (((len(facilities) - gaps) / len(facilities)) * 100)
            )

            # Create result
            result = RecallResult(
                drill_id=drill.drill_id,
                success=True,
                lots_traced=lots_traced,
                facilities_identified=len(facilities),
                total_quantity_affected=total_quantity,
                max_depth_forward=max_forward,
                max_depth_backward=max_backward,
                trace_time_seconds=trace_time,
                export_time_seconds=export_time,
                total_time_seconds=total_time,
                sla_compliant=sla_compliant,
                gaps_found=gaps,
                data_completeness_pct=completeness,
                affected_facilities=facilities,
                csv_export_path=csv_path,
                contact_list_path=contact_path,
                errors=errors,
                warnings=warnings,
            )

            drill.status = RecallStatus.COMPLETED
            drill.completed_at = datetime.utcnow()
            drill.result = result

        except Exception as e:
            # Handle execution failure
            errors.append(str(e))
            result = RecallResult(
                drill_id=drill.drill_id,
                success=False,
                total_time_seconds=time.time() - start_time,
                sla_compliant=False,
                errors=errors,
            )
            drill.status = RecallStatus.FAILED
            drill.completed_at = datetime.utcnow()
            drill.result = result

        # Update SLA metrics
        self._update_sla_metrics(drill.tenant_id, result)

        return result

    def _extract_facilities(
        self,
        trace_result: Dict[str, Any],
        direction: str,
    ) -> List[AffectedFacility]:
        """Extract facility info from trace results."""
        facilities = []

        raw_facilities = trace_result.get("facilities", [])
        for f in raw_facilities:
            facilities.append(
                AffectedFacility(
                    gln=f.get("gln", "unknown"),
                    name=f.get("name", "Unknown Facility"),
                    facility_type=f.get("type", direction),
                    lots_affected=f.get("lots", []),
                    quantity_affected=f.get("quantity", 0.0),
                    unit_of_measure=f.get("unit", "cases"),
                    contact_info=f.get("contact"),
                )
            )

        return facilities

    def _update_sla_metrics(self, tenant_id: str, result: RecallResult) -> None:
        """Update SLA metrics cache for tenant."""
        if tenant_id not in self._sla_metrics:
            self._sla_metrics[tenant_id] = {
                "total_drills": 0,
                "successful_drills": 0,
                "sla_compliant_drills": 0,
                "total_trace_time": 0.0,
                "avg_trace_time": 0.0,
                "last_drill_at": None,
            }

        metrics = self._sla_metrics[tenant_id]
        metrics["total_drills"] += 1

        if result.success:
            metrics["successful_drills"] += 1

        if result.sla_compliant:
            metrics["sla_compliant_drills"] += 1

        metrics["total_trace_time"] += result.trace_time_seconds
        metrics["avg_trace_time"] = (
            metrics["total_trace_time"] / metrics["total_drills"]
        )
        metrics["last_drill_at"] = datetime.utcnow().isoformat()

        # Calculate compliance rate
        metrics["sla_compliance_rate"] = (
            (metrics["sla_compliant_drills"] / metrics["total_drills"]) * 100
            if metrics["total_drills"] > 0
            else 100.0
        )

    def get_drill_history(
        self,
        tenant_id: str,
        limit: int = 50,
        status_filter: Optional[RecallStatus] = None,
        since: Optional[datetime] = None,
    ) -> List[RecallDrill]:
        """
        Get drill history for a tenant.

        Args:
            tenant_id: Tenant identifier
            limit: Maximum results to return
            status_filter: Filter by drill status
            since: Only return drills after this time

        Returns:
            List of RecallDrill instances
        """
        drills = self._drills.get(tenant_id, [])

        # Apply filters
        if status_filter:
            drills = [d for d in drills if d.status == status_filter]

        if since:
            drills = [d for d in drills if d.created_at >= since]

        # Sort by creation time, most recent first
        drills = sorted(drills, key=lambda d: d.created_at, reverse=True)

        return drills[:limit]

    def get_drill(self, tenant_id: str, drill_id: str) -> Optional[RecallDrill]:
        """Get a specific drill by ID."""
        drills = self._drills.get(tenant_id, [])
        for drill in drills:
            if drill.drill_id == drill_id:
                return drill
        return None

    def cancel_drill(self, drill: RecallDrill) -> bool:
        """Cancel a pending or in-progress drill."""
        if drill.status in (RecallStatus.PENDING, RecallStatus.IN_PROGRESS):
            drill.status = RecallStatus.CANCELLED
            drill.completed_at = datetime.utcnow()
            return True
        return False

    def get_sla_metrics(self, tenant_id: str) -> Dict[str, Any]:
        """Get SLA compliance metrics for a tenant."""
        return self._sla_metrics.get(
            tenant_id,
            {
                "total_drills": 0,
                "successful_drills": 0,
                "sla_compliant_drills": 0,
                "sla_compliance_rate": 100.0,
                "avg_trace_time": 0.0,
                "last_drill_at": None,
            },
        )

    def create_schedule(
        self,
        tenant_id: str,
        drill_type: RecallType,
        frequency_days: int = 90,  # Quarterly by default
        severity: RecallSeverity = RecallSeverity.CLASS_II,
        target_strategy: str = "random",
        specific_targets: Optional[List[str]] = None,
    ) -> ScheduledDrill:
        """
        Create a recurring drill schedule.

        Args:
            tenant_id: Tenant identifier
            drill_type: Type of drill to schedule
            frequency_days: Days between drills (90 = quarterly)
            severity: Simulated severity level
            target_strategy: How to select targets (random, rotating, specific)
            specific_targets: List of specific targets for 'specific' strategy

        Returns:
            Created ScheduledDrill instance
        """
        schedule = ScheduledDrill(
            schedule_id=f"sched_{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            drill_type=drill_type,
            severity=severity,
            frequency_days=frequency_days,
            next_run=datetime.utcnow() + timedelta(days=frequency_days),
            target_strategy=target_strategy,
            specific_targets=specific_targets,
        )

        if tenant_id not in self._schedules:
            self._schedules[tenant_id] = []
        self._schedules[tenant_id].append(schedule)

        return schedule

    def get_schedules(self, tenant_id: str) -> List[ScheduledDrill]:
        """Get all scheduled drills for a tenant."""
        return self._schedules.get(tenant_id, [])

    def get_schedule(
        self,
        tenant_id: str,
        schedule_id: str,
    ) -> Optional[ScheduledDrill]:
        """Get a specific schedule by ID."""
        schedules = self._schedules.get(tenant_id, [])
        for schedule in schedules:
            if schedule.schedule_id == schedule_id:
                return schedule
        return None

    def update_schedule(
        self,
        schedule: ScheduledDrill,
        enabled: Optional[bool] = None,
        frequency_days: Optional[int] = None,
    ) -> ScheduledDrill:
        """Update a schedule's configuration."""
        if enabled is not None:
            schedule.enabled = enabled

        if frequency_days is not None:
            schedule.frequency_days = frequency_days
            # Recalculate next run
            base = schedule.last_run or datetime.utcnow()
            schedule.next_run = base + timedelta(days=frequency_days)

        return schedule

    def delete_schedule(self, tenant_id: str, schedule_id: str) -> bool:
        """Delete a schedule."""
        schedules = self._schedules.get(tenant_id, [])
        for i, schedule in enumerate(schedules):
            if schedule.schedule_id == schedule_id:
                del schedules[i]
                return True
        return False

    def check_due_schedules(self, tenant_id: str) -> List[ScheduledDrill]:
        """Get schedules that are due for execution."""
        now = datetime.utcnow()
        schedules = self._schedules.get(tenant_id, [])
        return [s for s in schedules if s.enabled and s.next_run <= now]

    async def execute_scheduled_drill(
        self,
        schedule: ScheduledDrill,
    ) -> RecallDrill:
        """
        Execute a scheduled drill.

        Creates a new drill from the schedule and executes it.
        """
        # Select target based on strategy
        target_lot = None
        if schedule.target_strategy == "specific" and schedule.specific_targets:
            # Use first target (could rotate in future)
            target_lot = schedule.specific_targets[0]
        # For 'random' strategy, target would be selected from active lots

        # Create drill from schedule
        drill = self.create_drill(
            tenant_id=schedule.tenant_id,
            drill_type=schedule.drill_type,
            severity=schedule.severity,
            target_lot=target_lot,
            initiated_by="scheduler",
            reason="scheduled_drill",
            description=f"Scheduled drill from {schedule.schedule_id}",
        )

        # Execute
        await self.execute_drill(drill)

        # Update schedule
        schedule.last_run = datetime.utcnow()
        schedule.last_result = drill.drill_id
        schedule.next_run = datetime.utcnow() + timedelta(days=schedule.frequency_days)

        return drill

    def get_readiness_report(self, tenant_id: str) -> Dict[str, Any]:
        """
        Generate a recall readiness report for FDA audit.

        Returns comprehensive metrics on recall drill performance.
        """
        drills = self._drills.get(tenant_id, [])
        schedules = self._schedules.get(tenant_id, [])
        sla_metrics = self.get_sla_metrics(tenant_id)

        # Calculate additional metrics
        completed_drills = [d for d in drills if d.status == RecallStatus.COMPLETED]
        recent_drills = [
            d
            for d in completed_drills
            if d.completed_at
            and d.completed_at > datetime.utcnow() - timedelta(days=365)
        ]

        # Drill frequency analysis
        quarterly_count = len(
            [
                d
                for d in recent_drills
                if d.completed_at
                and d.completed_at > datetime.utcnow() - timedelta(days=90)
            ]
        )

        # Data quality from results
        avg_completeness = 0.0
        if recent_drills:
            completeness_values = [
                d.result.data_completeness_pct for d in recent_drills if d.result
            ]
            avg_completeness = (
                sum(completeness_values) / len(completeness_values)
                if completeness_values
                else 0.0
            )

        return {
            "tenant_id": tenant_id,
            "generated_at": datetime.utcnow().isoformat(),
            "overall_readiness": (
                "ready"
                if sla_metrics.get("sla_compliance_rate", 0) >= 95
                else "needs_improvement"
            ),
            "sla_compliance": {
                "rate_pct": sla_metrics.get("sla_compliance_rate", 100.0),
                "target_pct": 100.0,
                "status": (
                    "compliant"
                    if sla_metrics.get("sla_compliance_rate", 100) >= 95
                    else "at_risk"
                ),
            },
            "drill_metrics": {
                "total_drills": len(drills),
                "completed_drills": len(completed_drills),
                "drills_last_90_days": quarterly_count,
                "recommended_quarterly": 1,
                "avg_trace_time_seconds": sla_metrics.get("avg_trace_time", 0.0),
            },
            "data_quality": {
                "avg_completeness_pct": avg_completeness,
                "target_pct": 100.0,
            },
            "schedules": {
                "active_schedules": len([s for s in schedules if s.enabled]),
                "total_schedules": len(schedules),
            },
            "recommendations": self._generate_recommendations(
                sla_metrics,
                quarterly_count,
                avg_completeness,
            ),
        }

    def _generate_recommendations(
        self,
        sla_metrics: Dict[str, Any],
        quarterly_drills: int,
        avg_completeness: float,
    ) -> List[str]:
        """Generate improvement recommendations."""
        recommendations = []

        if quarterly_drills < 1:
            recommendations.append(
                "Schedule quarterly mock recalls to maintain FDA readiness"
            )

        if sla_metrics.get("sla_compliance_rate", 100) < 95:
            recommendations.append(
                "Improve trace query performance to meet 24-hour SLA consistently"
            )

        if avg_completeness < 95:
            recommendations.append(
                "Address data gaps to improve traceability completeness"
            )

        if not recommendations:
            recommendations.append(
                "Recall readiness is excellent - maintain current drill schedule"
            )

        return recommendations


# ============================================================================
# GLOBAL INSTANCE & CONVENIENCE FUNCTIONS
# ============================================================================

_recall_engine: Optional[MockRecallEngine] = None


def get_recall_engine() -> MockRecallEngine:
    """Get or create the global MockRecallEngine instance."""
    global _recall_engine
    if _recall_engine is None:
        _recall_engine = MockRecallEngine()
    return _recall_engine


def reset_recall_engine() -> None:
    """Reset the global engine (for testing)."""
    global _recall_engine
    _recall_engine = None


async def create_mock_recall(
    tenant_id: str,
    drill_type: str = "full_trace",
    severity: str = "class_ii",
    target_lot: Optional[str] = None,
    initiated_by: str = "api",
) -> Dict[str, Any]:
    """
    Convenience function to create and execute a mock recall drill.

    Args:
        tenant_id: Tenant identifier
        drill_type: Type of recall (forward_trace, backward_trace, full_trace)
        severity: FDA classification (class_i, class_ii, class_iii)
        target_lot: Optional starting lot code
        initiated_by: User/system identifier

    Returns:
        Dict with drill_id, status, and result summary
    """
    engine = get_recall_engine()

    drill = engine.create_drill(
        tenant_id=tenant_id,
        drill_type=RecallType(drill_type),
        severity=RecallSeverity(severity),
        target_lot=target_lot,
        initiated_by=initiated_by,
        reason="api_request",
    )

    result = await engine.execute_drill(drill)

    return {
        "drill_id": drill.drill_id,
        "status": drill.status.value,
        "sla_status": drill.sla_status.value,
        "result": result.get_summary(),
    }


def get_recall_history(
    tenant_id: str,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Get recent recall drill history."""
    engine = get_recall_engine()
    drills = engine.get_drill_history(tenant_id, limit=limit)
    return [d.to_dict() for d in drills]


def get_recall_readiness(tenant_id: str) -> Dict[str, Any]:
    """Get recall readiness report for tenant."""
    engine = get_recall_engine()
    return engine.get_readiness_report(tenant_id)
