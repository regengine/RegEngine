"""Regression tests for webhook HMAC signature verification (#1243) and
event-timestamp replay window enforcement (#1245).

These exercise the helpers directly rather than through the full ingest
pipeline so they stay green even when the DB-backed happy path isn't
available in the local test environment.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import app.webhook_router_v2 as wr  # noqa: E402


# ---------------------------------------------------------------------------
# Fake Request stub — the real starlette.Request needs an ASGI scope and we
# only need ``await request.body()`` to return bytes.
# ---------------------------------------------------------------------------


class _FakeRequest:
    def __init__(self, body: bytes):
        self._body = body

    async def body(self) -> bytes:
        return self._body


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# #1243 — HMAC verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_signature_noop_when_secret_unset(monkeypatch):
    """Unset secret = migration ramp — verification is skipped."""
    monkeypatch.delenv("WEBHOOK_HMAC_SECRET", raising=False)
    req = _FakeRequest(b'{"events": []}')
    # No header, no secret → must return without raising.
    await wr._verify_webhook_signature(req, x_webhook_signature=None)


@pytest.mark.asyncio
async def test_signature_required_when_secret_set(monkeypatch):
    """Secret set + missing signature header → 401."""
    monkeypatch.setenv("WEBHOOK_HMAC_SECRET", "shh")
    req = _FakeRequest(b'{"events": []}')

    with pytest.raises(HTTPException) as exc:
        await wr._verify_webhook_signature(req, x_webhook_signature=None)
    assert exc.value.status_code == 401
    assert exc.value.detail["error"] == "missing_webhook_signature"


@pytest.mark.asyncio
async def test_signature_valid_sha256_prefixed(monkeypatch):
    """``sha256=<hex>`` format with matching HMAC succeeds."""
    secret = "shh"
    monkeypatch.setenv("WEBHOOK_HMAC_SECRET", secret)
    body = b'{"events":[]}'
    sig = _sign(secret, body)
    req = _FakeRequest(body)

    # Must not raise.
    await wr._verify_webhook_signature(req, x_webhook_signature=f"sha256={sig}")


@pytest.mark.asyncio
async def test_signature_valid_bare_hex(monkeypatch):
    """Bare hex digest (Stripe-style fallback) is also accepted."""
    secret = "shh"
    monkeypatch.setenv("WEBHOOK_HMAC_SECRET", secret)
    body = b'{"events":[]}'
    sig = _sign(secret, body)
    req = _FakeRequest(body)

    await wr._verify_webhook_signature(req, x_webhook_signature=sig)


@pytest.mark.asyncio
async def test_signature_mismatch_rejected(monkeypatch):
    """Mismatched signature → 401, does not leak the expected value."""
    monkeypatch.setenv("WEBHOOK_HMAC_SECRET", "shh")
    req = _FakeRequest(b'{"events":[]}')

    with pytest.raises(HTTPException) as exc:
        await wr._verify_webhook_signature(
            req, x_webhook_signature="sha256=" + "0" * 64,
        )
    assert exc.value.status_code == 401
    assert exc.value.detail["error"] == "invalid_webhook_signature"


@pytest.mark.asyncio
async def test_signature_unsupported_scheme_rejected(monkeypatch):
    """Non-sha256 scheme → 401 with scheme echoed back for operator debugging."""
    monkeypatch.setenv("WEBHOOK_HMAC_SECRET", "shh")
    req = _FakeRequest(b'{"events":[]}')

    with pytest.raises(HTTPException) as exc:
        await wr._verify_webhook_signature(
            req, x_webhook_signature="md5=deadbeef",
        )
    assert exc.value.status_code == 401
    assert exc.value.detail["error"] == "unsupported_signature_scheme"
    assert exc.value.detail["scheme"] == "md5"


@pytest.mark.asyncio
async def test_signature_body_tampering_rejected(monkeypatch):
    """A signature valid for body A must not validate body B (tamper check)."""
    secret = "shh"
    monkeypatch.setenv("WEBHOOK_HMAC_SECRET", secret)
    original_body = json.dumps({"events": [{"n": 1}]}).encode()
    tampered_body = json.dumps({"events": [{"n": 999}]}).encode()
    sig_for_original = _sign(secret, original_body)
    req = _FakeRequest(tampered_body)

    with pytest.raises(HTTPException) as exc:
        await wr._verify_webhook_signature(
            req, x_webhook_signature=f"sha256={sig_for_original}",
        )
    assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# #1245 — event-timestamp replay window
# ---------------------------------------------------------------------------


def test_replay_window_accepts_fresh_event(monkeypatch):
    monkeypatch.delenv("WEBHOOK_MAX_EVENT_AGE_DAYS", raising=False)
    monkeypatch.delenv("WEBHOOK_MAX_EVENT_FUTURE_HOURS", raising=False)
    now = datetime.now(timezone.utc).isoformat()
    assert wr._validate_event_timestamp_window(now) is None


def test_replay_window_rejects_stale_event(monkeypatch):
    """Events older than WEBHOOK_MAX_EVENT_AGE_DAYS are rejected."""
    monkeypatch.delenv("WEBHOOK_MAX_EVENT_AGE_DAYS", raising=False)
    ts_old = (datetime.now(timezone.utc) - timedelta(days=180)).isoformat()
    err = wr._validate_event_timestamp_window(ts_old)
    assert err is not None
    assert "older than" in err
    assert "WEBHOOK_MAX_EVENT_AGE_DAYS" in err


def test_replay_window_rejects_future_event(monkeypatch):
    monkeypatch.delenv("WEBHOOK_MAX_EVENT_FUTURE_HOURS", raising=False)
    ts_future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    err = wr._validate_event_timestamp_window(ts_future)
    assert err is not None
    assert "in the future" in err


def test_replay_window_rejects_unparseable(monkeypatch):
    err = wr._validate_event_timestamp_window("not-a-timestamp")
    assert err is not None
    assert "not parseable" in err


def test_replay_window_env_overrides(monkeypatch):
    """Shrinking the window via env catches events the default would accept."""
    monkeypatch.setenv("WEBHOOK_MAX_EVENT_AGE_DAYS", "1")
    ts = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    err = wr._validate_event_timestamp_window(ts)
    assert err is not None
    assert "WEBHOOK_MAX_EVENT_AGE_DAYS=1" in err
