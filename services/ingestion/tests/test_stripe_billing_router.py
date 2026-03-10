"""Unit tests for Stripe billing router helpers."""

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

import app.authz as authz
from app.authz import IngestionPrincipal, get_ingestion_principal
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


def _build_client(principal: IngestionPrincipal) -> TestClient:
    app = FastAPI()
    app.include_router(stripe_billing.router)
    app.dependency_overrides[get_ingestion_principal] = lambda: principal
    return TestClient(app)


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


def test_portal_endpoint_creates_customer_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = _FakeRedis()
    tenant_id = "tenant-portal-1"
    monkeypatch.setattr(stripe_billing, "_redis_client", lambda: fake_redis)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kwargs: (True, 99))

    captured: dict[str, dict[str, str]] = {}

    def _fake_customer_create(**kwargs):
        captured["customer"] = kwargs
        return {"id": "cus_portal_1"}

    class _PortalSession:
        url = "https://billing.stripe.com/p/session/test_123"

    def _fake_portal_create(**kwargs):
        captured["portal"] = kwargs
        return _PortalSession()

    monkeypatch.setattr(stripe_billing.stripe.Customer, "create", _fake_customer_create)
    portal_namespace = stripe_billing.stripe.billing_portal
    if hasattr(portal_namespace, "Session"):
        monkeypatch.setattr(portal_namespace.Session, "create", _fake_portal_create)
    if hasattr(portal_namespace, "sessions"):
        monkeypatch.setattr(portal_namespace.sessions, "create", _fake_portal_create)

    principal = IngestionPrincipal(
        key_id="portal-key",
        tenant_id=tenant_id,
        scopes=["*"],
        auth_mode="test",
    )
    with _build_client(principal) as client:
        response = client.post(
            "/api/v1/billing/portal",
            json={
                "tenant_name": "Acme Foods",
                "customer_email": "billing@acme.example",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tenant_id"] == tenant_id
    assert payload["customer_id"] == "cus_portal_1"
    assert payload["portal_url"].startswith("https://billing.stripe.com/")
    assert captured["portal"]["customer"] == "cus_portal_1"

    mapping = fake_redis.hgetall(stripe_billing._tenant_subscription_key(tenant_id))
    assert mapping["customer_id"] == "cus_portal_1"
    assert mapping["customer_email"] == "billing@acme.example"


def test_invoice_list_returns_paginated_results(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = _FakeRedis()
    tenant_id = "tenant-invoice-1"
    monkeypatch.setattr(stripe_billing, "_redis_client", lambda: fake_redis)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kwargs: (True, 42))

    stripe_billing._store_subscription_mapping(
        tenant_id,
        {
            "tenant_id": tenant_id,
            "session_id": "",
            "customer_id": "cus_invoice_1",
            "subscription_id": "sub_invoice_1",
            "plan_id": "growth",
            "billing_period": "monthly",
            "status": "active",
            "customer_email": "billing@acme.example",
            "current_period_end": "",
        },
    )

    class _InvoicePage:
        data = [
            {
                "id": "in_1",
                "amount_due": 99900,
                "amount_paid": 99900,
                "currency": "usd",
                "status": "paid",
                "created": 1700000000,
                "invoice_pdf": "https://invoice.stripe.com/in_1.pdf",
                "hosted_invoice_url": "https://invoice.stripe.com/in_1",
            },
            {
                "id": "in_2",
                "amount_due": 199900,
                "amount_paid": 0,
                "currency": "usd",
                "status": "open",
                "created": 1700001000,
                "invoice_pdf": "https://invoice.stripe.com/in_2.pdf",
                "hosted_invoice_url": "https://invoice.stripe.com/in_2",
            },
        ]
        has_more = True

    captured_list_kwargs: dict[str, object] = {}

    def _fake_invoice_list(**kwargs):
        captured_list_kwargs.update(kwargs)
        return _InvoicePage()

    monkeypatch.setattr(stripe_billing.stripe.Invoice, "list", _fake_invoice_list)

    principal = IngestionPrincipal(
        key_id="billing-operator",
        tenant_id=tenant_id,
        scopes=["billing.invoices.read", "exchange.write"],
        auth_mode="test",
    )
    with _build_client(principal) as client:
        response = client.get(
            "/api/v1/billing/invoices",
            params={"starting_after": "in_prev", "limit": 2},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tenant_id"] == tenant_id
    assert payload["customer_id"] == "cus_invoice_1"
    assert payload["has_more"] is True
    assert payload["next_cursor"] == "in_2"
    assert len(payload["invoices"]) == 2
    assert payload["invoices"][0]["invoice_id"] == "in_1"
    assert payload["invoices"][0]["pdf_url"].endswith("in_1.pdf")
    assert captured_list_kwargs["customer"] == "cus_invoice_1"
    assert captured_list_kwargs["starting_after"] == "in_prev"
    assert captured_list_kwargs["limit"] == 2


def test_invoice_list_denied_for_viewer_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kwargs: (True, 5))

    principal = IngestionPrincipal(
        key_id="billing-viewer",
        tenant_id="tenant-viewer-1",
        scopes=["billing.invoices.read"],
        auth_mode="test",
    )
    with _build_client(principal) as client:
        response = client.get("/api/v1/billing/invoices")

    assert response.status_code == 403
    assert "admin/operator" in response.json()["detail"]


def test_invoice_pdf_rejects_cross_tenant_invoice(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = _FakeRedis()
    tenant_id = "tenant-invoice-2"
    monkeypatch.setattr(stripe_billing, "_redis_client", lambda: fake_redis)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kwargs: (True, 7))

    stripe_billing._store_subscription_mapping(
        tenant_id,
        {
            "tenant_id": tenant_id,
            "session_id": "",
            "customer_id": "cus_expected",
            "subscription_id": "sub_expected",
            "plan_id": "growth",
            "billing_period": "monthly",
            "status": "active",
            "customer_email": "billing@acme.example",
            "current_period_end": "",
        },
    )

    monkeypatch.setattr(
        stripe_billing.stripe.Invoice,
        "retrieve",
        lambda _invoice_id: {
            "id": "in_cross",
            "customer": "cus_other",
            "invoice_pdf": "https://invoice.stripe.com/in_cross.pdf",
            "hosted_invoice_url": "https://invoice.stripe.com/in_cross",
            "status": "paid",
            "created": 1700000000,
        },
    )

    principal = IngestionPrincipal(
        key_id="billing-operator",
        tenant_id=tenant_id,
        scopes=["billing.invoices.read", "exchange.write"],
        auth_mode="test",
    )
    with _build_client(principal) as client:
        response = client.get("/api/v1/billing/invoices/in_cross/pdf")

    assert response.status_code == 404
    assert response.json()["detail"] == "Invoice not found for tenant"
