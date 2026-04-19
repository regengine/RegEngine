"""Regression tests for #1076: Stripe webhook idempotency.

Context
-------
Stripe delivers webhooks **at least once**: if we don't ack within a
few seconds, or if we return 5xx, Stripe retries the same event (with
the same ``event.id``) for up to 3 days. Before the fix,
``_process_stripe_webhook`` dispatched every delivery to
``_handle_stripe_event`` without deduping, so a single real-world
event could fire its handlers multiple times:

1. ``checkout.session.completed`` — on retry, the server-side session
   cache may still be populated so tenant provisioning is skipped, but
   the ``_store_subscription_mapping`` write runs again with whatever
   metadata Stripe re-sent. If the first delivery's session cache
   entry has since expired (e.g. the first delivery was a 5xx storm
   from hours ago), we hit the "new self-serve signup" branch and
   call ``_create_tenant_via_admin`` a SECOND time — creating a
   duplicate tenant for the same real checkout.
2. ``invoice.paid`` — on retry, ``emit_funnel_event("payment_completed")``
   fires again, inflating conversion metrics.
3. ``customer.subscription.updated`` — on retry from an out-of-order
   delivery, the status field can flip back to a stale value.

The fix: claim ``event.id`` via Redis ``SET NX EX 86400`` after
signature verification; short-circuit with ``duplicate: True`` on
the second and subsequent deliveries.

These tests lock the fix in:

1. First delivery of a unique ``event.id`` runs the handler.
2. Retry with the same ``event.id`` does NOT run the handler again.
3. Signature-invalid payloads never consume a dedup slot (would let
   attackers burn event IDs).
4. A missing ``event.id`` (defensive — Stripe always sends one)
   falls through rather than crashing.
5. A Redis outage fails OPEN (don't block billing during an outage).
6. The dedup key format matches the contract
   (``billing:stripe:event:seen:{event_id}`` with 24h TTL).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

import app.authz as authz  # noqa: E402
from app.authz import IngestionPrincipal, get_ingestion_principal  # noqa: E402
from app import stripe_billing  # noqa: E402
from app.stripe_billing import state as state_mod  # noqa: E402


# ── Fake Redis with realistic SET/NX semantics ──────────────────────────────


class _FakeRedis:
    """In-memory stand-in that models just enough redis-py for the dedup
    gate. ``set(..., nx=True, ex=...)`` returns ``True`` on first write,
    ``None`` on subsequent writes (matching the real redis-py contract
    with ``decode_responses=True``)."""

    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.set_calls: list[tuple[str, str, dict[str, Any]]] = []

    def hset(self, key: str, mapping: dict[str, str]) -> None:
        self.hashes.setdefault(key, {})
        self.hashes[key].update(mapping)

    def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.hashes.get(key, {}))

    def set(
        self,
        key: str,
        value: str,
        nx: bool = False,
        ex: Optional[int] = None,
    ) -> Any:
        self.set_calls.append((key, value, {"nx": nx, "ex": ex}))
        if nx and key in self.values:
            # First-writer-wins semantics: redis-py returns None on
            # NX contention when decode_responses=True.
            return None
        self.values[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    def get(self, key: str) -> Optional[str]:
        return self.values.get(key)


def _build_client(principal: IngestionPrincipal) -> TestClient:
    app = FastAPI()
    app.include_router(stripe_billing.router)
    app.dependency_overrides[get_ingestion_principal] = lambda: principal
    return TestClient(app)


def _principal() -> IngestionPrincipal:
    return IngestionPrincipal(
        key_id="billing-webhook-test",
        tenant_id="tenant-webhook-idemp",
        scopes=["*"],
        auth_mode="test",
    )


# ── Unit: _mark_event_seen dedup primitive ──────────────────────────────────


def test_mark_event_seen_first_call_returns_true(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr(state_mod, "_redis_client", lambda: fake)

    assert state_mod._mark_event_seen("evt_new_1") is True
    # Key is written with the correct prefix.
    assert fake.values["billing:stripe:event:seen:evt_new_1"] == "1"
    # TTL is 24h.
    assert fake.ttls["billing:stripe:event:seen:evt_new_1"] == 24 * 60 * 60
    # NX flag used (first-writer-wins).
    assert fake.set_calls[0][2]["nx"] is True


def test_mark_event_seen_second_call_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr(state_mod, "_redis_client", lambda: fake)

    assert state_mod._mark_event_seen("evt_replay_1") is True
    # Second call for the same event_id returns False — duplicate.
    assert state_mod._mark_event_seen("evt_replay_1") is False


def test_mark_event_seen_different_ids_are_independent(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr(state_mod, "_redis_client", lambda: fake)

    assert state_mod._mark_event_seen("evt_a") is True
    assert state_mod._mark_event_seen("evt_b") is True
    assert state_mod._mark_event_seen("evt_a") is False
    assert state_mod._mark_event_seen("evt_b") is False


def test_mark_event_seen_empty_id_is_non_idempotent_but_does_not_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stripe always sends event.id; missing id is a defensive branch.
    We don't want to crash on malformed test fixtures, but we also
    don't want to consume a Redis slot for an empty key."""
    fake = _FakeRedis()
    monkeypatch.setattr(state_mod, "_redis_client", lambda: fake)

    assert state_mod._mark_event_seen("") is True
    # No Redis call happened — we short-circuited.
    assert fake.set_calls == []


def test_mark_event_seen_fails_open_on_redis_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Design choice (#1076): Redis outage must NOT block all Stripe
    webhooks, which would amplify Stripe's at-least-once retries and
    risk false past_due flips on payment.paid retries. Fail open and
    log loudly."""
    import redis as _redis_pkg

    class _ExplodingRedis:
        def set(self, *args, **kwargs):
            raise _redis_pkg.RedisError("connection refused")

    monkeypatch.setattr(state_mod, "_redis_client", lambda: _ExplodingRedis())

    # Fails open — returns True so the caller proceeds with the handler.
    assert state_mod._mark_event_seen("evt_during_outage") is True


def test_event_dedup_key_format() -> None:
    """The key format is part of the contract — if we ever change it,
    in-flight retries would re-fire. The prefix matches the other
    billing:* namespaces used in state.py."""
    assert state_mod._event_dedup_key("evt_42") == "billing:stripe:event:seen:evt_42"


# ── Integration: webhook endpoint short-circuits on replay ──────────────────


def test_webhook_dispatches_handler_on_first_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Baseline: a never-seen event.id still reaches the handler."""
    fake = _FakeRedis()
    monkeypatch.setattr(stripe_billing, "_redis_client", lambda: fake)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_123")
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kwargs: (True, 99))

    def _fake_construct_event(payload, sig_header, secret):
        return {"id": "evt_first_delivery", "type": "invoice.paid", "data": {"object": {}}}

    handler = AsyncMock()
    monkeypatch.setattr(stripe_billing.stripe.Webhook, "construct_event", _fake_construct_event)
    monkeypatch.setattr(stripe_billing, "_handle_stripe_event", handler)

    with _build_client(_principal()) as client:
        response = client.post(
            "/api/v1/billing/webhooks",
            content=b'{"id":"evt_first_delivery"}',
            headers={"Stripe-Signature": "t=123,v1=fake"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["received"] is True
    assert body.get("duplicate") is not True
    handler.assert_awaited_once()
    assert "billing:stripe:event:seen:evt_first_delivery" in fake.values


def test_webhook_short_circuits_on_duplicate_event_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE regression test for #1076: the same event.id delivered
    twice triggers the handler exactly once."""
    fake = _FakeRedis()
    monkeypatch.setattr(stripe_billing, "_redis_client", lambda: fake)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_123")
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kwargs: (True, 99))

    def _fake_construct_event(payload, sig_header, secret):
        return {"id": "evt_retry_1", "type": "invoice.paid", "data": {"object": {}}}

    handler = AsyncMock()
    monkeypatch.setattr(stripe_billing.stripe.Webhook, "construct_event", _fake_construct_event)
    monkeypatch.setattr(stripe_billing, "_handle_stripe_event", handler)

    with _build_client(_principal()) as client:
        # First delivery: handler runs.
        first = client.post(
            "/api/v1/billing/webhooks",
            content=b'{"id":"evt_retry_1"}',
            headers={"Stripe-Signature": "t=123,v1=fake"},
        )
        # Second delivery (Stripe retry): handler must NOT run again.
        second = client.post(
            "/api/v1/billing/webhooks",
            content=b'{"id":"evt_retry_1"}',
            headers={"Stripe-Signature": "t=456,v1=fake"},
        )

    assert first.status_code == 200
    assert first.json().get("duplicate") is not True

    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["event_type"] == "invoice.paid"

    # Handler awaited EXACTLY once across both deliveries.
    handler.assert_awaited_once()


def test_webhook_dedup_is_per_event_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Distinct event.ids should each dispatch independently, even
    when the event type is identical."""
    fake = _FakeRedis()
    monkeypatch.setattr(stripe_billing, "_redis_client", lambda: fake)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_123")
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kwargs: (True, 99))

    counter = {"n": 0}

    def _fake_construct_event(payload, sig_header, secret):
        counter["n"] += 1
        return {
            "id": f"evt_distinct_{counter['n']}",
            "type": "invoice.paid",
            "data": {"object": {}},
        }

    handler = AsyncMock()
    monkeypatch.setattr(stripe_billing.stripe.Webhook, "construct_event", _fake_construct_event)
    monkeypatch.setattr(stripe_billing, "_handle_stripe_event", handler)

    with _build_client(_principal()) as client:
        for _ in range(3):
            resp = client.post(
                "/api/v1/billing/webhooks",
                content=b'{}',
                headers={"Stripe-Signature": "t=1,v1=fake"},
            )
            assert resp.status_code == 200
            assert resp.json().get("duplicate") is not True

    assert handler.await_count == 3


def test_webhook_dedup_runs_after_signature_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#1076: we must NOT consume dedup slots for invalid signatures.
    Otherwise an attacker who can guess Stripe event IDs could burn
    them by sending forged requests, causing the real webhook to be
    silently ignored."""
    import stripe as _stripe_pkg

    fake = _FakeRedis()
    monkeypatch.setattr(stripe_billing, "_redis_client", lambda: fake)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_123")
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kwargs: (True, 99))

    def _fake_construct_event(payload, sig_header, secret):
        raise _stripe_pkg.error.SignatureVerificationError(
            "forged signature", sig_header=sig_header
        )

    handler = AsyncMock()
    monkeypatch.setattr(stripe_billing.stripe.Webhook, "construct_event", _fake_construct_event)
    monkeypatch.setattr(stripe_billing, "_handle_stripe_event", handler)

    with _build_client(_principal()) as client:
        response = client.post(
            "/api/v1/billing/webhooks",
            content=b'{"id":"evt_attacker_claim_1"}',
            headers={"Stripe-Signature": "t=999,v1=forged"},
        )

    # 401 rejection: signature verification failed BEFORE the dedup gate.
    assert response.status_code == 401
    # No dedup slot consumed — the attacker cannot burn Stripe event IDs.
    assert not any(k.startswith("billing:stripe:event:seen:") for k in fake.values)
    # Handler must NOT have run.
    handler.assert_not_awaited()


def test_webhook_fails_open_when_redis_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """During a Redis outage, webhooks must still process so a real
    payment.paid event is not mis-flipped to past_due by Stripe's
    retry logic. The handler runs at least once (fail-open) and the
    error is logged."""
    import redis as _redis_pkg

    class _ExplodingRedis:
        def set(self, *args, **kwargs):
            raise _redis_pkg.RedisError("connection refused")

        # Other helpers may be called downstream; make them no-ops.
        def hset(self, *a, **k): return None
        def hgetall(self, *a, **k): return {}
        def get(self, *a, **k): return None

    monkeypatch.setattr(stripe_billing, "_redis_client", lambda: _ExplodingRedis())
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_123")
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kwargs: (True, 99))

    def _fake_construct_event(payload, sig_header, secret):
        return {"id": "evt_outage_1", "type": "invoice.paid", "data": {"object": {}}}

    handler = AsyncMock()
    monkeypatch.setattr(stripe_billing.stripe.Webhook, "construct_event", _fake_construct_event)
    monkeypatch.setattr(stripe_billing, "_handle_stripe_event", handler)

    with _build_client(_principal()) as client:
        response = client.post(
            "/api/v1/billing/webhooks",
            content=b'{"id":"evt_outage_1"}',
            headers={"Stripe-Signature": "t=123,v1=fake"},
        )

    assert response.status_code == 200
    # Fail-open: handler ran despite Redis being down.
    handler.assert_awaited_once()


def test_webhook_missing_event_id_does_not_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defensive: if a malformed event sneaks past Stripe's signing
    (e.g. test harness sends a crafted payload), we shouldn't crash
    with a 500. We log the anomaly and dispatch — the handlers
    themselves are defensive about missing fields."""
    fake = _FakeRedis()
    monkeypatch.setattr(stripe_billing, "_redis_client", lambda: fake)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_123")
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kwargs: (True, 99))

    def _fake_construct_event(payload, sig_header, secret):
        return {"type": "invoice.paid", "data": {"object": {}}}  # no id

    handler = AsyncMock()
    monkeypatch.setattr(stripe_billing.stripe.Webhook, "construct_event", _fake_construct_event)
    monkeypatch.setattr(stripe_billing, "_handle_stripe_event", handler)

    with _build_client(_principal()) as client:
        response = client.post(
            "/api/v1/billing/webhooks",
            content=b'{}',
            headers={"Stripe-Signature": "t=123,v1=fake"},
        )

    assert response.status_code == 200
    handler.assert_awaited_once()


# ── Process-level: _process_stripe_webhook directly ─────────────────────────


@pytest.mark.asyncio
async def test_process_stripe_webhook_short_circuits_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Call ``_process_stripe_webhook`` twice with the same event.id
    at the function level (not the FastAPI route) — the dispatcher
    runs exactly once."""
    from app.stripe_billing import webhooks as webhooks_mod

    fake = _FakeRedis()
    monkeypatch.setattr(state_mod, "_redis_client", lambda: fake)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_123")

    def _fake_construct_event(payload, sig_header, secret):
        return {"id": "evt_proc_1", "type": "invoice.paid", "data": {"object": {}}}

    monkeypatch.setattr(stripe_billing.stripe.Webhook, "construct_event", _fake_construct_event)

    handler = AsyncMock()
    monkeypatch.setattr(webhooks_mod, "_handle_stripe_event", handler)

    request = MagicMock()
    request.body = AsyncMock(return_value=b'{"id":"evt_proc_1"}')

    first = await webhooks_mod._process_stripe_webhook(request, "t=1,v1=sig")
    second = await webhooks_mod._process_stripe_webhook(request, "t=2,v1=sig")

    assert first["received"] is True
    assert first.get("duplicate") is not True

    assert second["received"] is True
    assert second["duplicate"] is True

    handler.assert_awaited_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
