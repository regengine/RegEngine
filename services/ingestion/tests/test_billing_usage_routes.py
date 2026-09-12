"""Unit tests for the per-label metered billing API routes
(DESIGN_metering-billing.md §6): ``GET /usage``, ``POST /usage/report``,
``POST /usage/opt-in`` and ``DELETE /usage/opt-in``.

Monkeypatch-based, no live DB/Stripe/Redis — matches the style of
``test_stripe_billing_router.py`` / ``test_stripe_plans_1342.py``: route
functions are called directly with a fake session / fake Redis, bypassing
FastAPI's dependency-injection wiring (which is exercised separately by
route registration itself).
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any, List, Optional

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app import stripe_billing
from app.authz import IngestionPrincipal

TENANT_ID = "tenant-usage-1"


class _FakeRedis:
    def __init__(self):
        self.hashes: dict[str, dict[str, str]] = {}

    def hset(self, key: str, mapping: dict[str, str]):
        self.hashes.setdefault(key, {})
        self.hashes[key].update(mapping)

    def hgetall(self, key: str):
        return dict(self.hashes.get(key, {}))

    def set(self, key: str, value: str):
        pass

    def get(self, key: str):
        return None


class _Result:
    def __init__(self, row: Any = None) -> None:
        self._row = row

    def fetchone(self) -> Any:
        return self._row


class _FakeSession:
    """Programmable fake session mirroring the ``_FakeSession`` pattern in
    ``test_canonical_router_1342.py``: queued ``execute()`` results, calls
    recorded for assertions.
    """

    def __init__(self, results: Optional[List[_Result]] = None) -> None:
        self._results = list(results or [])
        self._call_index = 0
        self.calls: List[tuple] = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params))
        if self._call_index < len(self._results):
            result = self._results[self._call_index]
            self._call_index += 1
            return result
        return _Result()

    def commit(self) -> None:
        pass


def _principal(scopes: list[str]) -> IngestionPrincipal:
    return IngestionPrincipal(tenant_id=TENANT_ID, scopes=scopes, key_id="k1")


# ---------------------------------------------------------------------------
# GET /usage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_usage_returns_current_period_row(monkeypatch):
    fake_redis = _FakeRedis()
    monkeypatch.setattr(stripe_billing, "_redis_client", lambda: fake_redis)
    stripe_billing._store_subscription_mapping(
        TENANT_ID,
        {"plan_id": "growth", "metered_billing_enabled": "true"},
    )

    session = _FakeSession(results=[_Result(row=(42,)), _Result(row=(42,))])
    principal = _principal(["billing.usage.read"])

    response = await stripe_billing.get_usage(
        tenant_id=None,
        x_tenant_id=None,
        principal=principal,
        db_session=session,
    )

    assert response.tenant_id == TENANT_ID
    assert response.unit_count == 42
    # No prior report yet against this row, so it's also fully unbilled.
    assert response.unbilled_unit_count == 42
    assert response.metered_billing_enabled is True
    assert response.plan == "growth"
    # billing_period_start is the first of the current UTC month.
    assert response.billing_period_start.endswith("-01")


@pytest.mark.asyncio
async def test_get_usage_unbilled_count_includes_past_periods(monkeypatch):
    # Security-review fix: a past period's outstanding usage (e.g. from a
    # backfilled/backdated event) must be visible here even though it's
    # not reflected in the current-period `unit_count`.
    fake_redis = _FakeRedis()
    monkeypatch.setattr(stripe_billing, "_redis_client", lambda: fake_redis)
    stripe_billing._store_subscription_mapping(
        TENANT_ID,
        {"plan_id": "growth", "metered_billing_enabled": "true"},
    )

    # Current period has 10 units; the cross-period aggregate (current + a
    # past period with outstanding usage) is 25.
    session = _FakeSession(results=[_Result(row=(10,)), _Result(row=(25,))])
    principal = _principal(["billing.usage.read"])

    response = await stripe_billing.get_usage(
        tenant_id=None,
        x_tenant_id=None,
        principal=principal,
        db_session=session,
    )

    assert response.unit_count == 10
    assert response.unbilled_unit_count == 25


@pytest.mark.asyncio
async def test_get_usage_defaults_to_zero_when_no_counter_row(monkeypatch):
    fake_redis = _FakeRedis()
    monkeypatch.setattr(stripe_billing, "_redis_client", lambda: fake_redis)

    session = _FakeSession(results=[_Result(row=None), _Result(row=(0,))])
    principal = _principal(["billing.usage.read"])

    response = await stripe_billing.get_usage(
        tenant_id=None,
        x_tenant_id=None,
        principal=principal,
        db_session=session,
    )

    assert response.unit_count == 0
    assert response.unbilled_unit_count == 0
    assert response.metered_billing_enabled is False
    assert response.plan == "none"


@pytest.mark.asyncio
async def test_get_usage_503s_when_db_session_missing():
    principal = _principal(["billing.usage.read"])
    with pytest.raises(Exception) as exc_info:
        await stripe_billing.get_usage(
            tenant_id=None,
            x_tenant_id=None,
            principal=principal,
            db_session=None,
        )
    assert getattr(exc_info.value, "status_code", None) == 503


# ---------------------------------------------------------------------------
# POST /usage/report
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_report_usage_delegates_to_reporting_module(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    captured = {}

    def _fake_report(session, tenant_id):
        captured["session"] = session
        captured["tenant_id"] = tenant_id
        return {
            "tenant_id": tenant_id,
            "billing_period_start": "2026-09-01",
            "reported_delta": 5,
            "unit_count": 42,
            "identifier": "x",
            "meter_event_id": "mtr_1",
        }

    monkeypatch.setattr(stripe_billing, "report_tenant_usage_to_stripe", _fake_report)

    session = _FakeSession()
    principal = _principal(["billing.usage.report"])

    response = await stripe_billing.report_usage(
        tenant_id=None,
        x_tenant_id=None,
        principal=principal,
        db_session=session,
    )

    assert captured["tenant_id"] == TENANT_ID
    assert response["reported"] is True
    assert response["reported_delta"] == 5


@pytest.mark.asyncio
async def test_report_usage_returns_not_reported_on_none(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setattr(stripe_billing, "report_tenant_usage_to_stripe", lambda session, tenant_id: None)

    session = _FakeSession()
    principal = _principal(["billing.usage.report"])

    response = await stripe_billing.report_usage(
        tenant_id=None,
        x_tenant_id=None,
        principal=principal,
        db_session=session,
    )

    assert response["reported"] is False


@pytest.mark.asyncio
async def test_report_usage_surfaces_stripe_error_as_502(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")

    def _raise(session, tenant_id):
        raise stripe_billing.stripe.error.StripeError("boom")

    monkeypatch.setattr(stripe_billing, "report_tenant_usage_to_stripe", _raise)

    session = _FakeSession()
    principal = _principal(["billing.usage.report"])

    with pytest.raises(Exception) as exc_info:
        await stripe_billing.report_usage(
            tenant_id=None,
            x_tenant_id=None,
            principal=principal,
            db_session=session,
        )
    assert getattr(exc_info.value, "status_code", None) == 502


# ---------------------------------------------------------------------------
# POST /usage/opt-in
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_opt_in_requires_existing_flat_tier_subscription(monkeypatch):
    fake_redis = _FakeRedis()
    monkeypatch.setattr(stripe_billing, "_redis_client", lambda: fake_redis)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    # Admin scope so the role gate passes; no subscription_id stored.
    principal = _principal(["admin"])

    with pytest.raises(Exception) as exc_info:
        await stripe_billing.opt_in_metered_usage(tenant_id=None, x_tenant_id=None, principal=principal)
    assert getattr(exc_info.value, "status_code", None) == 400


@pytest.mark.asyncio
async def test_opt_in_attaches_subscription_item_and_stores_flag(monkeypatch):
    fake_redis = _FakeRedis()
    monkeypatch.setattr(stripe_billing, "_redis_client", lambda: fake_redis)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_PRICE_METERED_LABEL_EVENTS", "price_metered_1")

    stripe_billing._store_subscription_mapping(
        TENANT_ID,
        {"plan_id": "growth", "subscription_id": "sub_123"},
    )

    captured = {}

    class _Item:
        id = "si_metered_1"

    def _fake_create(**kwargs):
        captured.update(kwargs)
        return _Item()

    monkeypatch.setattr(stripe_billing.stripe.SubscriptionItem, "create", _fake_create)

    principal = _principal(["admin"])
    response = await stripe_billing.opt_in_metered_usage(tenant_id=None, x_tenant_id=None, principal=principal)

    assert captured["subscription"] == "sub_123"
    assert captured["price"] == "price_metered_1"
    assert response["metered_billing_enabled"] is True
    assert response["subscription_item_id"] == "si_metered_1"

    mapping = stripe_billing._get_subscription_mapping(TENANT_ID)
    assert mapping["metered_billing_enabled"] == "true"
    assert mapping["metered_subscription_item_id"] == "si_metered_1"


@pytest.mark.asyncio
async def test_opt_in_rejects_viewer_role(monkeypatch):
    fake_redis = _FakeRedis()
    monkeypatch.setattr(stripe_billing, "_redis_client", lambda: fake_redis)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")

    principal = _principal(["billing.usage.manage"])  # no admin/operator suffix => viewer role

    with pytest.raises(Exception) as exc_info:
        await stripe_billing.opt_in_metered_usage(tenant_id=None, x_tenant_id=None, principal=principal)
    assert getattr(exc_info.value, "status_code", None) == 403


# ---------------------------------------------------------------------------
# DELETE /usage/opt-in
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_opt_out_removes_subscription_item_and_clears_flag(monkeypatch):
    fake_redis = _FakeRedis()
    monkeypatch.setattr(stripe_billing, "_redis_client", lambda: fake_redis)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")

    stripe_billing._store_subscription_mapping(
        TENANT_ID,
        {
            "plan_id": "growth",
            "subscription_id": "sub_123",
            "metered_billing_enabled": "true",
            "metered_subscription_item_id": "si_metered_1",
        },
    )

    deleted = {}
    monkeypatch.setattr(
        stripe_billing.stripe.SubscriptionItem,
        "delete",
        lambda item_id: deleted.setdefault("id", item_id),
    )

    principal = _principal(["admin"])
    response = await stripe_billing.opt_out_metered_usage(tenant_id=None, x_tenant_id=None, principal=principal)

    assert deleted["id"] == "si_metered_1"
    assert response["metered_billing_enabled"] is False

    mapping = stripe_billing._get_subscription_mapping(TENANT_ID)
    assert mapping["metered_billing_enabled"] == "false"
    assert mapping["metered_subscription_item_id"] == ""


@pytest.mark.asyncio
async def test_opt_out_is_idempotent_when_not_previously_opted_in(monkeypatch):
    fake_redis = _FakeRedis()
    monkeypatch.setattr(stripe_billing, "_redis_client", lambda: fake_redis)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")

    stripe_billing._store_subscription_mapping(TENANT_ID, {"plan_id": "growth", "subscription_id": "sub_123"})

    def _fail_delete(item_id):
        raise AssertionError("should not attempt to delete a subscription item that was never stored")

    monkeypatch.setattr(stripe_billing.stripe.SubscriptionItem, "delete", _fail_delete)

    principal = _principal(["admin"])
    response = await stripe_billing.opt_out_metered_usage(tenant_id=None, x_tenant_id=None, principal=principal)

    assert response["metered_billing_enabled"] is False
