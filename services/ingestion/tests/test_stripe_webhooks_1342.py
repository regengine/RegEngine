"""Focused coverage for ``app/stripe_billing/webhooks.py`` — #1342.

Companion to ``test_stripe_webhook_idempotency.py`` (which covers the
dedup primitive), ``test_stripe_webhook_missing_handlers_1189.py``
(which covers the dispute/trial/customer-deleted handlers), and
``test_stripe_webhook_ordering_1196.py`` (which exists if present;
this file stands alone if not). Together these bring
``app/stripe_billing/webhooks.py`` to 100%.

Baseline gaps that this file targets:
- 90-91: ``_handle_checkout_completed`` tenant-name fallback when
  neither metadata.tenant_name NOR metadata.customer_email is present.
- 131: ``last_event_created`` watermark stamping on initial mapping.
- 142-170: #1196 pending-update drain block — applied / superseded paths.
- 213-239: ``_update_subscription_status`` no-mapping branches with and
  without a subscription_id (buffer vs. bare log).
- 245-256: #1196 reorder guard — stale event ignored.
- 272, 274: field updates for ``last_payment_at`` and
  ``last_event_created`` on the happy path.
- 458-459: dispatcher for ``checkout.session.completed``.
- 498-522: dispatcher for ``customer.subscription.updated`` +
  ``customer.subscription.deleted``.
- 539: dispatcher for unknown event types (logs & no-op).
- 550: ``_process_stripe_webhook`` missing ``STRIPE_WEBHOOK_SECRET`` → 500.
- 564: ``_process_stripe_webhook`` non-JSON payload → 400.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
import stripe
from fastapi import HTTPException

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app.stripe_billing import (  # noqa: E402
    customers as customers_mod,
    helpers as helpers_mod,
    state as state_mod,
    webhooks as webhooks_mod,
)


# ── Logger recorder (see routes test file for background on this) ──────────


class _RecorderLogger:
    """Stripe modules call stdlib logger with structlog-style kwargs,
    which stdlib rejects. We stub the logger so tests reach the
    following ``raise`` / state-update line rather than dying on a
    TypeError from the log call itself.  Production bug is flagged
    in a separate spawn_task."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...], dict[str, Any]]] = []

    def _record(
        self, level: str, msg: str, *args: Any, **kwargs: Any
    ) -> None:
        self.calls.append((level, msg, args, kwargs))

    def error(self, msg: str, *a: Any, **k: Any) -> None: self._record("error", msg, *a, **k)
    def warning(self, msg: str, *a: Any, **k: Any) -> None: self._record("warning", msg, *a, **k)
    def info(self, msg: str, *a: Any, **k: Any) -> None: self._record("info", msg, *a, **k)
    def debug(self, msg: str, *a: Any, **k: Any) -> None: self._record("debug", msg, *a, **k)


@pytest.fixture(autouse=True)
def _stub_logger(monkeypatch: pytest.MonkeyPatch) -> _RecorderLogger:
    recorder = _RecorderLogger()
    monkeypatch.setattr(webhooks_mod, "logger", recorder)
    return recorder


@pytest.fixture(autouse=True)
def _stub_configure_stripe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(helpers_mod, "_configure_stripe", lambda: None)


@pytest.fixture(autouse=True)
def _stub_emit_funnel(monkeypatch: pytest.MonkeyPatch) -> None:
    import shared.funnel_events as funnel_events
    monkeypatch.setattr(funnel_events, "emit_funnel_event", lambda **_: True)


# ── In-memory Redis fake + state stubs ─────────────────────────────────────


class _FakeRedis:
    """Covers the state-module helpers called from webhooks.py."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.hashes: dict[str, dict[str, str]] = {}

    def get(self, key: str) -> Optional[str]: return self.values.get(key)
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

    def getdel(self, key: str) -> Optional[str]:
        return self.values.pop(key, None)


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> _FakeRedis:
    fake = _FakeRedis()
    monkeypatch.setattr(state_mod, "_redis_client", lambda: fake)
    return fake


# ── _handle_checkout_completed ─────────────────────────────────────────────


class TestHandleCheckoutCompleted:
    """Gap lines: 90-91 (tenant-name fallback), 131 (watermark),
    142-170 (pending update drain)."""

    @pytest.mark.asyncio
    async def test_no_customer_email_no_tenant_name_uses_new_customer_team(
        self, monkeypatch: pytest.MonkeyPatch, fake_redis: _FakeRedis
    ) -> None:
        """Line 90-91: when neither metadata.tenant_name nor any email
        source is present, fall back to ``'New Customer Team'``.  This
        is the never-before-seen self-serve signup path."""
        created_tenants: list[str] = []

        async def _fake_create_tenant(tenant_name: str) -> str:
            created_tenants.append(tenant_name)
            return "tenant-autogen-1"

        monkeypatch.setattr(
            customers_mod, "_create_tenant_via_admin", _fake_create_tenant
        )

        session = {
            "id": "cs_new_1",
            "customer": "cus_1",
            "subscription": None,
            "metadata": {},
        }

        await webhooks_mod._handle_checkout_completed(session, event_created=100)

        assert created_tenants == ["New Customer Team"]
        # Mapping was written with the autogen tenant.
        mapping = fake_redis.hashes.get("billing:tenant:tenant-autogen-1", {})
        assert mapping.get("customer_id") == "cus_1"
        assert mapping.get("session_id") == "cs_new_1"

    @pytest.mark.asyncio
    async def test_metadata_customer_email_is_used_as_tenant_name_prefix(
        self, monkeypatch: pytest.MonkeyPatch, fake_redis: _FakeRedis
    ) -> None:
        """The email local-part + ' Team' becomes the tenant name when
        no explicit tenant_name was supplied."""
        created_tenants: list[str] = []

        async def _fake_create_tenant(tenant_name: str) -> str:
            created_tenants.append(tenant_name)
            return "tenant-autogen-2"

        monkeypatch.setattr(
            customers_mod, "_create_tenant_via_admin", _fake_create_tenant
        )

        session = {
            "id": "cs_new_2",
            "customer": "cus_2",
            "subscription": None,
            "metadata": {"customer_email": "ops@acme.co"},
        }

        await webhooks_mod._handle_checkout_completed(session, event_created=200)
        assert created_tenants == ["ops Team"]

    @pytest.mark.asyncio
    async def test_existing_server_binding_stamps_event_watermark(
        self, fake_redis: _FakeRedis, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Line 131: ``event_created`` is stamped as ``last_event_created``
        on the initial mapping so out-of-order subsequent updates can be
        correctly diffed."""
        # Pre-seed server-side binding.
        fake_redis.values["billing:session:cs_with_binding"] = "tenant-existing"

        # No subscription lookup hits the network.
        session = {
            "id": "cs_with_binding",
            "customer": "cus_existing",
            "subscription": None,
            "metadata": {"plan_id": "growth"},
        }

        await webhooks_mod._handle_checkout_completed(
            session, event_created=1_700_000_000
        )

        mapping = fake_redis.hashes["billing:tenant:tenant-existing"]
        assert mapping["last_event_created"] == "1700000000"

    @pytest.mark.asyncio
    async def test_pending_update_newer_than_checkout_is_applied(
        self, fake_redis: _FakeRedis, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lines 142-168: #1196 drain — a pending update arrived before
        the checkout event but has a NEWER event_created, so after
        checkout lands we apply the pending update on top."""
        fake_redis.values["billing:session:cs_drain_newer"] = "tenant-drain"

        # Pre-seed a pending update with a newer timestamp.
        import json as _json
        fake_redis.values["billing:pending_sub_update:sub_drain"] = _json.dumps(
            {
                "event_created": 1_700_000_500,
                "status": "past_due",
                "current_period_end": "2030-05-01T00:00:00+00:00",
                "last_invoice_id": "in_late",
                "last_payment_failure_at": "2030-04-30T23:59:59+00:00",
            }
        )

        # Stub Stripe subscription retrieve — the checkout flow calls it.
        monkeypatch.setattr(
            stripe.Subscription,
            "retrieve",
            lambda sid: {"status": "active", "current_period_end": 1_800_000_000},
        )

        session = {
            "id": "cs_drain_newer",
            "customer": "cus_drain",
            "subscription": "sub_drain",
            "metadata": {"plan_id": "growth"},
        }
        await webhooks_mod._handle_checkout_completed(
            session, event_created=1_700_000_000
        )

        mapping = fake_redis.hashes["billing:tenant:tenant-drain"]
        # Pending update's status overrode the checkout status.
        assert mapping["status"] == "past_due"
        assert mapping["last_invoice_id"] == "in_late"
        assert mapping["last_event_created"] == "1700000500"
        # Pending value was popped — not lingering.
        assert "billing:pending_sub_update:sub_drain" not in fake_redis.values

    @pytest.mark.asyncio
    async def test_pending_update_older_than_checkout_is_superseded(
        self, fake_redis: _FakeRedis, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lines 169-176: pending update is older than the checkout
        event — we drop it and keep the checkout's values."""
        fake_redis.values["billing:session:cs_super"] = "tenant-super"

        import json as _json
        fake_redis.values["billing:pending_sub_update:sub_super"] = _json.dumps(
            {"event_created": 500, "status": "past_due"}
        )

        monkeypatch.setattr(
            stripe.Subscription,
            "retrieve",
            lambda sid: {"status": "active", "current_period_end": None},
        )

        session = {
            "id": "cs_super",
            "customer": "cus_super",
            "subscription": "sub_super",
            "metadata": {"plan_id": "growth"},
        }
        await webhooks_mod._handle_checkout_completed(
            session, event_created=1_000_000
        )

        mapping = fake_redis.hashes["billing:tenant:tenant-super"]
        # Checkout's status wins — the older pending update was NOT applied.
        assert mapping["status"] == "active"
        # And the buffer was drained (we popped it regardless of whether we applied).
        assert "billing:pending_sub_update:sub_super" not in fake_redis.values

    @pytest.mark.asyncio
    async def test_customer_bound_tenant_resolves_via_customer_lookup(
        self, fake_redis: _FakeRedis
    ) -> None:
        """Path where the server-side session key is missing but the
        customer was previously bound to a tenant (repeat checkout
        from an existing Stripe customer)."""
        fake_redis.values["billing:customer:cus_repeat"] = "tenant-repeat"

        session = {
            "id": "cs_repeat",
            "customer": "cus_repeat",
            "subscription": None,
            "metadata": {},
        }
        await webhooks_mod._handle_checkout_completed(session, event_created=10)

        mapping = fake_redis.hashes["billing:tenant:tenant-repeat"]
        assert mapping["customer_id"] == "cus_repeat"

    @pytest.mark.asyncio
    async def test_metadata_tenant_mismatch_is_rejected(
        self, fake_redis: _FakeRedis
    ) -> None:
        """Attacker defense: server-side binding says tenant-A, metadata
        claims tenant-B — raise 400."""
        fake_redis.values["billing:session:cs_attack"] = "tenant-real"

        session = {
            "id": "cs_attack",
            "customer": "cus_attack",
            "subscription": None,
            "metadata": {"tenant_id": "tenant-forged"},
        }
        with pytest.raises(HTTPException) as excinfo:
            await webhooks_mod._handle_checkout_completed(
                session, event_created=1
            )
        assert excinfo.value.status_code == 400


# ── _update_subscription_status ────────────────────────────────────────────


class TestUpdateSubscriptionStatus:
    """Gap lines: 213-239 (no-mapping: buffer vs bare log), 245-256
    (reorder guard), 272, 274."""

    def test_no_mapping_with_subscription_id_buffers_update(
        self, fake_redis: _FakeRedis, _stub_logger: _RecorderLogger
    ) -> None:
        """#1196: a subscription.updated before checkout.completed
        must buffer its payload so checkout drain can recover it."""
        webhooks_mod._update_subscription_status(
            subscription_id="sub_early",
            customer_id="cus_early",
            status="active",
            event_created=500,
            current_period_end="2030-01-01T00:00:00+00:00",
            last_invoice_id="in_e",
            last_payment_at="2030-01-01T00:00:00+00:00",
            last_payment_failure_at=None,
        )
        # Buffer written.
        assert "billing:pending_sub_update:sub_early" in fake_redis.values
        # Log emitted.
        assert any(
            call[1].startswith("billing_mapping_not_found_update_buffered")
            for call in _stub_logger.calls
        )

    def test_no_mapping_no_subscription_id_logs_only(
        self, fake_redis: _FakeRedis, _stub_logger: _RecorderLogger
    ) -> None:
        """If we can't even buffer (no subscription_id) we log at WARN
        and return — this is a defensive branch for malformed events."""
        webhooks_mod._update_subscription_status(
            subscription_id=None,
            customer_id="cus_lost",
            status="active",
            event_created=1,
        )
        # No buffer key written.
        assert not any(
            k.startswith("billing:pending_sub_update:") for k in fake_redis.values
        )
        # Log emitted (structlog event with kwargs).
        assert any(
            call[0] == "warning" and call[1] == "billing_mapping_not_found"
            for call in _stub_logger.calls
        )

    def test_reorder_guard_skips_stale_event(
        self, fake_redis: _FakeRedis, _stub_logger: _RecorderLogger
    ) -> None:
        """#1196 reorder guard: an event older than ``last_event_created``
        on the mapping must be skipped entirely."""
        # Seed mapping + lookup index.
        fake_redis.hashes["billing:tenant:tenant-guard"] = {
            "tenant_id": "tenant-guard",
            "status": "active",
            "last_event_created": "5000",
        }
        fake_redis.values["billing:subscription:sub_g"] = "tenant-guard"

        webhooks_mod._update_subscription_status(
            subscription_id="sub_g",
            customer_id="cus_g",
            status="canceled",
            event_created=1000,  # older than 5000
        )
        # Status was NOT overwritten — mapping still shows 'active'.
        assert fake_redis.hashes["billing:tenant:tenant-guard"]["status"] == "active"
        # The out-of-order log fired.
        assert any(
            "stripe_webhook_event_out_of_order_ignored" in call[1]
            for call in _stub_logger.calls
        )

    def test_reorder_guard_handles_corrupt_last_event_created(
        self, fake_redis: _FakeRedis
    ) -> None:
        """Lines 247-248: malformed ``last_event_created`` defaults to 0
        so the update is accepted (not dropped)."""
        fake_redis.hashes["billing:tenant:tenant-corrupt"] = {
            "tenant_id": "tenant-corrupt",
            "status": "active",
            "last_event_created": "not-an-int",
        }
        fake_redis.values["billing:subscription:sub_corrupt"] = "tenant-corrupt"

        webhooks_mod._update_subscription_status(
            subscription_id="sub_corrupt",
            customer_id="cus_corrupt",
            status="past_due",
            event_created=100,
        )
        assert fake_redis.hashes["billing:tenant:tenant-corrupt"]["status"] == "past_due"

    def test_happy_path_updates_all_fields(
        self, fake_redis: _FakeRedis
    ) -> None:
        """Lines 258-275: the full update path, exercising every
        conditional field (current_period_end, last_invoice_id,
        last_payment_at, last_payment_failure_at, last_event_created)."""
        fake_redis.hashes["billing:tenant:tenant-full"] = {
            "tenant_id": "tenant-full",
            "status": "trialing",
        }
        fake_redis.values["billing:subscription:sub_full"] = "tenant-full"

        webhooks_mod._update_subscription_status(
            subscription_id="sub_full",
            customer_id="cus_full",
            status="active",
            current_period_end="2030-06-01T00:00:00+00:00",
            last_invoice_id="in_full",
            last_payment_at="2030-05-01T00:00:00+00:00",
            last_payment_failure_at="2030-04-01T00:00:00+00:00",
            event_created=2500,
        )
        mapping = fake_redis.hashes["billing:tenant:tenant-full"]
        assert mapping["status"] == "active"
        assert mapping["current_period_end"] == "2030-06-01T00:00:00+00:00"
        assert mapping["last_invoice_id"] == "in_full"
        assert mapping["last_payment_at"] == "2030-05-01T00:00:00+00:00"
        assert mapping["last_payment_failure_at"] == "2030-04-01T00:00:00+00:00"
        assert mapping["last_event_created"] == "2500"


# ── _handle_stripe_event dispatcher ────────────────────────────────────────


class TestHandleStripeEventDispatcher:
    """Gap lines: 458-459 (checkout), 498-522 (subscription updated/deleted),
    539 (unknown event)."""

    @pytest.mark.asyncio
    async def test_checkout_session_completed_delegates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Line 458-459: ``checkout.session.completed`` calls
        ``_handle_checkout_completed`` with the data object + event_created."""
        spy = AsyncMock()
        monkeypatch.setattr(webhooks_mod, "_handle_checkout_completed", spy)

        event = {
            "id": "evt_checkout",
            "type": "checkout.session.completed",
            "created": 1_700_000_000,
            "data": {"object": {"id": "cs_1"}},
        }
        await webhooks_mod._handle_stripe_event(event)
        spy.assert_awaited_once()
        kwargs = spy.await_args.kwargs
        assert kwargs["event_created"] == 1_700_000_000
        assert spy.await_args.args[0] == {"id": "cs_1"}

    @pytest.mark.asyncio
    async def test_subscription_updated_dispatches_to_update(
        self, fake_redis: _FakeRedis, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lines 497-506: ``customer.subscription.updated`` calls
        ``_update_subscription_status`` with the subscription id +
        customer + status."""
        fake_redis.hashes["billing:tenant:tenant-sub"] = {
            "tenant_id": "tenant-sub",
            "status": "trialing",
        }
        fake_redis.values["billing:subscription:sub_xyz"] = "tenant-sub"

        event = {
            "id": "evt_sub_u",
            "type": "customer.subscription.updated",
            "created": 2_000_000_000,
            "data": {
                "object": {
                    "id": "sub_xyz",
                    "customer": "cus_xyz",
                    "status": "past_due",
                    "current_period_end": 1_900_000_000,
                }
            },
        }
        await webhooks_mod._handle_stripe_event(event)

        mapping = fake_redis.hashes["billing:tenant:tenant-sub"]
        assert mapping["status"] == "past_due"
        # period_end was populated via the post-update tightening branch
        # (lines 512-521).
        assert mapping["current_period_end"].startswith("2030")

    @pytest.mark.asyncio
    async def test_subscription_deleted_sets_canceled(
        self, fake_redis: _FakeRedis, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``customer.subscription.deleted`` translates to status='canceled'
        regardless of what the object's own status field says."""
        fake_redis.hashes["billing:tenant:tenant-del"] = {
            "tenant_id": "tenant-del",
            "status": "active",
        }
        fake_redis.values["billing:subscription:sub_del"] = "tenant-del"

        event = {
            "id": "evt_sub_del",
            "type": "customer.subscription.deleted",
            "created": 2_500_000_000,
            "data": {
                "object": {
                    "id": "sub_del",
                    "customer": "cus_del",
                    "status": "active",  # ignored — deletion always means canceled
                    "current_period_end": None,
                }
            },
        }
        await webhooks_mod._handle_stripe_event(event)

        assert fake_redis.hashes["billing:tenant:tenant-del"]["status"] == "canceled"

    @pytest.mark.asyncio
    async def test_subscription_updated_period_end_blocked_by_reorder_guard(
        self, fake_redis: _FakeRedis
    ) -> None:
        """Lines 513-521 with the inner ``event_created < last_seen``
        branch: even though the reorder guard in ``_update_subscription_status``
        rejected the whole update, the dispatcher re-checks the watermark
        before trying to persist period_end. Its own guard must also
        refuse, so we never clobber the newer mapping's current_period_end.
        """
        fake_redis.hashes["billing:tenant:tenant-stale"] = {
            "tenant_id": "tenant-stale",
            "status": "active",
            "current_period_end": "2030-01-01T00:00:00+00:00",
            "last_event_created": "9999",
        }
        fake_redis.values["billing:subscription:sub_stale"] = "tenant-stale"

        event = {
            "id": "evt_stale",
            "type": "customer.subscription.updated",
            "created": 100,  # far older than 9999
            "data": {
                "object": {
                    "id": "sub_stale",
                    "customer": "cus_stale",
                    "status": "canceled",
                    "current_period_end": 1_700_000_000,
                }
            },
        }
        await webhooks_mod._handle_stripe_event(event)

        # Nothing changed — stale update was ignored by both guards.
        assert fake_redis.hashes["billing:tenant:tenant-stale"]["status"] == "active"
        assert (
            fake_redis.hashes["billing:tenant:tenant-stale"]["current_period_end"]
            == "2030-01-01T00:00:00+00:00"
        )

    @pytest.mark.asyncio
    async def test_invoice_paid_emits_funnel_event(
        self, fake_redis: _FakeRedis, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``invoice.paid`` drives both the status update AND the
        conversion-funnel emit — cover both branches so refactors
        don't drop one."""
        fake_redis.hashes["billing:tenant:tenant-paid"] = {
            "tenant_id": "tenant-paid",
            "status": "trialing",
        }
        fake_redis.values["billing:subscription:sub_paid"] = "tenant-paid"

        captured: list[dict[str, Any]] = []
        import shared.funnel_events as funnel_events
        monkeypatch.setattr(
            funnel_events,
            "emit_funnel_event",
            lambda **kwargs: captured.append(kwargs) or True,
        )

        event = {
            "id": "evt_paid",
            "type": "invoice.paid",
            "created": 2_000_000_000,
            "data": {
                "object": {
                    "id": "in_1",
                    "subscription": "sub_paid",
                    "customer": "cus_paid",
                    "period_end": 1_900_000_000,
                    "status_transitions": {"paid_at": 1_700_000_000},
                }
            },
        }
        await webhooks_mod._handle_stripe_event(event)

        assert fake_redis.hashes["billing:tenant:tenant-paid"]["status"] == "active"
        assert len(captured) == 1
        assert captured[0]["event_name"] == "payment_completed"
        assert captured[0]["tenant_id"] == "tenant-paid"

    @pytest.mark.asyncio
    async def test_invoice_payment_failed_sets_past_due(
        self, fake_redis: _FakeRedis
    ) -> None:
        fake_redis.hashes["billing:tenant:tenant-fail"] = {
            "tenant_id": "tenant-fail",
            "status": "active",
        }
        fake_redis.values["billing:subscription:sub_fail"] = "tenant-fail"

        event = {
            "id": "evt_fail",
            "type": "invoice.payment_failed",
            "created": 2_100_000_000,
            "data": {
                "object": {
                    "id": "in_fail",
                    "subscription": "sub_fail",
                    "customer": "cus_fail",
                    "created": 2_100_000_000,
                }
            },
        }
        await webhooks_mod._handle_stripe_event(event)

        mapping = fake_redis.hashes["billing:tenant:tenant-fail"]
        assert mapping["status"] == "past_due"
        assert mapping["last_invoice_id"] == "in_fail"

    @pytest.mark.asyncio
    async def test_unknown_event_type_is_logged_and_skipped(
        self, _stub_logger: _RecorderLogger
    ) -> None:
        """Line 539: unrecognized event types fall through to a
        debug/info log. No handler side-effect."""
        event = {
            "id": "evt_unknown",
            "type": "payout.paid",  # not handled
            "created": 1,
            "data": {"object": {}},
        }
        await webhooks_mod._handle_stripe_event(event)

        assert any(
            call[1] == "stripe_webhook_ignored" for call in _stub_logger.calls
        )


# ── _process_stripe_webhook ────────────────────────────────────────────────


class TestProcessStripeWebhook:
    """Gap lines: 550 (missing secret), 564 (bad payload)."""

    @pytest.mark.asyncio
    async def test_missing_webhook_secret_returns_500(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
        request = MagicMock()
        request.body = AsyncMock(return_value=b"{}")

        with pytest.raises(HTTPException) as excinfo:
            await webhooks_mod._process_stripe_webhook(
                request, stripe_signature="t=1,v1=fake"
            )
        assert excinfo.value.status_code == 500
        assert "STRIPE_WEBHOOK_SECRET" in excinfo.value.detail

    @pytest.mark.asyncio
    async def test_missing_signature_header_returns_400(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
        request = MagicMock()
        request.body = AsyncMock(return_value=b"{}")

        with pytest.raises(HTTPException) as excinfo:
            await webhooks_mod._process_stripe_webhook(
                request, stripe_signature=None
            )
        assert excinfo.value.status_code == 400
        assert "Stripe-Signature" in excinfo.value.detail

    @pytest.mark.asyncio
    async def test_non_json_payload_raises_400(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Line 564: ``stripe.Webhook.construct_event`` raises ValueError
        on malformed payloads — translate to 400."""
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")

        def _raise_value_error(**_kwargs: Any) -> Any:
            raise ValueError("not json")

        monkeypatch.setattr(
            stripe.Webhook, "construct_event", _raise_value_error
        )

        request = MagicMock()
        request.body = AsyncMock(return_value=b"not-json")

        with pytest.raises(HTTPException) as excinfo:
            await webhooks_mod._process_stripe_webhook(
                request, stripe_signature="t=1,v1=fake"
            )
        assert excinfo.value.status_code == 400
        assert "Invalid webhook payload" in excinfo.value.detail

    @pytest.mark.asyncio
    async def test_invalid_signature_returns_401_no_handler_run(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
        fake = _FakeRedis()
        monkeypatch.setattr(state_mod, "_redis_client", lambda: fake)

        def _raise_sig_err(**_kwargs: Any) -> Any:
            raise stripe.error.SignatureVerificationError(
                "bad sig", sig_header=_kwargs.get("sig_header", "")
            )

        monkeypatch.setattr(stripe.Webhook, "construct_event", _raise_sig_err)

        handler = AsyncMock()
        monkeypatch.setattr(webhooks_mod, "_handle_stripe_event", handler)

        request = MagicMock()
        request.body = AsyncMock(return_value=b"{}")

        with pytest.raises(HTTPException) as excinfo:
            await webhooks_mod._process_stripe_webhook(
                request, stripe_signature="t=1,v1=bad"
            )
        assert excinfo.value.status_code == 401
        # Handler did NOT run.
        handler.assert_not_awaited()
        # No dedup slot consumed.
        assert not any(
            k.startswith("billing:stripe:event:seen:") for k in fake.values
        )

    @pytest.mark.asyncio
    async def test_happy_path_ack_and_handler_awaited(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Exercises the full success path: secret set, signature ok,
        dedup slot fresh, handler dispatched, 200-shaped response."""
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
        fake = _FakeRedis()
        monkeypatch.setattr(state_mod, "_redis_client", lambda: fake)

        monkeypatch.setattr(
            stripe.Webhook,
            "construct_event",
            lambda **_: {"id": "evt_ok", "type": "invoice.paid", "data": {"object": {}}},
        )

        handler = AsyncMock()
        monkeypatch.setattr(webhooks_mod, "_handle_stripe_event", handler)

        request = MagicMock()
        request.body = AsyncMock(return_value=b'{"id":"evt_ok"}')

        response = await webhooks_mod._process_stripe_webhook(
            request, stripe_signature="t=1,v1=ok"
        )
        assert response == {"received": True, "event_type": "invoice.paid"}
        handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_duplicate_event_is_short_circuited(
        self, monkeypatch: pytest.MonkeyPatch, _stub_logger: _RecorderLogger
    ) -> None:
        """Lines 582-587: once ``_mark_event_seen`` reports the event id
        is already processed, we ack as ``duplicate=True`` and never call
        the handler."""
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")

        monkeypatch.setattr(
            stripe.Webhook,
            "construct_event",
            lambda **_: {
                "id": "evt_dup",
                "type": "invoice.paid",
                "data": {"object": {}},
            },
        )

        # Dedup returns False → this is a duplicate.
        monkeypatch.setattr(state_mod, "_mark_event_seen", lambda _eid: False)

        handler = AsyncMock()
        monkeypatch.setattr(webhooks_mod, "_handle_stripe_event", handler)

        request = MagicMock()
        request.body = AsyncMock(return_value=b'{"id":"evt_dup"}')

        response = await webhooks_mod._process_stripe_webhook(
            request, stripe_signature="t=1,v1=ok"
        )

        assert response == {
            "received": True,
            "event_type": "invoice.paid",
            "duplicate": True,
        }
        handler.assert_not_awaited()
        # Duplicate-ignored log emitted.
        assert any(
            "stripe_webhook_duplicate_ignored" in call[1]
            for call in _stub_logger.calls
        )


# ── _handle_checkout_completed client-metadata-tenant warning ──────────────


class TestHandleCheckoutCompletedClientMetadataWarning:
    """Gap line 82: when there's no server-side binding BUT the client
    supplied metadata.tenant_id, we warn & ignore — never trust the
    client-supplied id for a brand-new signup."""

    @pytest.mark.asyncio
    async def test_client_metadata_tenant_id_without_binding_is_warned(
        self,
        fake_redis: _FakeRedis,
        monkeypatch: pytest.MonkeyPatch,
        _stub_logger: _RecorderLogger,
    ) -> None:
        created: list[str] = []

        async def _fake_create(tenant_name: str) -> str:
            created.append(tenant_name)
            return "tenant-auto-warn"

        monkeypatch.setattr(
            customers_mod, "_create_tenant_via_admin", _fake_create
        )

        # No server-side binding at all.
        session = {
            "id": "cs_warn",
            "customer": "cus_warn",
            "subscription": None,
            "metadata": {"tenant_id": "tenant-forged-by-client"},
        }
        await webhooks_mod._handle_checkout_completed(session, event_created=1)

        # The client-supplied id was IGNORED — a fresh tenant was created.
        assert created == ["New Customer Team"]
        # Warning fired with the ignored-client-metadata marker.
        assert any(
            call[1].startswith(
                "stripe_webhook_ignored_client_metadata_tenant_id"
            )
            for call in _stub_logger.calls
        )


# ── _handle_trial_will_end ────────────────────────────────────────────────


class TestHandleTrialWillEnd:
    """Gap lines 296-324: handler + its dispatcher at 526-527."""

    def test_no_tenant_bound_logs_warning_and_returns(
        self, fake_redis: _FakeRedis, _stub_logger: _RecorderLogger
    ) -> None:
        """Lines 302-309: when neither subscription_id nor customer_id
        lookup finds a tenant we warn and no-op (no mapping written)."""
        subscription = {
            "id": "sub_trial_nowhere",
            "customer": "cus_trial_nowhere",
            "trial_end": 1_900_000_000,
            "status": "trialing",
        }

        webhooks_mod._handle_trial_will_end(subscription)

        # No mapping written.
        assert not fake_redis.hashes
        # Warning emitted.
        assert any(
            call[1].startswith("stripe_trial_will_end_tenant_not_found")
            for call in _stub_logger.calls
        )

    def test_happy_path_stamps_trial_end_and_notification(
        self, fake_redis: _FakeRedis, _stub_logger: _RecorderLogger
    ) -> None:
        """Lines 311-327: on success we stamp ``trial_end``,
        ``trial_will_end_notified_at``, preserve ``status``, and log."""
        fake_redis.hashes["billing:tenant:tenant-trial"] = {
            "tenant_id": "tenant-trial",
            "status": "trialing",
        }
        fake_redis.values["billing:subscription:sub_trial"] = "tenant-trial"

        subscription = {
            "id": "sub_trial",
            "customer": "cus_trial",
            "trial_end": 1_900_000_000,
            "status": "trialing",
        }

        webhooks_mod._handle_trial_will_end(subscription)

        mapping = fake_redis.hashes["billing:tenant:tenant-trial"]
        assert mapping["trial_end"].startswith("20")  # ISO date
        assert mapping["trial_will_end_notified_at"]  # non-empty ISO
        assert mapping["status"] == "trialing"
        assert any(
            call[0] == "warning"
            and call[1] == "stripe_trial_will_end"
            and call[3].get("tenant_id") == "tenant-trial"
            for call in _stub_logger.calls
        )

    @pytest.mark.asyncio
    async def test_dispatcher_routes_to_trial_will_end(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lines 526-527: ``customer.subscription.trial_will_end`` dispatch."""
        spy = MagicMock()
        monkeypatch.setattr(webhooks_mod, "_handle_trial_will_end", spy)

        event = {
            "id": "evt_trial",
            "type": "customer.subscription.trial_will_end",
            "created": 1_800_000_000,
            "data": {"object": {"id": "sub_t", "customer": "cus_t"}},
        }
        await webhooks_mod._handle_stripe_event(event)

        spy.assert_called_once_with({"id": "sub_t", "customer": "cus_t"})


# ── _handle_dispute_created ───────────────────────────────────────────────


class TestHandleDisputeCreated:
    """Gap lines 347-391: handler + dispatcher at 531-532."""

    def test_no_tenant_bound_logs_error_and_returns(
        self, fake_redis: _FakeRedis, _stub_logger: _RecorderLogger
    ) -> None:
        """Lines 353-360: customer lookup misses → ERROR log, no mapping
        write, no exception."""
        dispute = {
            "id": "dp_orphan",
            "charge": "ch_orphan",
            "customer": "cus_orphan",
            "amount": 5000,
            "currency": "usd",
            "reason": "fraudulent",
            "status": "warning_needs_response",
        }

        webhooks_mod._handle_dispute_created(dispute)

        assert not fake_redis.hashes
        assert any(
            call[0] == "error"
            and call[1].startswith("stripe_dispute_tenant_not_found")
            for call in _stub_logger.calls
        )

    def test_happy_path_persists_dispute_and_pages_on_error(
        self, fake_redis: _FakeRedis, _stub_logger: _RecorderLogger
    ) -> None:
        """Lines 362-391: dispute metadata persisted + ERROR-level log fires."""
        fake_redis.hashes["billing:tenant:tenant-disp"] = {
            "tenant_id": "tenant-disp",
            "status": "active",
        }
        fake_redis.values["billing:customer:cus_disp"] = "tenant-disp"

        dispute = {
            "id": "dp_42",
            "charge": "ch_42",
            "customer": "cus_disp",
            "amount": 9999,
            "currency": "usd",
            "reason": "fraudulent",
            "status": "warning_needs_response",
            "created": 1_800_000_000,
        }
        webhooks_mod._handle_dispute_created(dispute)

        mapping = fake_redis.hashes["billing:tenant:tenant-disp"]
        assert mapping["last_dispute_id"] == "dp_42"
        assert mapping["last_dispute_charge_id"] == "ch_42"
        assert mapping["last_dispute_amount_cents"] == "9999"
        assert mapping["last_dispute_currency"] == "usd"
        assert mapping["last_dispute_reason"] == "fraudulent"
        assert mapping["last_dispute_status"] == "warning_needs_response"
        assert mapping["last_dispute_opened_at"].startswith("20")

        # ERROR log fires (page on-call).
        assert any(
            call[0] == "error"
            and call[1] == "stripe_dispute_opened"
            and call[3].get("tenant_id") == "tenant-disp"
            for call in _stub_logger.calls
        )

    def test_missing_created_falls_back_to_now(
        self, fake_redis: _FakeRedis
    ) -> None:
        """Line 377: when ``created`` is missing we substitute a UTC now
        ISO string so ``last_dispute_opened_at`` is never empty."""
        fake_redis.hashes["billing:tenant:tenant-disp2"] = {
            "tenant_id": "tenant-disp2",
            "status": "active",
        }
        fake_redis.values["billing:customer:cus_disp2"] = "tenant-disp2"

        dispute = {
            "id": "dp_no_created",
            "charge": "ch",
            "customer": "cus_disp2",
            "amount": 10,
            "currency": "usd",
            "reason": "duplicate",
            "status": "needs_response",
            # no "created"
        }
        webhooks_mod._handle_dispute_created(dispute)

        mapping = fake_redis.hashes["billing:tenant:tenant-disp2"]
        assert mapping["last_dispute_opened_at"]  # non-empty

    @pytest.mark.asyncio
    async def test_dispatcher_routes_to_dispute_created(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lines 531-532: ``charge.dispute.created`` dispatch."""
        spy = MagicMock()
        monkeypatch.setattr(webhooks_mod, "_handle_dispute_created", spy)

        event = {
            "id": "evt_disp",
            "type": "charge.dispute.created",
            "created": 1_900_000_000,
            "data": {"object": {"id": "dp_1"}},
        }
        await webhooks_mod._handle_stripe_event(event)

        spy.assert_called_once_with({"id": "dp_1"})


# ── _handle_customer_deleted ──────────────────────────────────────────────


class TestHandleCustomerDeleted:
    """Gap lines 412-445: handler + dispatcher at 536-537."""

    def test_missing_customer_id_logs_and_returns(
        self, fake_redis: _FakeRedis, _stub_logger: _RecorderLogger
    ) -> None:
        """Lines 413-415: no ``id`` on the customer → warn & return."""
        webhooks_mod._handle_customer_deleted({})

        assert not fake_redis.hashes
        assert any(
            call[1] == "stripe_customer_deleted_missing_id"
            for call in _stub_logger.calls
        )

    def test_no_tenant_still_clears_stale_lookup(
        self, fake_redis: _FakeRedis, _stub_logger: _RecorderLogger
    ) -> None:
        """Lines 418-426: unknown customer still triggers the defensive
        lookup cleanup so stale pointers don't linger."""
        # Pre-seed a dangling lookup that points nowhere.
        fake_redis.values["billing:customer:cus_dangle"] = "tenant-ghost"
        # But no tenant mapping exists, and our lookup returns None.
        # Monkey-patch _find_tenant_id to simulate a hard miss.
        from app.stripe_billing import state as _state
        orig_find = _state._find_tenant_id
        _state._find_tenant_id = lambda sub, cust: None  # type: ignore[assignment]
        try:
            webhooks_mod._handle_customer_deleted({"id": "cus_dangle"})
        finally:
            _state._find_tenant_id = orig_find  # type: ignore[assignment]

        # Lookup cleared even though no tenant was bound.
        assert "billing:customer:cus_dangle" not in fake_redis.values
        assert any(
            call[1].startswith("stripe_customer_deleted_tenant_not_found")
            for call in _stub_logger.calls
        )

    def test_happy_path_marks_deleted_and_clears_both_lookups(
        self, fake_redis: _FakeRedis, _stub_logger: _RecorderLogger
    ) -> None:
        """Lines 428-445: mapping is flipped to ``customer_deleted``,
        both the customer and subscription lookups are deleted, and we
        WARN."""
        fake_redis.hashes["billing:tenant:tenant-ghost"] = {
            "tenant_id": "tenant-ghost",
            "status": "active",
            "subscription_id": "sub_ghost",
        }
        fake_redis.values["billing:customer:cus_ghost"] = "tenant-ghost"
        fake_redis.values["billing:subscription:sub_ghost"] = "tenant-ghost"

        webhooks_mod._handle_customer_deleted({"id": "cus_ghost"})

        mapping = fake_redis.hashes["billing:tenant:tenant-ghost"]
        assert mapping["status"] == "customer_deleted"
        assert mapping["customer_deleted_at"].startswith("20")
        # Both lookup keys deleted.
        assert "billing:customer:cus_ghost" not in fake_redis.values
        assert "billing:subscription:sub_ghost" not in fake_redis.values
        # WARN fired (structlog event with tenant_id kwarg).
        assert any(
            call[0] == "warning"
            and call[1] == "stripe_customer_deleted"
            and call[3].get("tenant_id") == "tenant-ghost"
            for call in _stub_logger.calls
        )

    def test_happy_path_without_subscription_skips_subscription_clear(
        self, fake_redis: _FakeRedis
    ) -> None:
        """Line 439-440: when no prior subscription_id was on the mapping
        we skip ``_clear_subscription_lookup`` (nothing to clear)."""
        fake_redis.hashes["billing:tenant:tenant-no-sub"] = {
            "tenant_id": "tenant-no-sub",
            "status": "active",
            # no subscription_id field
        }
        fake_redis.values["billing:customer:cus_nosub"] = "tenant-no-sub"

        webhooks_mod._handle_customer_deleted({"id": "cus_nosub"})

        assert (
            fake_redis.hashes["billing:tenant:tenant-no-sub"]["status"]
            == "customer_deleted"
        )
        # No subscription lookup to remove — nothing crashed.

    @pytest.mark.asyncio
    async def test_dispatcher_routes_to_customer_deleted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lines 536-537: ``customer.deleted`` dispatch."""
        spy = MagicMock()
        monkeypatch.setattr(webhooks_mod, "_handle_customer_deleted", spy)

        event = {
            "id": "evt_cdel",
            "type": "customer.deleted",
            "created": 2_100_000_000,
            "data": {"object": {"id": "cus_gone"}},
        }
        await webhooks_mod._handle_stripe_event(event)

        spy.assert_called_once_with({"id": "cus_gone"})


# ── corrupt last_event_created in subscription.updated dispatcher ──────────


class TestSubscriptionUpdatedCorruptWatermark:
    """Gap lines 517-518: the dispatcher's OWN watermark re-check defends
    against corrupt ``last_event_created`` values by defaulting to 0."""

    @pytest.mark.asyncio
    async def test_corrupt_watermark_allows_period_end_update(
        self, fake_redis: _FakeRedis
    ) -> None:
        """Corrupt ``last_event_created`` + ``event.created`` missing →
        the inner try/except at lines 515-518 falls through to
        ``last_seen = 0`` and we still persist ``current_period_end``.

        We omit ``created`` from the event so ``_update_subscription_status``
        keeps the existing corrupt watermark (it only overwrites when
        the incoming ``event_created`` is truthy), leaving the corrupt
        value in place for the dispatcher's own re-check to exercise
        the ValueError branch at 517-518."""
        fake_redis.hashes["billing:tenant:tenant-bad-wm"] = {
            "tenant_id": "tenant-bad-wm",
            "status": "active",
            "last_event_created": "not-a-number",
        }
        fake_redis.values["billing:subscription:sub_bad_wm"] = "tenant-bad-wm"

        event = {
            "id": "evt_bad_wm",
            "type": "customer.subscription.updated",
            # no "created" — event_created → None via _coerce_int default=0 → None
            "data": {
                "object": {
                    "id": "sub_bad_wm",
                    "customer": "cus_bad_wm",
                    "status": "canceled",
                    "current_period_end": 1_900_000_000,
                }
            },
        }
        await webhooks_mod._handle_stripe_event(event)

        # Both try/excepts swallowed the ValueError — mapping was updated.
        mapping = fake_redis.hashes["billing:tenant:tenant-bad-wm"]
        assert mapping["current_period_end"].startswith("20")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
