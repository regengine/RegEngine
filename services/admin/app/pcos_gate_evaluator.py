"""
Production Compliance OS — Gate Evaluator

Evaluates project readiness for state transitions and enforces
the go/no-go gate requirements defined in the RulePack.

Gate States:
  DRAFT → READY_FOR_REVIEW → GREENLIT → IN_PRODUCTION → WRAP → ARCHIVED
"""

from __future__ import annotations

import uuid as uuid_module
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from .pcos_models import (
    GateState,
    PCOSProjectModel,
    PCOSLocationModel,
    PCOSEngagementModel,
    PCOSTaskModel,
    PCOSEvidenceModel,
    PCOSGateEvaluationModel,
    PCOSInsurancePolicyModel,
    TaskStatus,
    ClassificationType,
    LocationType,
    EvidenceType,
)

logger = structlog.get_logger("pcos.gate_evaluator")


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class TaskSummary:
    """Summary of a blocking task."""
    id: uuid_module.UUID
    title: str
    task_type: str
    due_date: Optional[date] = None
    status: str = "pending"


@dataclass
class GateEvaluation:
    """Result of a gate evaluation."""
    project_id: uuid_module.UUID
    current_state: GateState
    target_state: Optional[GateState] = None
    can_transition: bool = False
    blocking_tasks_count: int = 0
    blocking_tasks: list[TaskSummary] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    risk_score: int = 0  # 0-100
    reasons: list[str] = field(default_factory=list)
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "project_id": str(self.project_id),
            "current_state": self.current_state.value,
            "target_state": self.target_state.value if self.target_state else None,
            "can_transition": self.can_transition,
            "blocking_tasks_count": self.blocking_tasks_count,
            "blocking_tasks": [
                {"id": str(t.id), "title": t.title, "task_type": t.task_type, "status": t.status}
                for t in self.blocking_tasks
            ],
            "missing_evidence": self.missing_evidence,
            "risk_score": self.risk_score,
            "reasons": self.reasons,
            "evaluated_at": self.evaluated_at.isoformat(),
        }


# Valid state transitions
VALID_TRANSITIONS = {
    GateState.DRAFT: [GateState.READY_FOR_REVIEW],
    GateState.READY_FOR_REVIEW: [GateState.GREENLIT, GateState.DRAFT],
    GateState.GREENLIT: [GateState.IN_PRODUCTION, GateState.READY_FOR_REVIEW],
    GateState.IN_PRODUCTION: [GateState.WRAP],
    GateState.WRAP: [GateState.ARCHIVED, GateState.IN_PRODUCTION],
    GateState.ARCHIVED: [],  # Terminal state
}


# =============================================================================
# Gate Evaluator Service
# =============================================================================

class PCOSGateEvaluator:
    """
    Evaluates project readiness for state transitions.
    
    Implements the gate requirements from the Production Compliance OS RulePack.
    """

    def __init__(self, db: AsyncSession, tenant_id: uuid_module.UUID):
        self.db = db
        self.tenant_id = tenant_id

    async def evaluate(
        self,
        project_id: uuid_module.UUID,
        target_state: Optional[GateState] = None,
    ) -> GateEvaluation:
        """
        Evaluate a project's gate status.
        
        Args:
            project_id: The project to evaluate
            target_state: Optional target state to check transition feasibility
            
        Returns:
            GateEvaluation with full status details
        """
        # Fetch project
        project = await self._get_project(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        current_state = GateState(project.gate_state)
        
        # Initialize evaluation
        evaluation = GateEvaluation(
            project_id=project_id,
            current_state=current_state,
            target_state=target_state,
        )

        # Gather project facts
        facts = await self._gather_project_facts(project_id)
        
        # Get blocking tasks
        blocking_tasks = await self._get_blocking_tasks(project_id)
        evaluation.blocking_tasks = blocking_tasks
        evaluation.blocking_tasks_count = len(blocking_tasks)

        # Get missing evidence
        missing_evidence = await self._get_missing_evidence(project_id, facts)
        evaluation.missing_evidence = missing_evidence

        # Calculate risk score
        evaluation.risk_score = self._calculate_risk_score(evaluation, facts)

        # Check if transition is valid
        if target_state:
            can_transition, reasons = await self._can_transition(
                project, current_state, target_state, evaluation, facts
            )
            evaluation.can_transition = can_transition
            evaluation.reasons = reasons
        else:
            # Default: check if can advance to next state
            next_states = VALID_TRANSITIONS.get(current_state, [])
            if next_states:
                # Try the primary advancement path
                primary_target = next_states[0]
                can_transition, reasons = await self._can_transition(
                    project, current_state, primary_target, evaluation, facts
                )
                evaluation.target_state = primary_target
                evaluation.can_transition = can_transition
                evaluation.reasons = reasons

        logger.info(
            "gate_evaluation_complete",
            project_id=str(project_id),
            current_state=current_state.value,
            target_state=target_state.value if target_state else None,
            can_transition=evaluation.can_transition,
            blocking_tasks=evaluation.blocking_tasks_count,
            risk_score=evaluation.risk_score,
        )

        return evaluation

    async def can_greenlight(self, project_id: uuid_module.UUID) -> tuple[bool, list[str]]:
        """
        Check if a project can be greenlit.
        
        Returns:
            Tuple of (can_greenlight, reasons_if_blocked)
        """
        evaluation = await self.evaluate(project_id, GateState.GREENLIT)
        return evaluation.can_transition, evaluation.reasons

    async def transition(
        self,
        project_id: uuid_module.UUID,
        target_state: GateState,
        actor_id: Optional[uuid_module.UUID] = None,
    ) -> GateEvaluation:
        """
        Attempt to transition a project to a new state.
        
        Raises:
            ValueError: If transition is not allowed
        """
        evaluation = await self.evaluate(project_id, target_state)

        if not evaluation.can_transition:
            raise ValueError(
                f"Cannot transition to {target_state.value}: {', '.join(evaluation.reasons)}"
            )

        # Perform the transition
        project = await self._get_project(project_id)
        project.gate_state = target_state.value
        project.gate_state_changed_at = datetime.now(timezone.utc)
        project.gate_state_changed_by = actor_id

        # Save gate evaluation snapshot
        await self._save_evaluation(evaluation, actor_id, "transition")

        await self.db.commit()

        logger.info(
            "gate_transition_complete",
            project_id=str(project_id),
            from_state=evaluation.current_state.value,
            to_state=target_state.value,
            actor_id=str(actor_id) if actor_id else None,
        )

        return evaluation

    # -------------------------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------------------------

    async def _get_project(self, project_id: uuid_module.UUID) -> Optional[PCOSProjectModel]:
        """Fetch project by ID."""
        result = await self.db.execute(
            select(PCOSProjectModel).where(
                PCOSProjectModel.id == project_id,
                PCOSProjectModel.tenant_id == self.tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def _gather_project_facts(self, project_id: uuid_module.UUID) -> dict:
        """
        Gather all relevant facts about a project for rule evaluation.
        """
        facts = {
            "has_locations": False,
            "has_permit_locations": False,
            "has_employees": False,
            "has_contractors": False,
            "minor_involved": False,
            "first_shoot_date": None,
            "days_until_shoot": None,
            "location_count": 0,
            "engagement_count": 0,
            "employee_count": 0,
            "contractor_count": 0,
            "evidence_types_present": set(),
        }

        # Get project
        project = await self._get_project(project_id)
        if project:
            facts["minor_involved"] = project.minor_involved
            facts["first_shoot_date"] = project.first_shoot_date
            if project.first_shoot_date:
                days_until = (project.first_shoot_date - date.today()).days
                facts["days_until_shoot"] = days_until

        # Count locations
        location_result = await self.db.execute(
            select(PCOSLocationModel).where(
                PCOSLocationModel.project_id == project_id,
                PCOSLocationModel.tenant_id == self.tenant_id,
            )
        )
        locations = location_result.scalars().all()
        facts["location_count"] = len(locations)
        facts["has_locations"] = len(locations) > 0

        # Check for permit-required locations
        permit_locations = [
            loc for loc in locations
            if loc.location_type in (LocationType.PUBLIC_ROW.value, LocationType.CERTIFIED_STUDIO.value)
            or loc.permit_required
        ]
        facts["has_permit_locations"] = len(permit_locations) > 0

        # Count engagements by classification
        engagement_result = await self.db.execute(
            select(PCOSEngagementModel).where(
                PCOSEngagementModel.project_id == project_id,
                PCOSEngagementModel.tenant_id == self.tenant_id,
                PCOSEngagementModel.status == "active",
            )
        )
        engagements = engagement_result.scalars().all()
        facts["engagement_count"] = len(engagements)

        employees = [e for e in engagements if e.classification == ClassificationType.EMPLOYEE.value]
        contractors = [e for e in engagements if e.classification == ClassificationType.CONTRACTOR.value]

        facts["employee_count"] = len(employees)
        facts["contractor_count"] = len(contractors)
        facts["has_employees"] = len(employees) > 0
        facts["has_contractors"] = len(contractors) > 0

        # Get evidence types present
        evidence_result = await self.db.execute(
            select(PCOSEvidenceModel.evidence_type).where(
                PCOSEvidenceModel.entity_type == "project",
                PCOSEvidenceModel.entity_id == project_id,
                PCOSEvidenceModel.tenant_id == self.tenant_id,
            )
        )
        evidence_types = {row[0] for row in evidence_result.all()}
        facts["evidence_types_present"] = evidence_types

        return facts

    async def _get_blocking_tasks(self, project_id: uuid_module.UUID) -> list[TaskSummary]:
        """Get all incomplete blocking tasks for the project."""
        result = await self.db.execute(
            select(PCOSTaskModel).where(
                PCOSTaskModel.source_type == "project",
                PCOSTaskModel.source_id == project_id,
                PCOSTaskModel.tenant_id == self.tenant_id,
                PCOSTaskModel.is_blocking == True,
                PCOSTaskModel.status.in_([
                    TaskStatus.PENDING.value,
                    TaskStatus.IN_PROGRESS.value,
                    TaskStatus.BLOCKED.value,
                ]),
            )
        )
        tasks = result.scalars().all()
        
        return [
            TaskSummary(
                id=task.id,
                title=task.title,
                task_type=task.task_type,
                due_date=task.due_date,
                status=task.status,
            )
            for task in tasks
        ]

    async def _get_missing_evidence(
        self, project_id: uuid_module.UUID, facts: dict
    ) -> list[str]:
        """Determine which required evidence is missing based on project facts."""
        missing = []
        present = facts.get("evidence_types_present", set())

        # If permit locations exist, need permit + COI
        if facts.get("has_permit_locations"):
            if EvidenceType.PERMIT_APPROVED.value not in present:
                missing.append("permit_approved")
            if EvidenceType.COI.value not in present:
                missing.append("coi")

        # If employees exist, need workers' comp and safety policies
        if facts.get("has_employees"):
            if EvidenceType.WORKERS_COMP_POLICY.value not in present:
                missing.append("workers_comp_policy")
            if EvidenceType.IIPP_POLICY.value not in present:
                missing.append("iipp_policy")
            if EvidenceType.WVPP_POLICY.value not in present:
                missing.append("wvpp_policy")

        # If contractors exist, check for classification memos
        if facts.get("has_contractors"):
            # Check engagement-level evidence
            engagement_result = await self.db.execute(
                select(PCOSEngagementModel).where(
                    PCOSEngagementModel.project_id == project_id,
                    PCOSEngagementModel.tenant_id == self.tenant_id,
                    PCOSEngagementModel.classification == ClassificationType.CONTRACTOR.value,
                    PCOSEngagementModel.classification_memo_signed == False,
                    PCOSEngagementModel.status == "active",
                )
            )
            unsigned_contractors = engagement_result.scalars().all()
            if unsigned_contractors:
                missing.append(f"classification_memo_signed ({len(unsigned_contractors)} contractors)")

        # If minors involved, need minor work permit
        if facts.get("minor_involved"):
            if EvidenceType.MINOR_WORK_PERMIT.value not in present:
                missing.append("minor_work_permit")

        return missing

    def _calculate_risk_score(self, evaluation: GateEvaluation, facts: dict) -> int:
        """
        Calculate risk score (0-100) based on evaluation results.
        
        Higher = more risky/less ready.
        """
        score = 0

        # Blocking tasks add significant risk
        score += min(evaluation.blocking_tasks_count * 15, 45)

        # Missing evidence adds risk
        score += min(len(evaluation.missing_evidence) * 10, 30)

        # Approaching shoot date without being greenlit adds risk
        days_until = facts.get("days_until_shoot")
        current_state = evaluation.current_state
        if days_until is not None and current_state != GateState.GREENLIT:
            if days_until <= 0:
                score += 25  # Shoot already started!
            elif days_until <= 3:
                score += 20
            elif days_until <= 7:
                score += 10
            elif days_until <= 14:
                score += 5

        # Minor involvement adds inherent risk
        if facts.get("minor_involved"):
            score += 5

        return min(score, 100)

    async def _can_transition(
        self,
        project: PCOSProjectModel,
        current_state: GateState,
        target_state: GateState,
        evaluation: GateEvaluation,
        facts: dict,
    ) -> tuple[bool, list[str]]:
        """
        Check if the transition from current to target state is allowed.
        
        Returns:
            Tuple of (can_transition, reasons_if_blocked)
        """
        reasons = []

        # Check if transition is valid in state machine
        valid_targets = VALID_TRANSITIONS.get(current_state, [])
        if target_state not in valid_targets:
            reasons.append(
                f"Invalid transition: {current_state.value} → {target_state.value}"
            )
            return False, reasons

        # State-specific requirements
        if target_state == GateState.READY_FOR_REVIEW:
            # Minimal requirements - just moving from draft
            pass

        elif target_state == GateState.GREENLIT:
            # Most stringent requirements

            # Must have zero blocking tasks
            if evaluation.blocking_tasks_count > 0:
                reasons.append(
                    f"{evaluation.blocking_tasks_count} blocking task(s) must be completed"
                )

            # Must have all required evidence
            if evaluation.missing_evidence:
                reasons.append(
                    f"Missing required evidence: {', '.join(evaluation.missing_evidence)}"
                )

            # Check for overdue tasks
            overdue_tasks = [
                t for t in evaluation.blocking_tasks
                if t.due_date and t.due_date < date.today()
            ]
            if overdue_tasks:
                reasons.append(f"{len(overdue_tasks)} task(s) are past due")

        elif target_state == GateState.IN_PRODUCTION:
            # Must be on or past first shoot date
            first_shoot = facts.get("first_shoot_date")
            if first_shoot and first_shoot > date.today():
                reasons.append(
                    f"First shoot date ({first_shoot}) has not arrived yet"
                )

        elif target_state == GateState.WRAP:
            # Check timecards are approved (basic check)
            # In v2, this could be more comprehensive
            pass

        can_transition = len(reasons) == 0
        return can_transition, reasons

    async def _save_evaluation(
        self,
        evaluation: GateEvaluation,
        actor_id: Optional[uuid_module.UUID],
        trigger_type: str,
    ) -> None:
        """Save the gate evaluation as a snapshot."""
        gate_eval = PCOSGateEvaluationModel(
            tenant_id=self.tenant_id,
            project_id=evaluation.project_id,
            evaluated_by=actor_id,
            trigger_type=trigger_type,
            current_state=evaluation.current_state.value,
            target_state=evaluation.target_state.value if evaluation.target_state else None,
            transition_allowed=evaluation.can_transition,
            blocking_tasks_count=evaluation.blocking_tasks_count,
            blocking_task_ids=[t.id for t in evaluation.blocking_tasks],
            missing_evidence=evaluation.missing_evidence,
            risk_score=evaluation.risk_score,
            reasons=evaluation.reasons,
            snapshot=evaluation.to_dict(),
        )
        self.db.add(gate_eval)


# =============================================================================
# Convenience Functions
# =============================================================================

async def evaluate_project_gate(
    db: AsyncSession,
    tenant_id: uuid_module.UUID,
    project_id: uuid_module.UUID,
    target_state: Optional[GateState] = None,
) -> GateEvaluation:
    """
    Convenience function to evaluate a project's gate status.
    """
    evaluator = PCOSGateEvaluator(db, tenant_id)
    return await evaluator.evaluate(project_id, target_state)


async def greenlight_project(
    db: AsyncSession,
    tenant_id: uuid_module.UUID,
    project_id: uuid_module.UUID,
    actor_id: Optional[uuid_module.UUID] = None,
) -> GateEvaluation:
    """
    Convenience function to attempt greenlighting a project.
    
    Raises:
        ValueError: If project cannot be greenlit
    """
    evaluator = PCOSGateEvaluator(db, tenant_id)
    return await evaluator.transition(project_id, GateState.GREENLIT, actor_id)
