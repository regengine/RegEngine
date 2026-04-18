"""Regression tests for #1184 — Stripe checkout / webhook tenant integrity.

Verifies:
1. ``create_checkout`` derives ``tenant_id`` from the authenticated
   principal / ``X-Tenant-ID`` header and ignores the client-supplied
   ``request.tenant_id``.
2. ``_handle_checkout_completed`` trusts the server-side session map
   before ``metadata.tenant_id`` and raises if the two disagree.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app import stripe_billing
from app.authz import IngestionPrincipal
from app.stripe_billing import webhooks as webhooks_mod
from fastapi import HTTPException


class _FakeRedis:
    def __init__(self):
        self.hashes: dict[str, dict[str, str]] = {}
        self.values: dict[str, str] = {}

    def hset(self, key: str, mapping: dict[str, str]):
        self.hashes.setdefault(key, {}).update(mapping)

    def hgetall(self, key: str):
        return dict(self.hashes.get(key, {}))

    def set(self, key: str, value: str):
        self.values[key] = value

    def get(self, key: str):
        return self.values.get(key)


# ---------------------------------------------------------------------------
# create_checkout ignores client-supplied tenant_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_checkout_ignores_client_tenant_id(monkeypatch):
    """Client sends ``tenant_id=victim``; authenticated principal is attacker.
    The checkout session metadata must carry the authenticated tenant."""
    fake_redis = _FakeRedis()
    monkeypatch.setattr(stripe_billing, "_redis_client", lambda: fake_redis)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_PRICE_GROWTH_MONTHLY", "price_growth_monthly")

    captured: dict = {}

    class _Session:
        id = "cs_test_456"
        url = "https://checkout.stripe.com/c/pay/cs_test_456"

    def _fake_create(**kwargs):
        captured.update(kwargs)
        return _Session()

    monkeypatch.setattr(stripe_billing.stripe.checkout.Session, "create", _fake_create)
    monkeypatch.setattr(
        stripe_billing,
        "emit_funnel_event",
        lambda **kwargs: True,
    )

    attacker = IngestionPrincipal(
        tenant_id="attacker-tenant",
        scopes=["billing.read"],
        key_id="key-attacker",
    )

    await stripe_billing.create_checkout(
        stripe_billing.CheckoutRequest(
            plan_id="growth",
            billing_period="monthly",
            tenant_id="victim-tenant",  # attacker's attempt
            customer_email="attacker@example.com",
        ),
        x_tenant_id=None,
        principal=attacker,
    )

    metadata = captured["metadata"]
    assert metadata["tenant_id"] == "attacker-tenant"
    # victim-tenant must NEVER appear in what we send to Stripe.
    assert "victim-tenant" not in str(metadata)


@pytest.mark.asyncio
async def test_create_checkout_unauthenticated_allowed_without_tenant(monkeypatch):
    """Self-serve signup (no principal) still allowed — tenant gets
    provisioned at webhook time, not bound from client metadata."""
    fake_redis = _FakeRedis()
    monkeypatch.setattr(stripe_billing, "_redis_client", lambda: fake_redis)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_PRICE_GROWTH_MONTHLY", "price_growth_monthly")

    captured: dict = {}

    class _Session:
        id = "cs_test_789"
        url = "https://checkout.stripe.com/c/pay/cs_test_789"

    def _fake_create(**kwargs):
        captured.update(kwargs)
        return _Session()

    monkeypatch.setattr(stripe_billing.stripe.checkout.Session, "create", _fake_create)
    monkeypatch.setattr(
        stripe_billing,
        "emit_funnel_event",
        lambda **kwargs: True,
    )

    await stripe_billing.create_checkout(
        stripe_billing.CheckoutRequest(
            plan_id="growth",
            billing_period="monthly",
            tenant_id="some-tenant",  # should be ignored
            customer_email="newuser@example.com",
        ),
        x_tenant_id=None,
        principal=None,
    )

    metadata = captured["metadata"]
    # No authenticated tenant => no tenant_id in metadata at all.
    assert "tenant_id" not in metadata
    # client-supplied tenant never copied in
    assert "some-tenant" not in str(metadata)


# ---------------------------------------------------------------------------
# Webhook: server-side tenant beats metadata
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_rejects_metadata_tenant_mismatch(monkeypatch):
    """Webhook sees metadata.tenant_id != server-side binding -> 400."""
    fake_redis = _FakeRedis()

    # Server bound this session to "real-tenant" at checkout creation.
    fake_redis.values["billing:session:cs_test_999"] = "real-tenant"

    monkeypatch.setattr(webhooks_mod._state_mod, "_redis_client", lambda: fake_redis)

    session = {
        "id": "cs_test_999",
        "customer": "cus_abc",
        "subscription": None,
        "customer_email": "whoever@example.com",
        "metadata": {
            "tenant_id": "hijack-tenant",  # attacker-injected
            "plan_id": "growth",
            "billing_period": "monthly",
        },
    }

    with pytest.raises(HTTPException) as exc:
        await webhooks_mod._handle_checkout_completed(session)
    assert exc.value.status_code == 400
    assert "tenant_id does not match" in exc.value.detail


@pytest.mark.asyncio
async def test_webhook_prefers_customer_mapping_over_metadata(monkeypatch):
    """If only the customer-id mapping exists (re-subscribe flow) it wins
    over any metadata claim."""
    fake_redis = _FakeRedis()
    fake_redis.values["billing:customer:cus_bound"] = "existing-tenant"

    monkeypatch.setattr(webhooks_mod._state_mod, "_redis_client", lambda: fake_redis)
    monkeypatch.setattr(
        webhooks_mod._state_mod,
        "_store_subscription_mapping",
        lambda tid, mapping: fake_redis.hset(f"billing:tenant:{tid}", mapping),
    )

    # No subscription fetch needed — subscription_id is None.
    session = {
        "id": "cs_new",
        "customer": "cus_bound",
        "subscription": None,
        "customer_email": "ops@example.com",
        "metadata": {
            "tenant_id": "attacker-tenant",
            "plan_id": "growth",
            "billing_period": "monthly",
        },
    }

    with pytest.raises(HTTPException) as exc:
        await webhooks_mod._handle_checkout_completed(session)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_webhook_provisions_new_tenant_when_no_binding(monkeypatch):
    """Brand-new self-serve customer: no session/customer mapping exists
    and any metadata.tenant_id is ignored; admin service provisions a new
    tenant."""
    fake_redis = _FakeRedis()
    monkeypatch.setattr(webhooks_mod._state_mod, "_redis_client", lambda: fake_redis)
    monkeypatch.setattr(
        webhooks_mod._state_mod,
        "_store_subscription_mapping",
        lambda tid, mapping: fake_redis.hset(f"billing:tenant:{tid}", mapping),
    )

    async def _fake_admin_create(tenant_name: str) -> str:
        return "freshly-provisioned-tenant"

    monkeypatch.setattr(
        webhooks_mod._customers_mod,
        "_create_tenant_via_admin",
        _fake_admin_create,
    )

    session = {
        "id": "cs_brand_new",
        "customer": "cus_brand_new",
        "subscription": None,
        "customer_email": "newbie@example.com",
        "metadata": {
            "tenant_id": "attacker-tenant",  # must be ignored
            "plan_id": "growth",
            "billing_period": "monthly",
            "tenant_name": "New Company",
        },
    }

    await webhooks_mod._handle_checkout_completed(session)

    # The provisioned tenant — never the attacker-supplied one — is what
    # lands in the subscription hash.
    stored = fake_redis.hashes.get("billing:tenant:freshly-provisioned-tenant")
    assert stored is not None
    assert stored["tenant_id"] == "freshly-provisioned-tenant"
    assert "billing:tenant:attacker-tenant" not in fake_redis.hashes
