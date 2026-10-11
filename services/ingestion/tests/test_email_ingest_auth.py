"""Unit tests for ``app.email_ingest.auth`` — the Basic-Auth webhook gate.

Mocking style follows ``test_stripe_plans_1342.py``: ``monkeypatch`` for env
vars, no live DB or network. Every branch of ``verify_inbound_email_auth`` is
exercised, plus the fail-closed-when-unset behavior called out in the
module's own docstring as a deliberate divergence from the
``WEBHOOK_HMAC_SECRET`` fail-open precedent.
"""

from __future__ import annotations

import base64

import app.email_ingest.auth as auth_mod
import pytest
from app.email_ingest.auth import _configured_credentials, email_inbound_auth_configured, verify_inbound_email_auth
from fastapi import HTTPException, Request
from shared.rate_limit import BruteForceLimiter

_USER = "postmark"
_PASSWORD = "s3cret"  # pragma: allowlist secret


def _basic_header(user: str, password: str) -> str:
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    # Ensure no ambient env leaks between tests / from the real environment.
    monkeypatch.delenv("EMAIL_INBOUND_BASIC_AUTH_USER", raising=False)
    monkeypatch.delenv("EMAIL_INBOUND_BASIC_AUTH_PASSWORD", raising=False)


def _configure(monkeypatch, user: str = _USER, password: str = _PASSWORD) -> None:
    monkeypatch.setenv("EMAIL_INBOUND_BASIC_AUTH_USER", user)
    monkeypatch.setenv("EMAIL_INBOUND_BASIC_AUTH_PASSWORD", password)


class TestConfiguredCredentials:
    def test_unset_returns_none(self):
        assert _configured_credentials() is None

    def test_only_user_set_returns_none(self, monkeypatch):
        monkeypatch.setenv("EMAIL_INBOUND_BASIC_AUTH_USER", _USER)
        assert _configured_credentials() is None

    def test_only_password_set_returns_none(self, monkeypatch):
        monkeypatch.setenv("EMAIL_INBOUND_BASIC_AUTH_PASSWORD", _PASSWORD)
        assert _configured_credentials() is None

    def test_blank_values_treated_as_unset(self, monkeypatch):
        monkeypatch.setenv("EMAIL_INBOUND_BASIC_AUTH_USER", "   ")
        monkeypatch.setenv("EMAIL_INBOUND_BASIC_AUTH_PASSWORD", "   ")
        assert _configured_credentials() is None

    def test_both_set_returns_tuple(self, monkeypatch):
        _configure(monkeypatch)
        assert _configured_credentials() == (_USER, _PASSWORD)


class TestEmailInboundAuthConfigured:
    def test_false_when_unset(self):
        assert email_inbound_auth_configured() is False

    def test_true_when_configured(self, monkeypatch):
        _configure(monkeypatch)
        assert email_inbound_auth_configured() is True


class TestVerifyInboundEmailAuth:
    async def test_fails_closed_when_unconfigured(self):
        # Deliberate divergence from WEBHOOK_HMAC_SECRET's fail-open ramp:
        # an endpoint that writes straight into compliance ingestion must
        # never silently skip auth just because the operator forgot to
        # set the env vars.
        with pytest.raises(HTTPException) as ei:
            await verify_inbound_email_auth(authorization=None)
        assert ei.value.status_code == 401
        assert "not configured" in ei.value.detail

    async def test_missing_header_raises_401(self, monkeypatch):
        _configure(monkeypatch)
        with pytest.raises(HTTPException) as ei:
            await verify_inbound_email_auth(authorization=None)
        assert ei.value.status_code == 401
        assert ei.value.headers == {"WWW-Authenticate": "Basic"}

    async def test_non_basic_scheme_raises_401(self, monkeypatch):
        _configure(monkeypatch)
        with pytest.raises(HTTPException) as ei:
            await verify_inbound_email_auth(authorization="Bearer sometoken")
        assert ei.value.status_code == 401
        assert ei.value.detail == "Missing credentials"

    async def test_malformed_base64_raises_401(self, monkeypatch):
        _configure(monkeypatch)
        with pytest.raises(HTTPException) as ei:
            await verify_inbound_email_auth(authorization="Basic not-valid-base64!!!")
        assert ei.value.status_code == 401
        assert ei.value.detail == "Invalid credentials"

    async def test_wrong_credentials_raise_401(self, monkeypatch):
        _configure(monkeypatch)
        header = _basic_header(_USER, "wrong-password")
        with pytest.raises(HTTPException) as ei:
            await verify_inbound_email_auth(authorization=header)
        assert ei.value.status_code == 401
        assert ei.value.detail == "Invalid credentials"

    async def test_wrong_username_raises_401(self, monkeypatch):
        _configure(monkeypatch)
        header = _basic_header("someone-else", _PASSWORD)
        with pytest.raises(HTTPException) as ei:
            await verify_inbound_email_auth(authorization=header)
        assert ei.value.status_code == 401

    async def test_credentials_without_colon_raise_401(self, monkeypatch):
        _configure(monkeypatch)
        token = base64.b64encode(b"nocolonhere").decode("ascii")
        with pytest.raises(HTTPException) as ei:
            await verify_inbound_email_auth(authorization=f"Basic {token}")
        assert ei.value.status_code == 401

    async def test_correct_credentials_pass(self, monkeypatch):
        _configure(monkeypatch)
        header = _basic_header(_USER, _PASSWORD)
        # No exception == success; the dependency has no return value.
        assert await verify_inbound_email_auth(authorization=header) is None

    async def test_password_containing_colons_is_supported(self, monkeypatch):
        # RFC 7617: the user-id ends at the first colon, everything after
        # it is the password. A password containing colons must authenticate.
        _configure(monkeypatch, password="with:several:colons")
        header = _basic_header(_USER, "with:several:colons")
        assert await verify_inbound_email_auth(authorization=header) is None


class TestBruteForceLimiting:
    def _request(self, ip: str = "10.9.8.7") -> Request:
        return Request(
            {"type": "http", "method": "POST", "path": "/webhooks/email/inbound", "headers": [], "client": (ip, 5000)}
        )

    def _fresh_limiter(self, monkeypatch, *, max_failures: int = 3):
        limiter = BruteForceLimiter(
            namespace="test-email-inbound-auth-fail", max_failures=max_failures, window_seconds=60, redis_client=None
        )
        limiter._redis = None  # ignore any env-provided Redis; per-test memory budget
        monkeypatch.setattr(auth_mod, "_email_auth_limiter", limiter)
        return limiter

    async def test_repeated_failures_block_further_attempts_with_429(self, monkeypatch):
        _configure(monkeypatch)
        self._fresh_limiter(monkeypatch, max_failures=3)
        bad = _basic_header(_USER, "wrong-password")
        request = self._request()
        for _ in range(3):
            with pytest.raises(HTTPException) as ei:
                await verify_inbound_email_auth(request, authorization=bad)
            assert ei.value.status_code == 401
        with pytest.raises(HTTPException) as ei:
            await verify_inbound_email_auth(request, authorization=bad)
        assert ei.value.status_code == 429
        assert ei.value.detail == "Too many authentication failures"

    async def test_block_is_scoped_to_the_attacker_ip(self, monkeypatch):
        _configure(monkeypatch)
        self._fresh_limiter(monkeypatch, max_failures=2)
        bad = _basic_header(_USER, "wrong-password")
        attacker = self._request("10.9.8.7")
        for _ in range(2):
            with pytest.raises(HTTPException):
                await verify_inbound_email_auth(attacker, authorization=bad)
        with pytest.raises(HTTPException) as ei:
            await verify_inbound_email_auth(attacker, authorization=bad)
        assert ei.value.status_code == 429
        # A different client presenting bad creds gets its own budget:
        # still 401, not 429.
        other = self._request("10.9.8.99")
        with pytest.raises(HTTPException) as ei:
            await verify_inbound_email_auth(other, authorization=bad)
        assert ei.value.status_code == 401

    async def test_correct_credentials_below_threshold_still_pass(self, monkeypatch):
        # A couple of stray failures (stale credential during rotation)
        # must not lock out the real sender.
        _configure(monkeypatch)
        self._fresh_limiter(monkeypatch, max_failures=3)
        request = self._request()
        bad = _basic_header(_USER, "wrong-password")
        for _ in range(2):
            with pytest.raises(HTTPException):
                await verify_inbound_email_auth(request, authorization=bad)
        assert await verify_inbound_email_auth(request, authorization=_basic_header(_USER, _PASSWORD)) is None

    async def test_unconfigured_gate_does_not_consume_budget(self, monkeypatch):
        # No credential configured means nothing to guess: these 401s must
        # not count, or the first real deliveries after setup would arrive
        # to an already-blocked budget.
        self._fresh_limiter(monkeypatch, max_failures=2)
        request = self._request()
        for _ in range(5):
            with pytest.raises(HTTPException) as ei:
                await verify_inbound_email_auth(request, authorization=_basic_header(_USER, _PASSWORD))
            assert ei.value.status_code == 401
        _configure(monkeypatch)
        assert await verify_inbound_email_auth(request, authorization=_basic_header(_USER, _PASSWORD)) is None

    async def test_scheme_match_is_case_insensitive(self, monkeypatch):
        _configure(monkeypatch)
        token = base64.b64encode(f"{_USER}:{_PASSWORD}".encode()).decode("ascii")
        assert await verify_inbound_email_auth(authorization=f"BASIC {token}") is None

    async def test_non_ascii_credentials_raise_401_not_500(self, monkeypatch):
        # Regression: hmac.compare_digest raises TypeError on non-ASCII str
        # inputs. A crafted Basic-Auth header can decode to valid non-ASCII
        # UTF-8 -- this must still 401, not crash into an unhandled 500.
        _configure(monkeypatch)
        header = _basic_header("ünïcode", "pass")
        with pytest.raises(HTTPException) as ei:
            await verify_inbound_email_auth(authorization=header)
        assert ei.value.status_code == 401
        assert ei.value.detail == "Invalid credentials"
