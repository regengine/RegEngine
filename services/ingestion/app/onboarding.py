"""
Onboarding Router.

Guided onboarding flow that gets new tenants to their first CTE
in under 5 minutes. Tracks progress through steps:
1. Company profile
2. First facility
3. First product (FTL check)
4. First CTE (sample Shipping event)
5. Verify chain integrity
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.webhook_router import _verify_api_key

logger = logging.getLogger("onboarding")

router = APIRouter(prefix="/api/v1/onboarding", tags=["Onboarding"])

# In-memory onboarding state
_onboarding_store: dict[str, dict] = {}

ONBOARDING_STEPS = [
    {
        "step": 1,
        "id": "company_profile",
        "title": "Company Profile",
        "description": "Tell us about your organization",
        "estimated_time": "1 min",
    },
    {
        "step": 2,
        "id": "first_facility",
        "title": "Add Your First Facility",
        "description": "Register a location with GLN or address",
        "estimated_time": "1 min",
    },
    {
        "step": 3,
        "id": "first_product",
        "title": "Add an FTL Product",
        "description": "Check if your product is on the Food Traceability List",
        "estimated_time": "1 min",
    },
    {
        "step": 4,
        "id": "first_cte",
        "title": "Record Your First CTE",
        "description": "Create a sample Shipping event with required KDEs",
        "estimated_time": "2 min",
    },
    {
        "step": 5,
        "id": "verify_chain",
        "title": "Verify Chain Integrity",
        "description": "See your SHA-256 audit trail in action",
        "estimated_time": "30 sec",
    },
]


class OnboardingProfile(BaseModel):
    """Step 1: Company profile."""
    company_name: str
    company_type: str = Field(..., description="grower, manufacturer, distributor, retailer, importer")
    contact_name: str
    contact_email: str


class OnboardingFacility(BaseModel):
    """Step 2: First facility."""
    facility_name: str
    address: str
    gln: Optional[str] = None


class OnboardingProduct(BaseModel):
    """Step 3: FTL product."""
    product_name: str
    product_category: str = Field(..., description="e.g. Leafy Greens, Fresh-Cut Fruits, Finfish")


class OnboardingCTE(BaseModel):
    """Step 4: First CTE."""
    cte_type: str = Field("shipping", description="CTE type")
    tlc: str = Field(..., description="Traceability Lot Code")
    quantity: int
    unit: str = "cases"
    ship_to: str


class OnboardingProgress(BaseModel):
    """Current onboarding progress."""
    tenant_id: str
    current_step: int
    completed_steps: list[str]
    total_steps: int
    percent_complete: int
    steps: list[dict]
    started_at: str
    first_cte_at: Optional[str] = None
    time_to_first_cte: Optional[str] = None


@router.get(
    "/steps",
    summary="Get onboarding step definitions",
)
async def get_steps():
    """Get the onboarding step definitions."""
    return {"steps": ONBOARDING_STEPS, "total_estimated_time": "5 min"}


@router.get(
    "/{tenant_id}/progress",
    response_model=OnboardingProgress,
    summary="Get onboarding progress",
)
async def get_progress(
    tenant_id: str,
    _: None = Depends(_verify_api_key),
) -> OnboardingProgress:
    """Get current onboarding progress for a tenant."""
    state = _onboarding_store.get(tenant_id, {
        "current_step": 1,
        "completed_steps": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "first_cte_at": None,
    })

    completed_count = len(state["completed_steps"])
    total = len(ONBOARDING_STEPS)

    time_to_cte = None
    if state.get("first_cte_at"):
        started = datetime.fromisoformat(state["started_at"])
        cte_time = datetime.fromisoformat(state["first_cte_at"])
        delta = cte_time - started
        minutes = int(delta.total_seconds() / 60)
        time_to_cte = f"{minutes} min" if minutes > 0 else "< 1 min"

    return OnboardingProgress(
        tenant_id=tenant_id,
        current_step=state["current_step"],
        completed_steps=state["completed_steps"],
        total_steps=total,
        percent_complete=int((completed_count / total) * 100),
        steps=ONBOARDING_STEPS,
        started_at=state["started_at"],
        first_cte_at=state.get("first_cte_at"),
        time_to_first_cte=time_to_cte,
    )


@router.post(
    "/{tenant_id}/step/{step_id}",
    summary="Complete an onboarding step",
)
async def complete_step(
    tenant_id: str,
    step_id: str,
    _: None = Depends(_verify_api_key),
):
    """Mark an onboarding step as complete."""
    now = datetime.now(timezone.utc)

    if tenant_id not in _onboarding_store:
        _onboarding_store[tenant_id] = {
            "current_step": 1,
            "completed_steps": [],
            "started_at": now.isoformat(),
            "first_cte_at": None,
        }

    state = _onboarding_store[tenant_id]

    if step_id not in state["completed_steps"]:
        state["completed_steps"].append(step_id)

    # Advance current step
    step_ids = [s["id"] for s in ONBOARDING_STEPS]
    if step_id in step_ids:
        idx = step_ids.index(step_id)
        state["current_step"] = min(idx + 2, len(ONBOARDING_STEPS))

    # Track first CTE time
    if step_id == "first_cte" and not state.get("first_cte_at"):
        state["first_cte_at"] = now.isoformat()

    completed_count = len(state["completed_steps"])
    is_complete = completed_count >= len(ONBOARDING_STEPS)

    logger.info("onboarding_step_completed", extra={
        "tenant_id": tenant_id,
        "step_id": step_id,
        "is_complete": is_complete,
    })

    return {
        "step_id": step_id,
        "completed": True,
        "onboarding_complete": is_complete,
        "next_step": ONBOARDING_STEPS[state["current_step"] - 1] if state["current_step"] <= len(ONBOARDING_STEPS) else None,
    }
