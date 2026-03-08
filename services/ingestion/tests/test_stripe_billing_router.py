"""Unit tests for Stripe billing router helpers."""

import sys
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app import stripe_billing


class _FakeRedis:
    def __init__(self):
        self.hashes: dict[str, dict[str, str]] = {}
        self.values: dict[str, str] = {}

    def hset(self, key: str, mapping: dict[str, str]):
        self.hashes.setdefault(key, {})
        self.hashes[key].update(mapping)

    def hgetall(self, key: str):
        return dict(self.hashes.get(key, {}))

    def set(self, key: str, value: str):
        self.values[key] = value

    def get(self, key: str):
        return self.values.get(key)


@pytest.mark.asyncio
async def test_create_checkout_uses_stripe_and_normalizes_plan(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_PRICE_GROWTH_MONTHLY", "price_growth_monthly")

    captured = {}

    class _Session:
        id = "cs_test_123"
        url = "https://checkout.stripe.com/c/pay/cs_test_123"

    def _fake_create(**kwargs):
        captured.update(kwargs)
        return _Session()

    monkeypatch.setattr(stripe_billing.stripe.checkout.Session, "create", _fake_create)

    response = await stripe_billing.create_checkout(
        stripe_billing.CheckoutRequest(
            plan_id="starter",  # legacy alias
            billing_period="monthly",
            tenant_id="tenant-1",
            tenant_name="Acme Foods",
            customer_email="ops@example.com",
        )
    )

    assert response.session_id == "cs_test_123"
    assert response.plan == "growth"
    assert captured["line_items"][0]["price"] == "price_growth_monthly"
    assert captured["metadata"]["tenant_id"] == "tenant-1"
    assert captured["metadata"]["plan_id"] == "growth"


@pytest.mark.asyncio
async def test_checkout_webhook_provisions_tenant_and_stores_mapping(monkeypatch):
    fake_redis = _FakeRedis()
    monkeypatch.setattr(stripe_billing, "_redis_client", lambda: fake_redis)

    async def _fake_create_tenant(name: str) -> str:
        assert name == "Acme Foods"
        return "tenant-123"

    monkeypatch.setattr(stripe_billing, "_create_tenant_via_admin", _fake_create_tenant)
    monkeypatch.setattr(
        stripe_billing.stripe.Subscription,
        "retrieve",
        lambda _: {"status": "active", "current_period_end": 1700000000},
    )

    await stripe_billing._handle_checkout_completed(
        {
            "id": "cs_1",
            "subscription": "sub_1",
            "customer": "cus_1",
            "customer_email": "buyer@example.com",
            "metadata": {
                "plan_id": "growth",
                "billing_period": "monthly",
                "tenant_name": "Acme Foods",
            },
        }
    )

    mapping = fake_redis.hgetall(stripe_billing._tenant_subscription_key("tenant-123"))
    assert mapping["tenant_id"] == "tenant-123"
    assert mapping["plan_id"] == "growth"
    assert mapping["subscription_id"] == "sub_1"
    assert mapping["customer_id"] == "cus_1"
    assert fake_redis.get(stripe_billing._subscription_lookup_key("sub_1")) == "tenant-123"


@pytest.mark.asyncio
async def test_invoice_payment_failed_marks_subscription_past_due(monkeypatch):
    fake_redis = _FakeRedis()
    monkeypatch.setattr(stripe_billing, "_redis_client", lambda: fake_redis)

    stripe_billing._store_subscription_mapping(
        "tenant-999",
        {
            "tenant_id": "tenant-999",
            "session_id": "cs_999",
            "customer_id": "cus_999",
            "subscription_id": "sub_999",
            "plan_id": "scale",
            "billing_period": "monthly",
            "status": "active",
            "customer_email": "buyer@example.com",
            "current_period_end": "",
        },
    )

    await stripe_billing._handle_stripe_event(
        {
            "type": "invoice.payment_failed",
            "data": {
                "object": {
                    "subscription": "sub_999",
                    "customer": "cus_999",
                }
            },
        }
    )

    mapping = fake_redis.hgetall(stripe_billing._tenant_subscription_key("tenant-999"))
    assert mapping["status"] == "past_due"
