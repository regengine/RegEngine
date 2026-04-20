"""Regression tests for issue #1196 — Stripe webhook event ordering.

Before the fix, ``customer.subscription.updated`` arriving before
``checkout.session.completed`` (Stripe reorders events) was silently
dropped by ``_update_subscription_status``. Also, two in-order status
updates could be applied in arrival order even when ``event.created``
said the second one was older, leaving the subscription in a stale
state.

These tests exercise the two safeguards:

1. **Reorder guard** — an event with ``event.created`` older than the
   stored ``last_event_created`` watermark is rejected.
2. **Missing-mapping recovery** — when no tenant mapping exists yet,
   the update is buffered by subscription_id. ``_handle_checkout_completed``
   drains the buffer and applies the pending update on top of its initial
   mapping if the buffered ``event_created`` is strictly newer than the
   checkout event's.
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.ingestion.app.stripe_billing import (
    _handle_checkout_completed,
    _handle_stripe_event,
    _update_subscription_status,
)


# ---------------------------------------------------------------------------
# Test fakes — in-memory substitutes for the Redis-backed state helpers.
# The four helpers the webhook module uses are: _find_tenant_id,
# _get_subscription_mapping, _store_subscription_mapping,
# _buffer_pending_subscription_update, _pop_pending_subscription_update.
# ---------------------------------------------------------------------------


class _FakeState:
    """In-memory replacement for services.ingestion.app.stripe_billing.state.

    Models two dicts:
      - ``tenants``: tenant_id → mapping dict
      - ``sub_to_tenant``: subscription_id → tenant_id
      - ``cus_to_tenant``: customer_id → tenant_id
      - ``pending``: subscription_id → buffered update dict
    """

    def __init__(self) -> None:
        self.tenants: Dict[str, Dict[str, str]] = {}
        self.sub_to_tenant: Dict[str, str] = {}
        self.cus_to_tenant: Dict[str, str] = {}
        self.pending: Dict[str, Dict[str, Any]] = {}

    # --- _store_subscription_mapping ---------------------------------------
    def store(self, tenant_id: str, payload: Dict[str, Any]) -> None:
        self.tenants.setdefault(tenant_id, {}).update(
            {k: ("" if v is None else str(v)) for k, v in payload.items()}
        )
        sub_id = payload.get("subscription_id")
        if sub_id:
            self.sub_to_tenant[str(sub_id)] = tenant_id
        cus_id = payload.get("customer_id")
        if cus_id:
            self.cus_to_tenant[str(cus_id)] = tenant_id

    # --- _get_subscription_mapping -----------------------------------------
    def get(self, tenant_id: str) -> Dict[str, str]:
        return dict(self.tenants.get(tenant_id, {}))

    # --- _find_tenant_id ---------------------------------------------------
    def find_tenant(self, subscription_id: Optional[str], customer_id: Optional[str]) -> Optional[str]:
        if subscription_id and subscription_id in self.sub_to_tenant:
            return self.sub_to_tenant[subscription_id]
        if customer_id and customer_id in self.cus_to_tenant:
            return self.cus_to_tenant[customer_id]
        return None

    # --- _buffer_pending_subscription_update -------------------------------
    def buffer(self, subscription_id: str, payload: Dict[str, Any]) -> bool:
        if not subscription_id:
            return False
        new_ts = int(payload.get("event_created") or 0)
        existing = self.pending.get(subscription_id)
        if existing:
            existing_ts = int(existing.get("event_created") or 0)
            if existing_ts > new_ts:
                return False
        self.pending[subscription_id] = dict(payload)
        return True

    # --- _pop_pending_subscription_update ----------------------------------
    def pop(self, subscription_id: str) -> Optional[Dict[str, Any]]:
        return self.pending.pop(subscription_id, None)


class _FakeRedisForCheckout:
    """Minimal stand-in for the redis client that ``_handle_checkout_completed``
    reaches for directly via ``_state_mod._redis_client()``.

    We only need ``.get(key)`` to return a pre-seeded tenant binding so
    the checkout handler takes the "tenant-already-exists" path and
    skips the admin-service tenant provisioning call. Anything else
    returns ``None``.
    """

    def __init__(self) -> None:
        self._store: Dict[str, str] = {}

    def bind_session(self, session_id: str, tenant_id: str) -> None:
        self._store[f"billing:session:{session_id}"] = tenant_id

    def bind_customer(self, customer_id: str, tenant_id: str) -> None:
        self._store[f"billing:customer:{customer_id}"] = tenant_id

    def get(self, key: str) -> Optional[str]:
        return self._store.get(key)


@pytest.fixture
def fake_redis():
    """Injected into ``_state_mod._redis_client`` so the checkout handler
    has a tenant binding to read at session-lookup time."""
    return _FakeRedisForCheckout()


@pytest.fixture
def fake_state(monkeypatch, fake_redis):
    """Wire a fresh _FakeState into the stripe_billing package namespace.

    The ``_PatchableModule`` trampoline in ``stripe_billing/__init__.py``
    propagates these assignments into the submodules that actually call
    the helpers, so both ``webhooks.py`` and ``state.py`` see the fake.
    """
    import services.ingestion.app.stripe_billing as sb_pkg

    state = _FakeState()
    monkeypatch.setattr(sb_pkg, "_store_subscription_mapping", state.store)
    monkeypatch.setattr(sb_pkg, "_get_subscription_mapping", state.get)
    monkeypatch.setattr(sb_pkg, "_find_tenant_id", state.find_tenant)
    monkeypatch.setattr(sb_pkg, "_buffer_pending_subscription_update", state.buffer)
    monkeypatch.setattr(sb_pkg, "_pop_pending_subscription_update", state.pop)
    monkeypatch.setattr(sb_pkg, "_redis_client", lambda: fake_redis)
    return state


# ---------------------------------------------------------------------------
# Event builders
# ---------------------------------------------------------------------------


def _subscription_event(
    *,
    event_type: str,
    subscription_id: str,
    customer_id: str,
    status: str,
    event_created: int,
    current_period_end: int = 1_800_000_000,
) -> Dict[str, Any]:
    return {
        "type": event_type,
        "created": event_created,
        "data": {
            "object": {
                "id": subscription_id,
                "customer": customer_id,
                "status": status,
                "current_period_end": current_period_end,
            },
        },
    }


# ---------------------------------------------------------------------------
# 1. Reorder guard
# ---------------------------------------------------------------------------


class TestReorderGuard_Issue1196:
    """An event with an older ``event.created`` must not overwrite a newer
    status that already landed."""

    def test_older_update_rejected(self, fake_state):
        # Seed mapping with a newer watermark.
        fake_state.store(
            "tenant-A",
            {
                "tenant_id": "tenant-A",
                "subscription_id": "sub_X",
                "customer_id": "cus_X",
                "status": "canceled",
                "last_event_created": "1800",
            },
        )

        # Now apply an older update that claims "active".
        _update_subscription_status(
            subscription_id="sub_X",
            customer_id="cus_X",
            status="active",
            event_created=1500,  # older
        )

        # Mapping unchanged.
        final = fake_state.get("tenant-A")
        assert final["status"] == "canceled"
        assert final["last_event_created"] == "1800"

    def test_newer_update_accepted(self, fake_state):
        fake_state.store(
            "tenant-A",
            {
                "tenant_id": "tenant-A",
                "subscription_id": "sub_X",
                "customer_id": "cus_X",
                "status": "active",
                "last_event_created": "1500",
            },
        )

        _update_subscription_status(
            subscription_id="sub_X",
            customer_id="cus_X",
            status="past_due",
            event_created=1800,
        )

        final = fake_state.get("tenant-A")
        assert final["status"] == "past_due"
        assert final["last_event_created"] == "1800"

    def test_equal_timestamp_accepted(self, fake_state):
        """Ties break in favor of applying — we don't want a retried
        identical event to stall status propagation."""
        fake_state.store(
            "tenant-A",
            {
                "tenant_id": "tenant-A",
                "subscription_id": "sub_X",
                "customer_id": "cus_X",
                "status": "incomplete",
                "last_event_created": "1500",
            },
        )

        _update_subscription_status(
            subscription_id="sub_X",
            customer_id="cus_X",
            status="active",
            event_created=1500,
        )

        assert fake_state.get("tenant-A")["status"] == "active"

    def test_no_event_created_disables_guard(self, fake_state):
        """Legacy events (pre-fix, ``event_created=None``) still apply —
        we don't gate on a missing watermark because that would break
        backwards-compat for replays from Stripe's event log."""
        fake_state.store(
            "tenant-A",
            {
                "tenant_id": "tenant-A",
                "subscription_id": "sub_X",
                "customer_id": "cus_X",
                "status": "active",
                "last_event_created": "9999",
            },
        )

        _update_subscription_status(
            subscription_id="sub_X",
            customer_id="cus_X",
            status="past_due",
            event_created=None,
        )

        # Without a watermark we have no basis to reject — apply.
        assert fake_state.get("tenant-A")["status"] == "past_due"


# ---------------------------------------------------------------------------
# 2. Missing-mapping recovery — direct call to _update_subscription_status
# ---------------------------------------------------------------------------


class TestMissingMappingBuffer_Issue1196:
    """When no tenant mapping exists, the update is buffered rather than
    silently dropped."""

    def test_update_without_mapping_is_buffered(self, fake_state):
        # No mapping exists.
        assert fake_state.find_tenant("sub_ORPH", "cus_ORPH") is None

        _update_subscription_status(
            subscription_id="sub_ORPH",
            customer_id="cus_ORPH",
            status="active",
            event_created=1700,
            current_period_end="2026-01-01T00:00:00+00:00",
        )

        # Buffered, not dropped.
        assert "sub_ORPH" in fake_state.pending
        buffered = fake_state.pending["sub_ORPH"]
        assert buffered["status"] == "active"
        assert int(buffered["event_created"]) == 1700
        assert buffered["current_period_end"] == "2026-01-01T00:00:00+00:00"
        # And obviously no tenant mapping materialized out of thin air.
        assert not fake_state.tenants

    def test_newer_buffered_update_wins_over_older(self, fake_state):
        """If two reordered updates arrive, the buffer keeps the newest
        by event.created."""
        _update_subscription_status(
            subscription_id="sub_Y",
            customer_id="cus_Y",
            status="active",
            event_created=1500,
        )
        _update_subscription_status(
            subscription_id="sub_Y",
            customer_id="cus_Y",
            status="past_due",
            event_created=1800,
        )

        # Newer wins.
        assert fake_state.pending["sub_Y"]["status"] == "past_due"

        # An even older one arriving third must not overwrite the newer.
        _update_subscription_status(
            subscription_id="sub_Y",
            customer_id="cus_Y",
            status="incomplete",
            event_created=1200,
        )
        assert fake_state.pending["sub_Y"]["status"] == "past_due"

    def test_update_without_subscription_id_is_not_buffered(self, fake_state):
        """If we can't key the buffer, we keep the pre-fix behavior — log
        and drop — because we have no way to recover it."""
        _update_subscription_status(
            subscription_id=None,
            customer_id="cus_Z",
            status="active",
            event_created=1700,
        )

        # No buffer slot available — empty pending queue.
        assert fake_state.pending == {}


# ---------------------------------------------------------------------------
# 3. Drain on checkout.session.completed
# ---------------------------------------------------------------------------


class TestPendingDrainedOnCheckout_Issue1196:
    """``_handle_checkout_completed`` must drain any buffered update for
    the subscription it just registered."""

    @pytest.mark.asyncio
    async def test_buffered_newer_update_applied_on_top_of_checkout(
        self, fake_state, fake_redis,
    ):
        # Checkout handler's session-lookup must succeed or it tries to
        # provision a tenant via the admin service. Pre-bind.
        fake_redis.bind_session("cs_test", "tenant-LATE")

        # Pre-seed a buffered update that arrived before checkout.
        fake_state.pending["sub_LATE"] = {
            "status": "active",
            "event_created": 2000,
            "current_period_end": "2026-07-01T00:00:00+00:00",
            "last_invoice_id": "",
            "last_payment_at": None,
            "last_payment_failure_at": None,
            "customer_id": "cus_LATE",
        }

        # Checkout-completed event with OLDER event.created, and a stale
        # synchronous Stripe.Subscription.retrieve returning "incomplete".
        fake_sub = {"status": "incomplete", "current_period_end": 1_700_000_000}
        with patch("services.ingestion.app.stripe_billing.webhooks.stripe") as mock_stripe:
            mock_stripe.Subscription.retrieve.return_value = fake_sub
            await _handle_checkout_completed(
                {
                    "id": "cs_test",
                    "customer": "cus_LATE",
                    "subscription": "sub_LATE",
                    "metadata": {"plan_id": "growth", "billing_period": "monthly", "tenant_id": "tenant-LATE"},
                    "customer_email": "user@example.com",
                },
                event_created=1500,  # older than buffered 2000
            )

        # Post-condition: buffered status ("active") overrode the stale
        # checkout-time status ("incomplete"), period_end came from buffer,
        # and watermark is the buffered event_created (2000).
        tenant_map = fake_state.get("tenant-LATE")
        assert tenant_map["status"] == "active"
        assert tenant_map["current_period_end"] == "2026-07-01T00:00:00+00:00"
        assert tenant_map["last_event_created"] == "2000"
        # Buffer drained.
        assert "sub_LATE" not in fake_state.pending

    @pytest.mark.asyncio
    async def test_buffered_older_update_discarded_on_checkout(
        self, fake_state, fake_redis,
    ):
        """If the buffered pending update is OLDER than the checkout event,
        the checkout's fresh fetch from Stripe is authoritative — we
        discard the stale buffer."""
        fake_redis.bind_session("cs_test", "tenant-OLD")

        fake_state.pending["sub_OLD"] = {
            "status": "incomplete",
            "event_created": 1000,
            "current_period_end": "2025-01-01T00:00:00+00:00",
            "customer_id": "cus_OLD",
        }

        fake_sub = {"status": "active", "current_period_end": 1_700_000_000}
        with patch("services.ingestion.app.stripe_billing.webhooks.stripe") as mock_stripe:
            mock_stripe.Subscription.retrieve.return_value = fake_sub
            await _handle_checkout_completed(
                {
                    "id": "cs_test",
                    "customer": "cus_OLD",
                    "subscription": "sub_OLD",
                    "metadata": {"plan_id": "growth", "billing_period": "monthly", "tenant_id": "tenant-OLD"},
                    "customer_email": "user@example.com",
                },
                event_created=2000,  # newer than buffered 1000
            )

        tenant_map = fake_state.get("tenant-OLD")
        # The checkout's live Stripe status ("active") wins, not the stale
        # buffered "incomplete".
        assert tenant_map["status"] == "active"
        assert tenant_map["last_event_created"] == "2000"
        # Buffer still drained even though we didn't apply it.
        assert "sub_OLD" not in fake_state.pending

    @pytest.mark.asyncio
    async def test_no_buffered_update_checkout_unchanged(
        self, fake_state, fake_redis,
    ):
        """Baseline: when no buffered update exists, checkout behaves
        exactly like before."""
        fake_redis.bind_session("cs_plain", "tenant-PLAIN")

        fake_sub = {"status": "trialing", "current_period_end": 1_700_000_000}
        with patch("services.ingestion.app.stripe_billing.webhooks.stripe") as mock_stripe:
            mock_stripe.Subscription.retrieve.return_value = fake_sub
            await _handle_checkout_completed(
                {
                    "id": "cs_plain",
                    "customer": "cus_PLAIN",
                    "subscription": "sub_PLAIN",
                    "metadata": {"plan_id": "growth", "billing_period": "monthly", "tenant_id": "tenant-PLAIN"},
                    "customer_email": "user@example.com",
                },
                event_created=1200,
            )

        tenant_map = fake_state.get("tenant-PLAIN")
        assert tenant_map["status"] == "trialing"
        assert tenant_map["last_event_created"] == "1200"


# ---------------------------------------------------------------------------
# 4. End-to-end: event envelope → _handle_stripe_event
# ---------------------------------------------------------------------------


class TestEndToEndEventOrdering_Issue1196:
    """Exercise the full envelope path to verify ``event.created`` is
    threaded from the wire into the reorder guard."""

    @pytest.mark.asyncio
    async def test_updated_before_created_no_longer_silently_drops(
        self, fake_state, fake_redis,
    ):
        """Regression: this exact sequence returned silently and left the
        subscription stuck on its checkout-time status."""
        fake_redis.bind_session("cs_race", "tenant-RACE")

        # #1 — subscription.updated arrives first, no mapping yet.
        await _handle_stripe_event(_subscription_event(
            event_type="customer.subscription.updated",
            subscription_id="sub_RACE",
            customer_id="cus_RACE",
            status="active",
            event_created=2000,
        ))

        # Pre-fix this would be gone. Now it's buffered.
        assert "sub_RACE" in fake_state.pending
        assert fake_state.pending["sub_RACE"]["status"] == "active"

        # #2 — checkout arrives later with an older event.created.
        fake_sub = {"status": "incomplete", "current_period_end": 1_700_000_000}
        with patch("services.ingestion.app.stripe_billing.webhooks.stripe") as mock_stripe:
            mock_stripe.Subscription.retrieve.return_value = fake_sub
            await _handle_stripe_event({
                "type": "checkout.session.completed",
                "created": 1500,
                "data": {
                    "object": {
                        "id": "cs_race",
                        "customer": "cus_RACE",
                        "subscription": "sub_RACE",
                        "metadata": {
                            "plan_id": "growth",
                            "billing_period": "monthly",
                            "tenant_id": "tenant-RACE",
                        },
                        "customer_email": "user@example.com",
                    },
                },
            })

        # Subscription is "active" (from the reordered update), not
        # "incomplete" (from the checkout's stale live-fetch).
        tenant_map = fake_state.get("tenant-RACE")
        assert tenant_map["status"] == "active"
        assert "sub_RACE" not in fake_state.pending

    @pytest.mark.asyncio
    async def test_two_updated_events_out_of_arrival_order(self, fake_state):
        """Two ``customer.subscription.updated`` events with reversed
        arrival order vs. ``event.created``: the final status must match
        the newer event.created, not arrival order."""
        # Seed mapping so both events find a tenant.
        fake_state.store(
            "tenant-Q",
            {
                "tenant_id": "tenant-Q",
                "subscription_id": "sub_Q",
                "customer_id": "cus_Q",
                "status": "active",
                "last_event_created": "1000",
            },
        )

        # Newer-in-Stripe-time event arrives FIRST.
        await _handle_stripe_event(_subscription_event(
            event_type="customer.subscription.updated",
            subscription_id="sub_Q",
            customer_id="cus_Q",
            status="canceled",
            event_created=2000,
        ))
        assert fake_state.get("tenant-Q")["status"] == "canceled"

        # Older-in-Stripe-time event arrives SECOND — must be rejected.
        await _handle_stripe_event(_subscription_event(
            event_type="customer.subscription.updated",
            subscription_id="sub_Q",
            customer_id="cus_Q",
            status="active",
            event_created=1500,
        ))

        assert fake_state.get("tenant-Q")["status"] == "canceled"
        assert fake_state.get("tenant-Q")["last_event_created"] == "2000"

    @pytest.mark.asyncio
    async def test_deleted_before_created_buffered_and_applied(
        self, fake_state, fake_redis,
    ):
        """A canceled subscription whose ``deleted`` event beats
        ``checkout.session.completed`` must still end up canceled."""
        fake_redis.bind_session("cs_del", "tenant-DEL")

        await _handle_stripe_event(_subscription_event(
            event_type="customer.subscription.deleted",
            subscription_id="sub_DEL",
            customer_id="cus_DEL",
            status="canceled",
            event_created=3000,
        ))

        assert fake_state.pending["sub_DEL"]["status"] == "canceled"

        fake_sub = {"status": "active", "current_period_end": 1_700_000_000}
        with patch("services.ingestion.app.stripe_billing.webhooks.stripe") as mock_stripe:
            mock_stripe.Subscription.retrieve.return_value = fake_sub
            await _handle_stripe_event({
                "type": "checkout.session.completed",
                "created": 1000,
                "data": {
                    "object": {
                        "id": "cs_del",
                        "customer": "cus_DEL",
                        "subscription": "sub_DEL",
                        "metadata": {
                            "plan_id": "growth",
                            "billing_period": "monthly",
                            "tenant_id": "tenant-DEL",
                        },
                        "customer_email": "x@example.com",
                    },
                },
            })

        # Final status reflects the cancellation even though the checkout
        # event's synchronous fetch reported "active".
        assert fake_state.get("tenant-DEL")["status"] == "canceled"
