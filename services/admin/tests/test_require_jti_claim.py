"""Regression tests for #1069 — tokens without ``jti`` are un-revocable
and must be rejected.

Before the fix, ``_check_revoked`` short-circuited (returned the payload
unmodified) on any token lacking a ``jti``. Since ``revoke_token`` keys
entirely on jti, such a token could not be individually revoked — it
remained valid until its natural expiry (default 60 min for access
tokens) regardless of logout or admin revocation.

The current ``create_access_token`` auto-generates a jti, so in steady
state every token has one. The only way to produce a pre-jti token is
to forge one (omitting the claim) or to have minted it before the
jti-adding code landed. Both cases should fail auth now.
"""
from __future__ import annotations

import os
import uuid
from datetime import timedelta

import jwt as pyjwt
import pytest


# ─────────────────────────────────────────────────────────────────────
# _check_revoked — sync-path contract
# ─────────────────────────────────────────────────────────────────────


def test_check_revoked_rejects_jti_free_payload(monkeypatch):
    """Default posture: a token payload with no jti is rejected."""
    from services.admin.app import auth_utils

    monkeypatch.setattr(auth_utils, "_revoked_jtis", set())
    monkeypatch.delenv("AUTH_ALLOW_LEGACY_JTI_FREE", raising=False)

    with pytest.raises(pyjwt.exceptions.InvalidTokenError) as excinfo:
        auth_utils._check_revoked({"sub": "u1"})
    assert "jti" in str(excinfo.value).lower()


def test_check_revoked_allows_jti_free_when_rollback_env_set(monkeypatch):
    """Escape hatch: ``AUTH_ALLOW_LEGACY_JTI_FREE=true`` preserves the
    old behavior. Pinning this keeps the rollback path working as
    long as the flag exists."""
    from services.admin.app import auth_utils

    monkeypatch.setattr(auth_utils, "_revoked_jtis", set())
    monkeypatch.setenv("AUTH_ALLOW_LEGACY_JTI_FREE", "true")

    payload = {"sub": "u1"}  # no jti
    assert auth_utils._check_revoked(payload) is payload


def test_check_revoked_rollback_flag_parses_case_insensitively(monkeypatch):
    """Operators will set TRUE/True/true/1/yes in a real incident —
    all of those must engage the rollback path."""
    from services.admin.app import auth_utils

    monkeypatch.setattr(auth_utils, "_revoked_jtis", set())
    for val in ("true", "True", "TRUE", "1", "yes"):
        monkeypatch.setenv("AUTH_ALLOW_LEGACY_JTI_FREE", val)
        assert auth_utils._check_revoked({"sub": "u1"}) == {"sub": "u1"}


def test_check_revoked_rollback_flag_ignores_bogus_values(monkeypatch):
    """Anything not in the accept-set (empty, ``false``, ``no``, etc.)
    must NOT engage rollback — we do not want a typo to silently
    re-open the hole."""
    from services.admin.app import auth_utils

    monkeypatch.setattr(auth_utils, "_revoked_jtis", set())
    for val in ("", "false", "no", "0", "off", "maybe"):
        monkeypatch.setenv("AUTH_ALLOW_LEGACY_JTI_FREE", val)
        with pytest.raises(pyjwt.exceptions.InvalidTokenError):
            auth_utils._check_revoked({"sub": "u1"})


def test_check_revoked_allows_jti_bearing_payload(monkeypatch):
    """Don't regress the common case — a normal token must still pass
    when its jti is not revoked."""
    from services.admin.app import auth_utils

    monkeypatch.setattr(auth_utils, "_revoked_jtis", set())
    monkeypatch.delenv("AUTH_ALLOW_LEGACY_JTI_FREE", raising=False)

    payload = {"sub": "u1", "jti": f"jti-{uuid.uuid4()}"}
    assert auth_utils._check_revoked(payload) is payload


# ─────────────────────────────────────────────────────────────────────
# decode_access_token — end-to-end
# ─────────────────────────────────────────────────────────────────────


def test_decode_rejects_forged_jti_free_token(monkeypatch):
    """The adversarial scenario: an attacker crafts a token that omits
    the jti claim specifically to bypass revocation. Even if the
    signature is valid, the decode must reject."""
    from services.admin.app import auth_utils

    monkeypatch.setattr(auth_utils, "_revoked_jtis", set())
    monkeypatch.delenv("AUTH_ALLOW_LEGACY_JTI_FREE", raising=False)

    # Forge a token with no jti using the same signing key.
    from services.admin.app.auth_utils import SECRET_KEY, ALGORITHM
    forged = pyjwt.encode(
        {"sub": "u1", "exp": int((__import__("time").time())) + 3600},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )

    with pytest.raises(pyjwt.exceptions.InvalidTokenError):
        auth_utils.decode_access_token(forged)


def test_decode_accepts_normally_minted_token(monkeypatch):
    """Sanity — the tokens our own mint path produces must still decode
    cleanly. If create_access_token ever regresses and stops adding
    jti, this test catches it."""
    from services.admin.app import auth_utils
    from services.admin.app.auth_utils import create_access_token

    monkeypatch.setattr(auth_utils, "_revoked_jtis", set())
    monkeypatch.delenv("AUTH_ALLOW_LEGACY_JTI_FREE", raising=False)

    tok = create_access_token({"sub": str(uuid.uuid4())})
    decoded = auth_utils.decode_access_token(tok)
    assert "jti" in decoded
    assert decoded["sub"]


def test_create_access_token_always_embeds_jti():
    """Pin the invariant that every token we mint has a jti. Without
    this invariant, #1069 would re-open: our own logout flow could
    mint a token that our own revocation check then refuses to
    revoke."""
    from services.admin.app.auth_utils import create_access_token

    for _ in range(5):
        tok = create_access_token({"sub": str(uuid.uuid4())})
        payload = pyjwt.decode(tok, options={"verify_signature": False})
        assert payload.get("jti"), "every token must embed a jti (#1069)"
