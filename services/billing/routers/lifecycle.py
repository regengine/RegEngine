"""
Lifecycle Router — Subscription plan change API.

Endpoints for managing upgrades, downgrades, proration,
trials, and cancellations.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel
from typing import Optional

from lifecycle_engine import lifecycle_engine, ChangeType, CancellationReason

router = APIRouter(prefix="/v1/billing/lifecycle", tags=["Lifecycle"])


# ── Request Models ─────────────────────────────────────────────────

class ChangePlanRequest(BaseModel):
    tenant_id: str
    tenant_name: str
    from_plan: str
    to_plan: str
    days_remaining: int = 15
    schedule: bool = False
    cancel_reason: Optional[CancellationReason] = None
    cancel_feedback: str = ""


class ProrationRequest(BaseModel):
    from_plan: str
    to_plan: str
    days_remaining: int
    days_in_period: int = 30


class StartTrialRequest(BaseModel):
    tenant_id: str
    tenant_name: str
    plan: str
    days: int = 14


# ── Endpoints ──────────────────────────────────────────────────────

@router.post("/change")
async def change_plan(request: ChangePlanRequest):
    """Execute or schedule a plan change."""
    change = lifecycle_engine.change_plan(
        tenant_id=request.tenant_id, tenant_name=request.tenant_name,
        from_plan=request.from_plan, to_plan=request.to_plan,
        days_remaining=request.days_remaining, schedule=request.schedule,
        cancel_reason=request.cancel_reason, cancel_feedback=request.cancel_feedback,
    )
    return {"change": change.model_dump(), "message": f"Plan {change.change_type.value}: {change.to_plan_name}"}


@router.post("/prorate")
async def calculate_proration(request: ProrationRequest):
    """Preview proration for a plan change."""
    try:
        result = lifecycle_engine.calculate_proration(
            from_plan=request.from_plan, to_plan=request.to_plan,
            days_remaining=request.days_remaining, days_in_period=request.days_in_period,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"proration": result.model_dump()}


@router.get("/changes")
async def list_changes(
    tenant_id: Optional[str] = Query(None),
    change_type: Optional[ChangeType] = Query(None),
):
    """List plan change history."""
    changes = lifecycle_engine.list_changes(tenant_id=tenant_id, change_type=change_type)
    return {"changes": [c.model_dump() for c in changes], "total": len(changes)}


@router.get("/changes/{change_id}")
async def get_change(change_id: str = Path(...)):
    """Get plan change details."""
    change = lifecycle_engine.get_change(change_id)
    if not change:
        raise HTTPException(status_code=404, detail=f"Change {change_id} not found")
    return {"change": change.model_dump()}


@router.get("/trials")
async def list_trials(active_only: bool = Query(False)):
    """List trials."""
    trials = lifecycle_engine.list_trials(active_only=active_only)
    return {"trials": [t.model_dump() for t in trials], "total": len(trials)}


@router.post("/trials")
async def start_trial(request: StartTrialRequest):
    """Start a new trial."""
    try:
        trial = lifecycle_engine.start_trial(
            tenant_id=request.tenant_id, tenant_name=request.tenant_name,
            plan=request.plan, days=request.days,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"trial": trial.model_dump(), "message": f"Trial started for {request.tenant_name}"}


@router.get("/summary")
async def lifecycle_summary():
    """Lifecycle overview."""
    return lifecycle_engine.get_summary()


@router.get("/plans")
async def list_plans():
    """Available plan catalog."""
    from lifecycle_engine import PLAN_CATALOG
    plans = []
    for key, val in PLAN_CATALOG.items():
        plans.append({
            "id": key, "name": val["name"],
            "monthly_cents": val["monthly_cents"],
            "monthly_display": f"${val['monthly_cents'] / 100:,.2f}",
            "annual_cents": val["annual_cents"],
            "annual_display": f"${val['annual_cents'] / 100:,.2f}",
            "tier": val["tier"],
        })
    return {"plans": plans}
