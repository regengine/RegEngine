# ============================================================
# FSMA 204 Recall — MockRecallEngine class
# Split from monolithic fsma_recall.py — zero logic changes.
# ============================================================
from __future__ import annotations

import inspect
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from .models import (
    AffectedFacility,
    RecallDrill,
    RecallResult,
    RecallSeverity,
    RecallStatus,
    RecallType,
    ScheduledDrill,
    SLAStatus,
)
from .persistence import (
    _get_db_engine,
    _upsert_drill_row,
    _update_drill_row,
    _load_drills_from_db,
    _load_drill_by_id_from_db,
    _dict_to_recall_drill,
)


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

        # In-memory cache for active drills in the current process lifetime
        self._drills: Dict[str, List[RecallDrill]] = {}

        # Scheduled drills by tenant (not yet persisted — schedules are low-volume)
        self._schedules: Dict[str, List[ScheduledDrill]] = {}

        # SLA metrics cache (rebuilt from DB on demand)
        self._sla_metrics: Dict[str, Dict[str, Any]] = {}

        # Lazy DB engine — initialised on first use
        self._db_engine = None

    def _get_engine(self):
        """Return (and cache) the DB engine, or None if DATABASE_URL is not set."""
        if self._db_engine is None:
            self._db_engine = _get_db_engine()
        return self._db_engine

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
            created_at=datetime.now(timezone.utc),
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

        # Persist to PostgreSQL so history survives restarts
        engine = self._get_engine()
        if engine is not None:
            _upsert_drill_row(engine, drill)

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
        drill.started_at = datetime.now(timezone.utc)

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
                    import logging
                    logging.getLogger("fsma_recall").warning(f"Export warning during recall drill: {e}", exc_info=True)
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
            drill.completed_at = datetime.now(timezone.utc)
            drill.result = result

        except Exception as e:
            # Handle execution failure
            import logging
            logging.getLogger("fsma_recall").error(f"Recall drill execution failed: {e}", exc_info=True)
            errors.append(str(e))
            result = RecallResult(
                drill_id=drill.drill_id,
                success=False,
                total_time_seconds=time.time() - start_time,
                sla_compliant=False,
                errors=errors,
            )
            drill.status = RecallStatus.FAILED
            drill.completed_at = datetime.now(timezone.utc)
            drill.result = result

        # Update SLA metrics
        self._update_sla_metrics(drill.tenant_id, result)

        # Persist updated drill status to PostgreSQL
        engine = self._get_engine()
        if engine is not None:
            _update_drill_row(engine, drill)

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
        metrics["last_drill_at"] = datetime.now(timezone.utc).isoformat()

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

        Reads from PostgreSQL when available so history survives restarts.
        Falls back to the in-process cache when the DB is unreachable.

        Args:
            tenant_id: Tenant identifier
            limit: Maximum results to return
            status_filter: Filter by drill status
            since: Only return drills after this time

        Returns:
            List of RecallDrill instances
        """
        engine = self._get_engine()
        if engine is not None:
            rows = _load_drills_from_db(engine, tenant_id, limit=limit * 2)
            drills = [_dict_to_recall_drill(r) for r in rows]
        else:
            drills = list(self._drills.get(tenant_id, []))

        # Apply filters
        if status_filter:
            drills = [d for d in drills if d.status == status_filter]

        if since:
            drills = [d for d in drills if d.created_at >= since]

        # Sort by creation time, most recent first
        drills = sorted(drills, key=lambda d: d.created_at, reverse=True)

        return drills[:limit]

    def get_drill(self, tenant_id: str, drill_id: str) -> Optional[RecallDrill]:
        """Get a specific drill by ID.

        Checks the in-process cache first (fast path for drills created in
        this request), then falls back to PostgreSQL for drills from prior
        restarts.
        """
        # Fast path: check in-memory cache first (covers drills just created)
        drills = self._drills.get(tenant_id, [])
        for drill in drills:
            if drill.drill_id == drill_id:
                return drill

        # DB path: drill may have been created before this process started
        engine = self._get_engine()
        if engine is not None:
            row = _load_drill_by_id_from_db(engine, tenant_id, drill_id)
            if row:
                return _dict_to_recall_drill(row)

        return None

    def cancel_drill(self, drill: RecallDrill) -> bool:
        """Cancel a pending or in-progress drill."""
        if drill.status in (RecallStatus.PENDING, RecallStatus.IN_PROGRESS):
            drill.status = RecallStatus.CANCELLED
            drill.completed_at = datetime.now(timezone.utc)
            engine = self._get_engine()
            if engine is not None:
                _update_drill_row(engine, drill)
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
            next_run=datetime.now(timezone.utc) + timedelta(days=frequency_days),
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
            base = schedule.last_run or datetime.now(timezone.utc)
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
        now = datetime.now(timezone.utc)
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
        schedule.last_run = datetime.now(timezone.utc)
        schedule.last_result = drill.drill_id
        schedule.next_run = datetime.now(timezone.utc) + timedelta(days=schedule.frequency_days)

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
            and d.completed_at > datetime.now(timezone.utc) - timedelta(days=365)
        ]

        # Drill frequency analysis
        quarterly_count = len(
            [
                d
                for d in recent_drills
                if d.completed_at
                and d.completed_at > datetime.now(timezone.utc) - timedelta(days=90)
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
            "generated_at": datetime.now(timezone.utc).isoformat(),
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
