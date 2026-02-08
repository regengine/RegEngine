"""
PCOS Dashboard Router — High-level metrics endpoint.
"""

from __future__ import annotations

from datetime import date as date_type
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ._shared import get_pcos_tenant_context
from ..pcos_models import (
    PCOSProjectModel,
    PCOSTaskModel,
    GateState,
    TaskStatus,
)

router = APIRouter(tags=["PCOS Dashboard"])


# =============================================================================
# DASHBOARD ENDPOINTS
# =============================================================================

@router.get("/dashboard")
def get_dashboard_metrics(
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """Get high-level dashboard metrics for PCOS."""
    db, tenant_id = ctx

    # Total projects
    total_projects = db.execute(
        select(func.count()).select_from(PCOSProjectModel).where(
            PCOSProjectModel.tenant_id == tenant_id
        )
    ).scalar() or 0

    # Active projects (not archived)
    active_projects = db.execute(
        select(func.count()).select_from(PCOSProjectModel).where(
            PCOSProjectModel.tenant_id == tenant_id,
            PCOSProjectModel.gate_state != GateState.ARCHIVED.value
        )
    ).scalar() or 0

    # Greenlit projects
    greenlit_projects = db.execute(
        select(func.count()).select_from(PCOSProjectModel).where(
            PCOSProjectModel.tenant_id == tenant_id,
            PCOSProjectModel.gate_state.in_([GateState.GREENLIT.value, GateState.IN_PRODUCTION.value])
        )
    ).scalar() or 0

    # Overdue tasks
    today = date_type.today()
    overdue_tasks = db.execute(
        select(func.count()).select_from(PCOSTaskModel).where(
            PCOSTaskModel.tenant_id == tenant_id,
            PCOSTaskModel.status == TaskStatus.PENDING.value,
            PCOSTaskModel.due_date < today
        )
    ).scalar() or 0

    # Total blocking tasks
    total_blocking_tasks = db.execute(
        select(func.count()).select_from(PCOSTaskModel).where(
            PCOSTaskModel.tenant_id == tenant_id,
            PCOSTaskModel.status == TaskStatus.PENDING.value,
            PCOSTaskModel.is_blocking == True
        )
    ).scalar() or 0

    # Expiring permits (next 30 days) - simplified for now
    expiring_permits = 0

    # Expiring insurance (next 30 days) - simplified for now
    expiring_insurance = 0

    # Average risk score
    avg_risk = db.execute(
        select(func.avg(PCOSProjectModel.risk_score)).where(
            PCOSProjectModel.tenant_id == tenant_id,
            PCOSProjectModel.gate_state != GateState.ARCHIVED.value
        )
    ).scalar()
    avg_risk_score = float(avg_risk or 0)

    return {
        "total_projects": total_projects,
        "active_projects": active_projects,
        "greenlit_projects": greenlit_projects,
        "overdue_tasks": overdue_tasks,
        "expiring_permits": expiring_permits,
        "expiring_insurance": expiring_insurance,
        "total_blocking_tasks": total_blocking_tasks,
        "avg_risk_score": round(avg_risk_score, 2)
    }
