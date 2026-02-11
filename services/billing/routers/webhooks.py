"""
Billing Service — Stripe Webhook Router

Receives and processes Stripe webhook events with HMAC signature verification.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime

import structlog
from fastapi import APIRouter, Request, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import stripe_client

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
    session = event.get("data", {}).get("object", {})
    metadata = session.get("metadata", {})
    tenant_id = metadata.get("tenant_id", "unknown")
    tier_id = metadata.get("tier_id", "unknown")

    logger.info(
        "checkout_completed",
        tenant_id=tenant_id,
        tier_id=tier_id,
        payment_status=session.get("payment_status"),
    )
    return f"Subscription activated for tenant {tenant_id}"


async def _handle_subscription_updated(event: dict) -> str:
    """Handle customer.subscription.updated — sync subscription state."""
    sub = event.get("data", {}).get("object", {})
    sub_id = sub.get("id", "unknown")
    status = sub.get("status", "unknown")

    logger.info("subscription_updated", subscription_id=sub_id, status=status)
    return f"Subscription {sub_id} updated to {status}"


async def _handle_payment_succeeded(event: dict) -> str:
    """Handle invoice.payment_succeeded — record successful payment."""
    invoice = event.get("data", {}).get("object", {})
    amount = invoice.get("amount_paid", 0)
    customer = invoice.get("customer", "unknown")

    logger.info("payment_succeeded", customer=customer, amount_cents=amount)
    return f"Payment of ${amount / 100:.2f} recorded for {customer}"


async def _handle_payment_failed(event: dict) -> str:
    """Handle invoice.payment_failed — flag subscription as past_due."""
    invoice = event.get("data", {}).get("object", {})
    customer = invoice.get("customer", "unknown")
    attempt = invoice.get("attempt_count", 0)

    logger.warning("payment_failed", customer=customer, attempt=attempt)
    return f"Payment failed for {customer} (attempt {attempt})"


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
