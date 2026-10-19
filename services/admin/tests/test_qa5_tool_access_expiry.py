"""QA5: tool-access JWTs must expire.

``confirm_code`` used to mint a JWT with no ``exp``/``iat`` claim, and
``decode_tool_access_token`` enforced only signature/aud/iss. A
one-time email check therefore minted a perpetual Bearer [REDACTED]: a leaked
token stayed valid indefinitely and survived email changes and
offboarding. New tokens carry a 24-hour expiry, the same lifetime as the
frontend ``re_tool_access`` cookie, and tokens without ``exp`` must
reverify (#3228, #3318).
"""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from starlette.requests import Request

pytest.importorskip("jwt")

_REPO_ADMIN = Path(__file__).resolve().parents[1]
if str(_REPO_ADMIN) not in sys.path:
    sys.path.insert(0, str(_REPO_ADMIN))


def _stub_request() -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
    }
    req = Request(scope)
    req.state.view_rate_limit = None
    return req


@pytest.fixture(autouse=True)
def disable_slowapi(monkeypatch):
    try:
        import slowapi.extension as _se

        monkeypatch.setattr(_se.Limiter, "_check_request_limit", lambda *a, **k: None)
    except Exception:
        pass


@pytest.fixture
def tvr(monkeypatch):
    monkeypatch.setenv("TOOL_ACCESS_SECRET", "qa5-expiry-secret")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    for modname in ["app.tool_verification_routes", "services.admin.app.tool_verification_routes"]:
        if modname in sys.modules:
            del sys.modules[modname]
    module = importlib.import_module("app.tool_verification_routes")
    module._memory_store.clear()
    module._redis_available = False
    module._redis_client = None
    module.RESEND_API_KEY = None
    return module


@pytest.mark.asyncio
async def test_confirm_code_token_carries_24_hour_exp(tvr, monkeypatch):
    """End-to-end through ``confirm_code`` with the code check passing
    and the lead save stubbed: the minted token must decode with
    exp/iat and a 24-hour lifetime."""
    import jwt as pyjwt

    async def _ok(_email, _code):
        return True, "", {}

    monkeypatch.setattr(tvr, "_check_code", _ok)
    monkeypatch.setattr(tvr, "_save_lead", lambda *a, **k: None)

    payload = tvr.ConfirmCodeRequest(email="Lead@Example.com", code="123456", tool_name="tcr")
    response = await tvr.confirm_code(payload=payload, request=_stub_request())

    decoded = pyjwt.decode(
        response.token,
        tvr.TOOL_ACCESS_SECRET,
        algorithms=["HS256"],
        audience=tvr.TOOL_ACCESS_AUDIENCE,
        issuer=tvr.SESSION_ISSUER,
    )
    assert decoded["email"] == "lead@example.com"
    assert decoded["exp"] - decoded["iat"] == 24 * 3600


def test_expired_tool_token_rejected(tvr):
    """A token past its exp must raise, even with a valid
    signature/aud/iss (proves expiry is enforced, not decorative)."""
    import jwt as pyjwt

    now = datetime.now(timezone.utc)
    stale = pyjwt.encode(
        {
            "email": "lead@example.com",
            "domain": "example.com",
            "type": "tool_access",
            "aud": tvr.TOOL_ACCESS_AUDIENCE,
            "iss": tvr.SESSION_ISSUER,
            "iat": now - timedelta(days=60),
            "exp": now - timedelta(days=30),
        },
        tvr.TOOL_ACCESS_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(pyjwt.exceptions.ExpiredSignatureError):
        tvr.decode_tool_access_token(stale)


def test_legacy_token_without_exp_must_reverify(tvr):
    """Pre-expiry tokens with no exp claim are rejected, so their holders
    must verify their email again (#3228)."""
    import jwt as pyjwt

    legacy = pyjwt.encode(
        {
            "email": "lead@example.com",
            "domain": "example.com",
            "type": "tool_access",
            "aud": tvr.TOOL_ACCESS_AUDIENCE,
            "iss": tvr.SESSION_ISSUER,
        },
        tvr.TOOL_ACCESS_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(pyjwt.exceptions.MissingRequiredClaimError, match="exp"):
        tvr.decode_tool_access_token(legacy)
