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


async def _handle_checkout_completed(
    session: dict[str, Any],
    *,
    event_created: Optional[int] = None,
) -> None:
    """Handle a completed Stripe checkout.

    #1184 fix: never trust ``metadata.tenant_id`` from the session alone.
    The trust order is:
      1. Server-side session lookup (``billing:session:{session_id}``) —
         populated at checkout creation with the authenticated tenant.
      2. Customer-id lookup (``billing:customer:{customer_id}``) — bound
         at the time of the first successful checkout for that Stripe
         customer.
      3. Metadata ``tenant_id`` is used ONLY as a tie-breaker when it
         matches one of the above lookups. A mismatch is logged and
         rejected as a tampering attempt.

    If none of the three yields a tenant (brand-new customer paying for
    the first time) we provision a tenant via the admin service.
    """
    metadata = session.get("metadata") or {}
    session_id = session.get("id")
    customer_id = session.get("customer")
    client = _state_mod._redis_client()

    server_side_tenant: Optional[str] = None
    if session_id:
        server_side_tenant = client.get(_state_mod._session_lookup_key(session_id))

    customer_bound_tenant: Optional[str] = None
    if customer_id:
        customer_bound_tenant = client.get(_state_mod._customer_lookup_key(customer_id))

    metadata_tenant = metadata.get("tenant_id")

    # Authoritative tenant is whatever the server itself recorded.
    tenant_id = server_side_tenant or customer_bound_tenant

    if tenant_id and metadata_tenant and metadata_tenant != tenant_id:
        # Attacker tried to send a checkout session claiming another
        # tenant in metadata. Refuse rather than silently trust the
        # server-side value — we want loud telemetry.
        logger.error(
            "stripe_webhook_metadata_tenant_mismatch "
            "server_tenant=%s metadata_tenant=%s session_id=%s customer_id=%s",
            tenant_id, metadata_tenant, session_id, customer_id,
        )
        raise HTTPException(
            status_code=400,
            detail="Checkout metadata tenant_id does not match server-side binding",
        )

    if not tenant_id:
        # No server-side binding — this is a brand-new self-serve signup.
        # Provision a tenant via the admin service. We ignore any client-
        # supplied ``metadata.tenant_id`` because it could collide with an
        # existing tenant.
        if metadata_tenant:
            logger.warning(
                "stripe_webhook_ignored_client_metadata_tenant_id "
                "client_tenant=%s session_id=%s (no server binding exists)",
                metadata_tenant, session_id,
            )

        tenant_name = metadata.get("tenant_name")
        if not tenant_name:
            fallback_email = metadata.get("customer_email") or session.get("customer_email")
            tenant_name = f"{(fallback_email or 'New Customer').split('@')[0]} Team"

        tenant_id = await _customers_mod._create_tenant_via_admin(tenant_name)
        logger.info("tenant_created_from_checkout", tenant_id=tenant_id, session_id=session_id)

    subscription_id = session.get("subscription")

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

    # #1196: the checkout event itself is the first write that establishes
    # a tenant ↔ subscription mapping. Stamp its ``event_created`` as the
    # watermark so subsequent reordered updates with older timestamps are
    # rejected by the reorder guard in ``_update_subscription_status``.
    initial_mapping: dict[str, str] = {
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
    }
    if event_created is not None:
        initial_mapping["last_event_created"] = str(int(event_created))

    _state_mod._store_subscription_mapping(tenant_id, initial_mapping)

    # #1196: drain any pending subscription.updated/.deleted that arrived
    # out of order (before this checkout event). Apply it on top of the
    # initial mapping only if its ``event_created`` is strictly newer than
    # the checkout event's — otherwise the checkout's synchronous
    # ``stripe.Subscription.retrieve`` above already reflects a later state.
    if subscription_id:
        pending = _state_mod._pop_pending_subscription_update(subscription_id)
        if pending:
            pending_event_created = int(pending.get("event_created") or 0)
            checkout_event_created = int(event_created or 0)
            if pending_event_created > checkout_event_created:
                existing = _state_mod._get_subscription_mapping(tenant_id)
                # Merge pending-update fields into the just-written mapping.
                pending_status = pending.get("status")
                if pending_status:
                    existing["status"] = pending_status
                for key in (
                    "current_period_end",
                    "last_invoice_id",
                    "last_payment_at",
                    "last_payment_failure_at",
                ):
                    value = pending.get(key)
                    if value is not None:
                        existing[key] = value
                existing["last_event_created"] = str(pending_event_created)
                _state_mod._store_subscription_mapping(tenant_id, existing)
                logger.info(
                    "stripe_pending_update_applied "
                    "subscription_id=%s tenant_id=%s pending_event_created=%s "
                    "checkout_event_created=%s status=%s",
                    subscription_id, tenant_id, pending_event_created,
                    checkout_event_created, pending_status,
                )
            else:
                logger.info(
                    "stripe_pending_update_superseded_by_checkout "
                    "subscription_id=%s tenant_id=%s pending_event_created=%s "
                    "checkout_event_created=%s",
                    subscription_id, tenant_id, pending_event_created,
                    checkout_event_created,
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
    event_created: Optional[int] = None,
) -> None:
    """Apply a subscription-state change from a webhook event.

    #1196: Stripe does not guarantee event ordering. Two safeguards:

    1. *Missing-mapping recovery*: if no tenant mapping exists yet (e.g.
       ``customer.subscription.updated`` arrived before
       ``checkout.session.completed``), we buffer the update keyed by
       subscription_id and let ``_handle_checkout_completed`` drain it
       once the mapping is created. The previous behavior silently
       dropped the event.

    2. *Reorder guard*: if a mapping exists but has a ``last_event_created``
       watermark newer than this event's ``event_created``, we skip the
       write. This prevents an older webhook from overwriting a newer
       status that already landed (e.g. ``canceled`` followed in Stripe-
       time by a retry of an earlier ``active``).
    """
    tenant_id = _state_mod._find_tenant_id(subscription_id, customer_id)
    if not tenant_id:
        # #1196: buffer the update so checkout processing can recover it.
        # Before the fix this return silently dropped the event; the
        # subscription would stay stuck on its initial status even after
        # a successful payment and status flip.
        if subscription_id:
            buffered = _state_mod._buffer_pending_subscription_update(
                subscription_id,
                {
                    "status": status,
                    "event_created": int(event_created or 0),
                    "current_period_end": current_period_end,
                    "last_invoice_id": last_invoice_id,
                    "last_payment_at": last_payment_at,
                    "last_payment_failure_at": last_payment_failure_at,
                    "customer_id": customer_id or "",
                },
            )
            logger.warning(
                "billing_mapping_not_found_update_buffered "
                "subscription_id=%s customer_id=%s status=%s "
                "event_created=%s buffered=%s",
                subscription_id, customer_id, status,
                event_created, buffered,
            )
        else:
            logger.warning(
                "billing_mapping_not_found "
                "subscription_id=%s customer_id=%s status=%s",
                subscription_id, customer_id, status,
            )
        return

    existing = _state_mod._get_subscription_mapping(tenant_id)

    # #1196 reorder guard: refuse stale events.
    if event_created is not None:
        try:
            last_seen = int(existing.get("last_event_created") or 0)
        except (ValueError, TypeError):
            last_seen = 0
        if int(event_created) < last_seen:
            logger.info(
                "stripe_webhook_event_out_of_order_ignored "
                "tenant_id=%s subscription_id=%s "
                "event_created=%s last_event_created=%s status=%s",
                tenant_id, subscription_id, event_created, last_seen, status,
            )
            return

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
    if event_created is not None:
        existing["last_event_created"] = str(int(event_created))
    _state_mod._store_subscription_mapping(tenant_id, existing)


async def _handle_stripe_event(event: dict[str, Any]) -> None:
    event_type = event.get("type")
    data_object = (event.get("data") or {}).get("object") or {}
    # #1196: Stripe event envelopes always carry ``created`` (unix seconds).
    # Missing / unparseable → 0, which disables the reorder guard for this
    # event (safe default: we apply it like pre-fix behavior). This matches
    # how we treat legacy events that existed in the queue before the fix.
    event_created = _helpers_mod._coerce_int(event.get("created"), default=0) or None

    if event_type == "checkout.session.completed":
        await _handle_checkout_completed(data_object, event_created=event_created)
        return

    if event_type == "invoice.payment_failed":
        _update_subscription_status(
            subscription_id=data_object.get("subscription"),
            customer_id=data_object.get("customer"),
            status="past_due",
            last_invoice_id=str(data_object.get("id", "") or ""),
            last_payment_failure_at=_helpers_mod._format_period_end(_helpers_mod._coerce_int(data_object.get("created"))),
            event_created=event_created,
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
            event_created=event_created,
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
            event_created=event_created,
        )

        # Persist period end when available — but only if the reorder guard
        # above actually accepted the update. We re-check the watermark to
        # stay consistent: if ``last_event_created`` moved past this event,
        # we already logged out-of-order and must not clobber period_end.
        tenant_id = _state_mod._find_tenant_id(data_object.get("id"), data_object.get("customer"))
        if tenant_id:
            existing = _state_mod._get_subscription_mapping(tenant_id)
            try:
                last_seen = int(existing.get("last_event_created") or 0)
            except (ValueError, TypeError):
                last_seen = 0
            if event_created is None or int(event_created) >= last_seen:
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

    # #1076: Stripe retries any webhook that doesn't ack within a few seconds
    # (and for up to 3 days on 5xx/timeouts), so the same real-world event
    # can arrive multiple times. Without dedup this would re-provision
    # tenants in ``checkout.session.completed``, re-emit ``payment_completed``
    # funnel events on every ``invoice.paid`` retry, and re-flip subscription
    # status on retries of ``customer.subscription.updated``.
    #
    # The gate runs AFTER signature verification: we don't want to consume
    # dedup slots for forged signatures (which would let an attacker burn
    # event IDs), but we need to dedup BEFORE any handler side effect.
    event_id = event.get("id")
    event_type = event.get("type")
    if not _state_mod._mark_event_seen(event_id or ""):
        logger.info(
            "stripe_webhook_duplicate_ignored event_id=%s event_type=%s",
            event_id,
            event_type,
        )
        return {
            "received": True,
            "event_type": event_type,
            "duplicate": True,
        }

    await _handle_stripe_event(event)
    logger.info("stripe_webhook_processed", event_type=event_type)
    return {"received": True, "event_type": event_type}
