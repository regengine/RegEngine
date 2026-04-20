"""Tests for Stripe webhook rate limiting and HMAC enforcement -- #1198.

Covers:
- Valid HMAC signature passes through (200 OK)
- Missing signature returns 400
- Invalid signature returns 400
- Rate limit trips 429 with Retry-After header after threshold
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app.stripe_billing import rate_limit as rate_limit_mod  # noqa: E402
from app.stripe_billing import webhooks as webhooks_mod  # noqa: E402


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_stripe_sig(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    """Construct a valid Stripe-Signature header value."""
    if timestamp is None:
        timestamp = int(time.time())
    signed_payload = f"{timestamp}.{payload.decode()}".encode()
    signature = hmac.new(
        secret.encode(),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()
    return f"t={timestamp},v1={signature}"


def _build_event(event_type: str = "invoice.paid") -> dict[str, Any]:
    return {
        "id": "evt_test_001",
        "object": "event",
        "type": event_type,
        "data": {"object": {}},
        "created": int(time.time()),
    }


WEBHOOK_SECRET = "whsec_test_secret_1234"


class _FakeRequest:
    """Minimal FastAPI Request stand-in."""

    def __init__(
        self,
        body: bytes,
        client_ip: str = "1.2.3.4",
        forwarded_for: str | None = None,
    ) -> None:
        self._body = body
        self.client = MagicMock()
        self.client.host = client_ip
        self.headers: dict[str, str] = {}
        if forwarded_for:
            self.headers["X-Forwarded-For"] = forwarded_for

    async def body(self) -> bytes:
        return self._body


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_rate_limit() -> None:
    """Reset in-memory buckets before every test."""
    with rate_limit_mod._lock:
        rate_limit_mod._buckets.clear()


@pytest.fixture()
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WEBHOOK_SECRET)


@pytest.fixture()
def _no_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub out the event handler and dedup so tests don't need Redis."""
    monkeypatch.setattr(webhooks_mod, "_handle_stripe_event", _noop_handler)
    monkeypatch.setattr(
        webhooks_mod._state_mod,
        "_mark_event_seen",
        lambda _: True,
    )
    monkeypatch.setattr(webhooks_mod._helpers_mod, "_configure_stripe", lambda: None)


async def _noop_handler(_event: Any) -> None:  # noqa: RUF029
    return


# ── Unit tests: rate_limit module ─────────────────────────────────────────


def test_rate_limit_allows_under_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STRIPE_WEBHOOK_RATE_LIMIT", "5")
    monkeypatch.setenv("STRIPE_WEBHOOK_RATE_WINDOW", "60")
    for _ in range(5):
        limited, _ = rate_limit_mod.is_rate_limited("10.0.0.1")
        assert not limited


def test_rate_limit_trips_at_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STRIPE_WEBHOOK_RATE_LIMIT", "3")
    monkeypatch.setenv("STRIPE_WEBHOOK_RATE_WINDOW", "60")
    for _ in range(3):
        rate_limit_mod.is_rate_limited("10.0.0.2")
    limited, retry_after = rate_limit_mod.is_rate_limited("10.0.0.2")
    assert limited
    assert retry_after >= 1


def test_rate_limit_per_ip_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STRIPE_WEBHOOK_RATE_LIMIT", "1")
    monkeypatch.setenv("STRIPE_WEBHOOK_RATE_WINDOW", "60")
    # Exhaust IP A
    rate_limit_mod.is_rate_limited("192.168.1.1")
    limited_a, _ = rate_limit_mod.is_rate_limited("192.168.1.1")
    assert limited_a
    # IP B is unaffected
    limited_b, _ = rate_limit_mod.is_rate_limited("192.168.1.2")
    assert not limited_b


# ── Integration tests: _process_stripe_webhook ─────────────────────────────


@pytest.mark.asyncio
async def test_valid_signature_accepted(_env: None, _no_side_effects: None) -> None:
    """A correctly-signed webhook returns {"received": True}."""
    event = _build_event()
    payload = json.dumps(event).encode()
    sig = _make_stripe_sig(payload, WEBHOOK_SECRET)
    req = _FakeRequest(body=payload, client_ip="1.2.3.4")

    with patch("stripe.Webhook.construct_event", return_value=event):
        result = await webhooks_mod._process_stripe_webhook(req, sig)

    assert result.get("received") is True


@pytest.mark.asyncio
async def test_missing_signature_returns_400(_env: None, _no_side_effects: None) -> None:
    """No Stripe-Signature header → 400."""
    from fastapi import HTTPException

    payload = json.dumps(_build_event()).encode()
    req = _FakeRequest(body=payload)

    with pytest.raises(HTTPException) as exc_info:
        await webhooks_mod._process_stripe_webhook(req, None)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_invalid_signature_returns_400(_env: None, _no_side_effects: None) -> None:
    """Bad HMAC signature → 400 (not 200, not 401)."""
    import stripe as _stripe
    from fastapi import HTTPException

    payload = json.dumps(_build_event()).encode()
    req = _FakeRequest(body=payload)

    with patch(
        "stripe.Webhook.construct_event",
        side_effect=_stripe.error.SignatureVerificationError("bad sig", "sig_header"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await webhooks_mod._process_stripe_webhook(req, "t=1,v1=badhex")

    assert exc_info.value.status_code == 400
    # Invalid-sig requests must NOT consume a rate-limit slot.
    limited, _ = rate_limit_mod.is_rate_limited("1.2.3.4")
    assert not limited, "Forged-sig requests must not consume rate-limit budget"


@pytest.mark.asyncio
async def test_rate_limit_returns_429_after_threshold(
    _env: None,
    _no_side_effects: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After STRIPE_WEBHOOK_RATE_LIMIT valid requests, next gets 429 + Retry-After."""
    monkeypatch.setenv("STRIPE_WEBHOOK_RATE_LIMIT", "2")
    monkeypatch.setenv("STRIPE_WEBHOOK_RATE_WINDOW", "60")

    event = _build_event()
    payload = json.dumps(event).encode()
    ip = "5.6.7.8"

    with patch("stripe.Webhook.construct_event", return_value=event):
        # First two pass
        for _ in range(2):
            req = _FakeRequest(body=payload, client_ip=ip)
            result = await webhooks_mod._process_stripe_webhook(req, "sig")
            assert result.get("received") is True

        # Third should be rate-limited
        req = _FakeRequest(body=payload, client_ip=ip)
        response = await webhooks_mod._process_stripe_webhook(req, "sig")

    # Returns a JSONResponse (not a plain dict) with status_code 429
    assert response.status_code == 429  # type: ignore[union-attr]
    assert "Retry-After" in response.headers  # type: ignore[union-attr]
