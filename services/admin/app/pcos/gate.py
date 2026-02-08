"""
PCOS Gate Router — Gate status evaluation and greenlight workflow.
"""

from __future__ import annotations

import uuid as uuid_module
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from uuid import UUID

import structlog

from ._shared import get_pcos_tenant_context
from ..pcos_models import (
    PCOSProjectModel,
    PCOSTaskModel,
    GateState,
)

logger = structlog.get_logger("pcos.gate")

router = APIRouter(tags=["PCOS Gate Management"])


# =============================================================================
# GATE STATUS ENDPOINTS
# =============================================================================

@router.get("/projects/{project_id}/gate-status")
def get_project_gate_status(
    project_id: uuid_module.UUID,
    target_state: Optional[str] = Query(None, description="Target state to evaluate"),
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """Get the current gate status for a project."""
    db, tenant_id = ctx

    # Get project
    result = db.execute(
        select(PCOSProjectModel).where(
            PCOSProjectModel.id == project_id,
            PCOSProjectModel.tenant_id == tenant_id,
        )
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get blocking tasks count
    blocking_tasks_result = db.execute(
        select(PCOSTaskModel).where(
            PCOSTaskModel.source_type == "project",
            PCOSTaskModel.source_id == project_id,
            PCOSTaskModel.tenant_id == tenant_id,
            PCOSTaskModel.is_blocking == True,
            PCOSTaskModel.status.in_(["pending", "in_progress", "blocked"]),
        )
    )
    blocking_tasks = blocking_tasks_result.scalars().all()

    # Calculate simple risk score
    risk_score = min(len(blocking_tasks) * 15, 100)

    current_state = GateState(project.gate_state)
    can_transition = len(blocking_tasks) == 0

    return {
        "id": str(uuid_module.uuid4()),
        "project_id": str(project_id),
        "current_state": current_state.value,
        "target_state": target_state,
        "transition_allowed": can_transition,
        "blocking_tasks_count": len(blocking_tasks),
        "blocking_tasks": [
            {"id": str(t.id), "title": t.title, "status": t.status}
            for t in blocking_tasks
        ],
        "missing_evidence": [],
        "risk_score": risk_score,
        "reasons": [] if can_transition else [f"{len(blocking_tasks)} blocking tasks remain"],
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/projects/{project_id}/greenlight")
def greenlight_project(
    project_id: uuid_module.UUID,
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """Attempt to greenlight a project."""
    db, tenant_id = ctx

    # Get project
    result = db.execute(
        select(PCOSProjectModel).where(
            PCOSProjectModel.id == project_id,
            PCOSProjectModel.tenant_id == tenant_id,
        )
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check blocking tasks
    blocking_tasks_result = db.execute(
        select(PCOSTaskModel).where(
            PCOSTaskModel.source_type == "project",
            PCOSTaskModel.source_id == project_id,
            PCOSTaskModel.tenant_id == tenant_id,
            PCOSTaskModel.is_blocking == True,
            PCOSTaskModel.status.in_(["pending", "in_progress", "blocked"]),
        )
    )
    blocking_tasks = blocking_tasks_result.scalars().all()

    if blocking_tasks:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot greenlight: {len(blocking_tasks)} blocking task(s) remain"
        )

    # Transition to greenlit
    project.gate_state = GateState.GREENLIT.value
    project.gate_state_changed_at = datetime.now(timezone.utc)

    db.commit()

    logger.info("project_greenlit", project_id=str(project_id), tenant_id=str(tenant_id))

    return {
        "project_id": str(project_id),
        "current_state": GateState.GREENLIT.value,
        "transition_allowed": True,
        "message": "Project successfully greenlit",
    }
