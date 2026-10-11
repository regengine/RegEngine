"""QA5 deep-pass regression tests for ``app/stripe_billing``.

Covers three real bugs found by reading every file in the module:

1. ``invoice.paid`` / ``invoice.payment_failed`` for a one-off (non
   subscription) invoice flipped the tenant's entitlement ``status`` to
   ``active`` / ``past_due`` even though no subscription exists. A paid
   one-off invoice (for example the auto-invoiced per-label
   ``InvoiceItem`` rows created by ``label_billing.charge_for_label``)
   must record payment metadata without touching entitlement state.
2. ``POST /usage/opt-in`` was not idempotent: calling it twice attached
   a second metered subscription item on Stripe and orphaned the first
   (still billing), because the stored item id was overwritten.
3. ``GET /invoices/{id}/pdf`` returned the PDF when Stripe's invoice
   carried no ``customer`` field at all, skipping the tenant ownership
   check (fail-open on missing data).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest
import stripe

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app import stripe_billing  # noqa: E402
from app.authz import IngestionPrincipal  # noqa: E402
from app.stripe_billing import (  # noqa: E402
    helpers as helpers_mod,
    routes as routes_mod,
    webhooks as webhooks_mod,
)

state_mod = webhooks_mod._state_mod

TENANT_ID = "tenant-qa5-1"


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.hashes: dict[str, dict[str, str]] = {}

    def get(self, key: str) -> Optional[str]:
        return self.values.get(key)

    def set(self, key: str, value: str, **_: Any) -> Any:
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


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> _FakeRedis:
    fake = _FakeRedis()
    monkeypatch.setattr(state_mod, "_redis_client", lambda: fake)
    return fake


@pytest.fixture(autouse=True)
def _stub_configure_stripe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(helpers_mod, "_configure_stripe", lambda: None)


def _principal(scopes: list[str], tenant_id: str = TENANT_ID) -> IngestionPrincipal:
    return IngestionPrincipal(tenant_id=tenant_id, scopes=scopes, key_id="k1")


# ── Bug 1: subscription-less invoice.paid must not entitle ────────────────


@pytest.mark.asyncio
async def test_invoice_paid_without_subscription_preserves_status(
    fake_redis: _FakeRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A one-off invoice payment (``subscription`` is None, e.g. invoiced
    per-label InvoiceItems) must not flip a canceled tenant to active."""
    fake_redis.hashes[f"billing:tenant:{TENANT_ID}"] = {
        "tenant_id": TENANT_ID,
        "status": "canceled",
        "customer_id": "cus_qa5",
    }
    fake_redis.values["billing:customer:cus_qa5"] = TENANT_ID

    emitted: list[dict[str, Any]] = []
    import shared.funnel_events as funnel_events

    monkeypatch.setattr(
        funnel_events,
        "emit_funnel_event",
        lambda **kwargs: emitted.append(kwargs) or True,
    )

    event = {
        "id": "evt_qa5_paid",
        "type": "invoice.paid",
        "created": 2_000_000_000,
        "data": {
            "object": {
                "id": "in_oneoff_1",
                "subscription": None,
                "customer": "cus_qa5",
                "status_transitions": {"paid_at": 2_000_000_000},
            }
        },
    }
    await webhooks_mod._handle_stripe_event(event)

    mapping = fake_redis.hashes[f"billing:tenant:{TENANT_ID}"]
    assert mapping["status"] == "canceled"
    assert mapping["last_invoice_id"] == "in_oneoff_1"
    assert mapping["last_payment_at"]
    # The payment still happened, so the funnel signal is still emitted.
    assert len(emitted) == 1
    assert emitted[0]["event_name"] == "payment_completed"


@pytest.mark.asyncio
async def test_invoice_payment_failed_without_subscription_preserves_status(
    fake_redis: _FakeRedis,
) -> None:
    """A failed one-off invoice payment must not flip an active tenant
    to past_due (which would 402 a paying subscriber)."""
    fake_redis.hashes[f"billing:tenant:{TENANT_ID}"] = {
        "tenant_id": TENANT_ID,
        "status": "active",
        "customer_id": "cus_qa5",
    }
    fake_redis.values["billing:customer:cus_qa5"] = TENANT_ID

    event = {
        "id": "evt_qa5_failed",
        "type": "invoice.payment_failed",
        "created": 2_100_000_000,
        "data": {
            "object": {
                "id": "in_oneoff_fail",
                "subscription": None,
                "customer": "cus_qa5",
                "created": 2_100_000_000,
            }
        },
    }
    await webhooks_mod._handle_stripe_event(event)

    mapping = fake_redis.hashes[f"billing:tenant:{TENANT_ID}"]
    assert mapping["status"] == "active"
    assert mapping["last_invoice_id"] == "in_oneoff_fail"
    assert mapping["last_payment_failure_at"]


# ── Bug 2: double opt-in must not attach a duplicate item ─────────────────


@pytest.mark.asyncio
async def test_opt_in_second_call_does_not_create_duplicate_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr(stripe_billing, "_redis_client", lambda: fake)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_PRICE_METERED_LABEL_EVENTS", "price_metered_1")

    stripe_billing._store_subscription_mapping(
        TENANT_ID,
        {
            "plan_id": "growth",
            "subscription_id": "sub_123",
            "status": "active",
            "metered_billing_enabled": "true",
            "metered_subscription_item_id": "si_metered_1",
        },
    )

    created = MagicMock(return_value=MagicMock(id="si_metered_2"))
    monkeypatch.setattr(stripe_billing.stripe.SubscriptionItem, "create", created)

    principal = _principal(["admin"])
    response = await stripe_billing.opt_in_metered_usage(
        tenant_id=None, x_tenant_id=None, principal=principal
    )

    assert created.call_count == 0
    assert response["metered_billing_enabled"] is True
    assert response["subscription_item_id"] == "si_metered_1"
    mapping = stripe_billing._get_subscription_mapping(TENANT_ID)
    assert mapping["metered_subscription_item_id"] == "si_metered_1"


# ── Bug 3: invoice PDF with no customer must fail closed ───────────────────


@pytest.mark.asyncio
async def test_invoice_pdf_with_missing_customer_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        routes_mod._state_mod,
        "_get_subscription_mapping",
        lambda _t: {"customer_id": "cus_mine"},
    )
    monkeypatch.setattr(
        stripe.Invoice,
        "retrieve",
        lambda _id: {
            "id": "in_nocus",
            "customer": None,
            "invoice_pdf": "https://files.stripe.com/pdf/in_nocus",
            "status": "paid",
            "created": 1_700_000_000,
            "hosted_invoice_url": None,
        },
    )

    with pytest.raises(Exception) as excinfo:
        await routes_mod.get_invoice_pdf(
            invoice_id="in_nocus",
            tenant_id="tenant-mine",
            x_tenant_id=None,
            principal=_principal(["*"], tenant_id="tenant-mine"),
        )
    assert getattr(excinfo.value, "status_code", None) == 404
