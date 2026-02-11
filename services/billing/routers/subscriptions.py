"""
Billing Service — Subscription Management Router

CRUD operations for tenant subscriptions with Stripe integration.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Header

from models import (
    PRICING_TIERS,
    Subscription,
    SubscriptionCreateRequest,
    SubscriptionResponse,
    SubscriptionStatus,
    BillingCycle,
    ChangeTierRequest,
)
import stripe_client
from utils import get_tenant_id

router = APIRouter(prefix="/v1/billing/subscriptions", tags=["subscriptions"])

# In-memory subscription store (would be DB in production)
_subscriptions: dict[str, Subscription] = {}  # tenant_id → Subscription



@router.get("/tiers")
async def list_tiers():
    """List available pricing tiers."""
    return {
        "tiers": [tier.model_dump() for tier in PRICING_TIERS.values()],
        "billing_cycles": ["monthly", "annual"],
        "annual_discount": "~17%",
    }


@router.get("/current")
async def get_current_subscription(x_tenant_id: Optional[str] = Header(None)):
    """Get the current subscription for a tenant."""
    tenant_id = get_tenant_id(x_tenant_id)
    sub = _subscriptions.get(tenant_id)

    if sub is None:
        return {
            "subscription": None,
            "message": "No active subscription",
            "available_tiers": list(PRICING_TIERS.keys()),
        }

    return {"subscription": sub.model_dump()}


@router.post("/create", response_model=SubscriptionResponse)
async def create_subscription(
    request: SubscriptionCreateRequest,
    x_tenant_id: Optional[str] = Header(None),
):
    """Create a new subscription for a tenant."""
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

    # Check if tenant already has a subscription
    existing = _subscriptions.get(tenant_id)
    if existing and existing.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING):
        raise HTTPException(
            status_code=409,
            detail="Tenant already has an active subscription. Use /change-tier to modify.",
        )

    # Create Stripe customer (sandbox-safe)
    customer = await stripe_client.create_customer(
        email=f"{tenant_id}@regengine.co",
        name=f"Tenant {tenant_id}",
        tenant_id=tenant_id,
    )

    # Calculate period
    now = datetime.utcnow()
    period_end = now + (timedelta(days=365) if request.billing_cycle == BillingCycle.ANNUAL else timedelta(days=30))

    subscription = Subscription(
        tenant_id=tenant_id,
        tier_id=request.tier_id,
        status=SubscriptionStatus.TRIALING,
        billing_cycle=request.billing_cycle,
        current_period_start=now,
        current_period_end=period_end,
        stripe_customer_id=customer["id"],
    )

    _subscriptions[tenant_id] = subscription

    return SubscriptionResponse(
        subscription=subscription,
        message=f"Subscription created: {tier.name} ({request.billing_cycle.value}). 14-day trial started.",
    )


@router.post("/cancel")
async def cancel_subscription(x_tenant_id: Optional[str] = Header(None)):
    """Cancel the current subscription for a tenant."""
    tenant_id = get_tenant_id(x_tenant_id)
    sub = _subscriptions.get(tenant_id)

    if sub is None or sub.status == SubscriptionStatus.CANCELED:
        raise HTTPException(status_code=404, detail="No active subscription to cancel")

    # Cancel in Stripe if we have a subscription ID
    if sub.stripe_subscription_id:
        await stripe_client.cancel_subscription(sub.stripe_subscription_id)

    sub.status = SubscriptionStatus.CANCELED
    sub.canceled_at = datetime.utcnow()

    return {
        "message": "Subscription canceled. You'll retain access until the end of the current period.",
        "access_until": sub.current_period_end.isoformat() if sub.current_period_end else None,
    }


@router.post("/change-tier")
async def change_tier(
    request: ChangeTierRequest,
    x_tenant_id: Optional[str] = Header(None),
):
    """Upgrade or downgrade the subscription tier."""
    tenant_id = get_tenant_id(x_tenant_id)
    sub = _subscriptions.get(tenant_id)

    if sub is None or sub.status not in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING):
        raise HTTPException(status_code=404, detail="No active subscription found")

    new_tier = PRICING_TIERS.get(request.new_tier_id)
    if new_tier is None:
        raise HTTPException(status_code=400, detail=f"Invalid tier: {request.new_tier_id}")

    if new_tier.monthly_price is None:
        raise HTTPException(
            status_code=400,
            detail="Enterprise tier requires custom pricing — contact sales@regengine.co",
        )

    old_tier_id = sub.tier_id
    sub.tier_id = request.new_tier_id

    # Determine upgrade vs downgrade
    old_price = PRICING_TIERS[old_tier_id].monthly_price or 0
    new_price = new_tier.monthly_price or 0
    direction = "upgraded" if new_price > old_price else "downgraded"

    return {
        "message": f"Successfully {direction} from {old_tier_id} to {request.new_tier_id}",
        "subscription": sub.model_dump(),
        "effective": "immediately" if direction == "upgraded" else "next billing cycle",
    }
