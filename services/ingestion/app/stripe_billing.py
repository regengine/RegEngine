"""
Stripe Billing Router.

Manages Stripe checkout sessions, subscription status, and webhook processing
for RegEngine's FSMA-first pricing tiers.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
import redis
import stripe
from shared.resilient_http import resilient_client
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.authz import IngestionPrincipal, get_ingestion_principal, require_permission
from app.config import get_settings
from app.webhook_compat import _verify_api_key
from shared.funnel_events import emit_funnel_event
from shared.permissions import has_permission

logger = logging.getLogger("stripe-billing")

router = APIRouter(prefix="/api/v1/billing", tags=["Billing & Subscriptions"])

DEFAULT_SUCCESS_URL = "https://regengine.co/dashboard?checkout=success"
DEFAULT_CANCEL_URL = "https://regengine.co/pricing?checkout=cancelled"
DEFAULT_PORTAL_RETURN_URL = "https://regengine.co/dashboard"

PLAN_ALIASES = {
    "starter": "growth",
    "professional": "scale",
    "base": "growth",
    "standard": "scale",
}


# ── Plan Definitions ──────────────────────────────────────────────

PLANS: dict[str, dict[str, Any]] = {
    "growth": {
        "id": "growth",
        "name": "Growth",
        "price_monthly": 999,
        "price_annual": 832,
        "stripe_price_env_monthly": "STRIPE_PRICE_GROWTH_MONTHLY",
        "stripe_price_env_annual": "STRIPE_PRICE_GROWTH_ANNUAL",
        "features": [
            "FSMA 204 traceability workspace",
            "Supplier onboarding + FTL scoping",
            "CSV upload + API ingestion",
            "Compliance scoring + FDA-ready export",
            "Recall simulation + drill workflows",
            "Email support",
        ],
        "limits": {
            "facilities": 1,
            "events_per_month": 50000,
        },
    },
    "scale": {
        "id": "scale",
        "name": "Scale",
        "price_monthly": 1999,
        "price_annual": 1666,
        "stripe_price_env_monthly": "STRIPE_PRICE_SCALE_MONTHLY",
        "stripe_price_env_annual": "STRIPE_PRICE_SCALE_ANNUAL",
        "features": [
            "Everything in Growth",
            "Multi-facility operations",
            "Expanded API + webhook limits",
            "Priority onboarding support",
            "Retailer-specific readiness benchmarks",
            "Priority support",
        ],
        "limits": {
            "facilities": 5,
            "events_per_month": 250000,
        },
    },
    "enterprise": {
        "id": "enterprise",
        "name": "Enterprise",
        "price_monthly": None,
        "price_annual": None,
        "stripe_price_env_monthly": None,
        "stripe_price_env_annual": None,
        "features": [
            "Everything in Scale",
            "Dedicated implementation plan",
            "Custom SLA + security review support",
            "Advanced integration and data architecture",
            "Executive sponsor + quarterly roadmap reviews",
        ],
        "limits": {
            "facilities": -1,
            "events_per_month": -1,
        },
    },
}


class CheckoutRequest(BaseModel):
    """Request to create a Stripe checkout session."""

    plan_id: str = Field(..., description="Plan: growth or scale")
    billing_period: str = Field("monthly", description="monthly or annual")
    tenant_id: Optional[str] = Field(default=None, description="Existing tenant ID if already provisioned")
    tenant_name: Optional[str] = Field(default=None, description="Tenant name for post-payment provisioning")
    customer_email: Optional[str] = Field(default=None, description="Payer email")
    success_url: str = Field(DEFAULT_SUCCESS_URL, description="Redirect URL on success")
    cancel_url: str = Field(DEFAULT_CANCEL_URL, description="Redirect URL on cancel")


class CheckoutResponse(BaseModel):
    """Stripe checkout session response."""

    checkout_url: str
    session_id: str
    plan: str
    billing_period: str
    amount: int
    currency: str = "usd"


class SubscriptionStatus(BaseModel):
    """Current subscription status for a tenant."""

    tenant_id: str
    plan: str
    status: str  # active, trialing, past_due, canceled, none
    current_period_end: Optional[str] = None
    events_used: int = 0
    events_limit: int = 0
    facilities_used: int = 0
    facilities_limit: int = 0


class BillingPortalRequest(BaseModel):
    """Request payload for creating a Stripe customer portal session."""

    tenant_id: Optional[str] = Field(default=None, description="Tenant ID override for legacy/master keys")
    tenant_name: Optional[str] = Field(default=None, description="Tenant display name for first-time Stripe customer creation")
    customer_email: Optional[str] = Field(default=None, description="Billing contact email for first-time Stripe customer creation")
    return_url: Optional[str] = Field(default=None, description="Optional Stripe portal return URL override")


class BillingPortalResponse(BaseModel):
    """Response payload for customer portal session creation."""

    portal_url: str
    tenant_id: str
    customer_id: str


class InvoiceSummary(BaseModel):
    """Flattened Stripe invoice summary for billing UI/API clients."""

    invoice_id: str
    amount_due: int
    amount_paid: int
    currency: str
    status: Optional[str] = None
    created_at: Optional[str] = None
    pdf_url: Optional[str] = None
    hosted_invoice_url: Optional[str] = None


class InvoiceListResponse(BaseModel):
    """Paginated invoice list response."""

    tenant_id: str
    customer_id: str
    invoices: list[InvoiceSummary]
    has_more: bool
    next_cursor: Optional[str] = None


class InvoicePdfResponse(BaseModel):
    """Invoice PDF lookup response."""

    tenant_id: str
    invoice_id: str
    status: Optional[str] = None
    created_at: Optional[str] = None
    pdf_url: str
    hosted_invoice_url: Optional[str] = None


def _normalize_plan_id(plan_id: str) -> str:
    normalized = PLAN_ALIASES.get(plan_id, plan_id)
    return normalized


def _normalize_billing_period(period: str) -> str:
    normalized = period.lower().strip()
    if normalized not in {"monthly", "annual"}:
        raise HTTPException(status_code=400, detail="billing_period must be 'monthly' or 'annual'")
    return normalized


def _configure_stripe() -> None:
    secret_key = os.getenv("STRIPE_SECRET_KEY")
    if not secret_key:
        raise HTTPException(status_code=500, detail="STRIPE_SECRET_KEY is not configured")
    stripe.api_key = secret_key


def _resolve_price_id(plan_id: str, billing_period: str) -> tuple[dict[str, Any], str, int]:
    normalized_plan = _normalize_plan_id(plan_id)
    plan = PLANS.get(normalized_plan)
    if not plan:
        raise HTTPException(status_code=400, detail=f"Invalid plan: {plan_id}")

    if normalized_plan == "enterprise":
        raise HTTPException(
            status_code=400,
            detail="Enterprise plans require a sales consultation. Contact sales@regengine.co",
        )

    price_env_var = plan[f"stripe_price_env_{billing_period}"]
    price_id = os.getenv(price_env_var) if price_env_var else None

    # Allow annual billing requests to fall back to monthly price IDs if annual IDs are not configured.
    if not price_id and billing_period == "annual":
        monthly_env_var = plan["stripe_price_env_monthly"]
        price_id = os.getenv(monthly_env_var) if monthly_env_var else None

    if not price_id:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Stripe price ID is not configured for plan '{normalized_plan}' "
                f"({billing_period})."
            ),
        )

    amount = plan[f"price_{billing_period}"]
    if amount is None:
        raise HTTPException(status_code=400, detail="Plan does not support self-serve checkout")

    return plan, price_id, amount


def _redis_client() -> redis.Redis:
    settings = get_settings()
    return redis.from_url(settings.redis_url, decode_responses=True)


def _tenant_subscription_key(tenant_id: str) -> str:
    return f"billing:tenant:{tenant_id}"


def _subscription_lookup_key(subscription_id: str) -> str:
    return f"billing:subscription:{subscription_id}"


def _customer_lookup_key(customer_id: str) -> str:
    return f"billing:customer:{customer_id}"


def _session_lookup_key(session_id: str) -> str:
    return f"billing:session:{session_id}"


def _store_subscription_mapping(tenant_id: str, payload: dict[str, str]) -> None:
    client = _redis_client()
    key = _tenant_subscription_key(tenant_id)
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()

    client.hset(key, mapping=payload)

    subscription_id = payload.get("subscription_id")
    if subscription_id:
        client.set(_subscription_lookup_key(subscription_id), tenant_id)

    customer_id = payload.get("customer_id")
    if customer_id:
        client.set(_customer_lookup_key(customer_id), tenant_id)

    session_id = payload.get("session_id")
    if session_id:
        client.set(_session_lookup_key(session_id), tenant_id)


def _get_subscription_mapping(tenant_id: str) -> dict[str, str]:
    client = _redis_client()
    return client.hgetall(_tenant_subscription_key(tenant_id))


def _find_tenant_id(subscription_id: Optional[str], customer_id: Optional[str]) -> Optional[str]:
    client = _redis_client()

    if subscription_id:
        tenant_id = client.get(_subscription_lookup_key(subscription_id))
        if tenant_id:
            return tenant_id

    if customer_id:
        tenant_id = client.get(_customer_lookup_key(customer_id))
        if tenant_id:
            return tenant_id

    return None


async def _create_tenant_via_admin(tenant_name: str) -> str:
    admin_base_url = os.getenv("ADMIN_SERVICE_URL", "http://localhost:8400").rstrip("/")
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


def _format_period_end(epoch_seconds: Optional[int]) -> Optional[str]:
    if not epoch_seconds:
        return None
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).isoformat()


def _normalize_scope(scope: str) -> str:
    return scope.strip().lower().replace(":", ".")


def _principal_role(principal: IngestionPrincipal) -> str:
    normalized_scopes = [_normalize_scope(scope) for scope in principal.scopes]
    if has_permission(normalized_scopes, "*") or any(scope.startswith("admin") for scope in normalized_scopes):
        return "admin"
    if any(scope.endswith((".write", ".ingest", ".export", ".verify")) for scope in normalized_scopes):
        return "operator"
    return "viewer"


def _enforce_admin_or_operator(principal: IngestionPrincipal, required_permission: str) -> None:
    if _principal_role(principal) == "viewer":
        raise HTTPException(
            status_code=403,
            detail=(
                "Insufficient role for invoice access: "
                f"requires admin/operator role with '{required_permission}'"
            ),
        )


def _resolve_tenant_context(
    explicit_tenant_id: Optional[str],
    x_tenant_id: Optional[str],
    principal: Optional[IngestionPrincipal] = None,
) -> str:
    resolved = (explicit_tenant_id or x_tenant_id or (principal.tenant_id if principal else None) or "").strip()
    if not resolved:
        raise HTTPException(status_code=400, detail="Tenant context required")
    return resolved


def _stripe_get(payload: Any, key: str, default: Any = None) -> Any:
    if isinstance(payload, dict):
        return payload.get(key, default)
    return getattr(payload, key, default)


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_optional_int(value: Any) -> Optional[int]:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _extract_invoice_period_end(invoice_payload: dict[str, Any]) -> Optional[str]:
    # Stripe invoice payloads can surface period end in several places depending on event type/version.
    direct_period_end = _coerce_optional_int(invoice_payload.get("period_end"))
    if direct_period_end:
        return _format_period_end(direct_period_end)

    lines = invoice_payload.get("lines") or {}
    data = lines.get("data") if isinstance(lines, dict) else None
    if isinstance(data, list):
        for line in data:
            if not isinstance(line, dict):
                continue
            line_period = line.get("period") or {}
            period_end = _coerce_optional_int(line_period.get("end"))
            if period_end:
                return _format_period_end(period_end)

    return None


def _extract_paid_at(invoice_payload: dict[str, Any]) -> Optional[str]:
    status_transitions = invoice_payload.get("status_transitions") or {}
    paid_at = _coerce_optional_int(status_transitions.get("paid_at"))
    if paid_at:
        return _format_period_end(paid_at)

    created = _coerce_optional_int(invoice_payload.get("created"))
    if created:
        return _format_period_end(created)

    return None


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


async def _handle_checkout_completed(session: dict[str, Any]) -> None:
    metadata = session.get("metadata") or {}
    session_id = session.get("id")

    client = _redis_client()

    tenant_id = metadata.get("tenant_id")
    if session_id:
        existing_tenant = client.get(_session_lookup_key(session_id))
        if existing_tenant:
            tenant_id = existing_tenant

    if not tenant_id:
        tenant_name = metadata.get("tenant_name")
        if not tenant_name:
            fallback_email = metadata.get("customer_email") or session.get("customer_email")
            tenant_name = f"{(fallback_email or 'New Customer').split('@')[0]} Team"

        tenant_id = await _create_tenant_via_admin(tenant_name)
        logger.info("tenant_created_from_checkout", tenant_id=tenant_id, session_id=session_id)

    subscription_id = session.get("subscription")
    customer_id = session.get("customer")

    plan_id = _normalize_plan_id(str(metadata.get("plan_id", "growth")))
    billing_period = _normalize_billing_period(str(metadata.get("billing_period", "monthly")))

    subscription_status = "active"
    current_period_end = None
    if subscription_id:
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            subscription_status = subscription.get("status", subscription_status)
            current_period_end = _format_period_end(subscription.get("current_period_end"))
        except stripe.error.StripeError as exc:  # pragma: no cover - network/API errors
            logger.warning("subscription_lookup_failed", subscription_id=subscription_id, error=str(exc))

    _store_subscription_mapping(
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
    tenant_id = _find_tenant_id(subscription_id, customer_id)
    if not tenant_id:
        logger.warning(
            "billing_mapping_not_found",
            subscription_id=subscription_id,
            customer_id=customer_id,
            status=status,
        )
        return

    existing = _get_subscription_mapping(tenant_id)
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
    _store_subscription_mapping(tenant_id, existing)


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
            last_payment_failure_at=_format_period_end(_coerce_int(data_object.get("created"))),
        )
        return

    if event_type == "invoice.paid":
        period_end = _extract_invoice_period_end(data_object)
        paid_at = _extract_paid_at(data_object)
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
        payment_tenant_id = _find_tenant_id(subscription_id, customer_id)
        emit_funnel_event(
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
        tenant_id = _find_tenant_id(data_object.get("id"), data_object.get("customer"))
        if tenant_id:
            existing = _get_subscription_mapping(tenant_id)
            existing["current_period_end"] = _format_period_end(data_object.get("current_period_end")) or ""
            _store_subscription_mapping(tenant_id, existing)
        return

    logger.info("stripe_webhook_ignored", event_type=event_type)


async def _process_stripe_webhook(
    request: Request,
    stripe_signature: Optional[str],
) -> dict[str, Any]:
    _configure_stripe()

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
        raise HTTPException(status_code=401, detail="Invalid Stripe signature") from exc

    await _handle_stripe_event(event)
    logger.info("stripe_webhook_processed", event_type=event.get("type"))
    return {"received": True, "event_type": event.get("type")}


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
async def create_checkout(request: CheckoutRequest) -> CheckoutResponse:
    """Create a Stripe checkout session."""
    _configure_stripe()

    billing_period = _normalize_billing_period(request.billing_period)
    plan, price_id, amount = _resolve_price_id(request.plan_id, billing_period)
    existing_customer_id: Optional[str] = None

    metadata = {
        "plan_id": plan["id"],
        "billing_period": billing_period,
    }
    if request.tenant_id:
        metadata["tenant_id"] = request.tenant_id
    if request.tenant_name:
        metadata["tenant_name"] = request.tenant_name
    if request.customer_email:
        metadata["customer_email"] = request.customer_email

    if request.tenant_id:
        try:
            existing_customer_id = _get_existing_customer_id(request.tenant_id)
        except redis.RedisError as exc:
            logger.warning("checkout_customer_lookup_failed tenant_id=%s error=%s", request.tenant_id, str(exc))

    checkout_kwargs: dict[str, Any] = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": request.success_url,
        "cancel_url": request.cancel_url,
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

    if request.tenant_id:
        try:
            _record_checkout_session_hint(
                tenant_id=request.tenant_id,
                session_id=str(session.id),
                plan_id=plan["id"],
                billing_period=billing_period,
                customer_email=request.customer_email,
                customer_id=existing_customer_id,
            )
        except redis.RedisError as exc:
            # Don't block checkout redirect if Redis is briefly unavailable.
            logger.warning("checkout_hint_store_failed tenant_id=%s error=%s", request.tenant_id, str(exc))

    emit_funnel_event(
        tenant_id=request.tenant_id,
        event_name="checkout_started",
        metadata={
            "plan_id": plan["id"],
            "billing_period": billing_period,
            "session_id": str(session.id),
        },
    )

    logger.info(
        "checkout_created",
        extra={
            "tenant_id": request.tenant_id,
            "plan": plan["id"],
            "amount": amount,
            "billing_period": billing_period,
            "session_id": session.id,
        },
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
    _: None = Depends(_verify_api_key),
) -> SubscriptionStatus:
    """Get current subscription status for a tenant."""
    _configure_stripe()

    try:
        mapping = _get_subscription_mapping(tenant_id)
    except redis.RedisError as exc:
        logger.error("subscription_mapping_read_failed", tenant_id=tenant_id, error=str(exc))
        raise HTTPException(status_code=503, detail="Billing state store unavailable") from exc

    if not mapping:
        return SubscriptionStatus(
            tenant_id=tenant_id,
            plan="none",
            status="none",
            current_period_end=None,
            events_used=0,
            events_limit=0,
            facilities_used=0,
            facilities_limit=0,
        )

    plan_id = _normalize_plan_id(mapping.get("plan_id", "growth"))
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
            _store_subscription_mapping(tenant_id, mapping)
        except stripe.error.StripeError as exc:  # pragma: no cover - network/API errors
            logger.warning("subscription_retrieve_failed", tenant_id=tenant_id, error=str(exc))

    limits = PLANS.get(plan_id, {}).get("limits", {})

    return SubscriptionStatus(
        tenant_id=tenant_id,
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
    return await _process_stripe_webhook(request, stripe_signature)


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
    return await _process_stripe_webhook(request, stripe_signature)


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
    _configure_stripe()

    tenant_id = _resolve_tenant_context(request.tenant_id, x_tenant_id, principal)
    return_url = request.return_url or os.getenv("STRIPE_PORTAL_RETURN_URL", DEFAULT_PORTAL_RETURN_URL)

    try:
        customer_id = _ensure_customer_mapping(
            tenant_id=tenant_id,
            tenant_name=request.tenant_name,
            customer_email=request.customer_email,
        )
    except redis.RedisError as exc:
        logger.error("portal_customer_lookup_failed", tenant_id=tenant_id, error=str(exc))
        raise HTTPException(status_code=503, detail="Billing state store unavailable") from exc

    try:
        session = _create_portal_session(customer_id=customer_id, return_url=return_url)
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
    _configure_stripe()
    _enforce_admin_or_operator(principal, "billing.invoices.read")

    resolved_tenant_id = _resolve_tenant_context(tenant_id, x_tenant_id, principal)
    try:
        mapping = _get_subscription_mapping(resolved_tenant_id)
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
    _configure_stripe()
    _enforce_admin_or_operator(principal, "billing.invoices.read")

    resolved_tenant_id = _resolve_tenant_context(tenant_id, x_tenant_id, principal)
    try:
        mapping = _get_subscription_mapping(resolved_tenant_id)
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
    _configure_stripe()

    return_url = os.getenv("STRIPE_PORTAL_RETURN_URL", DEFAULT_PORTAL_RETURN_URL)

    try:
        customer_id = _ensure_customer_mapping(
            tenant_id=tenant_id,
            tenant_name=None,
            customer_email=None,
        )
    except redis.RedisError as exc:
        logger.error("portal_customer_lookup_failed", tenant_id=tenant_id, error=str(exc))
        raise HTTPException(status_code=503, detail="Billing state store unavailable") from exc

    try:
        session = _create_portal_session(customer_id=customer_id, return_url=return_url)
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
