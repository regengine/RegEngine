"""FastAPI router and all endpoint functions."""

from __future__ import annotations

import os
from typing import Any, Optional

import redis
import stripe
import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from app.authz import IngestionPrincipal, get_ingestion_principal, require_permission
from app.webhook_compat import _verify_api_key
from shared import funnel_events as _funnel_mod

from . import customers as _customers_mod
from . import rate_limiting as _rate_limiting_mod
from . import helpers as _helpers_mod
from . import plans as _plans_mod
from . import state as _state_mod
from . import webhooks as _webhooks_mod
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
)
from .plans import DEFAULT_PORTAL_RETURN_URL, PLANS

logger = structlog.get_logger("stripe-billing")

router = APIRouter(prefix="/api/v1/billing", tags=["Billing & Subscriptions"])


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
async def create_checkout(
    request: CheckoutRequest,
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    principal: Optional[IngestionPrincipal] = Depends(get_ingestion_principal),
) -> CheckoutResponse:
    """Create a Stripe checkout session.

    #1184 fix: the tenant is derived from the authenticated principal /
    ``X-Tenant-ID`` header. The client-supplied ``request.tenant_id`` is
    ignored — honoring it would let an attacker bind another tenant's
    billing record to their Stripe customer. Unauthenticated callers may
    still trigger a new-tenant-at-checkout flow (no principal => no
    ``tenant_id`` placed in metadata, and the webhook will provision a
    fresh tenant when Stripe fires ``checkout.session.completed``).
    """
    _helpers_mod._configure_stripe()

    billing_period = _plans_mod._normalize_billing_period(request.billing_period)
    plan, price_id, amount = _plans_mod._resolve_price_id(request.plan_id, billing_period)
    existing_customer_id: Optional[str] = None

    # Resolve tenant ONLY from authenticated context — ignore request body.
    # Note: when this function is called directly (outside FastAPI DI, e.g.
    # in unit tests) the `x_tenant_id` / `principal` parameters may still
    # hold their FastAPI param defaults (Header/Depends objects). We coerce
    # them to a string/principal before use.
    safe_x_tenant_id = x_tenant_id if isinstance(x_tenant_id, str) else None
    safe_principal = principal if isinstance(principal, IngestionPrincipal) else None

    authenticated_tenant_id: Optional[str] = None
    try:
        authenticated_tenant_id = _helpers_mod._resolve_tenant_context(
            explicit_tenant_id=None,
            x_tenant_id=safe_x_tenant_id,
            principal=safe_principal,
        )
    except HTTPException:
        # Unauthenticated checkout creation (self-serve signup flow): the
        # webhook will call the admin service to provision a fresh tenant
        # after payment. We therefore allow the session to proceed without
        # binding to an existing tenant.
        authenticated_tenant_id = None

    if request.tenant_id and request.tenant_id != authenticated_tenant_id:
        logger.warning(
            "checkout_ignored_client_tenant_id",
            auth_tenant=authenticated_tenant_id,
            client_tenant=request.tenant_id,
        )

    metadata = {
        "plan_id": plan["id"],
        "billing_period": billing_period,
    }
    if authenticated_tenant_id:
        metadata["tenant_id"] = authenticated_tenant_id
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
    safe_success_url = _helpers_mod._validate_redirect_url(
        request.success_url, field="success_url"
    )
    safe_cancel_url = _helpers_mod._validate_redirect_url(
        request.cancel_url, field="cancel_url"
    )

    checkout_kwargs: dict[str, Any] = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": safe_success_url,
        "cancel_url": safe_cancel_url,
        "allow_promotion_codes": True,
        "metadata": metadata,
        "subscription_data": {"metadata": metadata},
    }
    if existing_customer_id:
        checkout_kwargs["customer"] = existing_customer_id
    elif request.customer_email:
        checkout_kwargs["customer_email"] = request.customer_email

    try:
        session = stripe.checkout.Session.create(**checkout_kwargs)
    except stripe.error.StripeError as exc:
        logger.error("checkout_create_failed", error=str(exc), plan=plan["id"])
        raise HTTPException(status_code=502, detail=f"Stripe checkout creation failed: {exc.user_message or str(exc)}") from exc

    if authenticated_tenant_id:
        try:
            _customers_mod._record_checkout_session_hint(
                tenant_id=authenticated_tenant_id,
                session_id=str(session.id),
                plan_id=plan["id"],
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
            "plan_id": plan["id"],
            "billing_period": billing_period,
            "session_id": str(session.id),
        },
    )

    logger.info(
        "checkout_created",
        tenant_id=authenticated_tenant_id,
        plan=plan["id"],
        amount=amount,
        billing_period=billing_period,
        session_id=session.id,
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
    _: None = None,
    principal: IngestionPrincipal = Depends(get_ingestion_principal),
) -> SubscriptionStatus:
    """Get current subscription status for a tenant."""
    _helpers_mod._configure_stripe()
    safe_principal = principal if isinstance(principal, IngestionPrincipal) else None
    resolved_tenant_id = _helpers_mod._resolve_tenant_context(tenant_id, None, safe_principal)

    try:
        mapping = _state_mod._get_subscription_mapping(resolved_tenant_id)
    except redis.RedisError as exc:
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
    current_period_end = mapping.get("current_period_end") or None
    subscription_id = mapping.get("subscription_id")

    if subscription_id:
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            status = subscription.get("status", status)
            current_period_end = _format_period_end(subscription.get("current_period_end"))

            mapping["status"] = status
            mapping["current_period_end"] = current_period_end or ""
            _state_mod._store_subscription_mapping(resolved_tenant_id, mapping)
        except stripe.error.StripeError as exc:  # pragma: no cover - network/API errors
            logger.warning("subscription_retrieve_failed", tenant_id=resolved_tenant_id, error=str(exc))

    limits = PLANS.get(plan_id, {}).get("limits", {})

    return SubscriptionStatus(
        tenant_id=resolved_tenant_id,
        plan=plan_id,
        status=status,
        current_period_end=current_period_end,
        events_used=0,
        events_limit=limits.get("events_per_month", 0),
        facilities_used=0,
        facilities_limit=limits.get("facilities", 0),
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
    """Primary Stripe webhook endpoint."""
    _rate_limiting_mod._check_stripe_webhook_rate_limit(request)
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
    """Legacy Stripe webhook path retained for backward compatibility."""
    _rate_limiting_mod._check_stripe_webhook_rate_limit(request)
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
        return_url = _helpers_mod._validate_redirect_url(
            request.return_url, field="return_url"
        )
    else:
        server_default = os.getenv("STRIPE_PORTAL_RETURN_URL", DEFAULT_PORTAL_RETURN_URL)
        return_url = _helpers_mod._validate_redirect_url(
            server_default, field="return_url"
        )

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
    tenant_id: Optional[str] = Query(default=None, description="Tenant ID override for legacy/master keys"),
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
    description=(
        "Fetches a Stripe invoice by ID and returns the hosted invoice PDF URL for the tenant."
    ),
)
async def get_invoice_pdf(
    invoice_id: str,
    tenant_id: Optional[str] = Query(default=None, description="Tenant ID override for legacy/master keys"),
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

    invoice_customer_id = str(_stripe_get(invoice, "customer", "") or "").strip()
    if invoice_customer_id and invoice_customer_id != customer_id:
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
    _: None = Depends(_verify_api_key),
) -> BillingPortalResponse:
    """Create Stripe customer portal session for self-service billing management."""
    _helpers_mod._configure_stripe()

    # #1186: validate the server-configured return_url. This endpoint
    # doesn't accept a client override, but the env-var value is still
    # run through the allowlist so a misconfigured STRIPE_PORTAL_RETURN_URL
    # fails at request time rather than silently redirecting.
    server_default = os.getenv("STRIPE_PORTAL_RETURN_URL", DEFAULT_PORTAL_RETURN_URL)
    return_url = _helpers_mod._validate_redirect_url(
        server_default, field="return_url"
    )

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
        raise HTTPException(status_code=502, detail=f"Stripe portal creation failed: {exc.user_message or str(exc)}") from exc

    portal_url = str(_stripe_get(session, "url", "") or "")
    if not portal_url:
        raise HTTPException(status_code=502, detail="Stripe portal creation failed: missing portal URL")

    return BillingPortalResponse(
        portal_url=portal_url,
        tenant_id=tenant_id,
        customer_id=customer_id,
    )
