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
    _dict_to_recall_drill,
    _get_db_engine,
    _load_drill_by_id_from_db,
    _load_drills_from_db,
    _select_random_target_lot,
    _update_drill_row,
    _upsert_drill_row,
)

# #2943: the drill warning appended when no trace function is wired and the
# engine falls back to hardcoded demo counts. Without it the fallback's 5/3 and
# 3/2 are indistinguishable from a real trace's numbers — and healthier-looking
# than the zeroes the real path used to record.
SIMULATED_TRACE_WARNING = "trace unavailable: missing target lot or graph backend; no trace evidence generated"

# Appended when the tracer returned facilities but no lot-event associations
# (``TraceResult.trace_rows is None``): the per-facility lots, the quantities
# and the orphan count cannot be measured, and the record says so rather
# than reporting zeroes.
NO_ASSOCIATIONS_WARNING = (
    "trace supplied no lot-event associations; per-facility lots, quantities and orphans were not computed"
)

# Event types that record a lot moving on from the facility that held it.
_ONWARD_EVENT_TYPES = frozenset({"SHIPPING", "TRANSFORMATION"})


def _facility_key(facility: Dict[str, Any]) -> Any:
    gln = facility.get("gln")
    if gln:
        return ("gln", str(gln))
    return ("name", facility.get("name"), facility.get("address"))


def _sum_lot_quantities(lots: List[Dict[str, Any]]) -> tuple[Optional[float], Optional[str]]:
    """Sum the lots' quantities when every lot has a numeric one in a single
    unit; otherwise ``(None, None)``. A partial sum would be presented as the
    facility's affected quantity, so none is offered."""
    if not lots:
        return None, None
    total = 0.0
    units: set = set()
    for lot in lots:
        quantity = lot.get("quantity")
        if quantity is None:
            return None, None
        try:
            total += float(quantity)
        except (TypeError, ValueError):
            return None, None
        units.add(str(lot.get("unit_of_measure") or "").strip().lower())
    if len(units) != 1 or "" in units:
        return None, None
    return total, units.pop()


def _count_orphans(trace_result: Any) -> Optional[int]:
    """Lots the forward trace reached that nothing moved on.

    Uses the lot-event associations (``trace_rows``): a lot counts when it
    has at least one recorded event and none of them is a SHIPPING or
    TRANSFORMATION event. The association does not carry the relationship
    direction, so a lot a transformation *produced* and nothing shipped is
    not counted (it has a TRANSFORMATION association); the count can be low,
    never high. ``None`` when the tracer supplied no associations.
    """
    trace_rows = _trace_field(trace_result, "trace_rows", None, required=False)
    if trace_rows is None:
        return None
    seen: set = set()
    moved_on: set = set()
    for association in trace_rows:
        lot_code = (association.get("lot") or {}).get("tlc")
        if not lot_code:
            continue
        seen.add(lot_code)
        event_type = str((association.get("event") or {}).get("type") or "").upper()
        if event_type in _ONWARD_EVENT_TYPES:
            moved_on.add(lot_code)
    lots = _trace_field(trace_result, "lots", [], required=False) or []
    return sum(1 for lot in lots if lot.get("tlc") in seen and lot.get("tlc") not in moved_on)


def _total_affected_quantity(facilities: List[AffectedFacility]) -> tuple[Optional[float], Optional[str]]:
    """Sum of the facilities' known quantities when all of them share one unit
    and none is unknown; otherwise ``(None, None)``."""
    with_lots = [f for f in facilities if f.lots_affected]
    if not with_lots or any(f.quantity_affected is None for f in with_lots):
        return None, None
    units = {str(f.unit_of_measure or "").lower() for f in with_lots}
    if len(units) != 1 or "" in units:
        return None, None
    return sum(float(f.quantity_affected) for f in with_lots), units.pop()


def _trace_field(trace_result: Any, name: str, default: Any, required: bool = True) -> Any:
    """Read ``name`` off a trace result that may be an object or a mapping.

    #2943 — the engine used to read ``result.get("lots_count")`` and
    ``result.get("max_depth")``. ``TraceResult``
    (``services/graph/app/fsma/types.py``) has neither field: the real ones are
    ``lots`` and ``hop_count``. Both ``.get()`` calls fell through to their
    ``0`` default on every real trace and the zeroes were persisted onto the
    drill record — the artifact a firm shows FDA to evidence 24-hour
    traceability.

    The router now hands the engine the ``TraceResult`` itself rather than
    ``TraceResult.__dict__``, so a renamed field surfaces as a missing
    attribute instead of a silent zero. Mappings are still accepted for
    callers that pass a plain dict; with ``required=True`` an absent key
    raises rather than defaulting, because a defaulted metric is exactly the
    failure mode this issue is about — the drill would record 0 and look like
    a clean trace.
    """
    if hasattr(trace_result, name):
        return getattr(trace_result, name)
    if isinstance(trace_result, dict):
        if name in trace_result:
            return trace_result[name]
        if required:
            raise KeyError(f"trace result is missing required field {name!r}; got keys {sorted(trace_result)}")
    return default


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
        orphans: Optional[int] = None
        associations_missing = False
        trace_time = 0.0
        # Set when the requested trace cannot be measured.
        simulated = False

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
                        # #2943: read TraceResult's real fields (`lots`,
                        # `hop_count`), not the never-present `lots_count` /
                        # `max_depth` keys that silently yielded 0.
                        lots_traced += len(_trace_field(result, "lots", []) or [])
                        max_forward = _trace_field(result, "hop_count", 0) or 0
                        extracted, has_associations = self._extract_facilities(result, "downstream")
                        facilities.extend(extracted)
                        associations_missing |= not has_associations
                        orphans = _count_orphans(result)
                else:
                    # Missing trace inputs/backends cannot create trace evidence.
                    simulated = True

            if drill.drill_type in (RecallType.BACKWARD_TRACE, RecallType.FULL_TRACE):
                if self._trace_backward and drill.target_lot:
                    if inspect.iscoroutinefunction(self._trace_backward):
                        result = await self._trace_backward(drill.target_lot, tenant_id=drill.tenant_id)
                    else:
                        result = self._trace_backward(drill.target_lot, tenant_id=drill.tenant_id)

                    if result:
                        # #2943: see the forward branch above.
                        lots_traced += len(_trace_field(result, "lots", []) or [])
                        max_backward = _trace_field(result, "hop_count", 0) or 0
                        extracted, has_associations = self._extract_facilities(result, "upstream")
                        facilities.extend(extracted)
                        associations_missing |= not has_associations
                else:
                    # Missing trace inputs/backends cannot create trace evidence.
                    simulated = True

            if drill.drill_type in (RecallType.MASS_BALANCE, RecallType.TARGETED):
                # These workflows do not yet execute a measured graph trace.
                simulated = True
                warnings.append("This drill type requires manual verification; no trace was measured")

            trace_time = time.time() - trace_start

            if simulated:
                warnings.append(SIMULATED_TRACE_WARNING)
            if associations_missing:
                warnings.append(NO_ASSOCIATIONS_WARNING)

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

            # Request to package: the FSMA 24-hour SLA runs from the
            # recall request (drill creation) to the packaged result.
            # Measuring only in-process compute seconds always yields a
            # sub-second value, so the flag could never breach.
            completed_at = datetime.now(timezone.utc)
            created_at = drill.created_at
            if created_at is not None and created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if created_at is not None:
                total_time = (completed_at - created_at).total_seconds()
            else:
                total_time = time.time() - start_time

            # Determine SLA compliance
            sla_compliant = not simulated and lots_traced > 0 and total_time < self.SLA_LIMIT_SECONDS

            # Data completeness: facilities the trace reached with no lot
            # attributed to them. Total quantity only when every facility
            # with lots has a known quantity in one shared unit.
            total_quantity, total_unit = _total_affected_quantity(facilities)
            gaps = len([f for f in facilities if not f.lots_affected])
            completeness = 0.0 if not facilities else (((len(facilities) - gaps) / len(facilities)) * 100)

            # Create result
            result = RecallResult(
                drill_id=drill.drill_id,
                success=not simulated and lots_traced > 0,
                lots_traced=lots_traced,
                facilities_identified=len(facilities),
                total_quantity_affected=total_quantity,
                unit_of_measure=total_unit,
                max_depth_forward=max_forward,
                max_depth_backward=max_backward,
                trace_time_seconds=trace_time,
                export_time_seconds=export_time,
                total_time_seconds=total_time,
                sla_compliant=sla_compliant,
                gaps_found=gaps,
                orphans_found=orphans,
                data_completeness_pct=completeness,
                affected_facilities=facilities,
                csv_export_path=csv_path,
                contact_list_path=contact_path,
                errors=errors,
                warnings=warnings,
                simulated=simulated,
            )

            drill.status = RecallStatus.COMPLETED
            drill.completed_at = completed_at
            drill.result = result

        except Exception as e:
            # Handle execution failure
            import logging

            logging.getLogger("fsma_recall").error(f"Recall drill execution failed: {e}", exc_info=True)
            errors.append(str(e))
            failed_at = datetime.now(timezone.utc)
            failed_created = drill.created_at
            if failed_created is not None and failed_created.tzinfo is None:
                failed_created = failed_created.replace(tzinfo=timezone.utc)
            if failed_created is not None:
                failed_total = (failed_at - failed_created).total_seconds()
            else:
                failed_total = time.time() - start_time
            result = RecallResult(
                drill_id=drill.drill_id,
                success=False,
                total_time_seconds=failed_total,
                sla_compliant=False,
                errors=errors,
            )
            drill.status = RecallStatus.FAILED
            drill.completed_at = failed_at
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
        trace_result: Any,
        direction: str,
    ) -> tuple[List[AffectedFacility], bool]:
        """Facilities the trace reached, with the lots the graph attributes to each.

        #2943: accepts a ``TraceResult`` or a mapping — the router no longer
        flattens the dataclass through ``__dict__``.

        The tracer's facility dicts carry ``gln``, ``name``, ``address`` and
        ``facility_type`` only. Lots and quantities come from the lot-event
        associations (``trace_rows``); the old code read ``lots``/``quantity``
        keys the tracer never emits, so every production drill recorded no
        lots per facility, 0% completeness, ``"unknown"`` GLNs, the trace
        direction as the facility type and ``"cases"`` as the unit.

        Returns ``(facilities, has_associations)``; when ``has_associations``
        is False the per-facility lots and quantities are unknown, not empty.
        """
        raw_facilities = _trace_field(trace_result, "facilities", [], required=False) or []
        trace_rows = _trace_field(trace_result, "trace_rows", None, required=False)

        lots_by_facility: Dict[Any, Dict[str, Dict[str, Any]]] = {}
        for association in trace_rows or []:
            facility = association.get("facility")
            lot = association.get("lot") or {}
            if not facility or not lot.get("tlc"):
                continue
            lots_by_facility.setdefault(_facility_key(facility), {})[str(lot["tlc"])] = lot

        facilities: List[AffectedFacility] = []
        for f in raw_facilities:
            lots = lots_by_facility.get(_facility_key(f), {})
            quantity, unit = _sum_lot_quantities(list(lots.values()))
            facilities.append(
                AffectedFacility(
                    gln=str(f.get("gln") or ""),
                    name=str(f.get("name") or ""),
                    facility_type=str(f.get("facility_type") or f.get("type") or ""),
                    lots_affected=sorted(lots),
                    quantity_affected=quantity,
                    unit_of_measure=unit,
                    contact_info=f.get("contact"),
                )
            )

        return facilities, trace_rows is not None

    def _update_sla_metrics(self, tenant_id: str, result: RecallResult) -> None:
        """Update SLA metrics cache for measured traces only."""
        if result.simulated:
            return
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
        metrics["avg_trace_time"] = metrics["total_trace_time"] / metrics["total_drills"]
        metrics["last_drill_at"] = datetime.now(timezone.utc).isoformat()

        # Calculate compliance rate
        metrics["sla_compliance_rate"] = (
            (metrics["sla_compliant_drills"] / metrics["total_drills"]) * 100 if metrics["total_drills"] > 0 else 100.0
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
        drills_by_id = {drill.drill_id: drill for drill in self._drills.get(tenant_id, [])}

        engine = self._get_engine()
        if engine is not None:
            rows = _load_drills_from_db(engine, tenant_id, limit=limit * 2)
            for row in rows:
                drill = _dict_to_recall_drill(row)
                drills_by_id.setdefault(drill.drill_id, drill)

        drills = list(drills_by_id.values())

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
                "sla_compliance_rate": None,
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

    def _select_random_target(self, tenant_id: str) -> str:
        """Select a random TLC from the tenant's active lots.

        Fails loudly (ValueError) rather than silently running an untargeted
        drill: a scheduled 'random' drill that never touches real lot data
        would report simulated metrics as if they were the tenant's.
        """
        engine = self._get_engine()
        if engine is None:
            raise ValueError("random target selection requires a configured database (DATABASE_URL is not set)")

        target_lot = _select_random_target_lot(engine, tenant_id)
        if target_lot is None:
            raise ValueError(
                f"tenant {tenant_id} has no active lots with a traceability lot code; "
                "cannot select a random drill target"
            )
        return target_lot

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
        elif schedule.target_strategy == "random":
            target_lot = self._select_random_target(schedule.tenant_id)

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
        completed_drills = [
            d for d in drills if d.status == RecallStatus.COMPLETED and d.result and not d.result.simulated
        ]
        recent_drills = [
            d
            for d in completed_drills
            if d.completed_at and d.completed_at > datetime.now(timezone.utc) - timedelta(days=365)
        ]

        # Drill frequency analysis
        quarterly_count = len(
            [
                d
                for d in recent_drills
                if d.completed_at and d.completed_at > datetime.now(timezone.utc) - timedelta(days=90)
            ]
        )

        # Data quality from results
        avg_completeness = None
        if recent_drills:
            completeness_values = [d.result.data_completeness_pct for d in recent_drills if d.result]
            avg_completeness = sum(completeness_values) / len(completeness_values) if completeness_values else None

        return {
            "tenant_id": tenant_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "overall_readiness": (
                "insufficient_data"
                if sla_metrics.get("sla_compliance_rate") is None
                else ("ready" if sla_metrics["sla_compliance_rate"] >= 95 else "needs_improvement")
            ),
            "sla_compliance": {
                "rate_pct": sla_metrics.get("sla_compliance_rate"),
                "target_pct": 100.0,
                "status": (
                    "unmeasured"
                    if sla_metrics.get("sla_compliance_rate") is None
                    else ("compliant" if sla_metrics["sla_compliance_rate"] >= 95 else "at_risk")
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
        avg_completeness: Optional[float],
    ) -> List[str]:
        """Generate improvement recommendations."""
        recommendations = []

        if quarterly_drills < 1:
            recommendations.append("Schedule quarterly mock recalls to maintain FDA readiness")

        if sla_metrics.get("sla_compliance_rate") is not None and sla_metrics["sla_compliance_rate"] < 95:
            recommendations.append("Improve trace query performance to meet 24-hour SLA consistently")

        if avg_completeness is not None and avg_completeness < 95:
            recommendations.append("Address data gaps to improve traceability completeness")

        if not recommendations:
            recommendations.append("Recall readiness is excellent - maintain current drill schedule")

        return recommendations
