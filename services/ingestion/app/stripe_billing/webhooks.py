"""Webhook event processing."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

import stripe
import structlog
from fastapi import HTTPException, Request

from shared import funnel_events as _funnel_mod

from . import customers as _customers_mod
from . import helpers as _helpers_mod
from . import plans as _plans_mod
from . import rate_limit as _rate_limit_mod
from . import state as _state_mod

logger = structlog.get_logger("stripe-billing")


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
            "stripe_webhook_metadata_tenant_mismatch",
            server_tenant=tenant_id,
            metadata_tenant=metadata_tenant,
            session_id=session_id,
            customer_id=customer_id,
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
                "stripe_webhook_ignored_client_metadata_tenant_id",
                client_tenant=metadata_tenant,
                session_id=session_id,
                reason="no server binding exists",
            )

        tenant_name = metadata.get("tenant_name")
        if not tenant_name:
            fallback_email = metadata.get("customer_email") or session.get("customer_email")
            tenant_name = f"{(fallback_email or 'New Customer').split('@')[0]} Team"

        tenant_id = await _customers_mod._create_tenant_via_admin(tenant_name)
        logger.info(
            "tenant_created_from_checkout",
            tenant_id=tenant_id,
            session_id=session_id,
        )

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
            logger.warning(
                "subscription_lookup_failed",
                subscription_id=subscription_id,
                error=str(exc),
            )

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
                    "stripe_pending_update_applied",
                    subscription_id=subscription_id,
                    tenant_id=tenant_id,
                    pending_event_created=pending_event_created,
                    checkout_event_created=checkout_event_created,
                    status=pending_status,
                )
            else:
                logger.info(
                    "stripe_pending_update_superseded_by_checkout",
                    subscription_id=subscription_id,
                    tenant_id=tenant_id,
                    pending_event_created=pending_event_created,
                    checkout_event_created=checkout_event_created,
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
                "billing_mapping_not_found_update_buffered",
                subscription_id=subscription_id,
                customer_id=customer_id,
                status=status,
                event_created=event_created,
                buffered=buffered,
            )
        else:
            logger.warning(
                "billing_mapping_not_found",
                subscription_id=subscription_id,
                customer_id=customer_id,
                status=status,
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
                "stripe_webhook_event_out_of_order_ignored",
                tenant_id=tenant_id,
                subscription_id=subscription_id,
                event_created=event_created,
                last_event_created=last_seen,
                status=status,
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


def _handle_trial_will_end(subscription: dict[str, Any]) -> None:
    """Handle ``customer.subscription.trial_will_end`` (#1189).

    Stripe fires this event ~3 days before a trialing subscription
    expires. The tenant needs a prompt to add a payment method, and
    product/marketing needs a signal to nudge conversion. We:

    1. Find the tenant via subscription or customer lookup.
    2. Persist ``trial_end`` and ``trial_will_end_notified_at`` onto
       the subscription mapping so the app can surface the countdown.
    3. Emit a WARN log so the 3-day window is visible in operator
       dashboards.

    If the tenant cannot be resolved (no prior successful checkout),
    we log and no-op — there is no subscription mapping to annotate
    yet, and the dashboard will pick up the countdown when the tenant
    completes checkout.
    """
    subscription_id = subscription.get("id")
    customer_id = subscription.get("customer")
    trial_end = _helpers_mod._format_period_end(
        _helpers_mod._coerce_int(subscription.get("trial_end"))
    )

    tenant_id = _state_mod._find_tenant_id(subscription_id, customer_id)
    if not tenant_id:
        logger.warning(
            "stripe_trial_will_end_tenant_not_found",
            subscription_id=subscription_id,
            customer_id=customer_id,
        )
        return

    existing = _state_mod._get_subscription_mapping(tenant_id)
    existing.update(
        {
            "trial_end": trial_end or "",
            "trial_will_end_notified_at": datetime.now(timezone.utc).isoformat(),
            "status": (
                str(subscription.get("status") or existing.get("status") or "trialing")
            ),
            "subscription_id": str(subscription_id or existing.get("subscription_id", "")),
            "customer_id": str(customer_id or existing.get("customer_id", "")),
        }
    )
    _state_mod._store_subscription_mapping(tenant_id, existing)
    logger.warning(
        "stripe_trial_will_end",
        tenant_id=tenant_id,
        subscription_id=subscription_id,
        trial_end=trial_end,
    )


def _handle_dispute_created(dispute: dict[str, Any]) -> None:
    """Handle ``charge.dispute.created`` (#1189).

    A chargeback has been opened. This is ops-critical: the tenant's
    payment method has been challenged by the cardholder's bank and
    Stripe will deduct the disputed amount (plus a dispute fee) until
    it is resolved. We:

    1. Locate the tenant via the customer_id on the dispute (newer
       Stripe API versions populate this field directly).
    2. Persist dispute metadata (id, amount_cents, currency, reason,
       status, charge, opened_at) onto the subscription mapping so
       the admin dashboard can surface the dispute.
    3. Emit an ERROR-level log so on-call is paged — a dispute
       requires a human response within Stripe's deadline (usually
       7 days) or the chargeback is lost by default.
    """
    dispute_id = str(dispute.get("id", "") or "")
    charge_id = str(dispute.get("charge", "") or "")
    customer_id = dispute.get("customer")

    # Tenant lookup: disputes are customer-scoped, not subscription-scoped
    # (a dispute could target any past charge for that customer).
    tenant_id = _state_mod._find_tenant_id(None, customer_id)
    if not tenant_id:
        logger.error(
            "stripe_dispute_tenant_not_found",
            dispute_id=dispute_id,
            charge_id=charge_id,
            customer_id=customer_id,
        )
        return

    existing = _state_mod._get_subscription_mapping(tenant_id)
    existing.update(
        {
            "last_dispute_id": dispute_id,
            "last_dispute_charge_id": charge_id,
            "last_dispute_amount_cents": str(
                _helpers_mod._coerce_int(dispute.get("amount"))
            ),
            "last_dispute_currency": str(dispute.get("currency", "") or ""),
            "last_dispute_reason": str(dispute.get("reason", "") or ""),
            "last_dispute_status": str(dispute.get("status", "") or ""),
            "last_dispute_opened_at": (
                _helpers_mod._format_period_end(
                    _helpers_mod._coerce_int(dispute.get("created"))
                )
                or datetime.now(timezone.utc).isoformat()
            ),
        }
    )
    _state_mod._store_subscription_mapping(tenant_id, existing)
    # ERROR not WARN: chargebacks must page a human.
    logger.error(
        "stripe_dispute_opened",
        tenant_id=tenant_id,
        dispute_id=dispute_id,
        amount_cents=existing["last_dispute_amount_cents"],
        currency=existing["last_dispute_currency"],
        reason=existing["last_dispute_reason"],
        charge_id=charge_id,
    )


def _handle_customer_deleted(customer: dict[str, Any]) -> None:
    """Handle ``customer.deleted`` (#1189).

    The Stripe customer has been deleted (typically an admin action in
    the Stripe dashboard, or a churned-account cleanup script). We:

    1. Locate the tenant via the customer_id.
    2. Mark the subscription mapping as ``customer_deleted`` and
       record ``customer_deleted_at``. We preserve the tenant hash
       as an audit record (past billing history doesn't vanish just
       because the Stripe customer was removed).
    3. Delete the ``billing:customer:{customer_id}`` lookup key and
       the ``billing:subscription:{subscription_id}`` lookup key so a
       subsequent out-of-order webhook for the stale IDs can't silently
       re-bind to the same tenant.
    4. Emit a WARN log — this event is uncommon enough that operators
       will want to know why the customer was removed.
    """
    customer_id = customer.get("id")
    if not customer_id:
        logger.warning("stripe_customer_deleted_missing_id")
        return

    tenant_id = _state_mod._find_tenant_id(None, customer_id)
    if not tenant_id:
        logger.warning(
            "stripe_customer_deleted_tenant_not_found",
            customer_id=customer_id,
        )
        # Still clear the stale lookup defensively — nothing bound to
        # it but also no reason to keep a dead pointer around.
        _state_mod._clear_customer_lookup(str(customer_id))
        return

    existing = _state_mod._get_subscription_mapping(tenant_id)
    prior_subscription_id = existing.get("subscription_id", "")
    existing.update(
        {
            "status": "customer_deleted",
            "customer_deleted_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    _state_mod._store_subscription_mapping(tenant_id, existing)

    _state_mod._clear_customer_lookup(str(customer_id))
    if prior_subscription_id:
        _state_mod._clear_subscription_lookup(str(prior_subscription_id))

    logger.warning(
        "stripe_customer_deleted",
        tenant_id=tenant_id,
        customer_id=customer_id,
        subscription_id=prior_subscription_id or "(none)",
    )


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

    # #1189: trial expiration notice (~3 days before trial_end).
    if event_type == "customer.subscription.trial_will_end":
        _handle_trial_will_end(data_object)
        return

    # #1189: chargeback opened — ops-critical, logs at ERROR.
    if event_type == "charge.dispute.created":
        _handle_dispute_created(data_object)
        return

    # #1189: Stripe customer removed — clean up lookup keys.
    if event_type == "customer.deleted":
        _handle_customer_deleted(data_object)
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

    # Signature verification MUST happen before the rate-limit counter is
    # incremented so that forged/replayed events with invalid signatures cannot
    # burn the rate-limit budget for legitimate Stripe IPs.
    try:
        event = stripe.Webhook.construct_event(
            payload=body,
            sig_header=stripe_signature,
            secret=webhook_secret,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook payload") from exc
    except stripe.error.SignatureVerificationError as exc:
        logger.warning("stripe_webhook_signature_invalid", error=str(exc))
        raise HTTPException(status_code=400, detail="Invalid Stripe signature") from exc

    # IP-based rate limit: 100 req/min per source IP (env: STRIPE_WEBHOOK_RATE_LIMIT /
    # STRIPE_WEBHOOK_RATE_WINDOW).  Only signature-verified requests consume a slot.
    client_ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )
    limited, retry_after = _rate_limit_mod.is_rate_limited(client_ip)
    if limited:
        logger.warning(
            "stripe_webhook_rate_limited",
            ip=client_ip,
            retry_after=retry_after,
        )
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests"},
            headers={"Retry-After": str(retry_after)},
        )

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
            "stripe_webhook_duplicate_ignored",
            event_id=event_id,
            event_type=event_type,
        )
        return {
            "received": True,
            "event_type": event_type,
            "duplicate": True,
        }

    await _handle_stripe_event(event)
    logger.info("stripe_webhook_processed", event_type=event_type)
    return {"received": True, "event_type": event_type}
