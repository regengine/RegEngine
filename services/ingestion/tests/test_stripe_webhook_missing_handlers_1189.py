"""Regression tests for missing Stripe webhook handlers (#1189).

Before this fix, ``_handle_stripe_event`` only dispatched on a handful
of event types (``checkout.session.completed``, ``invoice.payment_failed``,
``invoice.paid``, ``customer.subscription.deleted/updated``). Every
other event fell through to ``logger.info("stripe_webhook_ignored",
event_type=...)`` and was silently dropped, including three events
with direct operational consequences:

- ``customer.subscription.trial_will_end`` — Stripe fires this ~3 days
  before a trial expires. Without a handler, the tenant gets no prompt
  to add a payment method and product/marketing has no signal to nudge
  conversion.

- ``charge.dispute.created`` — a chargeback has been opened. Without a
  handler, on-call is never paged and the 7-day response window to
  contest the dispute expires silently, at which point Stripe loses
  the chargeback by default.

- ``customer.deleted`` — the Stripe customer has been deleted. Without
  a handler, the ``billing:customer:{customer_id}`` lookup remains
  pointed at the now-stale tenant, and a subsequent out-of-order
  webhook (common during Stripe retries) can re-bind that dead ID.

This suite locks each handler in. A regression that reverts the
handler to the silent-ignore branch fails specific named tests below.

The handlers live in ``services/ingestion/app/stripe_billing/webhooks.py``
(``_handle_trial_will_end``, ``_handle_dispute_created``,
``_handle_customer_deleted``) and the Redis cleanup helpers live in
``services/ingestion/app/stripe_billing/state.py``.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Optional

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app.stripe_billing import state as state_mod  # noqa: E402
from app.stripe_billing import webhooks as webhooks_mod  # noqa: E402


# ── Fake Redis that models enough for these handlers ───────────────────────


class _FakeRedis:
    """In-memory Redis stand-in with just the methods our handlers use."""

    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.values: dict[str, str] = {}
        self.delete_calls: list[str] = []

    # Hash API used by _store_subscription_mapping / _get_subscription_mapping
    def hset(self, key: str, mapping: dict[str, str]) -> None:
        self.hashes.setdefault(key, {})
        self.hashes[key].update(mapping)

    def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.hashes.get(key, {}))

    # Scalar API used by lookup keys.
    def set(
        self,
        key: str,
        value: str,
        nx: bool = False,
        ex: Optional[int] = None,
    ) -> Any:
        if nx and key in self.values:
            return None
        self.values[key] = value
        return True

    def get(self, key: str) -> Optional[str]:
        return self.values.get(key)

    def delete(self, key: str) -> int:
        self.delete_calls.append(key)
        existed = key in self.values
        self.values.pop(key, None)
        return 1 if existed else 0


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> _FakeRedis:
    """Install a shared _FakeRedis for both state_mod and webhooks_mod."""
    fake = _FakeRedis()
    monkeypatch.setattr(state_mod, "_redis_client", lambda: fake)
    return fake


# ── Shared fixtures: pre-bind a tenant via checkout so lookups succeed ─────


TENANT = "tenant-1189"
CUSTOMER = "cus_1189_abc"
SUBSCRIPTION = "sub_1189_xyz"


def _prebind_tenant(fake: _FakeRedis) -> None:
    """Simulate a prior successful checkout so the lookup keys resolve."""
    state_mod._store_subscription_mapping(
        TENANT,
        {
            "tenant_id": TENANT,
            "customer_id": CUSTOMER,
            "subscription_id": SUBSCRIPTION,
            "status": "trialing",
            "plan_id": "growth",
            "billing_period": "monthly",
        },
    )


# ---------------------------------------------------------------------------
# customer.subscription.trial_will_end
# ---------------------------------------------------------------------------


class TestTrialWillEnd_Issue1189:
    def test_persists_trial_end_and_notified_at(self, fake_redis) -> None:
        """Handler writes both ``trial_end`` (ISO8601) and
        ``trial_will_end_notified_at`` onto the subscription mapping
        so the app can surface the countdown and avoid re-notifying."""
        _prebind_tenant(fake_redis)
        # 2026-04-21 12:00:00 UTC
        trial_end_epoch = 1776513600

        webhooks_mod._handle_trial_will_end(
            {
                "id": SUBSCRIPTION,
                "customer": CUSTOMER,
                "status": "trialing",
                "trial_end": trial_end_epoch,
            }
        )
        mapping = state_mod._get_subscription_mapping(TENANT)
        assert mapping["trial_end"].startswith("2026-"), (
            f"trial_end must be ISO8601 formatted, got: {mapping.get('trial_end')!r}"
        )
        assert mapping["trial_will_end_notified_at"], (
            "trial_will_end_notified_at must be set so repeat notifications "
            "can be suppressed downstream"
        )

    def test_keeps_existing_plan_id_and_billing_period(self, fake_redis) -> None:
        """The trial-notice handler updates only the trial fields and
        status; plan_id / billing_period / other business fields set at
        checkout must survive untouched."""
        _prebind_tenant(fake_redis)
        webhooks_mod._handle_trial_will_end(
            {
                "id": SUBSCRIPTION,
                "customer": CUSTOMER,
                "status": "trialing",
                "trial_end": 1776513600,
            }
        )
        mapping = state_mod._get_subscription_mapping(TENANT)
        assert mapping["plan_id"] == "growth"
        assert mapping["billing_period"] == "monthly"

    def test_warn_log_emitted_for_operator_visibility(
        self, fake_redis, caplog,
    ) -> None:
        """The trial-notice must emit WARN so the 3-day countdown lands
        in operator dashboards and alerting. A silent INFO would hide
        this from conversion-tracking dashboards."""
        _prebind_tenant(fake_redis)
        with caplog.at_level(logging.WARNING, logger="stripe-billing"):
            webhooks_mod._handle_trial_will_end(
                {
                    "id": SUBSCRIPTION,
                    "customer": CUSTOMER,
                    "status": "trialing",
                    "trial_end": 1776513600,
                }
            )
        warn_records = [
            r for r in caplog.records
            if r.levelname == "WARNING"
            and "stripe_trial_will_end" in r.getMessage()
            and "tenant_not_found" not in r.getMessage()
        ]
        assert len(warn_records) == 1, (
            f"Expected exactly one WARN stripe_trial_will_end log, "
            f"got {len(warn_records)}"
        )

    def test_unknown_tenant_does_not_crash(self, fake_redis, caplog) -> None:
        """If the subscription/customer cannot be mapped to a tenant
        (e.g. trial started before our first successful checkout), the
        handler logs and no-ops rather than raising."""
        with caplog.at_level(logging.WARNING, logger="stripe-billing"):
            webhooks_mod._handle_trial_will_end(
                {
                    "id": "sub_unknown",
                    "customer": "cus_unknown",
                    "status": "trialing",
                    "trial_end": 1776513600,
                }
            )
        # Must have logged the miss.
        assert any(
            "stripe_trial_will_end_tenant_not_found" in r.getMessage()
            for r in caplog.records
        ), "Missing-tenant branch must log for operator visibility"

    def test_dispatcher_routes_trial_will_end_to_handler(
        self, fake_redis,
    ) -> None:
        """End-to-end: the top-level ``_handle_stripe_event`` dispatcher
        must route ``customer.subscription.trial_will_end`` to our new
        handler (not fall through to stripe_webhook_ignored)."""
        import asyncio
        _prebind_tenant(fake_redis)
        event = {
            "id": "evt_trial_1",
            "type": "customer.subscription.trial_will_end",
            "data": {
                "object": {
                    "id": SUBSCRIPTION,
                    "customer": CUSTOMER,
                    "status": "trialing",
                    "trial_end": 1776513600,
                }
            },
        }
        asyncio.run(webhooks_mod._handle_stripe_event(event))
        mapping = state_mod._get_subscription_mapping(TENANT)
        assert mapping.get("trial_will_end_notified_at"), (
            "Dispatcher must route trial_will_end into "
            "_handle_trial_will_end; silent fall-through indicates "
            "regression to the ignored-event branch"
        )


# ---------------------------------------------------------------------------
# charge.dispute.created
# ---------------------------------------------------------------------------


class TestDisputeCreated_Issue1189:
    def test_persists_dispute_metadata(self, fake_redis) -> None:
        """All ops-critical fields on the dispute must be persisted:
        id, charge, amount, currency, reason, status, and opened_at.
        Missing any of these cripples the admin dashboard's ability to
        render the dispute record for human response."""
        _prebind_tenant(fake_redis)
        webhooks_mod._handle_dispute_created(
            {
                "id": "dp_abc123",
                "charge": "ch_xyz789",
                "customer": CUSTOMER,
                "amount": 5000,  # cents
                "currency": "usd",
                "reason": "fraudulent",
                "status": "warning_needs_response",
                "created": 1712345678,
            }
        )
        mapping = state_mod._get_subscription_mapping(TENANT)
        assert mapping["last_dispute_id"] == "dp_abc123"
        assert mapping["last_dispute_charge_id"] == "ch_xyz789"
        assert mapping["last_dispute_amount_cents"] == "5000"
        assert mapping["last_dispute_currency"] == "usd"
        assert mapping["last_dispute_reason"] == "fraudulent"
        assert mapping["last_dispute_status"] == "warning_needs_response"
        assert mapping["last_dispute_opened_at"].startswith("2024-04-05"), (
            f"dispute opened_at must be ISO8601 from 'created' epoch, "
            f"got {mapping.get('last_dispute_opened_at')!r}"
        )

    def test_amount_cents_is_integer_string_not_float(
        self, fake_redis,
    ) -> None:
        """Amount must be stored as a cents-integer string, never a
        float/dollars conversion. A regression that divides by 100
        would lose the cent precision and confuse downstream
        aggregation (Stripe reports in cents)."""
        _prebind_tenant(fake_redis)
        webhooks_mod._handle_dispute_created(
            {
                "id": "dp_amount_test",
                "charge": "ch_x",
                "customer": CUSTOMER,
                "amount": 1999,
                "currency": "usd",
                "reason": "general",
                "status": "warning_under_review",
                "created": 1712345678,
            }
        )
        mapping = state_mod._get_subscription_mapping(TENANT)
        assert mapping["last_dispute_amount_cents"] == "1999", (
            "amount must be stored as the raw Stripe cents integer"
        )
        # Must not contain a decimal point.
        assert "." not in mapping["last_dispute_amount_cents"]

    def test_error_level_log_for_oncall_paging(
        self, fake_redis, caplog,
    ) -> None:
        """Chargebacks must log at ERROR so alerting pipelines
        (PagerDuty, Sentry) page a human. A WARN-level log would be
        deprioritized and the 7-day Stripe response window would
        expire silently."""
        _prebind_tenant(fake_redis)
        with caplog.at_level(logging.ERROR, logger="stripe-billing"):
            webhooks_mod._handle_dispute_created(
                {
                    "id": "dp_oncall_1",
                    "charge": "ch_x",
                    "customer": CUSTOMER,
                    "amount": 5000,
                    "currency": "usd",
                    "reason": "fraudulent",
                    "status": "warning_needs_response",
                    "created": 1712345678,
                }
            )
        error_records = [
            r for r in caplog.records
            if r.levelname == "ERROR"
            and "stripe_dispute_opened" in r.getMessage()
        ]
        assert len(error_records) == 1, (
            f"Expected exactly one ERROR stripe_dispute_opened log for "
            f"oncall paging, got {len(error_records)}"
        )

    def test_unknown_customer_logs_error_does_not_crash(
        self, fake_redis, caplog,
    ) -> None:
        """If Stripe sends a dispute for a customer we don't know
        (shouldn't happen in prod — all our customers originate from
        checkout — but the handler must not crash the event processor),
        we log at ERROR and skip the mapping update."""
        with caplog.at_level(logging.ERROR, logger="stripe-billing"):
            webhooks_mod._handle_dispute_created(
                {
                    "id": "dp_unknown_cust",
                    "charge": "ch_y",
                    "customer": "cus_we_dont_know",
                    "amount": 100,
                    "currency": "usd",
                    "reason": "general",
                    "status": "needs_response",
                    "created": 1712345678,
                }
            )
        assert any(
            "stripe_dispute_tenant_not_found" in r.getMessage()
            for r in caplog.records
        )

    def test_dispatcher_routes_dispute_created_to_handler(
        self, fake_redis,
    ) -> None:
        """End-to-end: dispatcher must route
        ``charge.dispute.created`` into ``_handle_dispute_created``."""
        import asyncio
        _prebind_tenant(fake_redis)
        event = {
            "id": "evt_dispute_1",
            "type": "charge.dispute.created",
            "data": {
                "object": {
                    "id": "dp_routed",
                    "charge": "ch_routed",
                    "customer": CUSTOMER,
                    "amount": 7500,
                    "currency": "usd",
                    "reason": "duplicate",
                    "status": "warning_needs_response",
                    "created": 1712345678,
                }
            },
        }
        asyncio.run(webhooks_mod._handle_stripe_event(event))
        mapping = state_mod._get_subscription_mapping(TENANT)
        assert mapping.get("last_dispute_id") == "dp_routed", (
            "Dispatcher must route dispute.created into the handler; "
            "regression to silent-ignore would leave the field absent"
        )


# ---------------------------------------------------------------------------
# customer.deleted
# ---------------------------------------------------------------------------


class TestCustomerDeleted_Issue1189:
    def test_flags_subscription_as_customer_deleted(self, fake_redis) -> None:
        """The subscription mapping must be marked ``customer_deleted``
        (distinct from ``canceled`` — canceled means the subscription
        ended; customer_deleted means the entire Stripe customer record
        was removed, which is a strictly stronger state)."""
        _prebind_tenant(fake_redis)
        webhooks_mod._handle_customer_deleted({"id": CUSTOMER})
        mapping = state_mod._get_subscription_mapping(TENANT)
        assert mapping["status"] == "customer_deleted"
        assert mapping["customer_deleted_at"], (
            "customer_deleted_at must be set so audit trail shows WHEN "
            "the deletion notice arrived"
        )

    def test_clears_customer_lookup_key(self, fake_redis) -> None:
        """The ``billing:customer:{customer_id}`` lookup MUST be deleted
        so a subsequent out-of-order webhook for the stale customer_id
        cannot silently re-bind to the same tenant."""
        _prebind_tenant(fake_redis)
        lookup_key = state_mod._customer_lookup_key(CUSTOMER)
        assert lookup_key in fake_redis.values, (
            "Preconditions: lookup key must exist before deletion"
        )

        webhooks_mod._handle_customer_deleted({"id": CUSTOMER})
        assert lookup_key not in fake_redis.values, (
            "customer lookup key MUST be deleted so a later webhook "
            "cannot silently re-resolve to the deleted tenant"
        )
        assert lookup_key in fake_redis.delete_calls, (
            "Handler must have called redis.delete on the lookup key"
        )

    def test_clears_subscription_lookup_key(self, fake_redis) -> None:
        """The ``billing:subscription:{subscription_id}`` lookup must
        also be cleared — a deleted customer means the subscription
        cannot be billed again, so the lookup is stale."""
        _prebind_tenant(fake_redis)
        sub_key = state_mod._subscription_lookup_key(SUBSCRIPTION)
        assert sub_key in fake_redis.values

        webhooks_mod._handle_customer_deleted({"id": CUSTOMER})
        assert sub_key not in fake_redis.values, (
            "subscription lookup key must be dropped alongside the "
            "customer key — both are now stale"
        )

    def test_preserves_tenant_subscription_hash_for_audit(
        self, fake_redis,
    ) -> None:
        """The tenant's subscription HASH (billing:tenant:{tenant_id})
        must survive for audit. Deleting it would erase billing history
        and break tenant-level reporting. We only flip status + delete
        the per-id LOOKUP keys."""
        _prebind_tenant(fake_redis)
        tenant_key = state_mod._tenant_subscription_key(TENANT)
        assert tenant_key in fake_redis.hashes

        webhooks_mod._handle_customer_deleted({"id": CUSTOMER})
        assert tenant_key in fake_redis.hashes, (
            "tenant subscription hash must survive customer deletion "
            "(audit trail requirement)"
        )
        # The audit record retains the original plan_id.
        assert fake_redis.hashes[tenant_key].get("plan_id") == "growth"

    def test_unknown_customer_still_clears_lookup_defensively(
        self, fake_redis, caplog,
    ) -> None:
        """If we never saw the customer (no _find_tenant_id hit), we
        still call delete on the lookup key defensively — there's no
        reason to leave a dangling pointer around if one happens to
        exist."""
        # Intentionally don't prebind — no tenant hash, no lookup key.
        # The handler should find no tenant, log the miss, and still
        # issue the defensive delete.
        with caplog.at_level(logging.WARNING, logger="stripe-billing"):
            webhooks_mod._handle_customer_deleted({"id": "cus_never_seen"})
        # Tenant-not-found warning fired.
        assert any(
            "stripe_customer_deleted_tenant_not_found" in r.getMessage()
            for r in caplog.records
        ), (
            "Unknown-customer branch must log tenant_not_found for "
            "operator visibility"
        )
        # The defensive delete was issued (even though the key wasn't
        # there — the idempotent DELETE is safe and the contract is
        # that we always clear the lookup on a deletion notice).
        assert state_mod._customer_lookup_key("cus_never_seen") in fake_redis.delete_calls, (
            "Defensive delete must be called on the customer lookup "
            "key even when no tenant binding exists"
        )

    def test_missing_id_does_not_crash(self, fake_redis, caplog) -> None:
        """A malformed event with no ``id`` must log and no-op, not
        raise (the dispatcher catches nothing and a raise would bubble
        out as a 500)."""
        with caplog.at_level(logging.WARNING, logger="stripe-billing"):
            webhooks_mod._handle_customer_deleted({})
        assert any(
            "stripe_customer_deleted_missing_id" in r.getMessage()
            for r in caplog.records
        )

    def test_dispatcher_routes_customer_deleted_to_handler(
        self, fake_redis,
    ) -> None:
        """End-to-end: dispatcher must route ``customer.deleted`` into
        ``_handle_customer_deleted``."""
        import asyncio
        _prebind_tenant(fake_redis)
        event = {
            "id": "evt_cust_del_1",
            "type": "customer.deleted",
            "data": {"object": {"id": CUSTOMER}},
        }
        asyncio.run(webhooks_mod._handle_stripe_event(event))
        mapping = state_mod._get_subscription_mapping(TENANT)
        assert mapping.get("status") == "customer_deleted", (
            "Dispatcher must route customer.deleted into the handler"
        )


# ---------------------------------------------------------------------------
# State helpers for the lookup cleanups
# ---------------------------------------------------------------------------


class TestStateLookupCleanup_Issue1189:
    def test_clear_customer_lookup_deletes_the_key(self, fake_redis) -> None:
        fake_redis.values[state_mod._customer_lookup_key("cus_clear")] = "tenant-x"
        state_mod._clear_customer_lookup("cus_clear")
        assert state_mod._customer_lookup_key("cus_clear") not in fake_redis.values

    def test_clear_customer_lookup_noop_on_empty_id(self, fake_redis) -> None:
        """Empty customer_id is a defensive guard — must not call Redis
        (otherwise a malformed Stripe payload could nuke an unrelated
        key named ``billing:customer:``)."""
        state_mod._clear_customer_lookup("")
        assert fake_redis.delete_calls == []

    def test_clear_subscription_lookup_deletes_the_key(self, fake_redis) -> None:
        fake_redis.values[state_mod._subscription_lookup_key("sub_clear")] = "tenant-x"
        state_mod._clear_subscription_lookup("sub_clear")
        assert state_mod._subscription_lookup_key("sub_clear") not in fake_redis.values

    def test_clear_subscription_lookup_noop_on_empty_id(self, fake_redis) -> None:
        state_mod._clear_subscription_lookup("")
        assert fake_redis.delete_calls == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
