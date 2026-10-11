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


# ---------------------------------------------------------------------------
# Regression: exp is REQUIRED on both decode paths.
#
# PyJWT only verifies exp when the claim is present, so before the fix a
# token without exp was accepted on the normal aud+iss path AND re-accepted
# by the legacy fallback (MissingRequiredClaimError -> decode without
# aud/iss checks). Old no-exp cookies are now rejected and must reverify.
# ---------------------------------------------------------------------------


def _tool_claims(tvr, *, with_aud_iss: bool, exp=None, iat=None) -> dict:
    now = datetime.now(timezone.utc)
    claims = {
        "email": "lead@corp.com",
        "domain": "corp.com",
        "verified_at": now.isoformat(),
        "type": "tool_access",
    }
    if with_aud_iss:
        claims["aud"] = tvr.TOOL_ACCESS_AUDIENCE
        claims["iss"] = tvr.SESSION_ISSUER
    claims["iat"] = iat or now
    if exp is not None:
        claims["exp"] = exp
    return claims


def test_no_exp_token_with_aud_iss_rejected(tvr):
    """Normal path: aud+iss present but exp missing -> rejected."""
    token = pyjwt.encode(
        _tool_claims(tvr, with_aud_iss=True, exp=None),
        tvr.TOOL_ACCESS_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(pyjwt.exceptions.MissingRequiredClaimError, match="exp"):
        tvr.decode_tool_access_token(token)


def test_no_exp_legacy_token_rejected(tvr):
    """Legacy path: no aud/iss/exp -> fallback must NOT re-accept."""
    token = pyjwt.encode(
        _tool_claims(tvr, with_aud_iss=False, exp=None),
        tvr.TOOL_ACCESS_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(pyjwt.exceptions.MissingRequiredClaimError, match="exp"):
        tvr.decode_tool_access_token(token)


def test_expired_legacy_token_rejected(tvr):
    """Legacy token (no aud/iss) past its exp is rejected."""
    now = datetime.now(timezone.utc)
    token = pyjwt.encode(
        _tool_claims(
            tvr,
            with_aud_iss=False,
            iat=now - timedelta(hours=2),
            exp=now - timedelta(seconds=10),
        ),
        tvr.TOOL_ACCESS_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(pyjwt.exceptions.ExpiredSignatureError):
        tvr.decode_tool_access_token(token)


def test_legacy_token_with_valid_exp_still_accepted(tvr):
    """Transitional rollout: legacy token WITH a fresh exp still decodes."""
    now = datetime.now(timezone.utc)
    token = pyjwt.encode(
        _tool_claims(
            tvr,
            with_aud_iss=False,
            iat=now,
            exp=now + timedelta(hours=24),
        ),
        tvr.TOOL_ACCESS_SECRET,
        algorithm="HS256",
    )
    payload = tvr.decode_tool_access_token(token)
    assert payload["email"] == "lead@corp.com"
    assert payload["type"] == "tool_access"


def test_wrong_audience_rejected(tvr):
    """Correct signature/iss/exp but wrong aud -> InvalidAudienceError."""
    now = datetime.now(timezone.utc)
    token = pyjwt.encode(
        {
            **_tool_claims(tvr, with_aud_iss=False, iat=now, exp=now + timedelta(hours=1)),
            "aud": "regengine-api",  # session audience, not tool-access
            "iss": tvr.SESSION_ISSUER,
        },
        tvr.TOOL_ACCESS_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(pyjwt.exceptions.InvalidAudienceError):
        tvr.decode_tool_access_token(token)


def test_wrong_issuer_rejected(tvr):
    """Correct signature/aud/exp but wrong iss -> InvalidIssuerError."""
    now = datetime.now(timezone.utc)
    token = pyjwt.encode(
        {
            **_tool_claims(tvr, with_aud_iss=False, iat=now, exp=now + timedelta(hours=1)),
            "aud": tvr.TOOL_ACCESS_AUDIENCE,
            "iss": "not-regengine-admin",
        },
        tvr.TOOL_ACCESS_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(pyjwt.exceptions.InvalidIssuerError):
        tvr.decode_tool_access_token(token)


@pytest.mark.parametrize("audience", ["regengine-api", ["regengine-api"], None, []])
def test_legacy_missing_issuer_cannot_bypass_present_audience(tvr, audience):
    claims = _tool_claims(tvr, with_aud_iss=False, exp=datetime.now(timezone.utc) + timedelta(hours=1))
    claims["aud"] = audience
    token = pyjwt.encode(claims, tvr.TOOL_ACCESS_SECRET, algorithm="HS256")
    with pytest.raises((pyjwt.exceptions.InvalidAudienceError, pyjwt.exceptions.MissingRequiredClaimError)):
        tvr.decode_tool_access_token(token)


@pytest.mark.parametrize("claim", ["aud", "iss", "aud_list"])
def test_legacy_preserves_valid_present_domain_claim(tvr, claim):
    claims = _tool_claims(tvr, with_aud_iss=False, exp=datetime.now(timezone.utc) + timedelta(hours=1))
    if claim == "iss":
        claims["iss"] = tvr.SESSION_ISSUER
    else:
        claims["aud"] = [tvr.TOOL_ACCESS_AUDIENCE] if claim == "aud_list" else tvr.TOOL_ACCESS_AUDIENCE
    token = pyjwt.encode(claims, tvr.TOOL_ACCESS_SECRET, algorithm="HS256")
    assert tvr.decode_tool_access_token(token)["type"] == "tool_access"


# ---------------------------------------------------------------------------
# Regression: TTL env parser must fall back to 24h for non-finite,
# non-positive, or unrepresentable durations. Before the fix, nan/inf/1e309
# crashed timedelta minting (ValueError/OverflowError), 1e100 overflowed,
# and 1e-100 minted a zero-duration (immediately expired) cookie.
#
# Lower bound: durations under one second round to zero JWT seconds, so
# anything below 1s falls back to the default; >= 1s configured values
# are preserved.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    ["nan", "NaN", "inf", "-inf", "Infinity", "1e309", "1e100", "1e8", "1e-100", "0", "0.0", "-0.5"],
)
def test_invalid_ttl_values_fall_back_to_default(tvr, monkeypatch, raw):
    monkeypatch.setenv("TOOL_ACCESS_TOKEN_EXPIRE_HOURS", raw)
    assert tvr._tool_access_expire_hours() == tvr.TOOL_ACCESS_TOKEN_EXPIRE_HOURS_DEFAULT


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["nan", "inf", "1e309", "1e100", "1e8", "1e-100"])
async def test_invalid_ttl_mint_does_not_crash_and_uses_default(tvr, monkeypatch, raw):
    """End-to-end: crash/tiny TTL configs still mint a usable 24h token."""
    monkeypatch.setenv("TOOL_ACCESS_TOKEN_EXPIRE_HOURS", raw)
    token = await _confirmed_token(tvr, monkeypatch, email=f"ttl-{raw}@corp.com")

    claims = _unverified_claims(token)
    lifetime = timedelta(seconds=(claims["exp"] - claims["iat"]))
    assert timedelta(hours=23) < lifetime < timedelta(hours=25)

    # Usable through the real decode path.
    assert tvr.decode_tool_access_token(token)["type"] == "tool_access"


def test_sub_second_ttl_falls_back_to_default(tvr, monkeypatch):
    """0.0001h ~= 0.36s < 1 JWT second -> default, not an expired cookie."""
    monkeypatch.setenv("TOOL_ACCESS_TOKEN_EXPIRE_HOURS", "0.0001")
    assert tvr._tool_access_expire_hours() == tvr.TOOL_ACCESS_TOKEN_EXPIRE_HOURS_DEFAULT


@pytest.mark.asyncio
async def test_small_but_valid_ttl_preserved(tvr, monkeypatch):
    """0.01h = 36s clears the 1s minimum -> configured value is honored."""
    monkeypatch.setenv("TOOL_ACCESS_TOKEN_EXPIRE_HOURS", "0.01")
    assert tvr._tool_access_expire_hours() == pytest.approx(0.01)

    token = await _confirmed_token(tvr, monkeypatch, email="small-ttl@corp.com")
    claims = _unverified_claims(token)
    lifetime = timedelta(seconds=(claims["exp"] - claims["iat"]))
    assert timedelta(seconds=30) < lifetime < timedelta(seconds=42)

    # Still accepted while fresh.
    assert tvr.decode_tool_access_token(token)["email"] == "small-ttl@corp.com"
