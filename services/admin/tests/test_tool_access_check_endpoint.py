"""Tool-access 24h enforcement where access is decided (PR #3228 follow-up).

Covers the gaps the audit reviewers found after the mint-side expiry fix:
minting capped at 24 hours, decode rejecting over-long lifetimes, the new
POST /api/v1/tools/check-access endpoint that the Next.js gate calls, and
the expires_in_seconds field the cookie maxAge is derived from.
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


def _stub_request(path: str = "/api/v1/tools/check-access") -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
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
    monkeypatch.setenv("TOOL_ACCESS_SECRET", "tool-check-test-secret")
    monkeypatch.setenv("REGENGINE_ENV", "test")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("TOOL_ACCESS_TOKEN_EXPIRE_HOURS", raising=False)
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
    return (await _confirmed_response(tvr, monkeypatch, rand_code=111111, email=email)).token


async def _confirmed_response(tvr, monkeypatch, *, rand_code: int, email: str):
    monkeypatch.setattr(tvr.secrets, "randbelow", lambda _: rand_code)
    monkeypatch.setattr(tvr, "_save_lead", MagicMock())
    await tvr.verify_email(
        payload=tvr.VerifyEmailRequest(email=email, tool_name="ftl-checker"),
        request=_stub_request(path="/api/v1/tools/verify-email"),
    )
    # verify_email stores f"{randbelow(900000) + 100000}"; reproduce it here.
    expected_code = f"{rand_code + 100000}"
    return await tvr.confirm_code(
        payload=tvr.ConfirmCodeRequest(email=email, code=expected_code, tool_name="ftl-checker"),
        request=_stub_request(path="/api/v1/tools/confirm-code"),
    )


def _mint(tvr, *, iat=None, lifetime: timedelta, with_aud_iss: bool = True) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "email": "lead@corp.com",
        "domain": "corp.com",
        "verified_at": now.isoformat(),
        "type": "tool_access",
        "iat": iat or now,
        "exp": now + lifetime,
    }
    if with_aud_iss:
        claims["aud"] = tvr.TOOL_ACCESS_AUDIENCE
        claims["iss"] = tvr.SESSION_ISSUER
    return pyjwt.encode(claims, tvr.TOOL_ACCESS_SECRET, algorithm="HS256")


# ---------------------------------------------------------------------------
# Mint cap: env values above 24h fall back to the 24h default.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["25", "48", "1000", "100000", "24.0001"])
def test_over_max_ttl_env_falls_back_to_default(tvr, monkeypatch, raw):
    monkeypatch.setenv("TOOL_ACCESS_TOKEN_EXPIRE_HOURS", raw)
    assert tvr._tool_access_expire_hours() == tvr.TOOL_ACCESS_TOKEN_EXPIRE_HOURS_DEFAULT


@pytest.mark.asyncio
async def test_over_max_ttl_mints_24h_token(tvr, monkeypatch):
    """An operator setting 48h still gets a 24h token, not an 11-year one."""
    monkeypatch.setenv("TOOL_ACCESS_TOKEN_EXPIRE_HOURS", "48")
    token = await _confirmed_token(tvr, monkeypatch, email="cap@corp.com")
    claims = _unverified_claims(token)
    lifetime = timedelta(seconds=(claims["exp"] - claims["iat"]))
    assert timedelta(hours=23) < lifetime < timedelta(hours=25)


def test_at_max_ttl_env_is_honored(tvr, monkeypatch):
    monkeypatch.setenv("TOOL_ACCESS_TOKEN_EXPIRE_HOURS", "24")
    assert tvr._tool_access_expire_hours() == pytest.approx(24.0)


# ---------------------------------------------------------------------------
# Decode cap: over-long lifetimes are rejected even with a valid signature.
# ---------------------------------------------------------------------------


def test_decode_rejects_token_living_longer_than_24h(tvr):
    token = _mint(tvr, lifetime=timedelta(hours=48))
    with pytest.raises(pyjwt.exceptions.InvalidTokenError):
        tvr.decode_tool_access_token(token)


def test_decode_rejects_over_long_legacy_token(tvr):
    token = _mint(tvr, lifetime=timedelta(hours=72), with_aud_iss=False)
    with pytest.raises(pyjwt.exceptions.InvalidTokenError):
        tvr.decode_tool_access_token(token)


def test_decode_accepts_token_at_exactly_24h(tvr):
    token = _mint(tvr, lifetime=timedelta(hours=24))
    assert tvr.decode_tool_access_token(token)["type"] == "tool_access"


def test_decode_accepts_short_lived_token(tvr):
    token = _mint(tvr, lifetime=timedelta(hours=2))
    assert tvr.decode_tool_access_token(token)["type"] == "tool_access"


# ---------------------------------------------------------------------------
# POST /check-access: the gate the Next.js cookie check calls.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_access_accepts_fresh_token(tvr):
    token = _mint(tvr, lifetime=timedelta(hours=23))
    result = await tvr.check_access_tool_token(
        payload=tvr.CheckAccessRequest(token=token),
        request=_stub_request(),
    )
    assert result == {"hasAccess": True}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "make_token",
    [
        lambda tvr: _mint(tvr, lifetime=timedelta(seconds=-10)),
        lambda tvr: "not-a-jwt",
        lambda tvr: "",
        lambda tvr: (
            _mint(
                tvr,
                lifetime=timedelta(hours=1),
                with_aud_iss=False,
            )[:-4]
            + "xxxx"
        ),
    ],
    ids=["expired", "garbage", "empty", "tampered-signature"],
)
async def test_check_access_rejects_bad_tokens(tvr, make_token):
    result = await tvr.check_access_tool_token(
        payload=tvr.CheckAccessRequest(token=make_token(tvr)),
        request=_stub_request(),
    )
    assert result == {"hasAccess": False}


@pytest.mark.asyncio
async def test_check_access_rejects_no_exp_token(tvr):
    now = datetime.now(timezone.utc)
    token = pyjwt.encode(
        {
            "email": "lead@corp.com",
            "domain": "corp.com",
            "verified_at": now.isoformat(),
            "type": "tool_access",
            "aud": tvr.TOOL_ACCESS_AUDIENCE,
            "iss": tvr.SESSION_ISSUER,
            "iat": now,
        },
        tvr.TOOL_ACCESS_SECRET,
        algorithm="HS256",
    )
    result = await tvr.check_access_tool_token(
        payload=tvr.CheckAccessRequest(token=token),
        request=_stub_request(),
    )
    assert result == {"hasAccess": False}


@pytest.mark.asyncio
async def test_check_access_rejects_over_long_token(tvr):
    token = _mint(tvr, lifetime=timedelta(hours=48))
    result = await tvr.check_access_tool_token(
        payload=tvr.CheckAccessRequest(token=token),
        request=_stub_request(),
    )
    assert result == {"hasAccess": False}


# ---------------------------------------------------------------------------
# confirm-code reports the minted lifetime for the cookie maxAge.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirm_reports_default_24h_lifetime(tvr, monkeypatch):
    confirm = await _confirmed_response(tvr, monkeypatch, rand_code=222222, email="life@corp.com")
    assert confirm.status == "verified"
    assert confirm.token != ""
    assert confirm.expires_in_seconds == 86400


@pytest.mark.asyncio
async def test_confirm_reports_configured_shorter_lifetime(tvr, monkeypatch):
    monkeypatch.setenv("TOOL_ACCESS_TOKEN_EXPIRE_HOURS", "2")
    confirm = await _confirmed_response(tvr, monkeypatch, rand_code=333333, email="short@corp.com")
    assert confirm.expires_in_seconds == 7200
