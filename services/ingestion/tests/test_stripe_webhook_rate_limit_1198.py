"""Tests for Stripe webhook rate limiting -- #1198."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from fastapi import HTTPException

import app.stripe_billing.rate_limiting as rl


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
    monkeypatch.setattr(rl, "_rate_buckets", {})     # fresh state
    req = _make_request("10.0.0.1")

    # Send 5 requests — well under the 100 RPM limit
    for _ in range(5):
        rl._check_stripe_webhook_rate_limit(req)  # must not raise


def test_rate_limit_blocks_after_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """After exceeding the per-IP limit a 429 must be raised."""
    monkeypatch.setattr(rl, "_redis_failed", True)
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


def test_rate_limit_uses_x_forwarded_for(monkeypatch: pytest.MonkeyPatch) -> None:
    """X-Forwarded-For header must be preferred over request.client.host."""
    monkeypatch.setattr(rl, "_redis_failed", True)
    monkeypatch.setattr(rl, "_rate_buckets", {})
    monkeypatch.setattr(rl, "_WEBHOOK_RATE_LIMIT", 2)

    req = MagicMock()
    req.headers = {"X-Forwarded-For": "203.0.113.10, 10.0.0.1"}
    req.client = MagicMock()
    req.client.host = "10.0.0.1"  # proxy IP, should NOT be used

    for _ in range(2):
        rl._check_stripe_webhook_rate_limit(req)

    with pytest.raises(HTTPException) as exc_info:
        rl._check_stripe_webhook_rate_limit(req)

    assert exc_info.value.status_code == 429
    # Confirm that the bucket key was for the forwarded IP
    assert "203.0.113.10" in rl._rate_buckets
