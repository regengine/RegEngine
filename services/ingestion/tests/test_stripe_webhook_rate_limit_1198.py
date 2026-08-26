"""Tests for Stripe webhook rate limiting -- #1198."""

from __future__ import annotations

import base64
import hashlib
import hmac
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import app.stripe_billing.rate_limiting as rl
from fastapi import HTTPException


def _make_request(ip: str = "1.2.3.4") -> MagicMock:
    req = MagicMock()
    req.headers = {}
    req.client = MagicMock()
    req.client.host = ip
    return req


# ---------------------------------------------------------------------------
# Unit tests for the rate limiting module
# ---------------------------------------------------------------------------


def test_rate_limit_allows_requests_under_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """Requests below the limit should pass without raising."""
    monkeypatch.setattr(rl, "_redis_failed", True)  # force in-memory path
    monkeypatch.setattr(rl, "_redis_retry_at", time.time() + 300)  # #2699: keep cooldown armed
    monkeypatch.setattr(rl, "_rate_buckets", {})  # fresh state
    req = _make_request("10.0.0.1")

    # Send 5 requests — well under the 100 RPM limit
    for _ in range(5):
        rl._check_stripe_webhook_rate_limit(req)  # must not raise


def test_rate_limit_blocks_after_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """After exceeding the per-IP limit a 429 must be raised."""
    monkeypatch.setattr(rl, "_redis_failed", True)
    monkeypatch.setattr(rl, "_redis_retry_at", time.time() + 300)  # #2699: keep cooldown armed
    monkeypatch.setattr(rl, "_rate_buckets", {})
    monkeypatch.setattr(rl, "_WEBHOOK_RATE_LIMIT", 5)  # lower limit for speed

    req = _make_request("10.0.0.2")

    # Exhaust the limit
    for _ in range(5):
        rl._check_stripe_webhook_rate_limit(req)

    # Next request must be rejected
    with pytest.raises(HTTPException) as exc_info:
        rl._check_stripe_webhook_rate_limit(req)

    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers


def test_rate_limit_is_per_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Different IPs must not share the same bucket."""
    monkeypatch.setattr(rl, "_redis_failed", True)
    monkeypatch.setattr(rl, "_redis_retry_at", time.time() + 300)  # #2699: keep cooldown armed
    monkeypatch.setattr(rl, "_rate_buckets", {})
    monkeypatch.setattr(rl, "_WEBHOOK_RATE_LIMIT", 3)

    req_a = _make_request("192.168.0.1")
    req_b = _make_request("192.168.0.2")

    for _ in range(3):
        rl._check_stripe_webhook_rate_limit(req_a)

    # req_a is now blocked
    with pytest.raises(HTTPException):
        rl._check_stripe_webhook_rate_limit(req_a)

    # req_b should still be allowed
    rl._check_stripe_webhook_rate_limit(req_b)  # must not raise


def test_rate_limit_ignores_unsigned_xff_even_when_legacy_peer_cidr_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A public shared edge cannot make caller-supplied XFF authoritative."""
    monkeypatch.setattr(rl, "_redis_failed", True)
    monkeypatch.setattr(rl, "_redis_retry_at", time.time() + 300)  # #2699: keep cooldown armed
    monkeypatch.setattr(rl, "_rate_buckets", {})
    monkeypatch.setattr(rl, "_WEBHOOK_RATE_LIMIT", 2)
    monkeypatch.setenv("STRIPE_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")

    req = MagicMock()
    req.headers = {"X-Forwarded-For": "203.0.113.10, 10.0.0.1"}
    req.client = MagicMock()
    req.client.host = "10.0.0.1"  # trusted-CIDR peer

    for _ in range(2):
        rl._check_stripe_webhook_rate_limit(req)

    with pytest.raises(HTTPException) as exc_info:
        rl._check_stripe_webhook_rate_limit(req)

    assert exc_info.value.status_code == 429
    assert "10.0.0.1" in rl._rate_buckets
    assert "203.0.113.10" not in rl._rate_buckets


def test_rate_limit_uses_fresh_signed_bff_client_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the HMAC-bound Vercel BFF attribution can select a client bucket."""
    hmac_key = "test-proxy-ip-hmac-key-material-32-bytes"
    timestamp = str(int(time.time()))
    client_ip = "203.0.113.10"
    request_id = "stripe-rate-limit-request"
    payload = f"v1\n{client_ip}\n{timestamp}\nPOST\n{request_id}".encode()
    digest = hmac.new(hmac_key.encode(), payload, hashlib.sha256).digest()
    signature = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    monkeypatch.setenv("REGENGINE_PROXY_IP_HMAC_KEY", hmac_key)
    monkeypatch.setattr(rl, "_redis_failed", True)
    monkeypatch.setattr(rl, "_redis_retry_at", time.time() + 300)
    monkeypatch.setattr(rl, "_rate_buckets", {})
    monkeypatch.setattr(rl, "_WEBHOOK_RATE_LIMIT", 2)

    req = MagicMock()
    req.method = "POST"
    req.headers = {
        "x-request-id": request_id,
        "x-regengine-proxy-client-ip": client_ip,
        "x-regengine-proxy-timestamp": timestamp,
        "x-regengine-proxy-signature": f"v1={signature}",
    }
    req.client = MagicMock()
    req.client.host = "10.0.0.1"

    for _ in range(2):
        rl._check_stripe_webhook_rate_limit(req)
    with pytest.raises(HTTPException) as exc_info:
        rl._check_stripe_webhook_rate_limit(req)

    assert exc_info.value.status_code == 429
    assert client_ip in rl._rate_buckets


def test_redis_path_uses_atomic_eval(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Redis branch must use a single atomic EVAL (no separate
    zcard-then-zadd race) and return its result verbatim."""
    captured: dict = {}

    class _FakeRedis:
        def eval(self, script, numkeys, key, *args):  # noqa: A003 - mirror redis-py
            captured["script"] = script
            captured["numkeys"] = numkeys
            captured["key"] = key
            captured["args"] = args
            return 0  # admitted

    monkeypatch.setattr(rl, "_get_redis", lambda: _FakeRedis())

    assert rl._check_redis("9.9.9.9", now=1000.0) == 0
    assert captured["numkeys"] == 1
    assert captured["key"] == "stripe_webhook:rate:9.9.9.9"
    # Atomicity markers: trim/count/admit/add all live in the Lua body.
    assert "ZADD" in captured["script"] and "ZCARD" in captured["script"]


def test_redis_eval_block_returns_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-zero EVAL result (seconds remaining) becomes a 429."""
    monkeypatch.setattr(rl, "_get_redis", lambda: type("R", (), {"eval": lambda self, *a: 7})())

    req = _make_request("8.8.8.8")
    with pytest.raises(HTTPException) as exc_info:
        rl._check_stripe_webhook_rate_limit(req)
    assert exc_info.value.status_code == 429
    assert exc_info.value.headers["Retry-After"] == "7"


def test_redis_eval_error_falls_back_to_in_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    """If EVAL raises, the limiter must fall back to the in-memory window."""

    class _BoomRedis:
        def eval(self, *a, **k):
            raise RuntimeError("redis exploded")

    monkeypatch.setattr(rl, "_get_redis", lambda: _BoomRedis())
    monkeypatch.setattr(rl, "_rate_buckets", {})

    assert rl._check_redis("7.7.7.7", now=2000.0) == 0
    assert "7.7.7.7" in rl._rate_buckets


def test_xff_ignored_when_peer_not_trusted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Untrusted peer cannot mint fresh buckets by rotating X-Forwarded-For.

    Regression for the XFF-bypass cluster found in the 2026-05-12 Suite 3
    audit: previously the limiter trusted XFF unconditionally, so an
    attacker could rotate the header per request and never hit the
    threshold.
    """
    monkeypatch.setattr(rl, "_redis_failed", True)
    monkeypatch.setattr(rl, "_redis_retry_at", time.time() + 300)  # #2699: keep cooldown armed
    monkeypatch.setattr(rl, "_rate_buckets", {})
    monkeypatch.setattr(rl, "_WEBHOOK_RATE_LIMIT", 3)
    monkeypatch.delenv("STRIPE_TRUSTED_PROXY_CIDRS", raising=False)
    monkeypatch.delenv("TRUSTED_PROXY_CIDRS", raising=False)

    attacker_socket_ip = "198.51.100.7"

    # Burn the threshold using rotating XFF values — limiter must group
    # all requests under the socket IP, NOT the spoofed XFF.
    for spoof in ("203.0.113.1", "203.0.113.2", "203.0.113.3"):
        req = MagicMock()
        req.headers = {"X-Forwarded-For": spoof}
        req.client = MagicMock()
        req.client.host = attacker_socket_ip
        rl._check_stripe_webhook_rate_limit(req)

    # Next attempt — still on the same socket IP — must be rejected.
    req = MagicMock()
    req.headers = {"X-Forwarded-For": "203.0.113.99"}
    req.client = MagicMock()
    req.client.host = attacker_socket_ip
    with pytest.raises(HTTPException) as exc_info:
        rl._check_stripe_webhook_rate_limit(req)

    assert exc_info.value.status_code == 429
    # The bucket is keyed on the socket IP, not the spoofed header.
    assert attacker_socket_ip in rl._rate_buckets
    assert "203.0.113.1" not in rl._rate_buckets
    assert "203.0.113.99" not in rl._rate_buckets
