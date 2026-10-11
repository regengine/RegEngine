"""Webhook event processing."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

import stripe
import structlog
from fastapi import HTTPException, Request
from shared import funnel_events as _funnel_mod, webhook_auth as _webhook_auth_mod

from . import (
    customers as _customers_mod,
    helpers as _helpers_mod,
    plans as _plans_mod,
    rate_limiting as _rate_limiting_mod,
    state as _state_mod,
)

logger = structlog.get_logger("stripe-billing")

# #2930: the only statuses ``subscription_gate`` admits (see
# ``subscription_gate.py`` ``allowed_statuses``). Anything the checkout
# handler writes from this set unlocks every paid surface, so it must be
# reached only from a verified Stripe read of a settled payment.
_ENTITLING_STATUSES = {"active", "trialing"}

# Checkout ``payment_status`` values that mean the money actually moved
# (or none was owed). Delayed payment methods — ACH/SEPA/Bacs, common in
# B2B food distribution — report ``"unpaid"`` on
# ``checkout.session.completed`` and only settle later via
# ``checkout.session.async_payment_succeeded``.
_SETTLED_PAYMENT_STATUSES = {"paid", "no_payment_required"}


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

    # Pulled from the Stripe-event metadata as the *claimed* tenant only —
    # never used for routing. Below, we compare it to the server-recorded
    # tenant binding and refuse the webhook if they disagree (EPIC-A
    # defense-in-depth). This is the rule's enforcement code, not a
    # violation of it.
    metadata_tenant = metadata.get("tenant_id")  # nosemgrep: tenant-id-from-request-body

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
        # #2930: bind the new tenant to this session/customer immediately.
        # Provisioning is an external side effect that Stripe's redelivery
        # cannot undo, and the mapping write that normally records these
        # lookups happens further down — past the Subscription.retrieve that
        # may now fail the ack. Without this, every retry of a failed lookup
        # would provision another tenant and orphan this one.
        _state_mod._bind_tenant_lookups(
            tenant_id,
            session_id=session_id,
            customer_id=customer_id,
        )

    subscription_id = session.get("subscription")

    plan_id = _plans_mod._normalize_plan_id(str(metadata.get("plan_id", "growth")))
    billing_period = _plans_mod._normalize_billing_period(str(metadata.get("billing_period", "monthly")))

    # #2930: never pre-set an entitling status. This value is persisted to
    # the very hash the subscription gate reads, so the pre-verification
    # default must be one the gate denies — a session with no subscription
    # (or one we could not verify) entitles nothing.
    subscription_status = "incomplete"
    current_period_end = None
    payment_status = str(session.get("payment_status") or "")
    if subscription_id:
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
        except stripe.error.StripeError as exc:
            # #2930: do NOT fall through with the default and ack 200 — the
            # dedup slot is already claimed, so a swallowed error would be
            # final. Fail the ack instead; ``_process_stripe_webhook``
            # releases the claim and Stripe redelivers.
            logger.error(
                "subscription_lookup_failed",
                subscription_id=subscription_id,
                session_id=session_id,
                error=str(exc),
            )
            raise HTTPException(
                status_code=503,
                detail="Stripe subscription lookup failed; webhook not processed",
            ) from exc
        subscription_status = subscription.get("status", subscription_status)
        # #2951: read the period end from wherever the negotiated API version
        # puts it — it lives on the subscription items now, not the
        # subscription — so the first mapping write no longer stores "".
        current_period_end = _helpers_mod._extract_subscription_period_end(subscription)

        # H2: ``metadata.plan_id`` is a client-supplied claim. The plan that
        # gets persisted — and that plan-feature gates later read — must be
        # the one the subscription's actual Stripe price maps to, never the
        # claim. Catalog gaps and multi-plan ambiguity fail closed exactly
        # like an unsettled payment: the mapping write proceeds so lookups
        # and retries stay consistent, but the status written is one the
        # entitlement gate denies, and the operator gets a loud alert.
        price_ids = _helpers_mod._extract_subscription_price_ids(subscription)
        stripe_plan: Optional[str] = None
        stripe_period: Optional[str] = None
        plan_ambiguous = False
        for price_id in price_ids:
            match = _plans_mod._plan_for_stripe_price(price_id)
            if match is None:
                continue
            if stripe_plan is not None and match != (stripe_plan, stripe_period):
                plan_ambiguous = True
                break
            stripe_plan, stripe_period = match
        if price_ids and (plan_ambiguous or stripe_plan is None):
            logger.error(
                "stripe_plan_unverifiable",
                tenant_id=tenant_id,
                subscription_id=subscription_id,
                price_ids=price_ids,
                claimed_plan=plan_id,
                claimed_billing_period=billing_period,
                ambiguous=plan_ambiguous,
            )
            subscription_status = "incomplete"
            plan_id = ""
        elif stripe_plan is not None and stripe_plan != plan_id:
            logger.error(
                "stripe_plan_metadata_mismatch",
                tenant_id=tenant_id,
                subscription_id=subscription_id,
                claimed_plan=plan_id,
                stripe_plan=stripe_plan,
                claimed_billing_period=billing_period,
                stripe_period=stripe_period,
            )
            plan_id = stripe_plan
            billing_period = stripe_period or billing_period

    # #2930: ``checkout.session.completed`` also fires for payments that have
    # not settled. Until the money lands the tenant is entitled to nothing,
    # whatever the subscription object says — ``async_payment_succeeded``
    # (handled in the dispatcher) is what promotes it.
    if subscription_status in _ENTITLING_STATUSES and payment_status not in _SETTLED_PAYMENT_STATUSES:
        logger.warning(
            "checkout_payment_not_settled",
            session_id=session_id,
            subscription_id=subscription_id,
            payment_status=payment_status or "(missing)",
            stripe_status=subscription_status,
        )
        subscription_status = "incomplete"

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
    preserve_status: bool = False,
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
            # #2699 fail closed: corrupt stored state must not become
            # last_seen=0 — that lets a STALE event (e.g. an old `active`)
            # overwrite current subscription status, which the entitlement
            # gate then reads. Refuse the update and alert; Stripe retries,
            # and the operator repairs the corrupt mapping.
            logger.error(
                "stripe_subscription_state_corrupt",
                tenant_id=tenant_id,
                subscription_id=subscription_id,
                last_event_created_raw=str(existing.get("last_event_created"))[:64],
                refused_status=status,
            )
            return
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

    # A one-off (non-subscription) invoice proves a payment happened but
    # says nothing about subscription entitlement, so it records invoice
    # metadata without touching the status the subscription gate reads.
    # Without this, invoicing a per-label InvoiceItem (see
    # ``label_billing.charge_for_label``) would flip a canceled tenant
    # back to ``active`` via ``invoice.paid``, or 402 a paying tenant via
    # ``invoice.payment_failed``.
    updated_fields: dict[str, str] = {
        "subscription_id": subscription_id or existing.get("subscription_id", ""),
        "customer_id": customer_id or existing.get("customer_id", ""),
    }
    if preserve_status:
        logger.info(
            "stripe_subscription_status_preserved_no_subscription",
            tenant_id=tenant_id,
            subscription_id=subscription_id,
            customer_id=customer_id,
            refused_status=status,
        )
    else:
        updated_fields["status"] = status
    existing.update(updated_fields)
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
    trial_end = _helpers_mod._format_period_end(_helpers_mod._coerce_int(subscription.get("trial_end")))

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
            "status": (str(subscription.get("status") or existing.get("status") or "trialing")),
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
            "last_dispute_amount_cents": str(_helpers_mod._coerce_int(dispute.get("amount"))),
            "last_dispute_currency": str(dispute.get("currency", "") or ""),
            "last_dispute_reason": str(dispute.get("reason", "") or ""),
            "last_dispute_status": str(dispute.get("status", "") or ""),
            "last_dispute_opened_at": (
                _helpers_mod._format_period_end(_helpers_mod._coerce_int(dispute.get("created")))
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

    # #2930: delayed payment methods settle after checkout completes. These
    # two events are the only thing that resolves the non-entitling status
    # written above, so the dispatcher must not ignore them.
    if event_type == "checkout.session.async_payment_succeeded":
        await _handle_checkout_completed(data_object, event_created=event_created)
        return

    if event_type == "checkout.session.async_payment_failed":
        _update_subscription_status(
            subscription_id=data_object.get("subscription"),
            customer_id=data_object.get("customer"),
            status="incomplete",
            event_created=event_created,
        )
        return

    if event_type == "invoice.payment_failed":
        _update_subscription_status(
            subscription_id=data_object.get("subscription"),
            customer_id=data_object.get("customer"),
            status="past_due",
            last_invoice_id=str(data_object.get("id", "") or ""),
            last_payment_failure_at=_helpers_mod._format_period_end(
                _helpers_mod._coerce_int(data_object.get("created"))
            ),
            event_created=event_created,
            # One-off invoices carry no subscription; only a subscription
            # invoice may move entitlement state (see _update_subscription_status).
            preserve_status=not data_object.get("subscription"),
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
            preserve_status=not subscription_id,
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
                # #2951: same relocated field on the event's subscription
                # payload. Persist only a value we actually resolved — a
                # missing period end means "unknown", not "cleared", and
                # blanking it here would destroy the renewal date the
                # ``invoice.paid`` handler derived from the invoice.
                event_period_end = _helpers_mod._extract_subscription_period_end(data_object)
                if event_period_end:
                    existing["current_period_end"] = event_period_end
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

    # Fail-closed secret gate owned by the shared webhook template
    # (``shared.webhook_auth``). A missing secret is a 500 with the same
    # message the billing tests pin. Note the one behavior change: a
    # blank (whitespace-only) secret is now also refused here instead of
    # being passed to the Stripe SDK.
    try:
        webhook_secret = _webhook_auth_mod.require_webhook_secret(
            os.getenv("STRIPE_WEBHOOK_SECRET"),
            connector_id="stripe",
        )
    except _webhook_auth_mod.WebhookSecretMissingError as exc:
        raise HTTPException(status_code=500, detail="STRIPE_WEBHOOK_SECRET is not configured") from exc

    # #2929: the rate limiter used to run in the route, BEFORE this point, on
    # a bucket keyed by client IP — which behind a shared reverse proxy is one
    # bucket for Stripe and every anonymous caller alike. Verification gates
    # first now: unverified traffic is charged to its own budget only once it
    # has been shown not to be Stripe, so a junk flood can no longer 429 a
    # genuine delivery and stall billing-state transitions.
    if not stripe_signature:
        _rate_limiting_mod._check_stripe_webhook_rate_limit(request)
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")

    body = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload=body,
            sig_header=stripe_signature,
            secret=webhook_secret,
        )
    except ValueError as exc:
        _rate_limiting_mod._check_stripe_webhook_rate_limit(request)
        raise HTTPException(status_code=400, detail="Invalid webhook payload") from exc
    except stripe.error.SignatureVerificationError as exc:
        logger.warning("stripe_webhook_signature_invalid", error=str(exc))
        _rate_limiting_mod._check_stripe_webhook_rate_limit(request)
        raise HTTPException(status_code=401, detail="Invalid Stripe signature") from exc

    # #2929: only a delivery Stripe actually signed consumes the genuine-
    # traffic budget, and its bucket key comes from the verified envelope —
    # never from a client-supplied header.
    _rate_limiting_mod._check_verified_stripe_webhook_rate_limit(event)

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

    # #2818: the dedup claim above is taken BEFORE the handler runs (it has
    # to be — the gate must close before any side effect). But it was never
    # released when the handler raised, so the failed event stayed "seen"
    # for the full 24h TTL and every Stripe retry short-circuited into the
    # duplicate branch above with 200 {"duplicate": true}. The event was
    # permanently dropped: a failed checkout.session.completed left a paying
    # tenant with no subscription mapping, a failed invoice.paid left them
    # stuck past_due.
    #
    # Releasing the claim ONLY on the failure path keeps duplicate
    # suppression intact for events that actually completed, while letting
    # Stripe's at-least-once retry do its job for the ones that did not.
    try:
        await _handle_stripe_event(event)
    except BaseException:
        _state_mod._release_event_claim(event_id or "")
        logger.warning(
            "stripe_webhook_handler_failed_claim_released",
            event_id=event_id,
            event_type=event_type,
        )
        raise
    logger.info("stripe_webhook_processed", event_type=event_type)
    return {"received": True, "event_type": event_type}
