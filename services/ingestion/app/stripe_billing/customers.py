"""Stripe customer lifecycle management."""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import stripe
from shared.resilient_http import resilient_client
from fastapi import HTTPException

from .helpers import _stripe_get
from .state import _get_subscription_mapping, _store_subscription_mapping

logger = logging.getLogger("stripe-billing")


async def _create_tenant_via_admin(tenant_name: str) -> str:
    admin_service_url = os.getenv("ADMIN_SERVICE_URL")
    if not admin_service_url:
        raise RuntimeError("ADMIN_SERVICE_URL is required — set it in the service environment")
    admin_base_url = admin_service_url.rstrip("/")
    admin_master_key = os.getenv("ADMIN_MASTER_KEY")

    if not admin_master_key:
        raise RuntimeError("ADMIN_MASTER_KEY is required to create tenants from Stripe webhooks")

    async with resilient_client(timeout=20.0, circuit_name="admin-service") as client:
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


def _create_portal_session(customer_id: str, return_url: str) -> Any:
    """Create Stripe portal session across SDK variants.

    H7 Proration Note: Subscription plan changes (upgrades/downgrades)
    happen exclusively through the Stripe Customer Portal. Stripe's portal
    uses the proration behavior configured on the portal *configuration*
    object (Dashboard > Settings > Customer portal > Subscriptions).
    RegEngine's portal configuration is set to "create_prorations" so that
    mid-cycle plan changes generate prorated line items automatically.

    There are no direct ``stripe.Subscription.modify()`` calls in this
    codebase — all subscription mutations flow through the portal, which
    inherits the proration setting from the portal configuration.
    """
    portal_namespace = getattr(stripe, "billing_portal", None)
    sessions_api = getattr(portal_namespace, "sessions", None)
    if sessions_api and hasattr(sessions_api, "create"):
        return sessions_api.create(
            customer=customer_id,
            return_url=return_url,
        )

    session_api = getattr(portal_namespace, "Session", None)
    if session_api and hasattr(session_api, "create"):
        return session_api.create(
            customer=customer_id,
            return_url=return_url,
        )

    raise HTTPException(status_code=500, detail="Stripe billing portal API is unavailable")


def _create_customer_for_tenant(
    tenant_id: str,
    tenant_name: Optional[str],
    customer_email: Optional[str],
) -> str:
    try:
        customer = stripe.Customer.create(
            email=customer_email,
            name=tenant_name or f"Tenant {tenant_id}",
            metadata={"tenant_id": tenant_id},
        )
    except stripe.error.StripeError as exc:
        logger.error("stripe_customer_create_failed", tenant_id=tenant_id, error=str(exc))
        raise HTTPException(
            status_code=502,
            detail=f"Stripe customer creation failed: {exc.user_message or str(exc)}",
        ) from exc

    customer_id = str(_stripe_get(customer, "id", "") or "")
    if not customer_id:
        raise HTTPException(status_code=502, detail="Stripe customer creation returned no customer ID")
    return customer_id


def _ensure_customer_mapping(
    tenant_id: str,
    tenant_name: Optional[str],
    customer_email: Optional[str],
) -> str:
    mapping = _get_subscription_mapping(tenant_id)
    customer_id = str(mapping.get("customer_id") or "").strip()
    if customer_id:
        return customer_id

    customer_id = _create_customer_for_tenant(
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        customer_email=customer_email,
    )

    _store_subscription_mapping(
        tenant_id,
        {
            "tenant_id": tenant_id,
            "session_id": mapping.get("session_id", ""),
            "customer_id": customer_id,
            "subscription_id": mapping.get("subscription_id", ""),
            "plan_id": mapping.get("plan_id", "none"),
            "billing_period": mapping.get("billing_period", "monthly"),
            "status": mapping.get("status", "none"),
            "customer_email": mapping.get("customer_email", "") or (customer_email or ""),
            "current_period_end": mapping.get("current_period_end", ""),
        },
    )
    return customer_id


def _get_existing_customer_id(tenant_id: Optional[str]) -> Optional[str]:
    if not tenant_id:
        return None

    mapping = _get_subscription_mapping(tenant_id)
    customer_id = str(mapping.get("customer_id") or "").strip()
    return customer_id or None


def _record_checkout_session_hint(
    tenant_id: Optional[str],
    session_id: str,
    plan_id: str,
    billing_period: str,
    customer_email: Optional[str],
    customer_id: Optional[str],
) -> None:
    if not tenant_id:
        return

    existing = _get_subscription_mapping(tenant_id)
    _store_subscription_mapping(
        tenant_id,
        {
            "tenant_id": tenant_id,
            "session_id": session_id,
            "customer_id": customer_id or existing.get("customer_id", ""),
            "subscription_id": existing.get("subscription_id", ""),
            "plan_id": plan_id,
            "billing_period": billing_period,
            "status": existing.get("status", "checkout_pending"),
            "customer_email": existing.get("customer_email", "") or (customer_email or ""),
            "current_period_end": existing.get("current_period_end", ""),
            "last_invoice_id": existing.get("last_invoice_id", ""),
            "last_payment_at": existing.get("last_payment_at", ""),
            "last_payment_failure_at": existing.get("last_payment_failure_at", ""),
        },
    )
