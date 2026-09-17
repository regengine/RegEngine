"""Plan definitions and normalization helpers."""

from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import HTTPException

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

DEFAULT_SUCCESS_URL = "https://regengine.co/dashboard?checkout=success"
DEFAULT_CANCEL_URL = "https://regengine.co/pricing?checkout=cancelled"
DEFAULT_PORTAL_RETURN_URL = "https://regengine.co/dashboard"


def _normalize_plan_id(plan_id: str) -> str:
    normalized = PLAN_ALIASES.get(plan_id, plan_id)
    return normalized


def _normalize_billing_period(period: str) -> str:
    normalized = period.lower().strip()
    if normalized not in {"monthly", "annual"}:
        raise HTTPException(status_code=400, detail="billing_period must be 'monthly' or 'annual'")
    return normalized


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

    # #2928: never substitute another period's price ID here. Billing an
    # annual request against the monthly Price silently enrolls the customer
    # on the wrong interval while the response and stored mapping both say
    # "annual" — an unconfigured price must fail loudly instead.
    if not price_id:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Stripe price ID is not configured for plan '{normalized_plan}' ({billing_period}). "
                f"Set {price_env_var}."
            ),
        )

    amount = plan[f"price_{billing_period}"]
    if amount is None:
        raise HTTPException(status_code=400, detail="Plan does not support self-serve checkout")

    return plan, price_id, amount


def _plan_for_stripe_price(price_id: str) -> Optional[tuple[str, str]]:
    """Reverse-map a Stripe price ID to ``(plan_id, billing_period)``.

    Webhook verification counterpart to ``_resolve_price_id``: checkout
    metadata *claims* a plan, but the subscription's actual price is
    Stripe-side truth. Walk the catalog's env-configured price IDs and
    return the plan/period the price belongs to. Returns ``None`` when
    the price matches no configured catalog entry. Never raises — the
    webhook path must fail closed on catalog gaps, not 500.
    """
    if not price_id:
        return None
    for plan_id, plan in PLANS.items():
        for period in ("monthly", "annual"):
            env_var = plan.get(f"stripe_price_env_{period}")
            if not env_var:
                continue
            if os.getenv(env_var) == price_id:
                return (plan_id, period)
    return None
