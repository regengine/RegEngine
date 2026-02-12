"""
Billing Service — Pydantic Models

Defines all data models for subscriptions, credits, checkout sessions,
invoices, and webhook events.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field
from uuid import uuid4


# ── Enums ──────────────────────────────────────────────────────────

class BillingCycle(str, Enum):
    MONTHLY = "monthly"
    ANNUAL = "annual"


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    TRIALING = "trialing"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    INCOMPLETE = "incomplete"


class CreditType(str, Enum):
    REFERRAL = "referral"
    EARLY_ADOPTER = "early_adopter"
    USAGE_BONUS = "usage_bonus"
    PARTNER = "partner"
    PROMO = "promo"


class CheckoutStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    EXPIRED = "expired"


# ── Pricing Tiers ──────────────────────────────────────────────────

class TierFeature(BaseModel):
    text: str
    included: bool = True


class PricingTier(BaseModel):
    id: str
    name: str
    description: str
    monthly_price: Optional[int] = None  # None = custom/contact sales
    annual_price: Optional[int] = None
    cte_limit: str
    features: List[TierFeature] = []
    highlighted: bool = False
    stripe_monthly_price_id: Optional[str] = None
    stripe_annual_price_id: Optional[str] = None


# Tier definitions matching existing pricing page
PRICING_TIERS: dict[str, PricingTier] = {
    "starter": PricingTier(
        id="starter",
        name="Starter",
        description="For small operations getting started with FSMA 204",
        monthly_price=299,
        annual_price=249,
        cte_limit="10,000",
        features=[
            TierFeature(text="API access"),
            TierFeature(text="1 integration"),
            TierFeature(text="Basic Gap Analysis"),
            TierFeature(text="Email support"),
            TierFeature(text="FDA 204 export"),
            TierFeature(text="7-day data retention"),
        ],
    ),
    "growth": PricingTier(
        id="growth",
        name="Growth",
        description="For growing companies with multiple facilities",
        monthly_price=799,
        annual_price=665,
        cte_limit="100,000",
        highlighted=True,
        features=[
            TierFeature(text="Everything in Starter"),
            TierFeature(text="5 integrations"),
            TierFeature(text="Advanced Gap Analysis"),
            TierFeature(text="Drift Alerts"),
            TierFeature(text="Multi-tenant isolation"),
            TierFeature(text="Priority email support"),
        ],
    ),
    "scale": PricingTier(
        id="scale",
        name="Scale",
        description="For enterprises with complex supply chains",
        monthly_price=1999,
        annual_price=1665,
        cte_limit="1,000,000",
        features=[
            TierFeature(text="Everything in Growth"),
            TierFeature(text="Unlimited integrations"),
            TierFeature(text="Regulatory intelligence feed"),
            TierFeature(text="White-label reports"),
            TierFeature(text="SSO/SAML support"),
            TierFeature(text="Enterprise SLA"),
        ],
    ),
    "enterprise": PricingTier(
        id="enterprise",
        name="Enterprise",
        description="Custom solutions for the largest organizations",
        monthly_price=None,
        annual_price=None,
        cte_limit="Unlimited",
        features=[
            TierFeature(text="Everything in Scale"),
            TierFeature(text="On-premise deployment"),
            TierFeature(text="Custom API limits"),
            TierFeature(text="Dedicated success manager"),
            TierFeature(text="SOC 2 Type II report"),
            TierFeature(text="24/7 phone support"),
        ],
    ),
}


# ── Subscription ───────────────────────────────────────────────────

class Subscription(BaseModel):
    id: str = Field(default_factory=lambda: f"sub_{uuid4().hex[:12]}")
    tenant_id: str
    tier_id: str
    status: SubscriptionStatus = SubscriptionStatus.TRIALING
    billing_cycle: BillingCycle = BillingCycle.ANNUAL
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    stripe_subscription_id: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    canceled_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SubscriptionCreateRequest(BaseModel):
    tier_id: str
    billing_cycle: BillingCycle = BillingCycle.ANNUAL
    credit_code: Optional[str] = None


class SubscriptionResponse(BaseModel):
    subscription: Subscription
    message: str = "Subscription created"


class ChangeTierRequest(BaseModel):
    new_tier_id: str


# ── Credits ────────────────────────────────────────────────────────

class CreditTransaction(BaseModel):
    id: str = Field(default_factory=lambda: f"cred_{uuid4().hex[:12]}")
    tenant_id: str
    credit_type: CreditType
    amount_cents: int  # Positive = credit added, negative = redeemed
    code: Optional[str] = None
    description: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None


class CreditBalance(BaseModel):
    tenant_id: str
    balance_cents: int = 0
    total_earned_cents: int = 0
    total_redeemed_cents: int = 0
    transactions: List[CreditTransaction] = []


class RedeemCreditRequest(BaseModel):
    code: str


class RedeemCreditResponse(BaseModel):
    success: bool
    amount_cents: int = 0
    credit_type: Optional[CreditType] = None
    new_balance_cents: int = 0
    message: str = ""


# ── Checkout ───────────────────────────────────────────────────────

class CheckoutSessionCreate(BaseModel):
    tier_id: str
    billing_cycle: BillingCycle = BillingCycle.ANNUAL
    credit_code: Optional[str] = None
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


class CheckoutSession(BaseModel):
    id: str = Field(default_factory=lambda: f"cs_{uuid4().hex[:12]}")
    tenant_id: Optional[str] = None
    tier_id: str
    billing_cycle: BillingCycle
    status: CheckoutStatus = CheckoutStatus.PENDING
    checkout_url: str = ""
    stripe_session_id: Optional[str] = None
    applied_credit_cents: int = 0
    subtotal_cents: int = 0
    total_cents: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── Webhooks ───────────────────────────────────────────────────────

class WebhookEvent(BaseModel):
    id: str
    type: str
    data: dict
    created_at: datetime = Field(default_factory=datetime.utcnow)
    processed: bool = False


# ── Invoices ───────────────────────────────────────────────────────

class Invoice(BaseModel):
    id: str = Field(default_factory=lambda: f"inv_{uuid4().hex[:12]}")
    tenant_id: str
    subscription_id: str
    amount_cents: int
    status: str = "paid"
    stripe_invoice_id: Optional[str] = None
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
