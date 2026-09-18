"""Unit tests for ``app.email_ingest.auth`` — the Basic-Auth webhook gate.

Mocking style follows ``test_stripe_plans_1342.py``: ``monkeypatch`` for env
vars, no live DB or network. Every branch of ``verify_inbound_email_auth`` is
exercised, plus the fail-closed-when-unset behavior called out in the
module's own docstring as a deliberate divergence from the
``WEBHOOK_HMAC_SECRET`` fail-open precedent.
"""

from __future__ import annotations

import base64

import pytest
from services.ingestion.app.email_ingest.auth import _configured_credentials, email_inbound_auth_configured, verify_inbound_email_auth
from fastapi import HTTPException

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
