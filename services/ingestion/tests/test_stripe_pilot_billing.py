"""Pilot checkout + webhook + A-2159 credit coverage (A-2155/A-2159).

All Stripe interactions are monkeypatched. No live Stripe calls, no keys.

Covers:
1. pilot checkout is ``mode=payment``, quantity 1, with variant metadata
   (including the convert_30 conversion window);
2. list checkout still bills ``facility_count`` as the subscription quantity;
3. subscription checkout persists ``facility_quantity`` from the item quantity;
4. settled pilot payment stores fee/variant/status/90-day period end;
5. unsettled pilot payment stores a non-entitling status;
6. the A-2159 customer-balance credit is applied once and is idempotent;
7. unverifiable/mismatched plan metadata still fails closed;
8. catalog pricing (999/499, no annual, no invented tiers) and EPCIS Preview
   remain intact.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import pytest
import stripe

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app import (
    subscription_gate as gate_mod,  # noqa: E402
    supplier_portal,  # noqa: E402
)
from app.authz import IngestionPrincipal  # noqa: E402
from app.stripe_billing import (  # noqa: E402
    customers as customers_mod,
    helpers as helpers_mod,
    plans as plans_mod,
    routes as routes_mod,
    state as state_mod,
    webhooks as webhooks_mod,
)
from app.stripe_billing.models import CheckoutRequest  # noqa: E402
from shared.circuit_breaker import redis_circuit  # noqa: E402

# ── Shared fakes/fixtures ──────────────────────────────────────────────────


class _FakeRedis:
    """Minimal in-memory stand-in for the state module's Redis calls."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.hashes: dict[str, dict[str, str]] = {}

    def get(self, key: str) -> Optional[str]:
        return self.values.get(key)

    def set(self, key: str, value: str, **_: Any) -> bool:
        self.values[key] = value
        return True

    def hset(self, key: str, mapping: dict[str, str]) -> None:
        self.hashes.setdefault(key, {}).update(mapping)

    def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.hashes.get(key, {}))

    def delete(self, key: str) -> int:
        existed = key in self.values or key in self.hashes
        self.values.pop(key, None)
        self.hashes.pop(key, None)
        return 1 if existed else 0

    def getdel(self, key: str) -> Optional[str]:
        return self.values.pop(key, None)


@pytest.fixture(autouse=True)
def _stub_configure_stripe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(helpers_mod, "_configure_stripe", lambda: None)


@pytest.fixture(autouse=True)
def _stub_funnel(monkeypatch: pytest.MonkeyPatch) -> None:
    import shared.funnel_events as funnel_events

    monkeypatch.setattr(funnel_events, "emit_funnel_event", lambda **_: True)


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> _FakeRedis:
    fake = _FakeRedis()
    monkeypatch.setattr(state_mod, "_redis_client", lambda: fake)
    return fake


def _principal(tenant_id: str = "tenant-pilot") -> IngestionPrincipal:
    return IngestionPrincipal(key_id="test-key", scopes=["*"], tenant_id=tenant_id, auth_mode="test")


def _capture_checkout(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    class _Session:
        id = "cs_pilot_test"
        url = "https://checkout.stripe.com/c/pay/cs_pilot_test"

    def _create(**kwargs: Any) -> _Session:
        captured.update(kwargs)
        return _Session()

    monkeypatch.setattr(stripe.checkout.Session, "create", _create)
    monkeypatch.setattr(customers_mod, "_get_existing_customer_id", lambda _tenant_id: None)
    monkeypatch.setattr(customers_mod, "_record_checkout_session_hint", lambda **_kwargs: None)
    return captured


# ── 1. Pilot checkout ──────────────────────────────────────────────────────


class TestPilotCheckout:
    @pytest.mark.asyncio
    async def test_standard_pilot_is_payment_mode_quantity_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("STRIPE_PRICE_PILOT_STANDARD", "price_pilot_standard")
        captured = _capture_checkout(monkeypatch)

        response = await routes_mod.create_checkout(
            CheckoutRequest(plan_id="pilot", facility_count=8),
            x_tenant_id=None,
            principal=_principal("tenant-pilot"),
        )

        assert captured["mode"] == "payment"
        assert captured["line_items"] == [{"price": "price_pilot_standard", "quantity": 1}]
        # Pilot must never create a subscription or attach subscription_data.
        assert "subscription_data" not in captured
        assert captured["metadata"]["plan_id"] == "pilot"
        assert captured["metadata"]["pilot_variant"] == "standard"
        assert captured["metadata"]["facility_quantity"] == "1"
        assert captured["metadata"]["tenant_id"] == "tenant-pilot"
        assert "pilot_convert_window_days" not in captured["metadata"]

        assert response.plan == "pilot"
        assert response.billing_period == "one_time"
        assert response.amount == plans_mod.PILOT_FEE_STANDARD_CENTS // 100 == 2000
        assert response.facility_quantity == 1

    @pytest.mark.asyncio
    async def test_convert_30_pilot_includes_window_and_1500_amount(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("STRIPE_PRICE_PILOT_CONVERT_30", "price_pilot_convert")
        captured = _capture_checkout(monkeypatch)

        response = await routes_mod.create_checkout(
            CheckoutRequest(plan_id="pilot", pilot_variant="convert_30"),
            x_tenant_id=None,
            principal=_principal("tenant-pilot-convert"),
        )

        assert captured["mode"] == "payment"
        assert captured["line_items"] == [{"price": "price_pilot_convert", "quantity": 1}]
        assert captured["metadata"]["plan_id"] == "pilot"
        assert captured["metadata"]["pilot_variant"] == "convert_30"
        assert captured["metadata"]["pilot_convert_window_days"] == "30"
        assert response.plan == "pilot"
        assert response.billing_period == "one_time"
        assert response.amount == plans_mod.PILOT_FEE_CONVERT_30_CENTS // 100 == 1500
        assert response.facility_quantity == 1

    @pytest.mark.asyncio
    async def test_unknown_pilot_variant_is_rejected_before_stripe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = _capture_checkout(monkeypatch)

        with pytest.raises(Exception) as excinfo:
            await routes_mod.create_checkout(
                CheckoutRequest(plan_id="pilot", pilot_variant="bogus"),
                x_tenant_id=None,
                principal=_principal(),
            )

        assert getattr(excinfo.value, "status_code", None) == 400
        assert captured == {}

    @pytest.mark.asyncio
    async def test_list_plan_still_bills_facility_count(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Regression: pilot handling must not change the list/founding path."""
        monkeypatch.setenv("STRIPE_PRICE_LIST_MONTHLY", "price_list_monthly")
        captured = _capture_checkout(monkeypatch)

        response = await routes_mod.create_checkout(
            CheckoutRequest(plan_id="list", billing_period="monthly", facility_count=7),
            x_tenant_id=None,
            principal=_principal("tenant-list"),
        )

        assert captured["mode"] == "subscription"
        assert captured["line_items"] == [{"price": "price_list_monthly", "quantity": 7}]
        assert captured["metadata"]["plan_id"] == "list"
        assert captured["metadata"]["facility_quantity"] == "7"
        assert captured["subscription_data"]["metadata"]["facility_quantity"] == "7"
        assert response.plan == "list"
        assert response.amount == 999
        assert response.facility_quantity == 7


# ── 2. Webhook: facility quantity ──────────────────────────────────────────


class TestWebhookFacilityQuantity:
    @pytest.mark.asyncio
    async def test_subscription_checkout_prefers_item_quantity(
        self, monkeypatch: pytest.MonkeyPatch, fake_redis: _FakeRedis
    ) -> None:
        monkeypatch.setenv("STRIPE_PRICE_LIST_MONTHLY", "price_list_monthly")
        fake_redis.values["billing:session:cs_facility"] = "tenant-facility"

        monkeypatch.setattr(
            stripe.Subscription,
            "retrieve",
            lambda _sid: {
                "status": "active",
                "items": {
                    "data": [
                        {
                            "price": {"id": "price_list_monthly"},
                            "quantity": 7,
                            "current_period_end": 1_800_000_000,
                        }
                    ]
                },
            },
        )

        await webhooks_mod._handle_checkout_completed(
            {
                "id": "cs_facility",
                "customer": "cus_facility",
                "subscription": "sub_facility",
                "mode": "subscription",
                "payment_status": "paid",
                "metadata": {
                    "plan_id": "list",
                    "billing_period": "monthly",
                    # Claimed metadata must lose to Stripe's item quantity.
                    "facility_quantity": "2",
                },
            },
            event_created=100,
        )

        mapping = fake_redis.hashes["billing:tenant:tenant-facility"]
        assert mapping["facility_quantity"] == "7"
        assert mapping["status"] == "active"

    @pytest.mark.asyncio
    async def test_subscription_updated_refreshes_facility_quantity(
        self, monkeypatch: pytest.MonkeyPatch, fake_redis: _FakeRedis
    ) -> None:
        monkeypatch.setenv("STRIPE_PRICE_LIST_MONTHLY", "price_list_monthly")
        fake_redis.hashes["billing:tenant:tenant-facility"] = {
            "tenant_id": "tenant-facility",
            "subscription_id": "sub_facility",
            "customer_id": "cus_facility",
            "plan_id": "list",
            "billing_period": "monthly",
            "status": "active",
            "facility_quantity": "2",
            "last_event_created": "100",
        }
        fake_redis.values["billing:subscription:sub_facility"] = "tenant-facility"
        fake_redis.values["billing:customer:cus_facility"] = "tenant-facility"

        await webhooks_mod._handle_stripe_event(
            {
                "id": "evt_facility_update",
                "type": "customer.subscription.updated",
                "created": 200,
                "data": {
                    "object": {
                        "id": "sub_facility",
                        "customer": "cus_facility",
                        "status": "active",
                        "items": {"data": [{"price": {"id": "price_list_monthly"}, "quantity": 5}]},
                    }
                },
            }
        )

        assert fake_redis.hashes["billing:tenant:tenant-facility"]["facility_quantity"] == "5"


# ── 3. Webhook: pilot payment ──────────────────────────────────────────────


class TestPilotWebhook:
    @pytest.mark.asyncio
    async def test_settled_convert_pilot_entitles_for_90_days(
        self, monkeypatch: pytest.MonkeyPatch, fake_redis: _FakeRedis
    ) -> None:
        fake_redis.values["billing:session:cs_pilot_paid"] = "tenant-pilot-paid"
        created = 1_700_000_000

        await webhooks_mod._handle_checkout_completed(
            {
                "id": "cs_pilot_paid",
                "customer": "cus_pilot_paid",
                "subscription": None,
                "mode": "payment",
                "payment_status": "paid",
                "amount_total": 150_000,
                "created": created,
                "metadata": {"plan_id": "pilot", "pilot_variant": "convert_30"},
            },
            event_created=created + 10,
        )

        mapping = fake_redis.hashes["billing:tenant:tenant-pilot-paid"]
        assert mapping["plan_id"] == "pilot"
        assert mapping["billing_period"] == "one_time"
        assert mapping["status"] == "pilot_active"
        assert mapping["pilot_fee_cents"] == "150000"
        assert mapping["pilot_amount_paid_cents"] == "150000"
        assert mapping["pilot_payment_settled"] == "true"
        assert mapping["pilot_session_id"] == "cs_pilot_paid"
        assert mapping["pilot_variant"] == "convert_30"
        assert mapping["pilot_credit_applied"] == "false"
        assert mapping["facility_quantity"] == "1"
        assert mapping["current_period_end"] == helpers_mod._format_period_end(
            created + plans_mod.PILOT_DURATION_DAYS * 86400
        )
        assert mapping["pilot_convert_window_end"] == helpers_mod._format_period_end(
            created + plans_mod.PILOT_CONVERT_WINDOW_DAYS * 86400
        )
        assert "pilot_active" in webhooks_mod._ENTITLING_STATUSES

    @pytest.mark.asyncio
    async def test_unsettled_pilot_payment_is_incomplete(
        self, monkeypatch: pytest.MonkeyPatch, fake_redis: _FakeRedis
    ) -> None:
        fake_redis.values["billing:session:cs_pilot_unpaid"] = "tenant-pilot-unpaid"

        await webhooks_mod._handle_checkout_completed(
            {
                "id": "cs_pilot_unpaid",
                "customer": "cus_pilot_unpaid",
                "subscription": None,
                "mode": "payment",
                "payment_status": "unpaid",
                "amount_total": 200_000,
                "metadata": {"plan_id": "pilot", "pilot_variant": "standard"},
            },
            event_created=100,
        )

        mapping = fake_redis.hashes["billing:tenant:tenant-pilot-unpaid"]
        assert mapping["status"] == "incomplete"
        assert mapping["status"] not in webhooks_mod._ENTITLING_STATUSES
        assert mapping["current_period_end"] == ""
        assert mapping["pilot_fee_cents"] == "200000"
        assert mapping["pilot_payment_settled"] == "false"
        assert mapping["pilot_amount_paid_cents"] == "200000"

    @pytest.mark.asyncio
    async def test_async_payment_succeeded_promotes_pilot(
        self, monkeypatch: pytest.MonkeyPatch, fake_redis: _FakeRedis
    ) -> None:
        fake_redis.values["billing:session:cs_pilot_async"] = "tenant-pilot-async"
        unpaid_session = {
            "id": "cs_pilot_async",
            "customer": "cus_pilot_async",
            "subscription": None,
            "mode": "payment",
            "payment_status": "unpaid",
            "amount_total": 200_000,
            "metadata": {"plan_id": "pilot", "pilot_variant": "standard"},
        }
        await webhooks_mod._handle_stripe_event(
            {"id": "evt_pilot_1", "type": "checkout.session.completed", "created": 100, "data": {"object": unpaid_session}}
        )
        assert fake_redis.hashes["billing:tenant:tenant-pilot-async"]["status"] == "incomplete"

        paid_session = {**unpaid_session, "payment_status": "paid"}
        await webhooks_mod._handle_stripe_event(
            {
                "id": "evt_pilot_2",
                "type": "checkout.session.async_payment_succeeded",
                "created": 200,
                "data": {"object": paid_session},
            }
        )
        assert fake_redis.hashes["billing:tenant:tenant-pilot-async"]["status"] == "pilot_active"

    @pytest.mark.asyncio
    async def test_duplicate_pilot_event_does_not_reset_applied_credit(
        self, monkeypatch: pytest.MonkeyPatch, fake_redis: _FakeRedis
    ) -> None:
        fake_redis.values["billing:session:cs_pilot_retry"] = "tenant-pilot-retry"
        fake_redis.hashes["billing:tenant:tenant-pilot-retry"] = {
            "tenant_id": "tenant-pilot-retry",
            "pilot_session_id": "cs_pilot_retry",
            "pilot_fee_cents": "150000",
            "pilot_payment_settled": "true",
            "pilot_amount_paid_cents": "150000",
            "pilot_credit_applied": "true",
            "status": "pilot_active",
        }

        await webhooks_mod._handle_checkout_completed(
            {
                "id": "cs_pilot_retry",
                "customer": "cus_pilot_retry",
                "subscription": None,
                "mode": "payment",
                "payment_status": "paid",
                "amount_total": 150_000,
                "metadata": {"plan_id": "pilot", "pilot_variant": "convert_30"},
            },
            event_created=600,
        )

        assert fake_redis.hashes["billing:tenant:tenant-pilot-retry"]["pilot_credit_applied"] == "true"


# ── 4. A-2159 credit ───────────────────────────────────────────────────────


class TestPilotCredit:
    @pytest.mark.asyncio
    async def test_credit_is_applied_once_with_negative_amount(
        self, monkeypatch: pytest.MonkeyPatch, fake_redis: _FakeRedis
    ) -> None:
        calls: list[tuple[str, dict[str, Any]]] = []

        def _create_balance_transaction(customer_id: str, **kwargs: Any) -> dict[str, Any]:
            calls.append((customer_id, kwargs))
            return {"id": "cbtxn_test"}

        monkeypatch.setattr(stripe.Customer, "create_balance_transaction", _create_balance_transaction)

        mapping = {
            "tenant_id": "tenant-credit",
            "customer_id": "cus_credit",
            "pilot_fee_cents": "150000",
            "pilot_credit_applied": "false",
        }

        assert webhooks_mod._apply_pilot_credit_if_eligible("tenant-credit", "cus_credit", mapping) is True
        assert calls == [
            (
                "cus_credit",
                {
                    "amount": -150_000,
                    "currency": "usd",
                    "description": "RegEngine pilot fee credit (A-2159)",
                },
            )
        ]
        assert mapping["pilot_credit_applied"] == "true"
        assert fake_redis.hashes["billing:tenant:tenant-credit"]["pilot_credit_applied"] == "true"

        # Second invocation (including a fresh read of the persisted mapping)
        # must be a no-op.
        fresh = state_mod._get_subscription_mapping("tenant-credit")
        assert webhooks_mod._apply_pilot_credit_if_eligible("tenant-credit", "cus_credit", fresh) is False
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_credit_stripe_error_leaves_flag_unapplied(
        self, monkeypatch: pytest.MonkeyPatch, fake_redis: _FakeRedis
    ) -> None:
        calls: list[Any] = []

        def _fail(*args: Any, **kwargs: Any) -> None:
            calls.append((args, kwargs))
            raise stripe.error.StripeError("stripe unavailable")

        monkeypatch.setattr(stripe.Customer, "create_balance_transaction", _fail)
        mapping = {
            "tenant_id": "tenant-credit-fail",
            "customer_id": "cus_credit_fail",
            "pilot_fee_cents": "200000",
        }

        assert webhooks_mod._apply_pilot_credit_if_eligible("tenant-credit-fail", "cus_credit_fail", mapping) is False
        assert len(calls) == 1
        assert mapping.get("pilot_credit_applied") != "true"
        assert "billing:tenant:tenant-credit-fail" not in fake_redis.hashes

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "mapping",
        [
            # Delayed payment never settled.
            {"pilot_fee_cents": "150000", "pilot_payment_settled": "false"},
            # 100%-promo pilot: catalog fee recorded, but nothing collected.
            {
                "pilot_fee_cents": "150000",
                "pilot_payment_settled": "true",
                "pilot_amount_paid_cents": "0",
            },
            # convert_30's 30-day conversion window already elapsed.
            {
                "pilot_fee_cents": "150000",
                "pilot_payment_settled": "true",
                "pilot_amount_paid_cents": "150000",
                "pilot_convert_window_end": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            },
        ],
    )
    async def test_credit_skips_unsettled_zero_or_expired_window(
        self, monkeypatch: pytest.MonkeyPatch, fake_redis: _FakeRedis, mapping: dict[str, str]
    ) -> None:
        calls: list[Any] = []
        monkeypatch.setattr(
            stripe.Customer,
            "create_balance_transaction",
            lambda *args, **kwargs: calls.append((args, kwargs)),
        )

        assert webhooks_mod._apply_pilot_credit_if_eligible("tenant-skip", "cus_skip", dict(mapping)) is False
        assert calls == []

    @pytest.mark.asyncio
    async def test_subscription_checkout_applies_prior_pilot_credit_once(
        self, monkeypatch: pytest.MonkeyPatch, fake_redis: _FakeRedis
    ) -> None:
        monkeypatch.setenv("STRIPE_PRICE_LIST_MONTHLY", "price_list_monthly")
        fake_redis.values["billing:session:cs_convert"] = "tenant-convert"
        fake_redis.values["billing:customer:cus_convert"] = "tenant-convert"
        fake_redis.hashes["billing:tenant:tenant-convert"] = {
            "tenant_id": "tenant-convert",
            "customer_id": "cus_convert",
            "plan_id": "pilot",
            "status": "pilot_active",
            "pilot_fee_cents": "150000",
            "pilot_variant": "convert_30",
            "pilot_credit_applied": "false",
            "facility_quantity": "1",
        }
        calls: list[tuple[str, dict[str, Any]]] = []

        def _create_balance_transaction(customer_id: str, **kwargs: Any) -> dict[str, Any]:
            calls.append((customer_id, kwargs))
            return {"id": "cbtxn_convert"}

        monkeypatch.setattr(stripe.Customer, "create_balance_transaction", _create_balance_transaction)
        monkeypatch.setattr(
            stripe.Subscription,
            "retrieve",
            lambda _sid: {
                "status": "active",
                "items": {"data": [{"price": {"id": "price_list_monthly"}, "quantity": 3, "current_period_end": 1_800_000_000}]},
            },
        )

        await webhooks_mod._handle_checkout_completed(
            {
                "id": "cs_convert",
                "customer": "cus_convert",
                "subscription": "sub_convert",
                "mode": "subscription",
                "payment_status": "paid",
                "metadata": {"plan_id": "list", "billing_period": "monthly", "facility_quantity": "3"},
            },
            event_created=300,
        )

        mapping = fake_redis.hashes["billing:tenant:tenant-convert"]
        assert calls == [
            (
                "cus_convert",
                {
                    "amount": -150_000,
                    "currency": "usd",
                    "description": "RegEngine pilot fee credit (A-2159)",
                },
            )
        ]
        assert mapping["pilot_credit_applied"] == "true"
        assert mapping["plan_id"] == "list"

        # A duplicate/retried checkout must not credit twice.
        await webhooks_mod._handle_checkout_completed(
            {
                "id": "cs_convert",
                "customer": "cus_convert",
                "subscription": "sub_convert",
                "mode": "subscription",
                "payment_status": "paid",
                "metadata": {"plan_id": "list", "billing_period": "monthly", "facility_quantity": "3"},
            },
            event_created=301,
        )
        assert len(calls) == 1


# ── 4b. Pilot entitlement expiry ───────────────────────────────────────────


class _GateRedis:
    def __init__(self, mapping: dict[str, str]) -> None:
        self.mapping = mapping

    def hget(self, _key: str, field: str) -> Optional[str]:
        return self.mapping.get(field)


class TestPilotEntitlementExpiry:
    def _check(self, monkeypatch: pytest.MonkeyPatch, mapping: dict[str, str]) -> tuple[Optional[str], bool]:
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setattr(gate_mod, "_get_redis_client", lambda _url: _GateRedis(mapping))
        redis_circuit.reset()
        try:
            return gate_mod._check_subscription_and_redis_health("tenant-pilot-gate")
        finally:
            redis_circuit.reset()

    def test_current_pilot_is_allowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mapping = {
            "status": "pilot_active",
            "current_period_end": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        }
        assert self._check(monkeypatch, mapping) == ("pilot_active", True)

    def test_expired_pilot_is_downgraded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mapping = {
            "status": "pilot_active",
            "current_period_end": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        }
        assert self._check(monkeypatch, mapping) == ("pilot_expired", True)

    def test_missing_period_end_fails_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert self._check(monkeypatch, {"status": "pilot_active"}) == ("pilot_expired", True)

    def test_supplier_portal_accepts_live_pilot_and_rejects_expired(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setattr(
            gate_mod,
            "_check_subscription_and_redis_health",
            lambda _tenant_id: ("pilot_active", True),
        )
        assert supplier_portal._portal_subscription_active("tenant-pilot") is True

        monkeypatch.setattr(
            gate_mod,
            "_check_subscription_and_redis_health",
            lambda _tenant_id: ("pilot_expired", True),
        )
        assert supplier_portal._portal_subscription_active("tenant-pilot") is False


# ── 5. Fail-closed plan verification + catalog regression ─────────────────


class TestPlanVerificationAndCatalog:
    @pytest.mark.asyncio
    async def test_unverifiable_plan_metadata_fails_closed(
        self, monkeypatch: pytest.MonkeyPatch, fake_redis: _FakeRedis
    ) -> None:
        monkeypatch.setenv("STRIPE_PRICE_LIST_MONTHLY", "price_list_monthly")
        fake_redis.values["billing:session:cs_unverifiable"] = "tenant-unverifiable"
        monkeypatch.setattr(
            stripe.Subscription,
            "retrieve",
            lambda _sid: {
                "status": "active",
                "items": {"data": [{"price": {"id": "price_not_in_catalog"}, "quantity": 1}]},
            },
        )

        await webhooks_mod._handle_checkout_completed(
            {
                "id": "cs_unverifiable",
                "customer": "cus_unverifiable",
                "subscription": "sub_unverifiable",
                "mode": "subscription",
                "payment_status": "paid",
                "metadata": {"plan_id": "list", "billing_period": "monthly"},
            },
            event_created=400,
        )

        mapping = fake_redis.hashes["billing:tenant:tenant-unverifiable"]
        assert mapping["plan_id"] == ""
        assert mapping["status"] == "incomplete"

    @pytest.mark.asyncio
    async def test_claimed_plan_mismatch_stores_stripe_truth(
        self, monkeypatch: pytest.MonkeyPatch, fake_redis: _FakeRedis
    ) -> None:
        """Existing H2 behavior: the paid Price wins over metadata claims."""
        monkeypatch.setenv("STRIPE_PRICE_FOUNDING_MONTHLY", "price_founding_monthly")
        fake_redis.values["billing:session:cs_claim"] = "tenant-claim"
        monkeypatch.setattr(
            stripe.Subscription,
            "retrieve",
            lambda _sid: {
                "status": "active",
                "items": {"data": [{"price": {"id": "price_founding_monthly"}, "quantity": 1, "current_period_end": 1_800_000_000}]},
            },
        )

        await webhooks_mod._handle_checkout_completed(
            {
                "id": "cs_claim",
                "customer": "cus_claim",
                "subscription": "sub_claim",
                "mode": "subscription",
                "payment_status": "paid",
                "metadata": {"plan_id": "list", "billing_period": "monthly"},
            },
            event_created=500,
        )

        mapping = fake_redis.hashes["billing:tenant:tenant-claim"]
        assert mapping["plan_id"] == "founding"
        assert mapping["status"] == "active"

    def test_prices_unchanged_no_invented_tiers(self) -> None:
        assert plans_mod.PLANS["list"]["price_monthly"] == 999
        assert plans_mod.PLANS["founding"]["price_monthly"] == 499
        assert plans_mod.PLANS["list"]["price_annual"] is None
        assert plans_mod.PLANS["founding"]["price_annual"] is None
        assert plans_mod.PILOT_FEE_STANDARD_CENTS == 200000
        assert plans_mod.PILOT_FEE_CONVERT_30_CENTS == 150000

        amounts = {
            value
            for plan in plans_mod.PLANS.values()
            for value in (plan["price_monthly"], plan["price_annual"])
            if value is not None
        }
        assert 1999 not in amounts
        assert 1666 not in amounts
        assert 832 not in amounts

    def test_epcis_preview_still_advertised(self) -> None:
        for plan_id in ("list", "founding", "enterprise"):
            features = plans_mod.PLANS[plan_id]["features"]
            assert any("EPCIS 1.2 export (Preview)" in feature for feature in features)
