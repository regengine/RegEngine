"""Unit tests for ``app.stripe_billing.plans`` — issue #1342.

Raises coverage from 80% to 100% by exercising the error branches
in ``_normalize_billing_period``, ``_resolve_price_id``, and the
annual→monthly fallback. Happy-path coverage already comes from
the Stripe webhook / router test suites; this file fills the
error-surface gaps they leave behind.

Pinned branches:
  - ``_normalize_billing_period``: raises HTTPException(400) on
    anything other than "monthly"/"annual" (lowercased + trimmed).
  - ``_resolve_price_id``:
      * Unknown plan → HTTPException(400) with the raw plan_id
        embedded in the detail.
      * ``enterprise`` plan → HTTPException(400) directing to sales;
        never leaks a Stripe price ID.
      * Missing monthly env → HTTPException(500) with plan + period
        in detail.
      * Missing annual env → falls back to monthly env before 500ing;
        this is the "annual pricing not configured yet" fallback
        that keeps the checkout page from 500ing mid-launch.
      * Plan with None amount (after a successful env lookup) →
        HTTPException(400) "does not support self-serve checkout".
  - ``_normalize_plan_id``: maps every alias in ``PLAN_ALIASES`` to
    the canonical plan; unknown ids are returned unchanged (to be
    rejected by ``_resolve_price_id``).
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
    PLAN_ALIASES,
    PLANS,
    _normalize_billing_period,
    _normalize_plan_id,
    _resolve_price_id,
)


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

    def test_unknown_plan_is_returned_unchanged(self):
        # Bad IDs are not rejected here — they pass through so the
        # caller (``_resolve_price_id``) can raise a uniform error.
        assert _normalize_plan_id("mystery-plan") == "mystery-plan"

    def test_canonical_ids_pass_through(self):
        # "growth" isn't in PLAN_ALIASES (it's already canonical) —
        # the ``.get(..., plan_id)`` default keeps it intact.
        assert _normalize_plan_id("growth") == "growth"
        assert _normalize_plan_id("scale") == "scale"
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
    def test_unknown_plan_raises_400_with_plan_id_echoed(self, monkeypatch):
        with pytest.raises(HTTPException) as ei:
            _resolve_price_id("mystery-plan", "monthly")
        assert ei.value.status_code == 400
        assert "mystery-plan" in ei.value.detail

    def test_enterprise_plan_raises_400_to_sales(self, monkeypatch):
        # Security / revenue contract: enterprise plans must NOT leak
        # a Stripe price ID to the checkout flow; customers have to
        # go through sales. If this 400 ever turns into a 200 the
        # whole enterprise tier is self-serve by accident.
        monkeypatch.setenv("STRIPE_PRICE_GROWTH_MONTHLY", "price_123")
        with pytest.raises(HTTPException) as ei:
            _resolve_price_id("enterprise", "monthly")
        assert ei.value.status_code == 400
        assert "sales" in ei.value.detail.lower()

    def test_missing_monthly_env_raises_500(self, monkeypatch):
        monkeypatch.delenv("STRIPE_PRICE_GROWTH_MONTHLY", raising=False)
        monkeypatch.delenv("STRIPE_PRICE_GROWTH_ANNUAL", raising=False)
        with pytest.raises(HTTPException) as ei:
            _resolve_price_id("growth", "monthly")
        assert ei.value.status_code == 500
        assert "growth" in ei.value.detail
        assert "monthly" in ei.value.detail

    def test_missing_annual_env_falls_back_to_monthly(self, monkeypatch):
        # Annual pricing not configured yet — the checkout page
        # degrades to the monthly price rather than 500ing. Pins the
        # fallback precedence so the ordering doesn't flip silently.
        monkeypatch.setenv("STRIPE_PRICE_GROWTH_MONTHLY", "price_fallback_m")
        monkeypatch.delenv("STRIPE_PRICE_GROWTH_ANNUAL", raising=False)
        plan, price_id, amount = _resolve_price_id("growth", "annual")
        assert price_id == "price_fallback_m"
        # Amount still comes from the annual column (the discounted one).
        assert amount == PLANS["growth"]["price_annual"]
        assert plan is PLANS["growth"]

    def test_missing_annual_and_monthly_env_raises_500(self, monkeypatch):
        monkeypatch.delenv("STRIPE_PRICE_GROWTH_MONTHLY", raising=False)
        monkeypatch.delenv("STRIPE_PRICE_GROWTH_ANNUAL", raising=False)
        with pytest.raises(HTTPException) as ei:
            _resolve_price_id("growth", "annual")
        assert ei.value.status_code == 500

    def test_alias_plan_routes_through_resolution(self, monkeypatch):
        # "starter" is an alias for "growth" — both the env lookup
        # and the amount read must happen against the canonical plan,
        # not the alias.
        monkeypatch.setenv("STRIPE_PRICE_GROWTH_MONTHLY", "price_alias_m")
        plan, price_id, amount = _resolve_price_id("starter", "monthly")
        assert plan is PLANS["growth"]
        assert price_id == "price_alias_m"
        assert amount == PLANS["growth"]["price_monthly"]


# ---------------------------------------------------------------------------
# _resolve_price_id — None-amount branch
# ---------------------------------------------------------------------------


class TestResolvePriceIdNoneAmount:
    def test_plan_with_none_price_raises_400(self, monkeypatch):
        # Line 130: when the plan has a null amount, the env might
        # still be set (test/dev situations) and the lookup gets
        # past the 500 branch — we still must refuse self-serve
        # checkout. Simulate by patching PLANS with a None-amount
        # plan whose env is set.
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
# _resolve_price_id — happy path (both billing periods)
# ---------------------------------------------------------------------------


class TestResolvePriceIdHappy:
    def test_monthly_returns_plan_price_and_amount(self, monkeypatch):
        monkeypatch.setenv("STRIPE_PRICE_SCALE_MONTHLY", "price_scale_m")
        plan, price_id, amount = _resolve_price_id("scale", "monthly")
        assert plan is PLANS["scale"]
        assert price_id == "price_scale_m"
        assert amount == PLANS["scale"]["price_monthly"]

    def test_annual_returns_plan_price_and_amount(self, monkeypatch):
        monkeypatch.setenv("STRIPE_PRICE_SCALE_ANNUAL", "price_scale_a")
        plan, price_id, amount = _resolve_price_id("scale", "annual")
        assert plan is PLANS["scale"]
        assert price_id == "price_scale_a"
        assert amount == PLANS["scale"]["price_annual"]


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

    def test_growth_and_scale_have_pricing(self):
        # Enterprise is supposed to be null-priced (handled by sales);
        # the other two must keep stripe-compatible positive ints.
        for pid in ("growth", "scale"):
            p = PLANS[pid]
            assert isinstance(p["price_monthly"], int) and p["price_monthly"] > 0
            assert isinstance(p["price_annual"], int) and p["price_annual"] > 0

    def test_enterprise_has_null_pricing(self):
        p = PLANS["enterprise"]
        assert p["price_monthly"] is None
        assert p["price_annual"] is None
        assert p["stripe_price_env_monthly"] is None
        assert p["stripe_price_env_annual"] is None
