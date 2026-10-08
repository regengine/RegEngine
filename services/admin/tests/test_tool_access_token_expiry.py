"""Tool-access JWT expiry (audit medium 9).

Tokens minted by POST /api/v1/tools/confirm-code must carry a short
``exp`` claim (default 24 hours, configurable via
``TOOL_ACCESS_TOKEN_EXPIRE_HOURS``) so a leaked or stolen cookie stops
working. ``decode_tool_access_token`` must reject expired tokens.
"""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import jwt as pyjwt
import pytest
from starlette.requests import Request

_REPO_ADMIN = Path(__file__).resolve().parents[1]
if str(_REPO_ADMIN) not in sys.path:
    sys.path.insert(0, str(_REPO_ADMIN))


def _stub_request() -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/tools/confirm-code",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
    }
    request = Request(scope)
    request.state.view_rate_limit = None
    return request


@pytest.fixture(autouse=True)
def disable_slowapi(monkeypatch):
    try:
        import slowapi.extension as slowapi_extension

        monkeypatch.setattr(slowapi_extension.Limiter, "_check_request_limit", lambda *a, **k: None)
    except Exception:
        pass


@pytest.fixture
def tvr(monkeypatch):
    monkeypatch.setenv("TOOL_ACCESS_SECRET", "tool-expiry-test-secret")
    monkeypatch.setenv("REGENGINE_ENV", "test")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    for modname in [
        "app.tool_verification_routes",
        "services.admin.app.tool_verification_routes",
    ]:
        sys.modules.pop(modname, None)
    module = importlib.import_module("app.tool_verification_routes")
    module._memory_store.clear()
    module._redis_available = False
    module._redis_client = None
    module.RESEND_API_KEY = None
    return module


def _unverified_claims(token: str) -> dict:
    return pyjwt.decode(
        token,
        options={
            "verify_signature": False,  # nosemgrep: python.jwt.security.unverified-jwt-decode.unverified-jwt-decode
            "verify_aud": False,
            "verify_iss": False,
            "verify_exp": False,
        },
    )


async def _confirmed_token(tvr, monkeypatch, email="lead@corp.com") -> str:
    monkeypatch.setattr(tvr.secrets, "randbelow", lambda _: 111111)
    monkeypatch.setattr(tvr, "_save_lead", MagicMock())
    await tvr.verify_email(
        payload=tvr.VerifyEmailRequest(email=email, tool_name="ftl-checker"),
        request=_stub_request(),
    )
    confirm = await tvr.confirm_code(
        payload=tvr.ConfirmCodeRequest(email=email, code="211111", tool_name="ftl-checker"),
        request=_stub_request(),
    )
    assert confirm.status == "verified"
    return confirm.token


@pytest.mark.asyncio
async def test_confirmed_token_carries_24h_expiry(tvr, monkeypatch):
    """Fresh /confirm-code token has iat/exp about 24 hours apart."""
    token = await _confirmed_token(tvr, monkeypatch)

    claims = _unverified_claims(token)
    assert "exp" in claims, "tool-access token must carry an exp claim"
    assert "iat" in claims, "tool-access token must carry an iat claim"
    lifetime = claims["exp"] - claims["iat"]
    assert timedelta(hours=23) < timedelta(seconds=lifetime) < timedelta(hours=25)

    # Fresh token verifies through the real decode path.
    payload = tvr.decode_tool_access_token(token)
    assert payload["email"] == "lead@corp.com"
    assert payload["type"] == "tool_access"


@pytest.mark.asyncio
async def test_expired_token_rejected(tvr, monkeypatch):
    """A tool-access token past its exp is rejected on use."""
    await _confirmed_token(tvr, monkeypatch)  # ensure module path works; token unused
    now = datetime.now(timezone.utc)
    expired = pyjwt.encode(
        {
            "email": "lead@corp.com",
            "domain": "corp.com",
            "verified_at": (now - timedelta(hours=2)).isoformat(),
            "type": "tool_access",
            "aud": "regengine-tool-access",
            "iss": "regengine-admin",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(seconds=10),
        },
        tvr.TOOL_ACCESS_SECRET,
        algorithm="HS256",
    )

    with pytest.raises(pyjwt.exceptions.ExpiredSignatureError):
        tvr.decode_tool_access_token(expired)


@pytest.mark.asyncio
async def test_expiry_hours_configurable(tvr, monkeypatch):
    """TOOL_ACCESS_TOKEN_EXPIRE_HOURS shortens the minted lifetime."""
    monkeypatch.setenv("TOOL_ACCESS_TOKEN_EXPIRE_HOURS", "2")
    token = await _confirmed_token(tvr, monkeypatch, email="other@corp.com")

    claims = _unverified_claims(token)
    lifetime = timedelta(seconds=(claims["exp"] - claims["iat"]))
    assert timedelta(hours=1, minutes=55) < lifetime < timedelta(hours=2, minutes=5)

    # Still accepted while fresh.
    assert tvr.decode_tool_access_token(token)["email"] == "other@corp.com"


@pytest.mark.asyncio
async def test_invalid_expiry_env_falls_back_to_default(tvr, monkeypatch):
    """Garbage or non-positive TTL config falls back to the 24h default."""
    monkeypatch.setenv("TOOL_ACCESS_TOKEN_EXPIRE_HOURS", "not-a-number")
    token = await _confirmed_token(tvr, monkeypatch, email="a@corp.com")
    lifetime = timedelta(seconds=(_unverified_claims(token)["exp"] - _unverified_claims(token)["iat"]))
    assert timedelta(hours=23) < lifetime < timedelta(hours=25)

    monkeypatch.setenv("TOOL_ACCESS_TOKEN_EXPIRE_HOURS", "-5")
    token = await _confirmed_token(tvr, monkeypatch, email="b@corp.com")
    lifetime = timedelta(seconds=(_unverified_claims(token)["exp"] - _unverified_claims(token)["iat"]))
    assert timedelta(hours=23) < lifetime < timedelta(hours=25)
