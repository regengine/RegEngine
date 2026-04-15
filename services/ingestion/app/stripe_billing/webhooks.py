"""Webhook event processing."""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import stripe
from fastapi import HTTPException, Request

from shared import funnel_events as _funnel_mod

from . import customers as _customers_mod
from . import helpers as _helpers_mod
from . import plans as _plans_mod
from . import state as _state_mod

logger = logging.getLogger("stripe-billing")


async def _handle_checkout_completed(session: dict[str, Any]) -> None:
    metadata = session.get("metadata") or {}
    session_id = session.get("id")

    client = _state_mod._redis_client()

    tenant_id = metadata.get("tenant_id")
    if session_id:
        existing_tenant = client.get(_state_mod._session_lookup_key(session_id))
        if existing_tenant:
            tenant_id = existing_tenant

    if not tenant_id:
        tenant_name = metadata.get("tenant_name")
        if not tenant_name:
            fallback_email = metadata.get("customer_email") or session.get("customer_email")
            tenant_name = f"{(fallback_email or 'New Customer').split('@')[0]} Team"

        tenant_id = await _customers_mod._create_tenant_via_admin(tenant_name)
        logger.info("tenant_created_from_checkout", tenant_id=tenant_id, session_id=session_id)

    subscription_id = session.get("subscription")
    customer_id = session.get("customer")

    plan_id = _plans_mod._normalize_plan_id(str(metadata.get("plan_id", "growth")))
    billing_period = _plans_mod._normalize_billing_period(str(metadata.get("billing_period", "monthly")))

    subscription_status = "active"
    current_period_end = None
    if subscription_id:
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            subscription_status = subscription.get("status", subscription_status)
            current_period_end = _helpers_mod._format_period_end(subscription.get("current_period_end"))
        except stripe.error.StripeError as exc:  # pragma: no cover - network/API errors
            logger.warning("subscription_lookup_failed", subscription_id=subscription_id, error=str(exc))

    _state_mod._store_subscription_mapping(
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


def _update_subscription_status(
    subscription_id: Optional[str],
    customer_id: Optional[str],
    status: str,
    *,
    current_period_end: Optional[str] = None,
    last_invoice_id: Optional[str] = None,
    last_payment_at: Optional[str] = None,
    last_payment_failure_at: Optional[str] = None,
) -> None:
    tenant_id = _state_mod._find_tenant_id(subscription_id, customer_id)
    if not tenant_id:
        logger.warning(
            "billing_mapping_not_found",
            subscription_id=subscription_id,
            customer_id=customer_id,
            status=status,
        )
        return

    existing = _state_mod._get_subscription_mapping(tenant_id)
    existing.update(
        {
            "status": status,
            "subscription_id": subscription_id or existing.get("subscription_id", ""),
            "customer_id": customer_id or existing.get("customer_id", ""),
        }
    )
    if current_period_end is not None:
        existing["current_period_end"] = current_period_end
    if last_invoice_id is not None:
        existing["last_invoice_id"] = last_invoice_id
    if last_payment_at is not None:
        existing["last_payment_at"] = last_payment_at
    if last_payment_failure_at is not None:
        existing["last_payment_failure_at"] = last_payment_failure_at
    _state_mod._store_subscription_mapping(tenant_id, existing)


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
            last_invoice_id=str(data_object.get("id", "") or ""),
            last_payment_failure_at=_helpers_mod._format_period_end(_helpers_mod._coerce_int(data_object.get("created"))),
        )
        return

    if event_type == "invoice.paid":
        period_end = _helpers_mod._extract_invoice_period_end(data_object)
        paid_at = _helpers_mod._extract_paid_at(data_object)
        subscription_id = data_object.get("subscription")
        customer_id = data_object.get("customer")
        _update_subscription_status(
            subscription_id=subscription_id,
            customer_id=customer_id,
            status="active",
            current_period_end=period_end,
            last_invoice_id=str(data_object.get("id", "") or ""),
            last_payment_at=paid_at,
        )
        payment_tenant_id = _state_mod._find_tenant_id(subscription_id, customer_id)
        _funnel_mod.emit_funnel_event(
            tenant_id=payment_tenant_id,
            event_name="payment_completed",
            metadata={
                "invoice_id": str(data_object.get("id", "") or ""),
                "subscription_id": str(subscription_id or ""),
            },
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
        tenant_id = _state_mod._find_tenant_id(data_object.get("id"), data_object.get("customer"))
        if tenant_id:
            existing = _state_mod._get_subscription_mapping(tenant_id)
            existing["current_period_end"] = _helpers_mod._format_period_end(data_object.get("current_period_end")) or ""
            _state_mod._store_subscription_mapping(tenant_id, existing)
        return

    logger.info("stripe_webhook_ignored", event_type=event_type)


async def _process_stripe_webhook(
    request: Request,
    stripe_signature: Optional[str],
) -> dict[str, Any]:
    _helpers_mod._configure_stripe()

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
        logger.warning("stripe_webhook_signature_invalid: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid Stripe signature") from exc

    await _handle_stripe_event(event)
    logger.info("stripe_webhook_processed", event_type=event.get("type"))
    return {"received": True, "event_type": event.get("type")}
