"""
Billing Service — Stripe Client Wrapper

Provides a sandbox-safe Stripe integration. When STRIPE_SECRET_KEY is not set,
all methods return mock responses so the service can run without Stripe credentials.
"""

from __future__ import annotations

import os
import hmac
import hashlib
import structlog
from typing import Optional
from uuid import uuid4

logger = structlog.get_logger(__name__)

# ── Configuration ──────────────────────────────────────────────────

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
BILLING_ENV = os.getenv("BILLING_ENV", "sandbox")  # sandbox | production

_stripe = None


def _get_stripe():
    """Lazy-load stripe SDK only when keys are available."""
    global _stripe
    if _stripe is not None:
        return _stripe
    if not STRIPE_SECRET_KEY:
        logger.warning("stripe_not_configured", msg="Running in sandbox mode — no real charges")
        return None
    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY
        _stripe = stripe
        logger.info("stripe_initialized", env=BILLING_ENV)
        return stripe
    except ImportError:
        logger.warning("stripe_sdk_missing", msg="Install stripe package for live billing")
        return None


def is_sandbox() -> bool:
    """Check whether we're running in sandbox mode."""
    return not STRIPE_SECRET_KEY or BILLING_ENV != "production"


# ── Customer ───────────────────────────────────────────────────────

async def create_customer(
    email: str,
    name: str,
    tenant_id: str,
    metadata: Optional[dict] = None,
) -> dict:
    """Create a Stripe customer or return mock data in sandbox."""
    stripe = _get_stripe()
    if stripe is None:
        mock_id = f"cus_sandbox_{uuid4().hex[:12]}"
        logger.info("sandbox_customer_created", customer_id=mock_id, tenant_id=tenant_id)
        return {
            "id": mock_id,
            "email": email,
            "name": name,
            "metadata": {"tenant_id": tenant_id, **(metadata or {})},
        }

    customer = stripe.Customer.create(
        email=email,
        name=name,
        metadata={"tenant_id": tenant_id, **(metadata or {})},
    )
    logger.info("stripe_customer_created", customer_id=customer.id, tenant_id=tenant_id)
    return {"id": customer.id, "email": email, "name": name, "metadata": customer.metadata}


# ── Checkout Session ───────────────────────────────────────────────

async def create_checkout_session(
    price_id: str,
    customer_id: Optional[str] = None,
    success_url: str = "https://regengine.co/checkout/success",
    cancel_url: str = "https://regengine.co/pricing",
    metadata: Optional[dict] = None,
) -> dict:
    """Create a Stripe Checkout session or return mock data in sandbox."""
    stripe = _get_stripe()
    if stripe is None:
        mock_id = f"cs_sandbox_{uuid4().hex[:12]}"
        mock_url = f"https://checkout.stripe.com/sandbox/{mock_id}"
        logger.info("sandbox_checkout_created", session_id=mock_id)
        return {
            "id": mock_id,
            "url": mock_url,
            "status": "open",
            "payment_status": "unpaid",
            "metadata": metadata or {},
        }

    params = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url + "?session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": cancel_url,
        "metadata": metadata or {},
    }
    if customer_id:
        params["customer"] = customer_id

    session = stripe.checkout.Session.create(**params)
    logger.info("stripe_checkout_created", session_id=session.id)
    return {
        "id": session.id,
        "url": session.url,
        "status": session.status,
        "payment_status": session.payment_status,
        "metadata": session.metadata,
    }


# ── Subscription ───────────────────────────────────────────────────

async def get_subscription(subscription_id: str) -> Optional[dict]:
    """Retrieve a Stripe subscription or return mock data."""
    stripe = _get_stripe()
    if stripe is None:
        return {
            "id": subscription_id,
            "status": "active",
            "current_period_start": 1707580800,
            "current_period_end": 1710259200,
            "cancel_at_period_end": False,
        }

    sub = stripe.Subscription.retrieve(subscription_id)
    return {
        "id": sub.id,
        "status": sub.status,
        "current_period_start": sub.current_period_start,
        "current_period_end": sub.current_period_end,
        "cancel_at_period_end": sub.cancel_at_period_end,
    }


async def cancel_subscription(subscription_id: str, at_period_end: bool = True) -> dict:
    """Cancel a Stripe subscription or return mock data."""
    stripe = _get_stripe()
    if stripe is None:
        logger.info("sandbox_subscription_canceled", subscription_id=subscription_id)
        return {
            "id": subscription_id,
            "status": "active",
            "cancel_at_period_end": at_period_end,
        }

    if at_period_end:
        sub = stripe.Subscription.modify(subscription_id, cancel_at_period_end=True)
    else:
        sub = stripe.Subscription.delete(subscription_id)
    logger.info("stripe_subscription_canceled", subscription_id=sub.id)
    return {
        "id": sub.id,
        "status": sub.status,
        "cancel_at_period_end": getattr(sub, "cancel_at_period_end", False),
    }


# ── Billing Portal ────────────────────────────────────────────────

async def create_billing_portal_session(
    customer_id: str,
    return_url: str = "https://regengine.co/dashboard",
) -> dict:
    """Create a Stripe Billing Portal session or return mock URL."""
    stripe = _get_stripe()
    if stripe is None:
        mock_url = f"https://billing.stripe.com/sandbox/portal/{customer_id}"
        return {"url": mock_url}

    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )
    return {"url": session.url}


# ── Webhook Verification ──────────────────────────────────────────

def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """Verify Stripe webhook HMAC signature."""
    if not STRIPE_WEBHOOK_SECRET:
        logger.warning("webhook_verification_skipped", reason="No webhook secret configured")
        return True  # Accept in sandbox

    stripe = _get_stripe()
    if stripe is None:
        return True

    try:
        stripe.Webhook.construct_event(payload, signature, STRIPE_WEBHOOK_SECRET)
        return True
    except (stripe.error.SignatureVerificationError, ValueError):
        logger.error("webhook_signature_invalid")
        return False
