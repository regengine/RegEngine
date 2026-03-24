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
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.webhook_compat import _verify_api_key

logger = logging.getLogger("onboarding")


def _get_db():
    """Get database session. Returns None if unavailable."""
    try:
        from shared.database import SessionLocal
        return SessionLocal()
    except Exception as exc:
        logger.warning("db_unavailable error=%s", str(exc))
        return None


def _seed_obligations_if_needed(tenant_id: str):
    """Seed FSMA 204 obligations for new tenant (idempotent)."""
    try:
        from shared.database import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("SELECT seed_obligations_for_tenant(:tid::uuid)"), {"tid": tenant_id})
            db.commit()
            logger.info("obligations_seeded tenant_id=%s", tenant_id)
        finally:
            db.close()
    except Exception as exc:
        logger.warning("obligation_seeding_failed tenant_id=%s error=%s", tenant_id, str(exc))

router = APIRouter(prefix="/api/v1/onboarding", tags=["Onboarding"])

# In-memory onboarding state fallback
_onboarding_store: dict[str, dict] = {}


def _db_get_onboarding(tenant_id: str) -> Optional[dict]:
    """Query onboarding progress from database."""
    db = _get_db()
    if not db:
        return None
    try:
        row = db.execute(
            text("SELECT state FROM fsma.tenant_onboarding WHERE tenant_id = :tid"),
            {"tid": tenant_id}
        ).fetchone()
        if not row:
            return None
        progress_data = json.loads(row[0]) if row[0] else {}
        return progress_data
    except Exception as exc:
        logger.warning("db_read_failed error=%s", str(exc))
        return None
    finally:
        db.close()


def _db_save_onboarding(tenant_id: str, progress: dict) -> bool:
    """Insert or update onboarding progress in database."""
    db = _get_db()
    if not db:
        return False
    try:
        progress_json = json.dumps(progress)
        db.execute(
            text("""
                INSERT INTO fsma.tenant_onboarding (tenant_id, state, created_at, updated_at)
                VALUES (:tid, :json, now(), now())
                ON CONFLICT (tenant_id) DO UPDATE SET state = :json, updated_at = now()
            """),
            {"tid": tenant_id, "json": progress_json}
        )
        db.commit()
        return True
    except Exception as exc:
        logger.warning("db_write_failed error=%s", str(exc))
        if db:
            db.rollback()
        return False
    finally:
        db.close()

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
    # Try DB first
    state = _db_get_onboarding(tenant_id)
    if state is None:
        # Fall back to memory or default
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

    # Try DB first
    state = _db_get_onboarding(tenant_id)
    if state is None:
        # Fall back to memory or create new
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

    # Seed obligations on first step completion (idempotent)
    if step_id == "company_profile":
        _seed_obligations_if_needed(tenant_id)

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

    # Try DB first, fall back to memory
    db_success = _db_save_onboarding(tenant_id, state)
    if not db_success:
        _onboarding_store[tenant_id] = state

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
