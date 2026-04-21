"""Regression tests for #1060 — tool-access JWTs vs session JWTs.

Before this fix:
  • TOOL_ACCESS_SECRET fell back through JWT_SIGNING_KEY → AUTH_SECRET_KEY,
    so tool-access cookies were signed with the same key as admin session
    tokens. A tool-access JWT could therefore be presented at any session
    endpoint that trusted a valid signature, and vice-versa.
  • Neither token type carried ``aud``/``iss`` claims, so even moving the
    secret apart wouldn't prevent cross-type forgery if an attacker ever
    leaked one key.

After this fix:
  • tool_verification_routes.TOOL_ACCESS_SECRET is distinct from
    auth_utils.SECRET_KEY. In production it MUST be set explicitly; the
    fallback chain through AUTH_SECRET_KEY is gone.
  • create_access_token stamps aud=SESSION_AUDIENCE, iss=SESSION_ISSUER.
  • /confirm-code stamps aud=TOOL_ACCESS_AUDIENCE, iss=SESSION_ISSUER.
  • decode_access_token requires aud=SESSION_AUDIENCE when aud is present.
  • decode_tool_access_token requires aud=TOOL_ACCESS_AUDIENCE when aud is
    present.
  • Tokens minted before the fix (no aud claim) still verify — signature is
    always checked. Once they expire the fallback becomes dead code.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest
import jwt as pyjwt


# Make services/admin importable (mirrors other test files in this dir)
_REPO_ADMIN = Path(__file__).resolve().parents[1]
if str(_REPO_ADMIN) not in sys.path:
    sys.path.insert(0, str(_REPO_ADMIN))


# ─────────────────────────────────────────────────────────────────────
# Test: constants exist and have the expected shape
# ─────────────────────────────────────────────────────────────────────
def test_audience_constants_are_distinct():
    from app.auth_utils import (
        SESSION_AUDIENCE,
        SESSION_ISSUER,
        TOOL_ACCESS_AUDIENCE,
    )

    # The three constants must all be non-empty strings …
    assert isinstance(SESSION_AUDIENCE, str) and SESSION_AUDIENCE
    assert isinstance(SESSION_ISSUER, str) and SESSION_ISSUER
    assert isinstance(TOOL_ACCESS_AUDIENCE, str) and TOOL_ACCESS_AUDIENCE

    # … and the two audiences MUST differ — that is the whole point of
    # the fix. If someone ever makes them equal, a tool-access token is
    # instantly usable as a session token again.
    assert SESSION_AUDIENCE != TOOL_ACCESS_AUDIENCE


# ─────────────────────────────────────────────────────────────────────
# Test: session tokens minted by create_access_token carry aud + iss
# ─────────────────────────────────────────────────────────────────────
def test_session_tokens_include_aud_and_iss():
    from app.auth_utils import (
        ALGORITHM,
        SECRET_KEY,
        SESSION_AUDIENCE,
        SESSION_ISSUER,
        create_access_token,
    )

    tok = create_access_token({"sub": "user-1", "tenant_id": "tenant-1"})

    # Decode bypassing aud/iss verification to inspect raw claims.
    claims = pyjwt.decode(
        tok,
        SECRET_KEY,
        algorithms=[ALGORITHM],
        options={"verify_aud": False, "verify_iss": False},  # nosemgrep: python.jwt.security.unverified-jwt-decode.unverified-jwt-decode
    )
    assert claims["aud"] == SESSION_AUDIENCE
    assert claims["iss"] == SESSION_ISSUER


# ─────────────────────────────────────────────────────────────────────
# Test: decode_access_token accepts its own tokens round-trip
# ─────────────────────────────────────────────────────────────────────
def test_decode_access_token_roundtrip_succeeds():
    from app.auth_utils import create_access_token, decode_access_token

    tok = create_access_token({"sub": "user-42", "tenant_id": "tenant-42"})
    payload = decode_access_token(tok)

    assert payload["sub"] == "user-42"
    assert payload["tenant_id"] == "tenant-42"


# ─────────────────────────────────────────────────────────────────────
# Test: decode_access_token REJECTS a token with TOOL_ACCESS aud
# (this is the core security property — a tool-access token must never
# be interpretable as a session token)
# ─────────────────────────────────────────────────────────────────────
def test_decode_access_token_rejects_tool_access_aud():
    from app.auth_utils import (
        ALGORITHM,
        SECRET_KEY,
        SESSION_ISSUER,
        TOOL_ACCESS_AUDIENCE,
        decode_access_token,
    )

    # Build a token signed with the SESSION key (worst case: attacker
    # somehow got the session key) but stamped as tool-access audience.
    # Even with a valid signature, audience mismatch must be rejected.
    forged = pyjwt.encode(
        {
            "sub": "attacker",
            "tenant_id": "victim",
            "aud": TOOL_ACCESS_AUDIENCE,
            "iss": SESSION_ISSUER,
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )

    with pytest.raises(pyjwt.exceptions.InvalidAudienceError):
        decode_access_token(forged)


# ─────────────────────────────────────────────────────────────────────
# Test: decode_access_token REJECTS a token with wrong issuer
# ─────────────────────────────────────────────────────────────────────
def test_decode_access_token_rejects_wrong_issuer():
    from app.auth_utils import (
        ALGORITHM,
        SECRET_KEY,
        SESSION_AUDIENCE,
        decode_access_token,
    )

    forged = pyjwt.encode(
        {
            "sub": "attacker",
            "aud": SESSION_AUDIENCE,
            "iss": "not-regengine-admin",
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )

    with pytest.raises(pyjwt.exceptions.InvalidIssuerError):
        decode_access_token(forged)


# ─────────────────────────────────────────────────────────────────────
# Test: LEGACY session tokens (no aud/iss) still decode — transitional
# compat so we don't log everyone out at deploy time.
# ─────────────────────────────────────────────────────────────────────
def test_decode_access_token_accepts_legacy_tokens_without_aud():
    from app.auth_utils import ALGORITHM, SECRET_KEY, decode_access_token

    legacy = pyjwt.encode(
        {"sub": "legacy-user", "tenant_id": "legacy-tenant"},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )

    payload = decode_access_token(legacy)
    assert payload["sub"] == "legacy-user"


# ─────────────────────────────────────────────────────────────────────
# Test: LEGACY tool-access tokens (no aud/iss) still decode
# ─────────────────────────────────────────────────────────────────────
def test_decode_tool_access_accepts_legacy_tokens_without_aud(monkeypatch):
    monkeypatch.setenv("TOOL_ACCESS_SECRET", "legacy-test-secret")
    _reload_tool_verification_routes()
    from app import tool_verification_routes as tvr

    legacy = pyjwt.encode(
        {"email": "u@example.com", "domain": "example.com"},
        tvr.TOOL_ACCESS_SECRET,
        algorithm="HS256",
    )

    payload = tvr.decode_tool_access_token(legacy)
    assert payload["email"] == "u@example.com"


# ─────────────────────────────────────────────────────────────────────
# Test: decode_tool_access_token REJECTS a session JWT
# (core cross-type-confusion protection)
# ─────────────────────────────────────────────────────────────────────
def test_decode_tool_access_rejects_session_jwt(monkeypatch):
    # Force separate secrets so the only thing distinguishing the
    # tokens is the audience claim, not the signature.
    monkeypatch.setenv("TOOL_ACCESS_SECRET", "different-tool-secret")
    _reload_tool_verification_routes()

    from app.auth_utils import (
        ALGORITHM,
        SESSION_AUDIENCE,
        SESSION_ISSUER,
        create_access_token,
    )
    from app import tool_verification_routes as tvr

    session_token = create_access_token({"sub": "legit-user"})

    # The session token is signed with SECRET_KEY, not TOOL_ACCESS_SECRET.
    # Its signature alone will be rejected. But to make the test specifically
    # prove the audience defense, we re-encode the same claims under the
    # tool-access key: worst case — attacker controls both keys — the token
    # STILL must be rejected because its aud is SESSION_AUDIENCE.
    session_claims = pyjwt.decode(  # nosemgrep: python.jwt.security.unverified-jwt-decode.unverified-jwt-decode
        session_token,
        options={"verify_signature": False},
    )
    assert session_claims["aud"] == SESSION_AUDIENCE
    assert session_claims["iss"] == SESSION_ISSUER

    impostor = pyjwt.encode(
        session_claims,
        tvr.TOOL_ACCESS_SECRET,
        algorithm=ALGORITHM,
    )

    with pytest.raises(pyjwt.exceptions.InvalidAudienceError):
        tvr.decode_tool_access_token(impostor)


# ─────────────────────────────────────────────────────────────────────
# Test: a valid tool-access token round-trips through decode_tool_access
# ─────────────────────────────────────────────────────────────────────
def test_tool_access_token_roundtrip(monkeypatch):
    monkeypatch.setenv("TOOL_ACCESS_SECRET", "roundtrip-secret")
    _reload_tool_verification_routes()
    from app.auth_utils import SESSION_ISSUER, TOOL_ACCESS_AUDIENCE
    from app import tool_verification_routes as tvr

    tok = pyjwt.encode(
        {
            "email": "lead@example.com",
            "domain": "example.com",
            "type": "tool_access",
            "aud": TOOL_ACCESS_AUDIENCE,
            "iss": SESSION_ISSUER,
        },
        tvr.TOOL_ACCESS_SECRET,
        algorithm="HS256",
    )

    payload = tvr.decode_tool_access_token(tok)
    assert payload["email"] == "lead@example.com"
    assert payload["domain"] == "example.com"
    assert payload["type"] == "tool_access"


# ─────────────────────────────────────────────────────────────────────
# Test: TOOL_ACCESS_SECRET no longer falls back to AUTH_SECRET_KEY
# (regression pin for the vulnerability itself)
# ─────────────────────────────────────────────────────────────────────
def test_tool_access_secret_does_not_fall_back_to_auth_secret(monkeypatch):
    monkeypatch.delenv("TOOL_ACCESS_SECRET", raising=False)
    monkeypatch.delenv("JWT_SIGNING_KEY", raising=False)
    monkeypatch.setenv("AUTH_SECRET_KEY", "session-key-do-not-reuse")
    monkeypatch.setenv("REGENGINE_ENV", "development")  # allow ephemeral dev key

    _reload_tool_verification_routes()
    from app import tool_verification_routes as tvr

    # Must NOT equal the session key — that was the bug.
    assert tvr.TOOL_ACCESS_SECRET != "session-key-do-not-reuse"
    # And must NOT be empty — fallback through to empty string would also
    # be a vulnerability (all tokens signed with "" would accept each other).
    assert tvr.TOOL_ACCESS_SECRET


# ─────────────────────────────────────────────────────────────────────
# Test: production deployments MUST provide TOOL_ACCESS_SECRET explicitly
# ─────────────────────────────────────────────────────────────────────
def test_tool_access_secret_fails_closed_in_production(monkeypatch):
    monkeypatch.delenv("TOOL_ACCESS_SECRET", raising=False)
    monkeypatch.delenv("JWT_SIGNING_KEY", raising=False)
    monkeypatch.setenv("AUTH_SECRET_KEY", "session-key-must-not-be-used")
    monkeypatch.setenv("REGENGINE_ENV", "production")

    with pytest.raises(RuntimeError) as excinfo:
        _reload_tool_verification_routes()

    msg = str(excinfo.value)
    assert "TOOL_ACCESS_SECRET" in msg
    assert "production" in msg.lower()
    # The error message should guide the operator to generate a fresh key,
    # not reuse AUTH_SECRET_KEY.
    assert "distinct" in msg.lower() or "separate" in msg.lower() or "1060" in msg


# ─────────────────────────────────────────────────────────────────────
# Test: production also fails closed when TOOL_ACCESS_SECRET is empty
# (whitespace-only values are defensively treated as unset)
# ─────────────────────────────────────────────────────────────────────
def test_tool_access_secret_empty_string_fails_in_production(monkeypatch):
    monkeypatch.setenv("TOOL_ACCESS_SECRET", "   ")  # whitespace only
    monkeypatch.setenv("REGENGINE_ENV", "production")

    with pytest.raises(RuntimeError):
        _reload_tool_verification_routes()


# ─────────────────────────────────────────────────────────────────────
# Test: cross-secret forgery — token signed with tool-access key
# cannot be verified as session token.
# ─────────────────────────────────────────────────────────────────────
def test_session_decode_rejects_tool_access_key_signature(monkeypatch):
    monkeypatch.setenv("TOOL_ACCESS_SECRET", "tool-secret-xyz")
    _reload_tool_verification_routes()
    from app.auth_utils import (
        ALGORITHM,
        SESSION_AUDIENCE,
        SESSION_ISSUER,
        decode_access_token,
    )
    from app import tool_verification_routes as tvr

    # Mint a token with the SESSION audience/issuer but signed using the
    # TOOL key. decode_access_token uses SESSION secret → signature fails.
    forged = pyjwt.encode(
        {
            "sub": "impostor",
            "aud": SESSION_AUDIENCE,
            "iss": SESSION_ISSUER,
        },
        tvr.TOOL_ACCESS_SECRET,
        algorithm=ALGORITHM,
    )

    with pytest.raises(pyjwt.exceptions.InvalidSignatureError):
        decode_access_token(forged)


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────
def _reload_tool_verification_routes():
    """Re-import tool_verification_routes so module-level env reads refresh.

    The module resolves TOOL_ACCESS_SECRET at import time via os.environ.
    Tests that toggle env vars need a fresh import to observe the change.
    """
    for modname in [
        "app.tool_verification_routes",
        "services.admin.app.tool_verification_routes",
    ]:
        if modname in sys.modules:
            del sys.modules[modname]
    importlib.import_module("app.tool_verification_routes")


# ─────────────────────────────────────────────────────────────────────
# Test: pre-#1060 bug reproduction — previously, a tool-access token
# signed with fall-through to AUTH_SECRET_KEY would pass decode_access_token
# because they shared the key and had no aud distinguishing claim.
# This test constructs exactly that scenario and shows it fails now.
# ─────────────────────────────────────────────────────────────────────
def test_regression_tool_access_cannot_impersonate_session():
    """Regression lock for the exact bug in #1060.

    Attack pre-fix:
      1. Attacker gets verified as a lead via /confirm-code.
      2. Backend issues tool_access JWT signed with AUTH_SECRET_KEY.
      3. Attacker presents the same JWT at an endpoint that calls
         decode_access_token(). Signature validates. No aud check.
         Attacker is now treated as a session user.

    Post-fix: the tool-access token carries aud=TOOL_ACCESS_AUDIENCE,
    and decode_access_token requires aud=SESSION_AUDIENCE. Even if
    TOOL_ACCESS_SECRET were accidentally set to AUTH_SECRET_KEY (which
    would itself be a misconfiguration), the token would still be
    rejected on audience mismatch.
    """
    from app.auth_utils import (
        ALGORITHM,
        SECRET_KEY,
        SESSION_ISSUER,
        TOOL_ACCESS_AUDIENCE,
        decode_access_token,
    )

    # Simulate the WORST case from the bug: secrets accidentally equal.
    tool_access_jwt_with_session_key = pyjwt.encode(
        {
            "email": "attacker@corp.com",
            "domain": "corp.com",
            "type": "tool_access",
            "aud": TOOL_ACCESS_AUDIENCE,
            "iss": SESSION_ISSUER,
        },
        SECRET_KEY,  # <-- accidental key reuse (pre-fix vulnerability)
        algorithm=ALGORITHM,
    )

    # Even though the signature verifies, audience mismatch rejects it.
    with pytest.raises(pyjwt.exceptions.InvalidAudienceError):
        decode_access_token(tool_access_jwt_with_session_key)
