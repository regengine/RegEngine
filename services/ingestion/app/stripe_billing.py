"""
Stripe Billing Router.

Manages Stripe checkout sessions, subscription status, and webhook processing
for RegEngine's FSMA-first pricing tiers.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
import redis
import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import get_settings
from app.webhook_router import _verify_api_key

logger = logging.getLogger("stripe-billing")

router = APIRouter(prefix="/api/v1/billing", tags=["Billing & Subscriptions"])

DEFAULT_SUCCESS_URL = "https://regengine.co/dashboard?checkout=success"
DEFAULT_CANCEL_URL = "https://regengine.co/pricing?checkout=cancelled"
DEFAULT_PORTAL_RETURN_URL = "https://regengine.co/dashboard"

PLAN_ALIASES = {
    "starter": "growth",
    "professional": "scale",
}


# ── Plan Definitions ──────────────────────────────────────────────

PLANS: dict[str, dict[str, Any]] = {
    "growth": {
        "id": "growth",
        "name": "Growth",
        "price_monthly": 999,
        "price_annual": 999,
        "stripe_price_env_monthly": "STRIPE_PRICE_GROWTH_MONTHLY",
        "stripe_price_env_annual": "STRIPE_PRICE_GROWTH_ANNUAL",
        "features": [
            "FSMA 204 traceability workspace",
            "Supplier onboarding + FTL scoping",
            "CSV upload + API ingestion",
            "Compliance scoring + FDA-ready export",
            "Recall simulation + drill workflows",
            "Email support",
        ],
        "limits": {
            "facilities": 1,
            "events_per_month": 50000,
        },
    },
    "scale": {
        "id": "scale",
        "name": "Scale",
        "price_monthly": 1999,
        "price_annual": 1999,
        "stripe_price_env_monthly": "STRIPE_PRICE_SCALE_MONTHLY",
        "stripe_price_env_annual": "STRIPE_PRICE_SCALE_ANNUAL",
        "features": [
            "Everything in Growth",
            "Multi-facility operations",
            "Expanded API + webhook limits",
            "Priority onboarding support",
            "Retailer-specific readiness benchmarks",
            "Priority support",
        ],
        "limits": {
            "facilities": 5,
            "events_per_month": 250000,
        },
    },
    "enterprise": {
        "id": "enterprise",
        "name": "Enterprise",
        "price_monthly": None,
        "price_annual": None,
        "stripe_price_env_monthly": None,
        "stripe_price_env_annual": None,
        "features": [
            "Everything in Scale",
            "Dedicated implementation plan",
            "Custom SLA + security review support",
            "Advanced integration and data architecture",
            "Executive sponsor + quarterly roadmap reviews",
        ],
        "limits": {
            "facilities": -1,
            "events_per_month": -1,
        },
    },
}


class CheckoutRequest(BaseModel):
    """Request to create a Stripe checkout session."""

    plan_id: str = Field(..., description="Plan: growth or scale")
    billing_period: str = Field("monthly", description="monthly or annual")
    tenant_id: Optional[str] = Field(default=None, description="Existing tenant ID if already provisioned")
    tenant_name: Optional[str] = Field(default=None, description="Tenant name for post-payment provisioning")
    customer_email: Optional[str] = Field(default=None, description="Payer email")
    success_url: str = Field(DEFAULT_SUCCESS_URL, description="Redirect URL on success")
    cancel_url: str = Field(DEFAULT_CANCEL_URL, description="Redirect URL on cancel")


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
    status: str  # active, trialing, past_due, canceled, none
    current_period_end: Optional[str] = None
    events_used: int = 0
    events_limit: int = 0
    facilities_used: int = 0
    facilities_limit: int = 0


def _normalize_plan_id(plan_id: str) -> str:
    normalized = PLAN_ALIASES.get(plan_id, plan_id)
    return normalized


def _normalize_billing_period(period: str) -> str:
    normalized = period.lower().strip()
    if normalized not in {"monthly", "annual"}:
        raise HTTPException(status_code=400, detail="billing_period must be 'monthly' or 'annual'")
    return normalized


def _configure_stripe() -> None:
    secret_key = os.getenv("STRIPE_SECRET_KEY")
    if not secret_key:
        raise HTTPException(status_code=500, detail="STRIPE_SECRET_KEY is not configured")
    stripe.api_key = secret_key


def _resolve_price_id(plan_id: str, billing_period: str) -> tuple[dict[str, Any], str, int]:
    normalized_plan = _normalize_plan_id(plan_id)
    plan = PLANS.get(normalized_plan)
    if not plan:
        raise HTTPException(status_code=400, detail=f"Invalid plan: {plan_id}")

    if normalized_plan == "enterprise":
        raise HTTPException(
            status_code=400,
            detail="Enterprise plans require a sales consultation. Contact sales@regengine.co",
        )

    price_env_var = plan[f"stripe_price_env_{billing_period}"]
    price_id = os.getenv(price_env_var) if price_env_var else None

    # Allow annual billing requests to fall back to monthly price IDs if annual IDs are not configured.
    if not price_id and billing_period == "annual":
        monthly_env_var = plan["stripe_price_env_monthly"]
        price_id = os.getenv(monthly_env_var) if monthly_env_var else None

    if not price_id:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Stripe price ID is not configured for plan '{normalized_plan}' "
                f"({billing_period})."
            ),
        )

    amount = plan[f"price_{billing_period}"]
    if amount is None:
        raise HTTPException(status_code=400, detail="Plan does not support self-serve checkout")

    return plan, price_id, amount


def _redis_client() -> redis.Redis:
    settings = get_settings()
    return redis.from_url(settings.redis_url, decode_responses=True)


def _tenant_subscription_key(tenant_id: str) -> str:
    return f"billing:tenant:{tenant_id}"


def _subscription_lookup_key(subscription_id: str) -> str:
    return f"billing:subscription:{subscription_id}"


def _customer_lookup_key(customer_id: str) -> str:
    return f"billing:customer:{customer_id}"


def _session_lookup_key(session_id: str) -> str:
    return f"billing:session:{session_id}"


def _store_subscription_mapping(tenant_id: str, payload: dict[str, str]) -> None:
    client = _redis_client()
    key = _tenant_subscription_key(tenant_id)
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()

    client.hset(key, mapping=payload)

    subscription_id = payload.get("subscription_id")
    if subscription_id:
        client.set(_subscription_lookup_key(subscription_id), tenant_id)

    customer_id = payload.get("customer_id")
    if customer_id:
        client.set(_customer_lookup_key(customer_id), tenant_id)

    session_id = payload.get("session_id")
    if session_id:
        client.set(_session_lookup_key(session_id), tenant_id)


def _get_subscription_mapping(tenant_id: str) -> dict[str, str]:
    client = _redis_client()
    return client.hgetall(_tenant_subscription_key(tenant_id))


def _find_tenant_id(subscription_id: Optional[str], customer_id: Optional[str]) -> Optional[str]:
    client = _redis_client()

    if subscription_id:
        tenant_id = client.get(_subscription_lookup_key(subscription_id))
        if tenant_id:
            return tenant_id

    if customer_id:
        tenant_id = client.get(_customer_lookup_key(customer_id))
        if tenant_id:
            return tenant_id

    return None


async def _create_tenant_via_admin(tenant_name: str) -> str:
    admin_base_url = os.getenv("ADMIN_SERVICE_URL", "http://localhost:8400").rstrip("/")
    admin_master_key = os.getenv("ADMIN_MASTER_KEY")

    if not admin_master_key:
        raise RuntimeError("ADMIN_MASTER_KEY is required to create tenants from Stripe webhooks")

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            f"{admin_base_url}/v1/admin/tenants",
            headers={"X-Admin-Key": admin_master_key},
            json={"name": tenant_name},
        )
        response.raise_for_status()

    payload = response.json()
    tenant_id = payload.get("tenant_id")
    if not tenant_id:
        raise RuntimeError("Admin tenant creation response missing tenant_id")

    return tenant_id


def _format_period_end(epoch_seconds: Optional[int]) -> Optional[str]:
    if not epoch_seconds:
        return None
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).isoformat()


async def _handle_checkout_completed(session: dict[str, Any]) -> None:
    metadata = session.get("metadata") or {}
    session_id = session.get("id")

    client = _redis_client()

    tenant_id = metadata.get("tenant_id")
    if session_id:
        existing_tenant = client.get(_session_lookup_key(session_id))
        if existing_tenant:
            tenant_id = existing_tenant

    if not tenant_id:
        tenant_name = metadata.get("tenant_name")
        if not tenant_name:
            fallback_email = metadata.get("customer_email") or session.get("customer_email")
            tenant_name = f"{(fallback_email or 'New Customer').split('@')[0]} Team"

        tenant_id = await _create_tenant_via_admin(tenant_name)
        logger.info("tenant_created_from_checkout", tenant_id=tenant_id, session_id=session_id)

    subscription_id = session.get("subscription")
    customer_id = session.get("customer")

    plan_id = _normalize_plan_id(str(metadata.get("plan_id", "growth")))
    billing_period = _normalize_billing_period(str(metadata.get("billing_period", "monthly")))

    subscription_status = "active"
    current_period_end = None
    if subscription_id:
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            subscription_status = subscription.get("status", subscription_status)
            current_period_end = _format_period_end(subscription.get("current_period_end"))
        except stripe.error.StripeError as exc:  # pragma: no cover - network/API errors
            logger.warning("subscription_lookup_failed", subscription_id=subscription_id, error=str(exc))

    _store_subscription_mapping(
        tenant_id,
        {
            "tenant_id": tenant_id,
            "session_id": session_id or "",
            "customer_id": customer_id or "",
            "subscription_id": subscription_id or "",
            "plan_id": plan_id,
            "billing_period": billing_period,
            "status": subscription_status,
            "customer_email": (
                (session.get("customer_details") or {}).get("email")
                or session.get("customer_email")
                or str(metadata.get("customer_email", ""))
            ),
            "current_period_end": current_period_end or "",
        },
    )


def _update_subscription_status(subscription_id: Optional[str], customer_id: Optional[str], status: str) -> None:
    tenant_id = _find_tenant_id(subscription_id, customer_id)
    if not tenant_id:
        logger.warning(
            "billing_mapping_not_found",
            subscription_id=subscription_id,
            customer_id=customer_id,
            status=status,
        )
        return

    existing = _get_subscription_mapping(tenant_id)
    existing.update(
        {
            "status": status,
            "subscription_id": subscription_id or existing.get("subscription_id", ""),
            "customer_id": customer_id or existing.get("customer_id", ""),
        }
    )
    _store_subscription_mapping(tenant_id, existing)


async def _handle_stripe_event(event: dict[str, Any]) -> None:
    event_type = event.get("type")
    data_object = (event.get("data") or {}).get("object") or {}

    if event_type == "checkout.session.completed":
        await _handle_checkout_completed(data_object)
        return

    if event_type == "invoice.payment_failed":
        _update_subscription_status(
            subscription_id=data_object.get("subscription"),
            customer_id=data_object.get("customer"),
            status="past_due",
        )
        return

    if event_type == "invoice.paid":
        _update_subscription_status(
            subscription_id=data_object.get("subscription"),
            customer_id=data_object.get("customer"),
            status="active",
        )
        return

    if event_type in {"customer.subscription.deleted", "customer.subscription.updated"}:
        sub_status = data_object.get("status")
        status = "canceled" if event_type == "customer.subscription.deleted" else (sub_status or "active")

        _update_subscription_status(
            subscription_id=data_object.get("id"),
            customer_id=data_object.get("customer"),
            status=status,
        )

        # Persist period end when available.
        tenant_id = _find_tenant_id(data_object.get("id"), data_object.get("customer"))
        if tenant_id:
            existing = _get_subscription_mapping(tenant_id)
            existing["current_period_end"] = _format_period_end(data_object.get("current_period_end")) or ""
            _store_subscription_mapping(tenant_id, existing)
        return

    logger.info("stripe_webhook_ignored", event_type=event_type)


@router.get(
    "/plans",
    summary="List available plans",
    description="Returns all available subscription plans with features and pricing.",
)
async def list_plans() -> dict[str, list[dict[str, Any]]]:
    """List all subscription plans."""
    return {
        "plans": [
            {
                "id": plan["id"],
                "name": plan["name"],
                "price_monthly": plan["price_monthly"],
                "price_annual": plan["price_annual"],
                "features": plan["features"],
                "limits": plan["limits"],
            }
            for plan in PLANS.values()
        ]
    }


@router.post(
    "/checkout",
    response_model=CheckoutResponse,
    summary="Create Stripe checkout session",
    description=(
        "Creates a Stripe checkout session for the selected plan and returns "
        "a URL for redirecting the customer to Stripe Checkout."
    ),
)
async def create_checkout(request: CheckoutRequest) -> CheckoutResponse:
    """Create a Stripe checkout session."""
    _configure_stripe()

    billing_period = _normalize_billing_period(request.billing_period)
    plan, price_id, amount = _resolve_price_id(request.plan_id, billing_period)

    metadata = {
        "plan_id": plan["id"],
        "billing_period": billing_period,
    }
    if request.tenant_id:
        metadata["tenant_id"] = request.tenant_id
    if request.tenant_name:
        metadata["tenant_name"] = request.tenant_name
    if request.customer_email:
        metadata["customer_email"] = request.customer_email

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=request.success_url,
            cancel_url=request.cancel_url,
            customer_email=request.customer_email,
            allow_promotion_codes=True,
            metadata=metadata,
            subscription_data={"metadata": metadata},
        )
    except stripe.error.StripeError as exc:
        logger.error("checkout_create_failed", error=str(exc), plan=plan["id"])
        raise HTTPException(status_code=502, detail=f"Stripe checkout creation failed: {exc.user_message or str(exc)}") from exc

    logger.info(
        "checkout_created",
        extra={
            "tenant_id": request.tenant_id,
            "plan": plan["id"],
            "amount": amount,
            "billing_period": billing_period,
            "session_id": session.id,
        },
    )

    return CheckoutResponse(
        checkout_url=session.url,
        session_id=session.id,
        plan=plan["id"],
        billing_period=billing_period,
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
    _configure_stripe()

    try:
        mapping = _get_subscription_mapping(tenant_id)
    except redis.RedisError as exc:
        logger.error("subscription_mapping_read_failed", tenant_id=tenant_id, error=str(exc))
        raise HTTPException(status_code=503, detail="Billing state store unavailable") from exc

    if not mapping:
        return SubscriptionStatus(
            tenant_id=tenant_id,
            plan="none",
            status="none",
            current_period_end=None,
            events_used=0,
            events_limit=0,
            facilities_used=0,
            facilities_limit=0,
        )

    plan_id = _normalize_plan_id(mapping.get("plan_id", "growth"))
    status = mapping.get("status", "none")
    current_period_end = mapping.get("current_period_end") or None
    subscription_id = mapping.get("subscription_id")

    if subscription_id:
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            status = subscription.get("status", status)
            current_period_end = _format_period_end(subscription.get("current_period_end"))

            mapping["status"] = status
            mapping["current_period_end"] = current_period_end or ""
            _store_subscription_mapping(tenant_id, mapping)
        except stripe.error.StripeError as exc:  # pragma: no cover - network/API errors
            logger.warning("subscription_retrieve_failed", tenant_id=tenant_id, error=str(exc))

    limits = PLANS.get(plan_id, {}).get("limits", {})

    return SubscriptionStatus(
        tenant_id=tenant_id,
        plan=plan_id,
        status=status,
        current_period_end=current_period_end,
        events_used=0,
        events_limit=limits.get("events_per_month", 0),
        facilities_used=0,
        facilities_limit=limits.get("facilities", 0),
    )


@router.post(
    "/webhook/stripe",
    summary="Stripe webhook handler",
    description="Handles Stripe webhook events (checkout.session.completed, invoice.paid, etc.)",
)
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(default=None, alias="Stripe-Signature"),
) -> dict[str, Any]:
    """Handle Stripe webhook events."""
    _configure_stripe()

    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not webhook_secret:
        raise HTTPException(status_code=500, detail="STRIPE_WEBHOOK_SECRET is not configured")

    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")

    body = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload=body,
            sig_header=stripe_signature,
            secret=webhook_secret,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook payload") from exc
    except stripe.error.SignatureVerificationError as exc:
        raise HTTPException(status_code=401, detail="Invalid Stripe signature") from exc

    await _handle_stripe_event(event)

    logger.info("stripe_webhook_processed", event_type=event.get("type"))
    return {"received": True, "event_type": event.get("type")}


@router.post(
    "/portal/{tenant_id}",
    summary="Create Stripe customer portal session",
    description="Creates a Stripe customer portal session for managing subscriptions.",
)
async def create_portal_session(
    tenant_id: str,
    _: None = Depends(_verify_api_key),
) -> dict[str, str]:
    """Create Stripe customer portal session for self-service billing management."""
    _configure_stripe()

    mapping = _get_subscription_mapping(tenant_id)
    customer_id = mapping.get("customer_id")
    if not customer_id:
        raise HTTPException(status_code=404, detail="No Stripe customer is linked to this tenant")

    return_url = os.getenv("STRIPE_PORTAL_RETURN_URL", DEFAULT_PORTAL_RETURN_URL)

    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
    except stripe.error.StripeError as exc:
        logger.error("portal_session_create_failed", tenant_id=tenant_id, error=str(exc))
        raise HTTPException(status_code=502, detail=f"Stripe portal creation failed: {exc.user_message or str(exc)}") from exc

    return {
        "portal_url": session.url,
        "tenant_id": tenant_id,
    }
