"""Regression tests for #2818 — Stripe webhook dedup claim never released.

Context
-------
``_process_stripe_webhook`` claims ``event.id`` via a Redis ``SET NX EX``
with a 24h TTL BEFORE dispatching to ``_handle_stripe_event`` — it has to,
the gate must close before any side effect (#1076). But the claim was never
released when the handler raised, so:

  * delivery 1 claims ``evt_x``, handler raises, request 500s;
  * Stripe retries ``evt_x``; ``_mark_event_seen`` returns False because the
    key is still there; we answer ``200 {"duplicate": true}``;
  * ...for 24 hours. The event is permanently dropped.

Real consequences: a failed ``checkout.session.completed`` leaves a paying
tenant with NO subscription mapping; a failed ``invoice.paid`` leaves them
stuck ``past_due``.

The fix releases the claim on the failure path only, so genuine duplicates
(the #1076 contract) are still suppressed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional
from unittest.mock import AsyncMock

import pytest
import redis as _redis_pkg
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

import services.ingestion.app.authz as authz  # noqa: E402
from services.ingestion.app import stripe_billing  # noqa: E402
from services.ingestion.app.authz import IngestionPrincipal, get_ingestion_principal  # noqa: E402
from services.ingestion.app.stripe_billing import state as state_mod  # noqa: E402


class _FakeRedis:
    """Same SET/NX semantics as the #1076 fixture, plus ``delete``."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.deleted: list[str] = []

    def set(self, key: str, value: str, nx: bool = False, ex: Optional[int] = None) -> Any:
        if nx and key in self.values:
            return None  # redis-py returns None on NX contention
        self.values[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    def get(self, key: str) -> Optional[str]:
        return self.values.get(key)

    def delete(self, key: str) -> int:
        self.deleted.append(key)
        return 1 if self.values.pop(key, None) is not None else 0


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(stripe_billing.router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="billing-webhook-test",
        tenant_id="tenant-webhook-2818",
        scopes=["*"],
        auth_mode="test",
    )
    return TestClient(app)


def _wire(monkeypatch: pytest.MonkeyPatch, fake: _FakeRedis, event: dict, handler) -> None:
    monkeypatch.setattr(stripe_billing, "_redis_client", lambda: fake)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_123")
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kwargs: (True, 99))
    monkeypatch.setattr(
        stripe_billing.stripe.Webhook,
        "construct_event",
        lambda payload, sig_header, secret: event,
    )
    monkeypatch.setattr(stripe_billing, "_handle_stripe_event", handler)


def _post(client: TestClient, event_id: str):
    return client.post(
        "/api/v1/billing/webhooks",
        content=f'{{"id":"{event_id}"}}'.encode(),
        headers={"Stripe-Signature": "t=123,v1=fake"},
    )


# ---------------------------------------------------------------------------
# _release_event_claim unit behaviour
# ---------------------------------------------------------------------------


def test_release_event_claim_deletes_the_dedup_key(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr(state_mod, "_redis_client", lambda: fake)

    assert state_mod._mark_event_seen("evt_release_1") is True
    assert "billing:stripe:event:seen:evt_release_1" in fake.values

    state_mod._release_event_claim("evt_release_1")

    assert "billing:stripe:event:seen:evt_release_1" not in fake.values
    # The event can be claimed again — i.e. Stripe's retry gets through.
    assert state_mod._mark_event_seen("evt_release_1") is True


def test_release_event_claim_ignores_empty_id(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr(state_mod, "_redis_client", lambda: fake)
    state_mod._release_event_claim("")
    assert fake.deleted == []


def test_release_event_claim_swallows_redis_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Must not convert a handler exception into a different one — the
    original traceback has to survive."""

    class _ExplodingRedis:
        def delete(self, *_a, **_kw):
            raise _redis_pkg.RedisError("connection refused")

    monkeypatch.setattr(state_mod, "_redis_client", lambda: _ExplodingRedis())
    state_mod._release_event_claim("evt_during_outage")  # no raise


# ---------------------------------------------------------------------------
# Endpoint behaviour: failed handler must not permanently drop the event
# ---------------------------------------------------------------------------


def test_failed_handler_releases_claim_so_stripe_retry_is_processed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE #2818 regression test.

    Delivery 1 fails; Stripe retries; the retry must actually RUN the
    handler instead of being answered ``200 {"duplicate": true}``.
    """
    fake = _FakeRedis()
    event = {"id": "evt_2818_retry", "type": "checkout.session.completed", "data": {"object": {}}}

    calls = {"n": 0}

    async def _flaky_handler(_event):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("admin service unreachable during tenant provisioning")

    _wire(monkeypatch, fake, event, _flaky_handler)

    with _build_client() as client:
        with pytest.raises(RuntimeError):
            _post(client, "evt_2818_retry")

        # The claim was released, so the retry is a FIRST delivery again.
        assert "billing:stripe:event:seen:evt_2818_retry" not in fake.values
        assert "billing:stripe:event:seen:evt_2818_retry" in fake.deleted

        retry = _post(client, "evt_2818_retry")

    assert retry.status_code == 200
    assert retry.json().get("duplicate") is not True
    assert calls["n"] == 2, "Stripe's retry must reach the handler, not the duplicate branch"


def test_pre_fix_behaviour_is_gone_no_permanent_duplicate_suppression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Before the fix, EVERY retry after a failure answered
    ``duplicate: true`` and the handler ran exactly once, forever."""
    fake = _FakeRedis()
    event = {"id": "evt_2818_always_fails", "type": "invoice.paid", "data": {"object": {}}}

    handler = AsyncMock(side_effect=RuntimeError("boom"))
    _wire(monkeypatch, fake, event, handler)

    with _build_client() as client:
        for _ in range(3):
            with pytest.raises(RuntimeError):
                _post(client, "evt_2818_always_fails")

    # Three deliveries, three real handler invocations — no silent
    # 200 {"duplicate": true} swallowing retries 2 and 3.
    assert handler.await_count == 3
    assert "billing:stripe:event:seen:evt_2818_always_fails" not in fake.values


def test_successful_handler_keeps_the_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    """The #1076 contract must survive: a genuine duplicate of an event
    that DID process is still suppressed, and nothing is deleted."""
    fake = _FakeRedis()
    event = {"id": "evt_2818_ok", "type": "invoice.paid", "data": {"object": {}}}
    handler = AsyncMock()
    _wire(monkeypatch, fake, event, handler)

    with _build_client() as client:
        first = _post(client, "evt_2818_ok")
        second = _post(client, "evt_2818_ok")

    assert first.status_code == 200
    assert first.json().get("duplicate") is not True
    assert second.status_code == 200
    assert second.json()["duplicate"] is True

    handler.assert_awaited_once()
    assert fake.deleted == []
    assert "billing:stripe:event:seen:evt_2818_ok" in fake.values


def test_http_exception_from_handler_also_releases_the_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A handler that rejects the event with a 4xx did not complete its
    work either — the claim must not outlive it."""
    from fastapi import HTTPException

    fake = _FakeRedis()
    event = {"id": "evt_2818_http", "type": "checkout.session.completed", "data": {"object": {}}}

    async def _rejecting_handler(_event):
        raise HTTPException(status_code=400, detail="tenant mismatch")

    _wire(monkeypatch, fake, event, _rejecting_handler)

    with _build_client() as client:
        response = _post(client, "evt_2818_http")

    assert response.status_code == 400
    assert "billing:stripe:event:seen:evt_2818_http" not in fake.values
