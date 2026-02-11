"""
Partners Router — Partner portal and commission management API.

Endpoints for partner registration, referral tracking,
commission management, and payout processing.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from pydantic import BaseModel, Field
from typing import Optional

from partner_engine import PartnerEngine, PartnerTier, PartnerStatus
from dependencies import get_partner_engine
from utils import format_cents, paginate

router = APIRouter(prefix="/v1/billing/partners", tags=["Partners"])


# ── Request Models ─────────────────────────────────────────────────

class RegisterPartnerRequest(BaseModel):
    name: str
    company: str
    email: str
    tier: PartnerTier = PartnerTier.SILVER


class RecordReferralRequest(BaseModel):
    tenant_id: str
    tenant_name: str
    tier_id: str
    monthly_value_cents: int = Field(..., gt=0)


class ProcessPayoutRequest(BaseModel):
    pass  # No body needed


# ── Endpoints ──────────────────────────────────────────────────────

@router.post("")
async def register_partner(
    request: RegisterPartnerRequest,
    engine: PartnerEngine = Depends(get_partner_engine),
):
    """Register a new channel partner."""
    partner = engine.register_partner(
        name=request.name, company=request.company,
        email=request.email, tier=request.tier,
    )
    return {
        "partner": partner.model_dump(),
        "message": f"Partner {partner.company} registered with code {partner.referral_code}",
    }


@router.get("")
async def list_partners(
    tier: Optional[PartnerTier] = Query(None),
    status: Optional[PartnerStatus] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    engine: PartnerEngine = Depends(get_partner_engine),
):
    """List all partners with optional filters and pagination."""
    partners = engine.list_partners(tier=tier, status=status)
    result = paginate([p.model_dump() for p in partners], page=page, page_size=page_size)
    return {
        "partners": result["items"],
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
        "total_pages": result["total_pages"],
        "has_next": result["has_next"],
        "has_prev": result["has_prev"],
    }


@router.get("/summary")
async def program_summary(engine: PartnerEngine = Depends(get_partner_engine)):
    """Partner program performance overview."""
    return engine.get_program_summary()


@router.get("/referrals")
async def list_referrals(
    partner_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    engine: PartnerEngine = Depends(get_partner_engine),
):
    """All referrals or filtered by partner, with pagination."""
    referrals = engine.list_referrals(partner_id=partner_id)
    result = paginate([r.model_dump() for r in referrals], page=page, page_size=page_size)
    return {
        "referrals": result["items"],
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
        "total_pages": result["total_pages"],
        "has_next": result["has_next"],
        "has_prev": result["has_prev"],
    }


@router.get("/payouts")
async def list_payouts(
    partner_id: Optional[str] = Query(None),
    engine: PartnerEngine = Depends(get_partner_engine),
):
    """Payout history."""
    payouts = engine.list_payouts(partner_id=partner_id)
    return {
        "payouts": [p.model_dump() for p in payouts],
        "total": len(payouts),
    }


@router.get("/{partner_id}")
async def get_partner(
    partner_id: str = Path(...),
    engine: PartnerEngine = Depends(get_partner_engine),
):
    """Get partner details."""
    partner = engine.get_partner(partner_id)
    if not partner:
        raise HTTPException(status_code=404, detail=f"Partner {partner_id} not found")
    return {"partner": partner.model_dump()}


@router.post("/{partner_id}/referral")
async def record_referral(
    request: RecordReferralRequest,
    partner_id: str = Path(...),
    engine: PartnerEngine = Depends(get_partner_engine),
):
    """Record a new referral for a partner."""
    try:
        referral = engine.record_referral(
            partner_id=partner_id,
            tenant_id=request.tenant_id,
            tenant_name=request.tenant_name,
            tier_id=request.tier_id,
            monthly_value_cents=request.monthly_value_cents,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    partner = engine.get_partner(partner_id)
    return {
        "referral": referral.model_dump(),
        "partner_tier": partner.tier.value if partner else "unknown",
        "message": f"Referral recorded: {request.tenant_name}",
    }


@router.post("/{partner_id}/payout")
async def create_payout(
    partner_id: str = Path(...),
    engine: PartnerEngine = Depends(get_partner_engine),
):
    """Create a payout for pending commissions."""
    try:
        payout = engine.create_payout(partner_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "payout": payout.model_dump(),
        "message": f"Payout created: {format_cents(payout.amount_cents)}",
    }


@router.post("/payouts/{payout_id}/process")
async def process_payout(
    payout_id: str = Path(...),
    engine: PartnerEngine = Depends(get_partner_engine),
):
    """Mark a payout as paid."""
    try:
        payout = engine.process_payout(payout_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "payout": payout.model_dump(),
        "message": "Payout processed successfully",
    }
