"""
Partners Router — Partner portal and commission management API.

Endpoints for partner registration, referral tracking,
commission management, and payout processing.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel
from typing import Optional

from partner_engine import partner_engine, PartnerTier, PartnerStatus

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
    monthly_value_cents: int


class ProcessPayoutRequest(BaseModel):
    pass  # No body needed


# ── Endpoints ──────────────────────────────────────────────────────

@router.post("")
async def register_partner(request: RegisterPartnerRequest):
    """Register a new channel partner."""
    partner = partner_engine.register_partner(
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
):
    """List all partners with optional filters."""
    partners = partner_engine.list_partners(tier=tier, status=status)
    return {
        "partners": [p.model_dump() for p in partners],
        "total": len(partners),
    }


@router.get("/summary")
async def program_summary():
    """Partner program performance overview."""
    return partner_engine.get_program_summary()


@router.get("/referrals")
async def list_referrals(partner_id: Optional[str] = Query(None)):
    """All referrals or filtered by partner."""
    referrals = partner_engine.list_referrals(partner_id=partner_id)
    return {
        "referrals": [r.model_dump() for r in referrals],
        "total": len(referrals),
    }


@router.get("/payouts")
async def list_payouts(partner_id: Optional[str] = Query(None)):
    """Payout history."""
    payouts = partner_engine.list_payouts(partner_id=partner_id)
    return {
        "payouts": [p.model_dump() for p in payouts],
        "total": len(payouts),
    }


@router.get("/{partner_id}")
async def get_partner(partner_id: str = Path(...)):
    """Get partner details."""
    partner = partner_engine.get_partner(partner_id)
    if not partner:
        raise HTTPException(status_code=404, detail=f"Partner {partner_id} not found")
    return {"partner": partner.model_dump()}


@router.post("/{partner_id}/referral")
async def record_referral(
    request: RecordReferralRequest,
    partner_id: str = Path(...),
):
    """Record a new referral for a partner."""
    try:
        referral = partner_engine.record_referral(
            partner_id=partner_id,
            tenant_id=request.tenant_id,
            tenant_name=request.tenant_name,
            tier_id=request.tier_id,
            monthly_value_cents=request.monthly_value_cents,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    partner = partner_engine.get_partner(partner_id)
    return {
        "referral": referral.model_dump(),
        "partner_tier": partner.tier.value if partner else "unknown",
        "message": f"Referral recorded: {request.tenant_name}",
    }


@router.post("/{partner_id}/payout")
async def create_payout(partner_id: str = Path(...)):
    """Create a payout for pending commissions."""
    try:
        payout = partner_engine.create_payout(partner_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "payout": payout.model_dump(),
        "message": f"Payout created: ${payout.amount_cents / 100:,.2f}",
    }


@router.post("/payouts/{payout_id}/process")
async def process_payout(payout_id: str = Path(...)):
    """Mark a payout as paid."""
    try:
        payout = partner_engine.process_payout(payout_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "payout": payout.model_dump(),
        "message": "Payout processed successfully",
    }
