"""
Billing Service — Checkout Router

Creates Stripe Checkout sessions with credit application.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header

from models import (
    PRICING_TIERS,
    BillingCycle,
    CheckoutSessionCreate,
    CheckoutSession,
    CheckoutStatus,
)
import stripe_client
from credit_engine import CreditEngine
from dependencies import get_credit_engine
from utils import get_tenant_id, format_cents

router = APIRouter(prefix="/v1/billing/checkout", tags=["checkout"])

# In-memory session store
_sessions: dict[str, CheckoutSession] = {}


def _calculate_total(tier_id: str, billing_cycle: BillingCycle) -> int:
    """Calculate total in cents for a tier and billing cycle."""
    tier = PRICING_TIERS.get(tier_id)
    if not tier or tier.monthly_price is None:
        return 0
    price = tier.annual_price if billing_cycle == BillingCycle.ANNUAL else tier.monthly_price
    return (price or 0) * 100  # Convert dollars to cents


@router.post("/session")
async def create_checkout_session(
    request: CheckoutSessionCreate,
    x_tenant_id: Optional[str] = Header(None),
    credit_eng: CreditEngine = Depends(get_credit_engine),
):
    """Create a Stripe Checkout session for a subscription."""
    tenant_id = get_tenant_id(x_tenant_id)

    # Validate tier
    tier = PRICING_TIERS.get(request.tier_id)
    if tier is None:
        raise HTTPException(status_code=400, detail=f"Invalid tier: {request.tier_id}")

    if tier.monthly_price is None:
        raise HTTPException(
            status_code=400,
            detail="Enterprise tier requires custom pricing — contact sales@regengine.co",
        )

    # Calculate pricing
    subtotal_cents = _calculate_total(request.tier_id, request.billing_cycle)
    applied_credit_cents = 0

    # Apply credit code if provided
    if request.credit_code:
        result = credit_eng.redeem_code(tenant_id, request.credit_code)
        if result.success:
            applied_credit_cents = result.amount_cents

    # Apply any existing credit balance
    total_cents, credits_used = credit_eng.apply_credit_to_invoice(
        tenant_id, subtotal_cents
    )
    applied_credit_cents += credits_used

    # Determine Stripe price ID (uses sandbox mock IDs)
    price_id = (
        tier.stripe_annual_price_id
        if request.billing_cycle == BillingCycle.ANNUAL
        else tier.stripe_monthly_price_id
    ) or f"price_sandbox_{request.tier_id}_{request.billing_cycle.value}"

    # Create Stripe checkout session
    stripe_session = await stripe_client.create_checkout_session(
        price_id=price_id,
        success_url=request.success_url or "https://regengine.co/checkout/success",
        cancel_url=request.cancel_url or "https://regengine.co/pricing",
        metadata={
            "tenant_id": tenant_id,
            "tier_id": request.tier_id,
            "billing_cycle": request.billing_cycle.value,
            "applied_credit_cents": str(applied_credit_cents),
        },
    )

    # Create our checkout session record
    session = CheckoutSession(
        tenant_id=tenant_id,
        tier_id=request.tier_id,
        billing_cycle=request.billing_cycle,
        checkout_url=stripe_session["url"],
        stripe_session_id=stripe_session["id"],
        applied_credit_cents=applied_credit_cents,
        subtotal_cents=subtotal_cents,
        total_cents=max(0, subtotal_cents - applied_credit_cents),
    )
    _sessions[session.id] = session

    return {
        "session_id": session.id,
        "checkout_url": session.checkout_url,
        "tier": tier.name,
        "billing_cycle": request.billing_cycle.value,
        "subtotal": format_cents(subtotal_cents),
        "credits_applied": format_cents(applied_credit_cents) if applied_credit_cents > 0 else None,
        "total": format_cents(session.total_cents),
        "sandbox_mode": stripe_client.is_sandbox(),
    }


@router.get("/session/{session_id}")
async def get_checkout_session(session_id: str):
    """Check the status of a checkout session."""
    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session.id,
        "status": session.status.value,
        "tier_id": session.tier_id,
        "total_cents": session.total_cents,
        "created_at": session.created_at.isoformat(),
    }
