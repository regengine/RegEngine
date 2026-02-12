"""
Billing Service — Stripe Webhook Router

Receives and processes Stripe webhook events with HMAC signature verification.
"""

from __future__ import annotations

import json
from datetime import datetime

import structlog
from fastapi import APIRouter, Request, HTTPException

import stripe_client
import store

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/billing/webhooks", tags=["webhooks"])

# Event log for debugging/auditing
_processed_events: list[dict] = []


@router.post("/stripe")
async def stripe_webhook(request: Request):
    """Receive and process Stripe webhook events.

    Verifies HMAC signature and dispatches to appropriate handler.
    """
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")

    # Verify signature
    if not stripe_client.verify_webhook_signature(payload, signature):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type = event.get("type", "unknown")
    event_id = event.get("id", "unknown")

    logger.info("webhook_received", event_type=event_type, event_id=event_id)

    # Dispatch to handler
    handler = _EVENT_HANDLERS.get(event_type, _handle_unknown)
    result = await handler(event)

    # Log processed event
    _processed_events.append({
        "event_id": event_id,
        "event_type": event_type,
        "processed_at": datetime.utcnow().isoformat(),
        "result": result,
    })

    return {"received": True, "event_type": event_type}


# ── Event Handlers ─────────────────────────────────────────────────

async def _handle_checkout_completed(event: dict) -> str:
    """Handle checkout.session.completed — activate subscription."""
    session_data = event.get("data", {}).get("object", {})
    metadata = session_data.get("metadata", {})
    tenant_id = metadata.get("tenant_id")
    tier_id = metadata.get("tier_id")
    stripe_sub_id = session_data.get("subscription")

    if not tenant_id:
        return "Missing tenant_id in metadata"

    logger.info(
        "checkout_completed",
        tenant_id=tenant_id,
        tier_id=tier_id,
        subscription_id=stripe_sub_id,
        payment_status=session_data.get("payment_status"),
    )

    # Update subscription state
    if tenant_id in store.subscriptions:
        sub = store.subscriptions[tenant_id]
        # Transition from TRIALING/INCOMPLETE to ACTIVE
        sub.status = "active"
        sub.stripe_subscription_id = stripe_sub_id
        # Update period from Stripe if available
        # (simulated here since we don't fetch from Stripe API during webhook)
        sub.updated_at = datetime.utcnow()
        logger.info("subscription_activated", tenant_id=tenant_id)
    else:
        logger.warning("subscription_not_found_for_activation", tenant_id=tenant_id)

    return f"Subscription activated for tenant {tenant_id}"


async def _handle_subscription_updated(event: dict) -> str:
    """Handle customer.subscription.updated — sync subscription state."""
    sub_data = event.get("data", {}).get("object", {})
    sub_id = sub_data.get("id")
    new_status = sub_data.get("status")
    
    # Find subscription by stripe_id (inefficient for in-memory, ok for demo)
    # In DB we would query WHERE stripe_subscription_id = sub_id
    target_tenant = None
    for tid, sub in store.subscriptions.items():
        if sub.stripe_subscription_id == sub_id:
            sub.status = new_status
            sub.updated_at = datetime.utcnow()
            target_tenant = tid
            break

    logger.info("subscription_sync", subscription_id=sub_id, status=new_status, tenant_id=target_tenant)
    return f"Subscription {sub_id} updated to {new_status}"


async def _handle_payment_succeeded(event: dict) -> str:
    """Handle invoice.payment_succeeded — record successful payment."""
    invoice = event.get("data", {}).get("object", {})
    amount = invoice.get("amount_paid", 0)
    customer_id = invoice.get("customer")
    sub_id = invoice.get("subscription")

    logger.info("payment_succeeded", customer=customer_id, amount_cents=amount, subscription=sub_id)
    
    # If this was for a specific subscription, ensure it's active
    if sub_id:
        for tid, sub in store.subscriptions.items():
            if sub.stripe_subscription_id == sub_id:
                if sub.status == "past_due":
                    sub.status = "active"
                    logger.info("subscription_reactivated", tenant_id=tid)
                break

    return f"Payment of ${amount / 100:.2f} recorded for {customer_id}"


async def _handle_payment_failed(event: dict) -> str:
    """Handle invoice.payment_failed — flag subscription as past_due."""
    invoice = event.get("data", {}).get("object", {})
    customer_id = invoice.get("customer")
    sub_id = invoice.get("subscription")
    attempt = invoice.get("attempt_count", 0)

    logger.warning("payment_failed", customer=customer_id, attempt=attempt)

    if sub_id:
        for tid, sub in store.subscriptions.items():
            if sub.stripe_subscription_id == sub_id:
                sub.status = "past_due"
                logger.warning("subscription_past_due", tenant_id=tid)
                break

    return f"Payment failed for {customer_id} (attempt {attempt})"


async def _handle_unknown(event: dict) -> str:
    """Handle unregistered event types."""
    event_type = event.get("type", "unknown")
    logger.info("unhandled_webhook_event", event_type=event_type)
    return f"Unhandled event type: {event_type}"


_EVENT_HANDLERS = {
    "checkout.session.completed": _handle_checkout_completed,
    "customer.subscription.updated": _handle_subscription_updated,
    "invoice.payment_succeeded": _handle_payment_succeeded,
    "invoice.payment_failed": _handle_payment_failed,
}


@router.get("/events")
async def list_processed_events():
    """List recently processed webhook events (debug/audit endpoint)."""
    return {
        "events": _processed_events[-50:],
        "total": len(_processed_events),
    }
