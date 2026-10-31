"""Unit tests for ``app.stripe_billing.plans`` — issue #1342 / A-2155.

Pins the approved list/founding packaging and the transitional alias period:

  - Canonical ``PLANS`` keys are ``list``, ``founding``, ``enterprise``;
    growth/scale are aliases → ``list`` and premium → ``enterprise``.
  - List is $999/mo per facility, founding is $499/mo per facility.
    Annual is OPEN (``price_annual is None``) and must 400, never fall
    back to the monthly Price.
  - List monthly may fall back to the deprecated
    ``STRIPE_PRICE_GROWTH_MONTHLY`` env for the alias period only.
  - Pilot is one-time, not a recurring plan: constants/helpers only.
  - Every plan feature list advertises the EPCIS export as Preview.

Raises coverage from 80% to 100% by exercising the error branches in
``_normalize_billing_period``, ``_resolve_price_id``,
``_resolve_pilot_price_id`` and ``_plan_for_stripe_price``. No live
Stripe calls are made.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))


from app.stripe_billing import plans as mod  # noqa: E402
from app.stripe_billing.plans import (  # noqa: E402
    DEPRECATED_LIST_PRICE_ENV_MONTHLY,
    PILOT_CONVERT_WINDOW_DAYS,
    PILOT_DURATION_DAYS,
    PILOT_FEE_CONVERT_30_CENTS,
    PILOT_FEE_STANDARD_CENTS,
    PILOT_PRICE_ENV_CONVERT_30,
    PILOT_PRICE_ENV_STANDARD,
    PLAN_ALIASES,
    PLANS,
    _normalize_billing_period,
    _normalize_plan_id,
    _plan_for_stripe_price,
    _resolve_pilot_price_id,
    _resolve_price_id,
)


def _clear_catalog_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every price env this module reads so tests are deterministic."""
    for name in (
        "STRIPE_PRICE_LIST_MONTHLY",
        "STRIPE_PRICE_FOUNDING_MONTHLY",
        DEPRECATED_LIST_PRICE_ENV_MONTHLY,
        "STRIPE_PRICE_GROWTH_ANNUAL",
        "STRIPE_PRICE_SCALE_MONTHLY",
        "STRIPE_PRICE_SCALE_ANNUAL",
        PILOT_PRICE_ENV_STANDARD,
        PILOT_PRICE_ENV_CONVERT_30,
    ):
        monkeypatch.delenv(name, raising=False)


# ---------------------------------------------------------------------------
# _normalize_plan_id — alias map + passthrough
# ---------------------------------------------------------------------------


class TestNormalizePlanId:
    @pytest.mark.parametrize(
        "alias,canonical",
        sorted(PLAN_ALIASES.items()),
    )
    def test_every_alias_maps_to_canonical_plan(self, alias, canonical):
        # Parameterized over the actual dict so adding a new alias
        # automatically tightens the test.
        assert _normalize_plan_id(alias) == canonical

    @pytest.mark.parametrize(
        "alias",
        ["growth", "base", "starter", "scale", "standard", "professional"],
    )
    def test_legacy_self_serve_tiers_alias_to_list(self, alias):
        assert _normalize_plan_id(alias) == "list"

    def test_premium_goes_to_sales_not_a_dollar_sku(self):
        # There is no approved Premium self-serve SKU; route it to sales.
        assert _normalize_plan_id("premium") == "enterprise"
        assert "premium" not in PLANS

    def test_unknown_plan_is_returned_unchanged(self):
        # Bad IDs are not rejected here — they pass through so the
        # caller (``_resolve_price_id``) can raise a uniform error.
        assert _normalize_plan_id("mystery-plan") == "mystery-plan"

    def test_canonical_ids_pass_through(self):
        assert _normalize_plan_id("list") == "list"
        assert _normalize_plan_id("founding") == "founding"
        assert _normalize_plan_id("enterprise") == "enterprise"


# ---------------------------------------------------------------------------
# _normalize_billing_period — strip / lower / validate
# ---------------------------------------------------------------------------


class TestNormalizeBillingPeriod:
    @pytest.mark.parametrize("period", ["monthly", "annual"])
    def test_canonical_passes_through(self, period):
        assert _normalize_billing_period(period) == period

    def test_mixed_case_is_lowercased(self):
        assert _normalize_billing_period("MONTHLY") == "monthly"
        assert _normalize_billing_period("Annual") == "annual"

    def test_surrounding_whitespace_stripped(self):
        assert _normalize_billing_period("  monthly  ") == "monthly"

    def test_invalid_period_raises_http_400(self):
        # Must raise HTTPException (not ValueError) — the caller is a
        # FastAPI route and the raised exception becomes the 400 JSON
        # body via FastAPI's default handler.
        with pytest.raises(HTTPException) as ei:
            _normalize_billing_period("quarterly")
        assert ei.value.status_code == 400
        assert "monthly" in ei.value.detail
        assert "annual" in ei.value.detail

    def test_empty_string_raises_http_400(self):
        with pytest.raises(HTTPException) as ei:
            _normalize_billing_period("")
        assert ei.value.status_code == 400


# ---------------------------------------------------------------------------
# _resolve_price_id — every error branch
# ---------------------------------------------------------------------------


class TestResolvePriceIdErrors:
    def test_unknown_plan_raises_400_with_plan_id_echoed(self):
        with pytest.raises(HTTPException) as ei:
            _resolve_price_id("mystery-plan", "monthly")
        assert ei.value.status_code == 400
        assert "mystery-plan" in ei.value.detail

    def test_enterprise_plan_raises_400_to_sales(self, monkeypatch):
        # Security / revenue contract: enterprise plans must NOT leak
        # a Stripe price ID to the checkout flow; customers have to
        # go through sales. Premium must land here too.
        monkeypatch.setenv("STRIPE_PRICE_LIST_MONTHLY", "price_123")
        for plan_id in ("enterprise", "premium"):
            with pytest.raises(HTTPException) as ei:
                _resolve_price_id(plan_id, "monthly")
            assert ei.value.status_code == 400
            assert "sales" in ei.value.detail.lower()

    def test_missing_list_monthly_env_raises_500_naming_new_var(self, monkeypatch):
        _clear_catalog_env(monkeypatch)
        with pytest.raises(HTTPException) as ei:
            _resolve_price_id("list", "monthly")
        assert ei.value.status_code == 500
        assert "list" in ei.value.detail
        assert "monthly" in ei.value.detail
        assert "STRIPE_PRICE_LIST_MONTHLY" in ei.value.detail
        # The deprecated fallback is documented in the detail for operators.
        assert DEPRECATED_LIST_PRICE_ENV_MONTHLY in ei.value.detail

    def test_missing_founding_monthly_env_raises_500(self, monkeypatch):
        _clear_catalog_env(monkeypatch)
        with pytest.raises(HTTPException) as ei:
            _resolve_price_id("founding", "monthly")
        assert ei.value.status_code == 500
        assert "founding" in ei.value.detail
        assert "STRIPE_PRICE_FOUNDING_MONTHLY" in ei.value.detail

    @pytest.mark.parametrize("plan_id", ["list", "founding"])
    def test_annual_raises_400_and_never_falls_back_to_monthly(self, monkeypatch, plan_id):
        # Annual is OPEN pending approval: monthly env being set must not
        # make an annual checkout succeed against the monthly Price.
        monkeypatch.setenv("STRIPE_PRICE_LIST_MONTHLY", "price_list_m")
        monkeypatch.setenv("STRIPE_PRICE_FOUNDING_MONTHLY", "price_founding_m")
        with pytest.raises(HTTPException) as ei:
            _resolve_price_id(plan_id, "annual")
        assert ei.value.status_code == 400
        assert "annual" in ei.value.detail.lower()
        assert "not configured" in ei.value.detail.lower()
        assert "price_list_m" not in ei.value.detail
        assert "price_founding_m" not in ei.value.detail

    def test_list_monthly_falls_back_to_deprecated_growth_env(self, monkeypatch):
        _clear_catalog_env(monkeypatch)
        monkeypatch.setenv(DEPRECATED_LIST_PRICE_ENV_MONTHLY, "price_growth_legacy")
        plan, price_id, amount = _resolve_price_id("list", "monthly")
        assert plan is PLANS["list"]
        assert price_id == "price_growth_legacy"
        assert amount == 999

    def test_alias_plan_routes_through_resolution(self, monkeypatch):
        # Every legacy alias resolves against the canonical list plan,
        # including the deprecated monthly env fallback.
        _clear_catalog_env(monkeypatch)
        monkeypatch.setenv(DEPRECATED_LIST_PRICE_ENV_MONTHLY, "price_alias_m")
        for alias in ("growth", "base", "starter", "scale", "standard", "professional"):
            plan, price_id, amount = _resolve_price_id(alias, "monthly")
            assert plan is PLANS["list"]
            assert price_id == "price_alias_m"
            assert amount == 999

    def test_premium_routes_to_sales(self):
        with pytest.raises(HTTPException) as ei:
            _resolve_price_id("premium", "monthly")
        assert ei.value.status_code == 400
        assert "sales" in ei.value.detail.lower()

    def test_never_substitutes_the_other_periods_price_id(self, monkeypatch):
        # #2928 regression guard, exercised with a synthetic plan so the
        # rule stays pinned even though list/founding have no annual Price.
        fake_plan = {
            "id": "fakeplan",
            "price_monthly": 1000,
            "price_annual": 10000,
            "stripe_price_env_monthly": "FAKE_PLAN_MONTHLY",
            "stripe_price_env_annual": "FAKE_PLAN_ANNUAL",
        }
        monkeypatch.setitem(PLANS, "fakeplan", fake_plan)
        monkeypatch.setenv("FAKE_PLAN_MONTHLY", "price_fake_m")
        monkeypatch.delenv("FAKE_PLAN_ANNUAL", raising=False)
        try:
            with pytest.raises(HTTPException) as ei:
                _resolve_price_id("fakeplan", "annual")
            assert ei.value.status_code == 500
            assert "FAKE_PLAN_ANNUAL" in ei.value.detail
            # The monthly price ID must never leak into the annual path.
            assert "price_fake_m" not in ei.value.detail
        finally:
            PLANS.pop("fakeplan", None)


# ---------------------------------------------------------------------------
# _resolve_price_id — None-amount branch
# ---------------------------------------------------------------------------


class TestResolvePriceIdNoneAmount:
    def test_plan_with_none_price_raises_400(self, monkeypatch):
        # When the plan has a null amount, the env might still be set
        # (test/dev situations) and the lookup gets past the 500 branch —
        # we still must refuse self-serve checkout.
        fake_plan = {
            "id": "fakeplan",
            "price_monthly": None,
            "price_annual": None,
            "stripe_price_env_monthly": "FAKE_PLAN_MONTHLY",
            "stripe_price_env_annual": "FAKE_PLAN_ANNUAL",
        }
        monkeypatch.setitem(PLANS, "fakeplan", fake_plan)
        monkeypatch.setenv("FAKE_PLAN_MONTHLY", "price_fake_m")
        try:
            with pytest.raises(HTTPException) as ei:
                _resolve_price_id("fakeplan", "monthly")
            assert ei.value.status_code == 400
            assert "self-serve" in ei.value.detail
        finally:
            PLANS.pop("fakeplan", None)


# ---------------------------------------------------------------------------
# _resolve_price_id — happy path
# ---------------------------------------------------------------------------


class TestResolvePriceIdHappy:
    def test_list_monthly_returns_plan_price_and_amount(self, monkeypatch):
        _clear_catalog_env(monkeypatch)
        monkeypatch.setenv("STRIPE_PRICE_LIST_MONTHLY", "price_list_m")
        plan, price_id, amount = _resolve_price_id("list", "monthly")
        assert plan is PLANS["list"]
        assert price_id == "price_list_m"
        assert amount == 999

    def test_founding_monthly_returns_plan_price_and_amount(self, monkeypatch):
        _clear_catalog_env(monkeypatch)
        monkeypatch.setenv("STRIPE_PRICE_FOUNDING_MONTHLY", "price_founding_m")
        plan, price_id, amount = _resolve_price_id("founding", "monthly")
        assert plan is PLANS["founding"]
        assert price_id == "price_founding_m"
        assert amount == 499

    def test_list_env_wins_over_deprecated_growth_env(self, monkeypatch):
        # During the alias period the new LIST var is authoritative.
        _clear_catalog_env(monkeypatch)
        monkeypatch.setenv("STRIPE_PRICE_LIST_MONTHLY", "price_list_new")
        monkeypatch.setenv(DEPRECATED_LIST_PRICE_ENV_MONTHLY, "price_growth_old")
        _, price_id, _ = _resolve_price_id("list", "monthly")
        assert price_id == "price_list_new"


# ---------------------------------------------------------------------------
# _plan_for_stripe_price — reverse map
# ---------------------------------------------------------------------------


class TestPlanForStripePrice:
    @pytest.mark.parametrize(
        "env_var,value,expected",
        [
            ("STRIPE_PRICE_LIST_MONTHLY", "price_list_m", ("list", "monthly")),
            ("STRIPE_PRICE_FOUNDING_MONTHLY", "price_founding_m", ("founding", "monthly")),
            (PILOT_PRICE_ENV_STANDARD, "price_pilot_std", ("pilot", "one_time")),
            (PILOT_PRICE_ENV_CONVERT_30, "price_pilot_conv", ("pilot", "one_time")),
            (DEPRECATED_LIST_PRICE_ENV_MONTHLY, "price_growth_legacy", ("list", "monthly")),
        ],
    )
    def test_reverse_maps_configured_prices(self, monkeypatch, env_var, value, expected):
        _clear_catalog_env(monkeypatch)
        monkeypatch.setenv(env_var, value)
        assert _plan_for_stripe_price(value) == expected

    @pytest.mark.parametrize(
        "env_var",
        ["STRIPE_PRICE_GROWTH_ANNUAL", "STRIPE_PRICE_SCALE_MONTHLY", "STRIPE_PRICE_SCALE_ANNUAL"],
    )
    def test_old_annual_and_scale_envs_do_not_invent_entitlements(self, monkeypatch, env_var):
        # Only growth monthly survives as an alias. Old annual/scale Prices
        # must not reverse-map to an annual or scale entitlement.
        _clear_catalog_env(monkeypatch)
        monkeypatch.setenv(env_var, "price_legacy_only")
        assert _plan_for_stripe_price("price_legacy_only") is None

    def test_pilot_is_not_a_recurring_plan(self):
        assert "pilot" not in PLANS

    def test_empty_and_unknown_prices_return_none(self, monkeypatch):
        _clear_catalog_env(monkeypatch)
        assert _plan_for_stripe_price("") is None
        assert _plan_for_stripe_price("price_unknown") is None


# ---------------------------------------------------------------------------
# Pilot helpers — one-time constants only, no recurring plan
# ---------------------------------------------------------------------------


class TestPilotHelpers:
    def test_pilot_constants(self):
        assert PILOT_FEE_STANDARD_CENTS == 200000
        assert PILOT_FEE_CONVERT_30_CENTS == 150000
        assert PILOT_DURATION_DAYS == 90
        assert PILOT_CONVERT_WINDOW_DAYS == 30

    @pytest.mark.parametrize(
        "variant,env_var,value",
        [
            ("standard", PILOT_PRICE_ENV_STANDARD, "price_pilot_std"),
            ("convert_30", PILOT_PRICE_ENV_CONVERT_30, "price_pilot_conv"),
        ],
    )
    def test_resolves_pilot_price_by_variant(self, monkeypatch, variant, env_var, value):
        _clear_catalog_env(monkeypatch)
        monkeypatch.setenv(env_var, value)
        assert _resolve_pilot_price_id(variant) == value

    def test_invalid_variant_raises_400(self):
        with pytest.raises(HTTPException) as ei:
            _resolve_pilot_price_id("bogus")
        assert ei.value.status_code == 400
        assert "standard" in ei.value.detail
        assert "convert_30" in ei.value.detail

    @pytest.mark.parametrize(
        "variant,env_var",
        [
            ("standard", PILOT_PRICE_ENV_STANDARD),
            ("convert_30", PILOT_PRICE_ENV_CONVERT_30),
        ],
    )
    def test_missing_pilot_env_raises_500_naming_var(self, monkeypatch, variant, env_var):
        _clear_catalog_env(monkeypatch)
        with pytest.raises(HTTPException) as ei:
            _resolve_pilot_price_id(variant)
        assert ei.value.status_code == 500
        assert env_var in ei.value.detail


# ---------------------------------------------------------------------------
# Catalog shape — approved A-2155 packaging
# ---------------------------------------------------------------------------


class TestCatalogShape:
    def test_canonical_plan_keys(self):
        assert set(PLANS) == {"list", "founding", "enterprise"}

    def test_list_values(self):
        plan = PLANS["list"]
        assert plan["name"] == "RegEngine List"
        assert plan["price_monthly"] == 999
        assert plan["price_annual"] is None
        assert plan["stripe_price_env_monthly"] == "STRIPE_PRICE_LIST_MONTHLY"
        assert plan["stripe_price_env_annual"] is None
        assert plan["limits"]["facilities"] == -1  # quantity-driven
        assert plan["limits"]["events_per_month"] == 50000  # CTE caps OPEN

    def test_founding_values(self):
        plan = PLANS["founding"]
        assert plan["name"] == "RegEngine Founding Design Partner"
        assert plan["price_monthly"] == 499
        assert plan["price_annual"] is None
        assert plan["stripe_price_env_monthly"] == "STRIPE_PRICE_FOUNDING_MONTHLY"
        assert plan["stripe_price_env_annual"] is None
        assert plan["limits"]["facilities"] == -1  # quantity-driven
        assert plan["limits"]["events_per_month"] == 50000  # CTE caps OPEN

    def test_enterprise_has_null_pricing_and_unlimited_limits(self):
        plan = PLANS["enterprise"]
        assert plan["price_monthly"] is None
        assert plan["price_annual"] is None
        assert plan["stripe_price_env_monthly"] is None
        assert plan["stripe_price_env_annual"] is None
        assert plan["limits"] == {"facilities": -1, "events_per_month": -1}

    def test_every_plan_features_include_epcis_export_preview(self):
        for plan_id, plan in PLANS.items():
            features = [feature.lower() for feature in plan["features"]]
            assert any("epcis" in feature and "preview" in feature for feature in features), (
                f"Plan '{plan_id}' is missing the EPCIS export Preview line"
            )

    def test_removed_tiers_are_not_canonical_plans(self):
        for legacy in ("growth", "scale", "base", "starter", "standard", "professional"):
            assert legacy not in PLANS


# ---------------------------------------------------------------------------
# Module constants — stable URLs
# ---------------------------------------------------------------------------


class TestModuleConstants:
    def test_default_urls_point_to_regengine_co(self):
        # If these ever change without a concurrent update to the
        # Stripe dashboard / marketing site, checkout success /
        # cancel flows silently redirect to a 404.
        assert mod.DEFAULT_SUCCESS_URL.startswith("https://regengine.co/")
        assert mod.DEFAULT_CANCEL_URL.startswith("https://regengine.co/")
        assert mod.DEFAULT_PORTAL_RETURN_URL.startswith("https://regengine.co/")
