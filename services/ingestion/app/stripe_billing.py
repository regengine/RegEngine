"""
Stripe Billing Router.

Manages subscription checkout sessions, plan management, and webhook
handling for Stripe payment events. Supports three tiers:
- Starter: $149/mo (1 facility, 5 supplier links, CSV/manual only)
- Professional: $499/mo (5 facilities, unlimited suppliers, IoT + API)
- Enterprise: Custom pricing (unlimited, SSO, dedicated support)
"""

from __future__ import annotations

import logging
import hmac
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel, Field

from app.webhook_router import _verify_api_key

logger = logging.getLogger("stripe-billing")

router = APIRouter(prefix="/api/v1/billing", tags=["Billing & Subscriptions"])


# ── Plan Definitions ──────────────────────────────────────────────

PLANS = {
    "starter": {
        "id": "starter",
        "name": "Starter",
        "price_monthly": 149,
        "price_annual": 1490,  # ~2 months free
        "stripe_price_id_monthly": "price_starter_monthly",
        "stripe_price_id_annual": "price_starter_annual",
        "features": [
            "1 facility",
            "5 supplier portal links",
            "CSV upload & manual entry",
            "All 6 CTE types",
            "SHA-256 audit trail",
            "Compliance score dashboard",
            "FDA export (CSV)",
            "Email support",
        ],
        "limits": {
            "facilities": 1,
            "supplier_links": 5,
            "events_per_month": 5000,
            "api_access": False,
            "iot_import": False,
            "epcis_export": False,
            "sso": False,
        },
    },
    "professional": {
        "id": "professional",
        "name": "Professional",
        "price_monthly": 499,
        "price_annual": 4990,
        "stripe_price_id_monthly": "price_pro_monthly",
        "stripe_price_id_annual": "price_pro_annual",
        "features": [
            "5 facilities",
            "Unlimited supplier portal links",
            "API + webhook integration",
            "IoT temperature monitoring (Sensitech, Tive)",
            "EPCIS 2.0 export (Walmart, Kroger, Costco)",
            "SOP generator",
            "Mock audit drills",
            "Priority support",
        ],
        "limits": {
            "facilities": 5,
            "supplier_links": -1,  # unlimited
            "events_per_month": 50000,
            "api_access": True,
            "iot_import": True,
            "epcis_export": True,
            "sso": False,
        },
    },
    "enterprise": {
        "id": "enterprise",
        "name": "Enterprise",
        "price_monthly": None,  # Custom
        "price_annual": None,
        "stripe_price_id_monthly": None,
        "stripe_price_id_annual": None,
        "features": [
            "Unlimited facilities",
            "Unlimited supplier portal links",
            "Full API + webhook + IoT",
            "All export formats",
            "SSO / SAML integration",
            "Custom recall playbooks",
            "Dedicated account manager",
            "99.9% SLA",
            "On-premise deployment option",
        ],
        "limits": {
            "facilities": -1,
            "supplier_links": -1,
            "events_per_month": -1,
            "api_access": True,
            "iot_import": True,
            "epcis_export": True,
            "sso": True,
        },
    },
}


class CheckoutRequest(BaseModel):
    """Request to create a Stripe checkout session."""
    plan_id: str = Field(..., description="Plan: starter, professional")
    billing_period: str = Field("monthly", description="monthly or annual")
    tenant_id: str = Field(..., description="Tenant ID")
    success_url: str = Field(
        "https://regengine.co/dashboard/compliance?checkout=success",
        description="Redirect URL on success"
    )
    cancel_url: str = Field(
        "https://regengine.co/pricing?checkout=cancelled",
        description="Redirect URL on cancel"
    )


class CheckoutResponse(BaseModel):
    """Stripe checkout session response."""
    checkout_url: str
    session_id: str
    plan: str
    billing_period: str
    amount: int
    currency: str = "usd"


class SubscriptionStatus(BaseModel):
    """Current subscription status for a tenant."""
    tenant_id: str
    plan: str
    status: str  # "active", "trialing", "past_due", "cancelled", "none"
    current_period_end: Optional[str] = None
    events_used: int = 0
    events_limit: int = 0
    facilities_used: int = 0
    facilities_limit: int = 0


@router.get(
    "/plans",
    summary="List available plans",
    description="Returns all available subscription plans with features and pricing.",
)
async def list_plans():
    """List all subscription plans."""
    return {"plans": list(PLANS.values())}


@router.post(
    "/checkout",
    response_model=CheckoutResponse,
    summary="Create Stripe checkout session",
    description="Creates a Stripe checkout session for the selected plan. Returns a URL to redirect the user to.",
)
async def create_checkout(
    request: CheckoutRequest,
    _: None = Depends(_verify_api_key),
) -> CheckoutResponse:
    """Create a Stripe checkout session."""
    plan = PLANS.get(request.plan_id)
    if not plan:
        raise HTTPException(status_code=400, detail=f"Invalid plan: {request.plan_id}")

    if request.plan_id == "enterprise":
        raise HTTPException(
            status_code=400,
            detail="Enterprise plans require a sales consultation. Contact sales@regengine.co"
        )

    if request.billing_period == "annual":
        amount = plan["price_annual"]
        price_id = plan["stripe_price_id_annual"]
    else:
        amount = plan["price_monthly"]
        price_id = plan["stripe_price_id_monthly"]

    # In production: stripe.checkout.Session.create(...)
    # For now, return a simulated session
    session_id = f"cs_test_{request.tenant_id}_{request.plan_id}"

    logger.info(
        "checkout_created",
        extra={
            "tenant_id": request.tenant_id,
            "plan": request.plan_id,
            "amount": amount,
        },
    )

    return CheckoutResponse(
        checkout_url=f"https://checkout.stripe.com/c/pay/{session_id}",
        session_id=session_id,
        plan=request.plan_id,
        billing_period=request.billing_period,
        amount=amount,
    )


@router.get(
    "/subscription/{tenant_id}",
    response_model=SubscriptionStatus,
    summary="Get subscription status",
)
async def get_subscription(
    tenant_id: str,
    _: None = Depends(_verify_api_key),
) -> SubscriptionStatus:
    """Get current subscription status for a tenant."""
    # In production: query Stripe API + local database
    # For pilot: return trial status
    return SubscriptionStatus(
        tenant_id=tenant_id,
        plan="professional",
        status="trialing",
        current_period_end=datetime.now(timezone.utc).isoformat(),
        events_used=127,
        events_limit=50000,
        facilities_used=2,
        facilities_limit=5,
    )


@router.post(
    "/webhook/stripe",
    summary="Stripe webhook handler",
    description="Handles Stripe webhook events (checkout.session.completed, invoice.paid, etc.)",
)
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(default=None, alias="Stripe-Signature"),
):
    """Handle Stripe webhook events."""
    configured_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if configured_secret:
        if not stripe_signature or not hmac.compare_digest(stripe_signature, configured_secret):
            raise HTTPException(status_code=401, detail="Invalid Stripe signature")

    body = await request.body()
    # In production: verify signature with stripe.Webhook.construct_event()

    # For now, acknowledge receipt
    logger.info("stripe_webhook_received", extra={"body_length": len(body)})

    return {"received": True}


@router.post(
    "/portal/{tenant_id}",
    summary="Create Stripe customer portal session",
    description="Creates a Stripe customer portal session for managing subscriptions.",
)
async def create_portal_session(
    tenant_id: str,
    _: None = Depends(_verify_api_key),
):
    """Create Stripe customer portal session for self-service billing management."""
    # In production: stripe.billing_portal.Session.create(...)
    return {
        "portal_url": f"https://billing.stripe.com/p/session/test_{tenant_id}",
        "tenant_id": tenant_id,
    }
