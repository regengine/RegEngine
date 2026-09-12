"""Pydantic request/response models for Stripe billing."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

DEFAULT_SUCCESS_URL = "https://regengine.co/dashboard?checkout=success"
DEFAULT_CANCEL_URL = "https://regengine.co/pricing?checkout=cancelled"


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
    billing_period: Optional[str] = None
    current_period_end: Optional[str] = None
    events_used: int = 0
    events_limit: int = 0
    facilities_used: int = 0
    facilities_limit: int = 0


class UsageResponse(BaseModel):
    """Current-period per-label metered usage for a tenant.

    ``billing_period_start``/``_end`` are the UTC-calendar-month bucket
    used for local display/idempotency purposes only — they are not
    necessarily the tenant's real Stripe invoice period boundary. See
    DESIGN_metering-billing.md §3.3/§7.2 for the rationale.
    """

    tenant_id: str
    billing_period_start: str
    billing_period_end: str
    unit_count: int
    metered_billing_enabled: bool
    plan: str


class BillingPortalRequest(BaseModel):
    """Request payload for creating a Stripe customer portal session."""

    tenant_id: Optional[str] = Field(default=None, description="Optional tenant assertion; must match the credential")
    tenant_name: Optional[str] = Field(
        default=None, description="Tenant display name for first-time Stripe customer creation"
    )
    customer_email: Optional[str] = Field(
        default=None, description="Billing contact email for first-time Stripe customer creation"
    )
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
