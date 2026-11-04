"""Plan definitions and normalization helpers."""

from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import HTTPException

# Transitional aliases for the old flat-tier catalog. Under per-facility
# pricing the facility count is the subscription quantity, so ``scale`` no
# longer needs a separate 5-facility SKU; both legacy tiers collapse to
# ``list``. ``premium`` was never a self-serve SKU — keep it sales-only.
PLAN_ALIASES = {
    "growth": "list",
    "base": "list",
    "starter": "list",
    "scale": "list",
    "standard": "list",
    "professional": "list",
    "premium": "enterprise",
}

# Deprecated env var for the pre-A-2155 growth monthly price. Accepted as a
# fallback only during the alias period; new deploys set the LIST var.
DEPRECATED_LIST_PRICE_ENV_MONTHLY = "STRIPE_PRICE_GROWTH_MONTHLY"

# Pilot pricing is one-time, not a recurring self-serve plan. Amounts live
# outside the PLANS catalog on purpose: checkout quantity and webhook credit
# handling ship in follow-up PRs.
PILOT_FEE_STANDARD_CENTS = 200000
PILOT_FEE_CONVERT_30_CENTS = 150000
PILOT_DURATION_DAYS = 90
PILOT_CONVERT_WINDOW_DAYS = 30

PILOT_PRICE_ENV_STANDARD = "STRIPE_PRICE_PILOT_STANDARD"
PILOT_PRICE_ENV_CONVERT_30 = "STRIPE_PRICE_PILOT_CONVERT_30"

_PILOT_PRICE_ENV_BY_VARIANT = {
    "standard": PILOT_PRICE_ENV_STANDARD,
    "convert_30": PILOT_PRICE_ENV_CONVERT_30,
}


# ── Plan Definitions ──────────────────────────────────────────────

# A-2155/A-2158 packaging. List and founding are billed per facility: the
# subscription quantity carries the facility count (wired up in a follow-up
# PR), so ``limits.facilities`` is -1 ("quantity-driven") rather than a
# hardcoded seat count. CTE / event caps remain OPEN for approval — keep the
# prior growth-level 50000 until product signs off; do not invent new caps.
PLANS: dict[str, dict[str, Any]] = {
    "list": {
        "id": "list",
        "name": "RegEngine List",
        "price_monthly": 999,
        "price_annual": None,
        "stripe_price_env_monthly": "STRIPE_PRICE_LIST_MONTHLY",
        "stripe_price_env_annual": None,
        "features": [
            "FSMA 204 traceability workspace",
            "Supplier onboarding + FTL scoping",
            "CSV upload + API ingestion",
            "Compliance scoring + FDA-ready export",
            "Recall simulation + drill workflows",
            "EPCIS 1.2 export (Preview)",
            "Email support",
        ],
        "limits": {
            # Per-facility pricing: facility count is the subscription
            # quantity, not a hardcoded tier limit.
            "facilities": -1,
            # Prior growth cap. CTE caps are OPEN per A-2155.
            "events_per_month": 50000,
        },
    },
    "founding": {
        "id": "founding",
        "name": "RegEngine Founding Design Partner",
        "price_monthly": 499,
        "price_annual": None,
        "stripe_price_env_monthly": "STRIPE_PRICE_FOUNDING_MONTHLY",
        "stripe_price_env_annual": None,
        "features": [
            "Everything in RegEngine List",
            "Founding design partner pricing",
            "Supplier onboarding + FTL scoping",
            "CSV upload + API ingestion",
            "Compliance scoring + FDA-ready export",
            "Recall simulation + drill workflows",
            "EPCIS 1.2 export (Preview)",
            "Design partner support",
        ],
        "limits": {
            # Per-facility pricing: facility count is the subscription
            # quantity, not a hardcoded tier limit.
            "facilities": -1,
            # Prior growth cap. CTE caps are OPEN per A-2155.
            "events_per_month": 50000,
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
            "Everything in RegEngine List",
            "Dedicated implementation plan",
            "Custom SLA + security review support",
            "Advanced integration and data architecture",
            "Executive sponsor + quarterly roadmap reviews",
            "EPCIS 1.2 export (Preview)",
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


# ── Metered add-ons (per-label metered billing, DESIGN_metering-billing.md) ──
#
# A metered add-on is attached alongside a tenant's existing flat-tier
# subscription (see stripe_billing/usage_reporting.py opt-in flow) — it is
# not a standalone plan, so it deliberately does not appear in ``PLANS``.
METERED_ADDONS: dict[str, dict[str, Any]] = {
    "label_events": {
        "id": "label_events",
        "name": "Per-Label Metering",
        "stripe_price_env": "STRIPE_PRICE_METERED_LABEL_EVENTS",
        "meter_event_name": "regengine_label_events",
        "unit_label": "label event",
    },
}


def _normalize_plan_id(plan_id: str) -> str:
    normalized = PLAN_ALIASES.get(plan_id, plan_id)
    return normalized


def _normalize_billing_period(period: str) -> str:
    normalized = period.lower().strip()
    if normalized not in {"monthly", "annual"}:
        raise HTTPException(status_code=400, detail="billing_period must be 'monthly' or 'annual'")
    return normalized


def _resolve_pilot_price_id(variant: str) -> str:
    """Resolve the one-time pilot Price ID for ``standard`` or ``convert_30``.

    Pilot is deliberately not a recurring ``PLANS`` entry — this helper only
    returns the Stripe Price ID. Checkout quantity / webhook credit behavior
    lands in later PRs.
    """
    env_var = _PILOT_PRICE_ENV_BY_VARIANT.get(variant)
    if env_var is None:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid pilot variant: {variant}. Expected 'standard' or 'convert_30'.",
        )

    price_id = os.getenv(env_var)
    if not price_id:
        raise HTTPException(
            status_code=500,
            detail=f"Stripe price ID is not configured for pilot variant '{variant}'. Set {env_var}.",
        )
    return price_id


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

    # Annual pricing is OPEN pending approval (C.Lee). List/founding have no
    # annual Price and must not silently fall back to monthly: a 400 is
    # clearer than a 500 and tells the caller annual is not offered yet.
    if billing_period == "annual" and plan.get("price_annual") is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Annual pricing is not configured for plan '{normalized_plan}' "
                "(annual pricing is OPEN pending approval). "
                "Use monthly billing or contact sales@regengine.co."
            ),
        )

    price_env_var = plan[f"stripe_price_env_{billing_period}"]
    price_id = os.getenv(price_env_var) if price_env_var else None

    # Alias period only: the old growth monthly Price still resolves to the
    # list plan so existing Stripe subscriptions/links keep working until the
    # STRIPE_PRICE_LIST_MONTHLY values are set in the environment.
    if not price_id and normalized_plan == "list" and billing_period == "monthly":
        price_id = os.getenv(DEPRECATED_LIST_PRICE_ENV_MONTHLY)

    # #2928: never substitute another period's price ID here. Billing an
    # annual request against the monthly Price silently enrolls the customer
    # on the wrong interval while the response and stored mapping both say
    # "annual" — an unconfigured price must fail loudly instead.
    if not price_id:
        detail = (
            f"Stripe price ID is not configured for plan '{normalized_plan}' ({billing_period}). Set {price_env_var}."
        )
        if normalized_plan == "list" and billing_period == "monthly":
            detail += f" Deprecated fallback {DEPRECATED_LIST_PRICE_ENV_MONTHLY} is also unset (alias period only)."
        raise HTTPException(status_code=500, detail=detail)

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

    The deprecated growth monthly env still maps to list during the alias
    period. Old annual growth/scale envs are intentionally *not* mapped:
    annual pricing is OPEN, so we must not invent an annual entitlement.

    Pilot Price IDs map to ``("pilot", "one_time")`` even though pilot has
    no recurring ``PLANS`` entry. The webhook PR decides whether that grants
    any status; this helper only identifies the Price.
    """
    if not price_id:
        return None

    configured: list[tuple[str, str, str]] = []
    for plan_id, plan in PLANS.items():
        for period in ("monthly", "annual"):
            env_var = plan.get(f"stripe_price_env_{period}")
            if env_var:
                configured.append((env_var, plan_id, period))

    # Alias period only — deprecated monthly list price.
    configured.append((DEPRECATED_LIST_PRICE_ENV_MONTHLY, "list", "monthly"))

    # One-time pilot prices (not recurring plans).
    configured.append((PILOT_PRICE_ENV_STANDARD, "pilot", "one_time"))
    configured.append((PILOT_PRICE_ENV_CONVERT_30, "pilot", "one_time"))

    for env_var, plan_id, period in configured:
        if os.getenv(env_var) == price_id:
            return (plan_id, period)
    return None
