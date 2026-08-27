"""``customer.deleted`` cleanup must survive a subsequent read — #2953.

``_handle_customer_deleted`` does two deliberate things: it marks the
tenant ``customer_deleted`` (an audit marker) and it deletes the
``billing:customer:{id}`` / ``billing:subscription:{id}`` lookup keys so a
later out-of-order webhook carrying those stale identifiers cannot
re-bind to the tenant. The intent is documented verbatim in both
``webhooks.py`` and ``state.py``.

The next authenticated ``GET /api/v1/billing/subscription/{tenant_id}``
undid both. Its write-back calls ``_store_subscription_mapping`` with the
still-populated hash, and that function unconditionally re-creates all
three lookup keys from the payload — no status check of any kind — while
``mapping["status"] = status`` replaces ``customer_deleted`` with
whatever Stripe currently reports (canceled subscriptions stay
retrievable, so the refresh succeeds).

The billing settings page calls that GET on load, so the documented
invariant held only until the next page view.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

import pytest
import stripe

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from app.stripe_billing import (  # noqa: E402
    helpers as helpers_mod,
    routes as routes_mod,
    state as state_mod,
    webhooks as webhooks_mod,
)

TENANT = "tenant-2953"
CUSTOMER = "cus_2953_abc"
SUBSCRIPTION = "sub_2953_xyz"
SESSION = "cs_2953_session"


class _FakeRedis:
    """In-memory Redis stand-in covering the calls these paths make."""

    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.values: dict[str, str] = {}

    def hset(self, key: str, mapping: dict[str, str]) -> None:
        self.hashes.setdefault(key, {})
        self.hashes[key].update(mapping)

    def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.hashes.get(key, {}))

    def set(self, key: str, value: str, nx: bool = False, ex: Optional[int] = None) -> Any:
        if nx and key in self.values:
            return None
        self.values[key] = value
        return True

    def get(self, key: str) -> Optional[str]:
        return self.values.get(key)

    def delete(self, key: str) -> int:
        existed = key in self.values
        self.values.pop(key, None)
        return 1 if existed else 0


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> _FakeRedis:
    fake = _FakeRedis()
    monkeypatch.setattr(state_mod, "_redis_client", lambda: fake)
    return fake


@pytest.fixture(autouse=True)
def _stub_stripe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(helpers_mod, "_configure_stripe", lambda: None)
    # Stripe keeps canceled subscriptions retrievable after the customer is
    # deleted, so the GET's refresh succeeds and reports "canceled".
    monkeypatch.setattr(
        stripe.Subscription,
        "retrieve",
        lambda _sub_id: {"status": "canceled", "items": {"data": [{"current_period_end": 1_800_000_000}]}},
    )


def _prebind_tenant(fake: _FakeRedis) -> None:
    """Simulate a prior successful checkout so every lookup resolves."""
    state_mod._store_subscription_mapping(
        TENANT,
        {
            "tenant_id": TENANT,
            "customer_id": CUSTOMER,
            "subscription_id": SUBSCRIPTION,
            "session_id": SESSION,
            "status": "active",
            "plan_id": "growth",
            "billing_period": "monthly",
        },
    )


class TestSubscriptionReadDoesNotResurrectDeletedCustomer_Issue2953:
    @pytest.mark.asyncio
    async def test_get_subscription_leaves_lookup_keys_deleted(self, fake_redis: _FakeRedis) -> None:
        """Acceptance criterion 1: after ``customer.deleted``, a subsequent
        GET must leave both lookup keys absent from Redis."""
        _prebind_tenant(fake_redis)
        webhooks_mod._handle_customer_deleted({"id": CUSTOMER})

        customer_key = state_mod._customer_lookup_key(CUSTOMER)
        subscription_key = state_mod._subscription_lookup_key(SUBSCRIPTION)
        assert customer_key not in fake_redis.values, "precondition: handler cleared the customer lookup"
        assert subscription_key not in fake_redis.values, "precondition: handler cleared the subscription lookup"

        await routes_mod.get_subscription(TENANT, _=None)

        assert customer_key not in fake_redis.values, (
            "a GET must not re-create billing:customer:{id} — that restores exactly the routing "
            "the customer.deleted handler removed"
        )
        assert subscription_key not in fake_redis.values, (
            "a GET must not re-create billing:subscription:{id} after customer.deleted"
        )

    @pytest.mark.asyncio
    async def test_customer_deleted_marker_survives_a_read(self, fake_redis: _FakeRedis) -> None:
        """Acceptance criterion 2: ``customer_deleted`` / ``customer_deleted_at``
        must survive a subsequent subscription read."""
        _prebind_tenant(fake_redis)
        webhooks_mod._handle_customer_deleted({"id": CUSTOMER})
        deleted_at = state_mod._get_subscription_mapping(TENANT)["customer_deleted_at"]

        result = await routes_mod.get_subscription(TENANT, _=None)

        mapping = state_mod._get_subscription_mapping(TENANT)
        assert mapping["status"] == "customer_deleted", (
            f"terminal customer_deleted marker was overwritten with {mapping['status']!r}; "
            "the audit record that the Stripe customer was removed is destroyed"
        )
        assert mapping["customer_deleted_at"] == deleted_at
        assert result.status == "customer_deleted", (
            "the API must keep reporting the terminal state, not Stripe's subscription status"
        )

    @pytest.mark.asyncio
    async def test_later_subscription_updated_does_not_resolve_the_tenant(
        self,
        fake_redis: _FakeRedis,
    ) -> None:
        """Acceptance criterion 3: a ``customer.subscription.updated`` event
        carrying the deleted identifiers, arriving after the read, must not
        resolve to the tenant and must not mutate its entitlement state."""
        _prebind_tenant(fake_redis)
        webhooks_mod._handle_customer_deleted({"id": CUSTOMER})

        await routes_mod.get_subscription(TENANT, _=None)

        assert state_mod._find_tenant_id(SUBSCRIPTION, CUSTOMER) is None, (
            "stale identifiers must not resolve to the tenant after customer.deleted"
        )

        webhooks_mod._update_subscription_status(
            subscription_id=SUBSCRIPTION,
            customer_id=CUSTOMER,
            status="active",
            event_created=2_000_000_000,
        )
        mapping = state_mod._get_subscription_mapping(TENANT)
        assert mapping["status"] == "customer_deleted", (
            f"an out-of-order webhook re-bound to the deleted tenant and set status={mapping['status']!r}"
        )


class TestStoreMappingRefusesTerminalLookupRebind_Issue2953:
    def test_store_subscription_mapping_does_not_bind_lookups_when_customer_deleted(
        self,
        fake_redis: _FakeRedis,
    ) -> None:
        """The invariant belongs in ``_store_subscription_mapping`` itself so
        any future caller inherits it, not just ``get_subscription``."""
        _prebind_tenant(fake_redis)
        webhooks_mod._handle_customer_deleted({"id": CUSTOMER})

        mapping = state_mod._get_subscription_mapping(TENANT)
        assert mapping["status"] == "customer_deleted"

        # A well-meaning writer persists the audit hash again.
        state_mod._store_subscription_mapping(TENANT, mapping)

        assert state_mod._customer_lookup_key(CUSTOMER) not in fake_redis.values
        assert state_mod._subscription_lookup_key(SUBSCRIPTION) not in fake_redis.values
        # The audit hash itself must still be written — this is not a no-op.
        assert fake_redis.hashes[state_mod._tenant_subscription_key(TENANT)]["plan_id"] == "growth"
