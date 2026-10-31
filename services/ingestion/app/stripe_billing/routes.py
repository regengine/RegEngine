"""FastAPI router and all endpoint functions."""

from __future__ import annotations

import os
from typing import Any, Optional

import redis
import stripe
import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from shared import funnel_events as _funnel_mod
from shared.database import get_db_session
from shared.tenant_context import set_tenant_guc_if_uuid
from sqlalchemy import text

from ..authz import (
    IngestionPrincipal,
    get_ingestion_principal,
    get_optional_ingestion_principal,
    require_permission,
)
from . import (
    customers as _customers_mod,
    helpers as _helpers_mod,
    plans as _plans_mod,
    rate_limiting as _rate_limiting_mod,
    state as _state_mod,
    usage as _usage_mod,
    usage_reporting as _usage_reporting_mod,
    webhooks as _webhooks_mod,
)
from .helpers import (
    _coerce_int,
    _format_period_end,
    _stripe_get,
)
from .models import (
    BillingPortalRequest,
    BillingPortalResponse,
    CheckoutRequest,
    CheckoutResponse,
    InvoiceListResponse,
    InvoicePdfResponse,
    InvoiceSummary,
    SubscriptionStatus,
    UsageResponse,
)
from .plans import DEFAULT_PORTAL_RETURN_URL, METERED_ADDONS, PLANS

logger = structlog.get_logger("stripe-billing")

router = APIRouter(prefix="/api/v1/billing", tags=["Billing & Subscriptions"])

# ``app.dependency_overrides[_get_db_session]`` in tests must reference the
# exact callable passed to ``Depends()`` below — matches the pattern already
# used by ``canonical_router.py`` / ``webhook_router_v2.py``.
_get_db_session = get_db_session

# List/founding are billed per facility, with the facility count carried as
# the subscription quantity. Cap the self-serve checkout quantity so a typo
# (or a compromised client) cannot open a five-figure monthly subscription;
# product can raise this later.
MAX_CHECKOUT_FACILITY_QUANTITY = 100


def _allow_subscription_read_fallback() -> bool:
    """Allow local/test callers to treat a missing billing state store as empty.

    The settings page only needs a best-effort subscription snapshot. During
    Playwright/local dev runs we intentionally boot without Redis, so returning
    "no plan" is less noisy than surfacing a background 503 while still keeping
    production fail-closed unless this fallback is explicitly enabled.
    """
    raw = os.getenv("ALLOW_BILLING_STATE_READ_FALLBACK", "").strip().lower()
    return raw in {"1", "true", "yes"}


@router.get(
    "/plans",
    summary="List available plans",
    description="Returns all available subscription plans with features and pricing.",
)
async def list_plans() -> dict[str, list[dict[str, Any]]]:
    """List all subscription plans.

    Compatibility contract for the pricing page: the ``list`` plan carries
    ``ga_monthly`` / ``partner_monthly`` so the page can render the approved
    A-2155 amounts without a backend change. Annual fields are null until
    C.Lee approves annual pricing (OPEN) — do not invent annual amounts.
    Claude owns the pricing-page follow-up to consume the new ids/fields.
    """
    list_plan = PLANS["list"]
    compat_amounts = {
        "ga_monthly": list_plan["price_monthly"],
        "partner_monthly": PLANS["founding"]["price_monthly"],
        "ga_annual": None,
        "partner_annual": None,
    }

    plans: list[dict[str, Any]] = []
    for plan in PLANS.values():
        payload = {
            "id": plan["id"],
            "name": plan["name"],
            "price_monthly": plan["price_monthly"],
            "price_annual": plan["price_annual"],
            "features": plan["features"],
            "limits": plan["limits"],
            "product_status": "Beta",
        }
        if plan["id"] == "list":
            payload.update(compat_amounts)
        plans.append(payload)

    # Synthetic compatibility entry for the page's historical ``base`` tier
    # id. It mirrors the list plan's monthly amounts until Claude updates the
    # page. ``standard``/``premium`` are intentionally omitted: there is no
    # approved self-serve Standard/Premium dollar SKU, and null-priced
    # placeholders would be skipped by the page anyway.
    plans.append(
        {
            "id": "base",
            "name": list_plan["name"],
            "price_monthly": list_plan["price_monthly"],
            "price_annual": list_plan["price_annual"],
            "features": list_plan["features"],
            "limits": list_plan["limits"],
            "product_status": "Beta",
            **compat_amounts,
        }
    )

    return {"plans": plans}


@router.post(
    "/checkout",
    response_model=CheckoutResponse,
    dependencies=[Depends(_rate_limiting_mod._check_stripe_checkout_rate_limit)],
    summary="Create Stripe checkout session",
    description=(
        "Creates a Stripe checkout session for the selected plan and returns "
        "a URL for redirecting the customer to Stripe Checkout."
    ),
)
async def create_checkout(
    request: CheckoutRequest,
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    principal: Optional[IngestionPrincipal] = Depends(get_optional_ingestion_principal),
) -> CheckoutResponse:
    """Create a Stripe checkout session.

    #1184 fix: the tenant is derived from the authenticated principal;
    ``X-Tenant-ID`` is only a matching assertion. The client-supplied
    ``request.tenant_id`` is ignored — honoring it would let an attacker bind
    another tenant's billing record to their Stripe customer. Anonymous callers may
    still trigger a new-tenant-at-checkout flow (no principal => no
    ``tenant_id`` placed in metadata, and the webhook will provision a
    fresh tenant when Stripe fires ``checkout.session.completed``).
    """
    _helpers_mod._configure_stripe()

    normalized_plan_id = _plans_mod._normalize_plan_id(request.plan_id)

    # Pilot is a one-time payment product, deliberately absent from the
    # recurring ``PLANS`` catalog. It must be handled BEFORE
    # ``_resolve_price_id`` (which only knows recurring plans), and its
    # checkout is always quantity 1 regardless of facility_count.
    is_pilot = normalized_plan_id == "pilot"
    pilot_variant: Optional[str] = None
    if is_pilot:
        pilot_variant = str(request.pilot_variant or "standard").strip().lower()
        if pilot_variant not in {"standard", "convert_30"}:
            raise HTTPException(
                status_code=400,
                detail="pilot_variant must be 'standard' or 'convert_30'",
            )
        plan_id = "pilot"
        billing_period = "one_time"
        price_id = _plans_mod._resolve_pilot_price_id(pilot_variant)
        fee_cents = (
            _plans_mod.PILOT_FEE_STANDARD_CENTS
            if pilot_variant == "standard"
            else _plans_mod.PILOT_FEE_CONVERT_30_CENTS
        )
        amount = fee_cents // 100
        facility_quantity = 1
        if request.facility_count is not None and request.facility_count != 1:
            # Prefer ignore-with-log over 400: pilot pricing is not
            # per-facility, and a stale frontend may still send its
            # default facility count.
            logger.info(
                "checkout_pilot_ignored_facility_count",
                facility_count=request.facility_count,
                pilot_variant=pilot_variant,
            )
    else:
        billing_period = _plans_mod._normalize_billing_period(request.billing_period)
        plan, price_id, amount = _plans_mod._resolve_price_id(normalized_plan_id, billing_period)
        plan_id = plan["id"]

        # List/founding are billed per facility: the facility count is the
        # subscription quantity. There is no server-side facility-inventory
        # helper in this package yet, so the only supported sources are an
        # explicit ``facility_count`` on the request (validated below) or the
        # default of 1. Never trust a client-supplied tenant inventory for
        # billing quantity.
        facility_quantity = 1
        if plan_id in {"list", "founding"}:
            if request.facility_count is not None:
                facility_quantity = request.facility_count
            if facility_quantity < 1:
                raise HTTPException(status_code=400, detail="facility_count must be at least 1")
            if facility_quantity > MAX_CHECKOUT_FACILITY_QUANTITY:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"facility_count must be at most {MAX_CHECKOUT_FACILITY_QUANTITY}. "
                        "Contact sales@regengine.co for more facilities."
                    ),
                )

    existing_customer_id: Optional[str] = None

    # Resolve tenant ONLY from authenticated context — ignore request body and
    # ignore X-Tenant-ID entirely when no credential was presented.
    # Note: when this function is called directly (outside FastAPI DI, e.g.
    # in unit tests) the `x_tenant_id` / `principal` parameters may still
    # hold their FastAPI param defaults (Header/Depends objects). We coerce
    # them to a string/principal before use.
    safe_x_tenant_id = x_tenant_id if isinstance(x_tenant_id, str) else None
    safe_principal = principal if isinstance(principal, IngestionPrincipal) else None

    authenticated_tenant_id: Optional[str] = None
    if safe_principal is not None:
        authenticated_tenant_id = _helpers_mod._resolve_tenant_context(
            explicit_tenant_id=None,
            x_tenant_id=safe_x_tenant_id,
            principal=safe_principal,
        )

    if request.tenant_id and request.tenant_id != authenticated_tenant_id:
        logger.warning(
            "checkout_ignored_client_tenant_id",
            auth_tenant=authenticated_tenant_id,
            client_tenant=request.tenant_id,
        )

    metadata = {
        "plan_id": plan_id,
        "billing_period": billing_period,
        # Stripe metadata values must be strings. The webhook/PR3 credit path
        # reads this to reconcile the subscription quantity with facilities.
        "facility_quantity": str(facility_quantity),
    }
    if is_pilot:
        # A-2155/A-2159: the webhook needs the purchased pilot flavor to
        # pick the credit amount and (for convert_30) the conversion window.
        metadata["pilot_variant"] = str(pilot_variant)
        if pilot_variant == "convert_30":
            metadata["pilot_convert_window_days"] = str(_plans_mod.PILOT_CONVERT_WINDOW_DAYS)
    if authenticated_tenant_id:
        # Outbound assignment: stamp the authenticated principal's tenant_id
        # onto the Stripe checkout-session metadata for webhook cross-check
        # later. This is a write into the metadata we'll send to Stripe,
        # NOT a read of a client-supplied tenant.
        metadata["tenant_id"] = authenticated_tenant_id  # nosemgrep: tenant-id-from-request-body
    if request.tenant_name:
        metadata["tenant_name"] = request.tenant_name
    if request.customer_email:
        metadata["customer_email"] = request.customer_email
    # Attach issuing API-key id for webhook cross-check / audit trail.
    principal_key_id = getattr(safe_principal, "key_id", None) if safe_principal else None
    if principal_key_id:
        metadata["issued_by_key_id"] = str(principal_key_id)

    if authenticated_tenant_id:
        try:
            existing_customer_id = _customers_mod._get_existing_customer_id(authenticated_tenant_id)
        except redis.RedisError as exc:
            logger.warning(
                "checkout_customer_lookup_failed",
                tenant_id=authenticated_tenant_id,
                error=str(exc),
            )

    # #1186: validate redirect URLs against the allowlist BEFORE handing
    # them to Stripe. An unvalidated ``success_url`` lets an attacker
    # chain Stripe-branded trust into an arbitrary-host redirect.
    safe_success_url = _helpers_mod._validate_redirect_url(request.success_url, field="success_url")
    safe_cancel_url = _helpers_mod._validate_redirect_url(request.cancel_url, field="cancel_url")

    checkout_kwargs: dict[str, Any] = {
        "mode": "payment" if is_pilot else "subscription",
        "line_items": [{"price": price_id, "quantity": facility_quantity}],
        "success_url": safe_success_url,
        "cancel_url": safe_cancel_url,
        "allow_promotion_codes": True,
        "metadata": metadata,
    }
    if not is_pilot:
        # Pilot is a one-time payment; there is no subscription to attach
        # metadata to. Do NOT set subscription_data for pilot.
        checkout_kwargs["subscription_data"] = {"metadata": metadata}
    if existing_customer_id:
        checkout_kwargs["customer"] = existing_customer_id
    elif request.customer_email:
        checkout_kwargs["customer_email"] = request.customer_email

    try:
        session = stripe.checkout.Session.create(**checkout_kwargs)
    except stripe.error.StripeError as exc:
        logger.error("checkout_create_failed", error=str(exc), plan=plan_id)
        raise HTTPException(
            status_code=502, detail=f"Stripe checkout creation failed: {exc.user_message or str(exc)}"
        ) from exc

    if authenticated_tenant_id:
        try:
            _customers_mod._record_checkout_session_hint(
                tenant_id=authenticated_tenant_id,
                session_id=str(session.id),
                plan_id=plan_id,
                billing_period=billing_period,
                customer_email=request.customer_email,
                customer_id=existing_customer_id,
            )
        except redis.RedisError as exc:
            # Don't block checkout redirect if Redis is briefly unavailable.
            logger.warning(
                "checkout_hint_store_failed",
                tenant_id=authenticated_tenant_id,
                error=str(exc),
            )

    _funnel_mod.emit_funnel_event(
        tenant_id=authenticated_tenant_id,
        event_name="checkout_started",
        metadata={
            "plan_id": plan_id,
            "billing_period": billing_period,
            "session_id": str(session.id),
        },
    )

    logger.info(
        "checkout_created",
        tenant_id=authenticated_tenant_id,
        plan=plan_id,
        amount=amount,
        facility_quantity=facility_quantity,
        billing_period=billing_period,
        pilot_variant=pilot_variant,
        session_id=session.id,
    )

    return CheckoutResponse(
        checkout_url=session.url,
        session_id=session.id,
        plan=plan_id,
        billing_period=billing_period,
        amount=amount,
        facility_quantity=facility_quantity,
    )


@router.get(
    "/subscription/{tenant_id}",
    response_model=SubscriptionStatus,
    summary="Get subscription status",
)
async def get_subscription(
    tenant_id: str,
    _: None = None,
    principal: IngestionPrincipal = Depends(require_permission("billing.subscription.read")),
) -> SubscriptionStatus:
    """Get current subscription status for a tenant."""
    safe_principal = principal if isinstance(principal, IngestionPrincipal) else None
    resolved_tenant_id = _helpers_mod._resolve_tenant_context(tenant_id, None, safe_principal)

    try:
        mapping = _state_mod._get_subscription_mapping(resolved_tenant_id)
    except redis.RedisError as exc:
        if _allow_subscription_read_fallback():
            logger.info(
                "subscription_mapping_read_fallback_empty",
                tenant_id=resolved_tenant_id,
                error=str(exc),
            )
            mapping = {}
        else:
            logger.error("subscription_mapping_read_failed", tenant_id=resolved_tenant_id, error=str(exc))
            raise HTTPException(status_code=503, detail="Billing state store unavailable") from exc

    if not mapping:
        return SubscriptionStatus(
            tenant_id=resolved_tenant_id,
            plan="none",
            status="none",
            current_period_end=None,
            events_used=0,
            events_limit=0,
            facilities_used=0,
            facilities_limit=0,
        )

    plan_id = _plans_mod._normalize_plan_id(mapping.get("plan_id", "growth"))
    status = mapping.get("status", "none")
    billing_period = mapping.get("billing_period") or None
    current_period_end = mapping.get("current_period_end") or None
    subscription_id = mapping.get("subscription_id")

    if subscription_id and status in _state_mod._TERMINAL_STATUSES:
        # #2953: ``customer_deleted`` is terminal and sticky. Refreshing from
        # Stripe here would overwrite the audit marker with the subscription's
        # current status (Stripe keeps canceled subscriptions retrievable), and
        # the write-back would re-create the very lookup keys the
        # ``customer.deleted`` handler deleted. A GET must not reverse a
        # security cleanup.
        logger.info(
            "subscription_refresh_skipped_terminal_status",
            tenant_id=resolved_tenant_id,
            subscription_id=subscription_id,
            status=status,
        )
    elif subscription_id:
        try:
            _helpers_mod._configure_stripe()
            subscription = stripe.Subscription.retrieve(subscription_id)
            status = subscription.get("status", status)
            # #2951: ``current_period_end`` moved onto the subscription items
            # in the API version the pinned SDK sends, so the old top-level
            # read returned None for every live subscription and the write-back
            # stored "" over the renewal date the ``invoice.paid`` handler
            # derived from the invoice. Read both shapes, and write only a
            # value we actually resolved — a GET must never destroy persisted
            # billing state (the webhook path already refuses that write, see
            # ``_update_subscription_status``).
            refreshed_period_end = _helpers_mod._extract_subscription_period_end(subscription)
            if refreshed_period_end:
                current_period_end = refreshed_period_end

            mapping["status"] = status
            if refreshed_period_end:
                mapping["current_period_end"] = refreshed_period_end
            _state_mod._store_subscription_mapping(resolved_tenant_id, mapping)
        except HTTPException as exc:
            if getattr(exc, "status_code", None) != 500:
                raise
            logger.warning(
                "subscription_refresh_skipped_stripe_unconfigured",
                tenant_id=resolved_tenant_id,
                subscription_id=subscription_id,
            )
        except stripe.error.StripeError as exc:  # pragma: no cover - network/API errors
            logger.warning("subscription_retrieve_failed", tenant_id=resolved_tenant_id, error=str(exc))

    limits = PLANS.get(plan_id, {}).get("limits", {})

    # Per-facility plans store the billed facility count as the subscription
    # quantity. Prefer it over the plan's static limit (which is -1 /
    # "quantity-driven" for list and founding).
    facility_quantity = _coerce_int(mapping.get("facility_quantity"), 0)
    facilities_limit = facility_quantity if facility_quantity > 0 else limits.get("facilities", 0)

    return SubscriptionStatus(
        tenant_id=resolved_tenant_id,
        plan=plan_id,
        status=status,
        billing_period=billing_period,
        current_period_end=current_period_end,
        events_used=0,
        events_limit=limits.get("events_per_month", 0),
        facilities_used=0,
        facilities_limit=facilities_limit,
    )


@router.post(
    "/webhooks",
    summary="Stripe webhook handler",
    description="Handles Stripe webhook events (checkout.session.completed, invoice.paid, etc.)",
)
async def stripe_webhooks(
    request: Request,
    stripe_signature: Optional[str] = Header(default=None, alias="Stripe-Signature"),
) -> dict[str, Any]:
    """Primary Stripe webhook endpoint.

    #2929: the rate limiter used to run here, ahead of signature
    verification, on a route with no auth dependency — so unsigned junk and
    genuine Stripe deliveries shared one per-proxy-peer bucket and an
    anonymous caller could 429 every billing webhook. The limiter now lives
    inside ``_process_stripe_webhook``, on the far side of
    ``stripe.Webhook.construct_event``, with separate budgets for verified
    and unverified traffic.
    """
    return await _webhooks_mod._process_stripe_webhook(request, stripe_signature)


@router.post(
    "/webhook/stripe",
    summary="Stripe webhook handler",
    description="Handles Stripe webhook events (checkout.session.completed, invoice.paid, etc.)",
    include_in_schema=False,
)
async def stripe_webhook_legacy(
    request: Request,
    stripe_signature: Optional[str] = Header(default=None, alias="Stripe-Signature"),
) -> dict[str, Any]:
    """Legacy Stripe webhook path retained for backward compatibility.

    #2929: same reordering as the primary route — verification gates first.
    """
    return await _webhooks_mod._process_stripe_webhook(request, stripe_signature)


@router.post(
    "/portal",
    response_model=BillingPortalResponse,
    summary="Create Stripe customer portal session",
    description=(
        "Creates a tenant-scoped Stripe customer portal session and returns a redirect URL. "
        "If the tenant has no linked Stripe customer yet, creates one first."
    ),
)
async def create_portal_session_for_tenant(
    request: BillingPortalRequest,
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    principal: IngestionPrincipal = Depends(get_ingestion_principal),
) -> BillingPortalResponse:
    """Create Stripe customer portal session for self-service billing changes."""
    _helpers_mod._configure_stripe()

    tenant_id = _helpers_mod._resolve_tenant_context(request.tenant_id, x_tenant_id, principal)

    # #1186: validate the client-supplied return_url against the allowlist.
    # When the client omits return_url, fall through to the server-configured
    # default (still validated so misconfigured env vars fail loudly instead
    # of shipping a stray open redirect).
    if request.return_url:
        return_url = _helpers_mod._validate_redirect_url(request.return_url, field="return_url")
    else:
        server_default = os.getenv("STRIPE_PORTAL_RETURN_URL", DEFAULT_PORTAL_RETURN_URL)
        return_url = _helpers_mod._validate_redirect_url(server_default, field="return_url")

    try:
        customer_id = _customers_mod._ensure_customer_mapping(
            tenant_id=tenant_id,
            tenant_name=request.tenant_name,
            customer_email=request.customer_email,
        )
    except redis.RedisError as exc:
        logger.error("portal_customer_lookup_failed", tenant_id=tenant_id, error=str(exc))
        raise HTTPException(status_code=503, detail="Billing state store unavailable") from exc

    try:
        session = _customers_mod._create_portal_session(customer_id=customer_id, return_url=return_url)
    except stripe.error.StripeError as exc:
        logger.error("portal_session_create_failed", tenant_id=tenant_id, error=str(exc))
        raise HTTPException(
            status_code=502,
            detail=f"Stripe portal creation failed: {exc.user_message or str(exc)}",
        ) from exc

    portal_url = str(_stripe_get(session, "url", "") or "")
    if not portal_url:
        raise HTTPException(status_code=502, detail="Stripe portal creation failed: missing portal URL")

    return BillingPortalResponse(
        portal_url=portal_url,
        tenant_id=tenant_id,
        customer_id=customer_id,
    )


@router.get(
    "/invoices",
    response_model=InvoiceListResponse,
    summary="List tenant Stripe invoices",
    description=(
        "Lists Stripe invoices for the tenant-linked customer with cursor pagination "
        "using Stripe's starting_after parameter."
    ),
)
async def list_invoices(
    tenant_id: Optional[str] = Query(default=None, description="Optional tenant assertion; must match the credential"),
    limit: int = Query(default=25, ge=1, le=100),
    starting_after: Optional[str] = Query(default=None, description="Stripe pagination cursor"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    principal: IngestionPrincipal = Depends(require_permission("billing.invoices.read")),
) -> InvoiceListResponse:
    """List Stripe invoices for a tenant's customer record."""
    _helpers_mod._configure_stripe()
    _helpers_mod._enforce_admin_or_operator(principal, "billing.invoices.read")

    resolved_tenant_id = _helpers_mod._resolve_tenant_context(tenant_id, x_tenant_id, principal)
    try:
        mapping = _state_mod._get_subscription_mapping(resolved_tenant_id)
    except redis.RedisError as exc:
        logger.error("invoice_mapping_read_failed", tenant_id=resolved_tenant_id, error=str(exc))
        raise HTTPException(status_code=503, detail="Billing state store unavailable") from exc

    customer_id = str(mapping.get("customer_id") or "").strip()
    if not customer_id:
        raise HTTPException(status_code=404, detail="No Stripe customer is linked to this tenant")

    list_kwargs: dict[str, Any] = {
        "customer": customer_id,
        "limit": limit,
    }
    if starting_after:
        list_kwargs["starting_after"] = starting_after

    try:
        page = stripe.Invoice.list(**list_kwargs)
    except stripe.error.StripeError as exc:
        logger.error("invoice_list_failed", tenant_id=resolved_tenant_id, customer_id=customer_id, error=str(exc))
        raise HTTPException(
            status_code=502,
            detail=f"Stripe invoice list failed: {exc.user_message or str(exc)}",
        ) from exc

    invoices: list[InvoiceSummary] = []
    for raw_invoice in list(_stripe_get(page, "data", []) or []):
        invoice_id = str(_stripe_get(raw_invoice, "id", "") or "")
        if not invoice_id:
            continue

        invoices.append(
            InvoiceSummary(
                invoice_id=invoice_id,
                amount_due=_coerce_int(_stripe_get(raw_invoice, "amount_due")),
                amount_paid=_coerce_int(_stripe_get(raw_invoice, "amount_paid")),
                currency=str(_stripe_get(raw_invoice, "currency", "usd") or "usd"),
                status=_stripe_get(raw_invoice, "status"),
                created_at=_format_period_end(_coerce_int(_stripe_get(raw_invoice, "created"))),
                pdf_url=_stripe_get(raw_invoice, "invoice_pdf"),
                hosted_invoice_url=_stripe_get(raw_invoice, "hosted_invoice_url"),
            )
        )

    has_more = bool(_stripe_get(page, "has_more", False))
    next_cursor = invoices[-1].invoice_id if has_more and invoices else None

    return InvoiceListResponse(
        tenant_id=resolved_tenant_id,
        customer_id=customer_id,
        invoices=invoices,
        has_more=has_more,
        next_cursor=next_cursor,
    )


@router.get(
    "/invoices/{invoice_id}/pdf",
    response_model=InvoicePdfResponse,
    summary="Get Stripe invoice PDF URL",
    description=("Fetches a Stripe invoice by ID and returns the hosted invoice PDF URL for the tenant."),
)
async def get_invoice_pdf(
    invoice_id: str,
    tenant_id: Optional[str] = Query(default=None, description="Optional tenant assertion; must match the credential"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    principal: IngestionPrincipal = Depends(require_permission("billing.invoices.read")),
) -> InvoicePdfResponse:
    """Return Stripe-hosted invoice PDF URL for an authorized tenant."""
    _helpers_mod._configure_stripe()
    _helpers_mod._enforce_admin_or_operator(principal, "billing.invoices.read")

    resolved_tenant_id = _helpers_mod._resolve_tenant_context(tenant_id, x_tenant_id, principal)
    try:
        mapping = _state_mod._get_subscription_mapping(resolved_tenant_id)
    except redis.RedisError as exc:
        logger.error("invoice_mapping_read_failed", tenant_id=resolved_tenant_id, error=str(exc))
        raise HTTPException(status_code=503, detail="Billing state store unavailable") from exc

    customer_id = str(mapping.get("customer_id") or "").strip()
    if not customer_id:
        raise HTTPException(status_code=404, detail="No Stripe customer is linked to this tenant")

    try:
        invoice = stripe.Invoice.retrieve(invoice_id)
    except stripe.error.InvalidRequestError as exc:
        raise HTTPException(status_code=404, detail=f"Invoice '{invoice_id}' was not found") from exc
    except stripe.error.StripeError as exc:
        logger.error("invoice_retrieve_failed", invoice_id=invoice_id, tenant_id=resolved_tenant_id, error=str(exc))
        raise HTTPException(
            status_code=502,
            detail=f"Stripe invoice retrieval failed: {exc.user_message or str(exc)}",
        ) from exc

    # Fail closed when Stripe returns no customer on the invoice: without
    # it the tenant ownership check below cannot prove this invoice
    # belongs to the caller, so it must 404 rather than serve the PDF.
    invoice_customer_id = str(_stripe_get(invoice, "customer", "") or "").strip()
    if not invoice_customer_id or invoice_customer_id != customer_id:
        raise HTTPException(status_code=404, detail="Invoice not found for tenant")

    pdf_url = str(_stripe_get(invoice, "invoice_pdf", "") or "").strip()
    if not pdf_url:
        raise HTTPException(status_code=404, detail=f"Invoice '{invoice_id}' does not have a PDF URL")

    return InvoicePdfResponse(
        tenant_id=resolved_tenant_id,
        invoice_id=str(_stripe_get(invoice, "id", invoice_id) or invoice_id),
        status=_stripe_get(invoice, "status"),
        created_at=_format_period_end(_coerce_int(_stripe_get(invoice, "created"))),
        pdf_url=pdf_url,
        hosted_invoice_url=_stripe_get(invoice, "hosted_invoice_url"),
    )


@router.post(
    "/portal/{tenant_id}",
    summary="Create Stripe customer portal session",
    description="Legacy endpoint. Creates a Stripe customer portal session for managing subscriptions.",
)
async def create_portal_session_legacy(
    tenant_id: str,
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    principal: IngestionPrincipal = Depends(get_ingestion_principal),
) -> BillingPortalResponse:
    """Create Stripe customer portal session for self-service billing management.

    RE-SEC-INGEST-001: previously this legacy route accepted ``tenant_id`` from
    the URL while only verifying that *some* API key was valid (the principal
    was discarded via ``_: None = Depends(_verify_api_key)``). Any holder of any
    valid API key could mint a Stripe customer-portal session for any tenant —
    a cross-tenant IDOR over billing.

    The route now resolves the authenticated principal's tenant via
    ``_resolve_tenant_context`` (matching the non-legacy ``/portal`` route) and
    verifies the URL ``tenant_id`` matches. On mismatch we return 404 to avoid
    a tenant-existence oracle.
    """
    safe_principal = principal if isinstance(principal, IngestionPrincipal) else None
    safe_x_tenant_id = x_tenant_id if isinstance(x_tenant_id, str) else None

    auth_tenant_id = _helpers_mod._resolve_tenant_context(None, safe_x_tenant_id, safe_principal)
    if tenant_id != auth_tenant_id:
        logger.warning(
            "portal_legacy_tenant_mismatch",
            url_tenant=tenant_id,
            auth_tenant=auth_tenant_id,
            key_id=getattr(safe_principal, "key_id", None) if safe_principal else None,
        )
        raise HTTPException(status_code=404, detail="Not found")

    _helpers_mod._configure_stripe()

    # #1186: validate the server-configured return_url. This endpoint
    # doesn't accept a client override, but the env-var value is still
    # run through the allowlist so a misconfigured STRIPE_PORTAL_RETURN_URL
    # fails at request time rather than silently redirecting.
    server_default = os.getenv("STRIPE_PORTAL_RETURN_URL", DEFAULT_PORTAL_RETURN_URL)
    return_url = _helpers_mod._validate_redirect_url(server_default, field="return_url")

    try:
        customer_id = _customers_mod._ensure_customer_mapping(
            tenant_id=tenant_id,
            tenant_name=None,
            customer_email=None,
        )
    except redis.RedisError as exc:
        logger.error("portal_customer_lookup_failed", tenant_id=tenant_id, error=str(exc))
        raise HTTPException(status_code=503, detail="Billing state store unavailable") from exc

    try:
        session = _customers_mod._create_portal_session(customer_id=customer_id, return_url=return_url)
    except stripe.error.StripeError as exc:
        logger.error("portal_session_create_failed", tenant_id=tenant_id, error=str(exc))
        raise HTTPException(
            status_code=502, detail=f"Stripe portal creation failed: {exc.user_message or str(exc)}"
        ) from exc

    portal_url = str(_stripe_get(session, "url", "") or "")
    if not portal_url:
        raise HTTPException(status_code=502, detail="Stripe portal creation failed: missing portal URL")

    return BillingPortalResponse(
        portal_url=portal_url,
        tenant_id=tenant_id,
        customer_id=customer_id,
    )


# ── Per-label metered billing (DESIGN_metering-billing.md §6) ──────────────
#
# Usage itself is counted unconditionally for every tenant inside
# ``CanonicalEventStore.persist_event`` / ``persist_events_batch``
# (``services/shared/canonical_persistence/writer.py``) — these routes only
# read that accumulated state and manage whether it is ever reported to
# Stripe.


@router.get(
    "/usage",
    response_model=UsageResponse,
    summary="Get current-period label usage",
    description=(
        "Returns the tenant's current-period per-label metered usage (accepted "
        "TraceabilityEvent count), plus the total unbilled unit count across "
        "ALL billing periods (current and past — a backfilled event can land "
        "in a past period). Populated for every tenant regardless of "
        "metered-billing opt-in status."
    ),
)
async def get_usage(
    tenant_id: Optional[str] = Query(default=None, description="Optional tenant assertion; must match the credential"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    principal: IngestionPrincipal = Depends(require_permission("billing.usage.read")),
    db_session=Depends(get_db_session),
) -> UsageResponse:
    """Return current-period per-label usage for the authenticated tenant."""
    if db_session is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    resolved_tenant_id = _helpers_mod._resolve_tenant_context(tenant_id, x_tenant_id, principal)
    set_tenant_guc_if_uuid(db_session, resolved_tenant_id)  # RLS backstop (UUID tenants only)

    period_start, period_end = _usage_mod._current_billing_period()
    row = db_session.execute(
        text(
            """
            SELECT unit_count
            FROM billing.tenant_usage_counters
            WHERE tenant_id = :tenant_id AND billing_period_start = :period_start
            """
        ),
        {"tenant_id": resolved_tenant_id, "period_start": period_start},
    ).fetchone()
    unit_count = int(row[0]) if row else 0

    # Security-review fix: surface usage sitting in ANY period (not just the
    # current one) that hasn't yet been reported to Stripe. A backfilled or
    # deliberately backdated event (see ``increment_usage_for_event``'s
    # handling of ``event_timestamp``) increments a *past* period's counter
    # row, which the query above never sees — without this, that usage was
    # invisible here even though it's real, accepted, billable usage.
    unbilled_row = db_session.execute(
        text(
            """
            SELECT COALESCE(SUM(unit_count - last_reported_count), 0)
            FROM billing.tenant_usage_counters
            WHERE tenant_id = :tenant_id AND unit_count > last_reported_count
            """
        ),
        {"tenant_id": resolved_tenant_id},
    ).fetchone()
    unbilled_unit_count = int(unbilled_row[0]) if unbilled_row and unbilled_row[0] is not None else 0

    try:
        mapping = _state_mod._get_subscription_mapping(resolved_tenant_id)
    except redis.RedisError as exc:
        if _allow_subscription_read_fallback():
            logger.info(
                "usage_subscription_mapping_read_fallback_empty",
                tenant_id=resolved_tenant_id,
                error=str(exc),
            )
            mapping = {}
        else:
            logger.error("usage_subscription_mapping_read_failed", tenant_id=resolved_tenant_id, error=str(exc))
            raise HTTPException(status_code=503, detail="Billing state store unavailable") from exc

    plan_id = _plans_mod._normalize_plan_id(mapping.get("plan_id", "growth")) if mapping else "none"
    metered_billing_enabled = mapping.get("metered_billing_enabled") == "true"

    return UsageResponse(
        tenant_id=resolved_tenant_id,
        billing_period_start=period_start.isoformat(),
        billing_period_end=period_end.isoformat(),
        unit_count=unit_count,
        unbilled_unit_count=unbilled_unit_count,
        metered_billing_enabled=metered_billing_enabled,
        plan=plan_id,
    )


@router.post(
    "/usage/report",
    summary="Report current-period usage to Stripe",
    description=(
        "Pushes this tenant's un-reported current-period label usage to Stripe's "
        "Billing Meters API. No-ops if the tenant is not opted into metered "
        "billing, has no linked Stripe customer, or has nothing new to report. "
        "Safe to call repeatedly."
    ),
)
async def report_usage(
    tenant_id: Optional[str] = Query(default=None, description="Optional tenant assertion; must match the credential"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    principal: IngestionPrincipal = Depends(require_permission("billing.usage.report")),
    db_session=Depends(get_db_session),
) -> dict[str, Any]:
    """Trigger an on-demand usage report to Stripe for the tenant's current period."""
    if db_session is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    resolved_tenant_id = _helpers_mod._resolve_tenant_context(tenant_id, x_tenant_id, principal)
    _helpers_mod._configure_stripe()
    set_tenant_guc_if_uuid(db_session, resolved_tenant_id)  # RLS backstop (UUID tenants only)

    try:
        result = _usage_reporting_mod.report_tenant_usage_to_stripe(db_session, resolved_tenant_id)
    except stripe.error.StripeError as exc:
        logger.error("usage_report_failed", tenant_id=resolved_tenant_id, error=str(exc))
        raise HTTPException(
            status_code=502,
            detail=f"Stripe usage report failed: {exc.user_message or str(exc)}",
        ) from exc

    if result is None:
        return {
            "tenant_id": resolved_tenant_id,
            "reported": False,
            "detail": "No new usage to report, or tenant is not opted into metered billing.",
        }

    return {"tenant_id": resolved_tenant_id, "reported": True, **result}


@router.post(
    "/usage/opt-in",
    summary="Opt a tenant into per-label metered billing",
    description=(
        "Attaches the metered label-events Price as a second subscription item "
        "alongside the tenant's existing flat-tier subscription. The tenant must "
        "already have an active flat-tier subscription — metering is an add-on, "
        "not a standalone plan."
    ),
)
async def opt_in_metered_usage(
    tenant_id: Optional[str] = Query(default=None, description="Optional tenant assertion; must match the credential"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    principal: IngestionPrincipal = Depends(require_permission("billing.usage.manage")),
) -> dict[str, Any]:
    """Attach the metered label-events add-on to the tenant's subscription."""
    _helpers_mod._enforce_admin_or_operator(principal, "billing.usage.manage")
    _helpers_mod._configure_stripe()

    resolved_tenant_id = _helpers_mod._resolve_tenant_context(tenant_id, x_tenant_id, principal)

    try:
        mapping = _state_mod._get_subscription_mapping(resolved_tenant_id)
    except redis.RedisError as exc:
        logger.error("usage_opt_in_mapping_read_failed", tenant_id=resolved_tenant_id, error=str(exc))
        raise HTTPException(status_code=503, detail="Billing state store unavailable") from exc

    # Idempotency guard: a repeat call must not attach a second metered
    # subscription item. The first item is still live on Stripe, so
    # creating another one and overwriting the stored id would orphan it
    # (still metering, still billing) and double-bill the tenant.
    existing_item_id = str(mapping.get("metered_subscription_item_id") or "").strip()
    if mapping.get("metered_billing_enabled") == "true" and existing_item_id:
        logger.info(
            "usage_opt_in_already_enabled",
            tenant_id=resolved_tenant_id,
            subscription_item_id=existing_item_id,
        )
        return {
            "tenant_id": resolved_tenant_id,
            "metered_billing_enabled": True,
            "subscription_item_id": existing_item_id,
        }

    subscription_id = str(mapping.get("subscription_id") or "").strip()
    if not subscription_id:
        raise HTTPException(
            status_code=400,
            detail="Tenant has no active flat-tier subscription; metered billing is an add-on, not a standalone plan.",
        )

    addon = METERED_ADDONS["label_events"]
    price_id = os.getenv(addon["stripe_price_env"], "").strip()
    if not price_id:
        raise HTTPException(status_code=500, detail=f"{addon['stripe_price_env']} is not configured")

    try:
        item = stripe.SubscriptionItem.create(subscription=subscription_id, price=price_id)
    except stripe.error.StripeError as exc:
        logger.error("usage_opt_in_subscription_item_failed", tenant_id=resolved_tenant_id, error=str(exc))
        raise HTTPException(
            status_code=502,
            detail=f"Stripe metered add-on attach failed: {exc.user_message or str(exc)}",
        ) from exc

    _state_mod._store_subscription_mapping(
        resolved_tenant_id,
        {
            "metered_billing_enabled": "true",
            "metered_subscription_item_id": str(_stripe_get(item, "id", "") or ""),
        },
    )

    logger.info(
        "usage_opt_in_enabled",
        tenant_id=resolved_tenant_id,
        subscription_id=subscription_id,
        subscription_item_id=_stripe_get(item, "id", ""),
    )

    return {
        "tenant_id": resolved_tenant_id,
        "metered_billing_enabled": True,
        "subscription_item_id": _stripe_get(item, "id", ""),
    }


@router.delete(
    "/usage/opt-in",
    summary="Opt a tenant out of per-label metered billing",
    description=(
        "Removes the metered label-events subscription item and clears the "
        "tenant's opt-in flag. Idempotent: no-ops if the tenant was not opted in."
    ),
)
async def opt_out_metered_usage(
    tenant_id: Optional[str] = Query(default=None, description="Optional tenant assertion; must match the credential"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    principal: IngestionPrincipal = Depends(require_permission("billing.usage.manage")),
) -> dict[str, Any]:
    """Detach the metered label-events add-on from the tenant's subscription."""
    _helpers_mod._enforce_admin_or_operator(principal, "billing.usage.manage")
    _helpers_mod._configure_stripe()

    resolved_tenant_id = _helpers_mod._resolve_tenant_context(tenant_id, x_tenant_id, principal)

    try:
        mapping = _state_mod._get_subscription_mapping(resolved_tenant_id)
    except redis.RedisError as exc:
        logger.error("usage_opt_out_mapping_read_failed", tenant_id=resolved_tenant_id, error=str(exc))
        raise HTTPException(status_code=503, detail="Billing state store unavailable") from exc

    subscription_item_id = str(mapping.get("metered_subscription_item_id") or "").strip()
    if subscription_item_id:
        try:
            stripe.SubscriptionItem.delete(subscription_item_id)
        except stripe.error.InvalidRequestError as exc:
            # Already gone on Stripe's side (e.g. the subscription itself was
            # canceled) — treat as already-opted-out rather than failing the
            # local flag flip.
            logger.info(
                "usage_opt_out_subscription_item_missing",
                tenant_id=resolved_tenant_id,
                subscription_item_id=subscription_item_id,
                error=str(exc),
            )
        except stripe.error.StripeError as exc:
            logger.error(
                "usage_opt_out_subscription_item_failed",
                tenant_id=resolved_tenant_id,
                subscription_item_id=subscription_item_id,
                error=str(exc),
            )
            raise HTTPException(
                status_code=502,
                detail=f"Stripe metered add-on removal failed: {exc.user_message or str(exc)}",
            ) from exc

    _state_mod._store_subscription_mapping(
        resolved_tenant_id,
        {
            "metered_billing_enabled": "false",
            "metered_subscription_item_id": "",
        },
    )

    logger.info("usage_opt_in_disabled", tenant_id=resolved_tenant_id)

    return {"tenant_id": resolved_tenant_id, "metered_billing_enabled": False}
