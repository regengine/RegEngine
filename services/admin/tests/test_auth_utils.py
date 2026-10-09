"""Focused coverage for ``app.auth_utils`` — session JWT mint/decode plus helpers.

No test file named for this module existed on origin/main; nearby suites
(test_require_jti_claim, test_check_revoked_async, test_jwt_kid_rotation_*)
pin slices of it from other angles, but nothing exercises the main public
surface (mint/decode roundtrip, audience separation, expiry handling,
refresh-token helpers, revocation-key shape, key-registry sync) in one place.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import jwt as pyjwt
import pytest
from app import auth_utils
from app.auth_runtime import AuthRuntimeConfigurationError


@pytest.fixture
def clean_auth_state(monkeypatch):
    """Isolate module-global crypto state so tests never leak into each other."""
    monkeypatch.setattr(auth_utils, "_active_kid", None)
    monkeypatch.setattr(auth_utils, "_active_secret", None)
    monkeypatch.setattr(auth_utils, "_verification_keys", {})
    monkeypatch.setattr(auth_utils, "_revoked_jtis", set())
    monkeypatch.setattr(auth_utils, "_revocation_redis", None)
    monkeypatch.setenv("REGENGINE_ENV", "test")
    monkeypatch.delenv("AUTH_ALLOW_LEGACY_JTI_FREE", raising=False)
    return auth_utils


def _mint(**claims):
    """Mint a token signed with the module SECRET_KEY, bypassing create_access_token."""
    payload = {
        "sub": f"user-{uuid.uuid4()}",
        "jti": f"jti-{uuid.uuid4()}",
        "aud": auth_utils.SESSION_AUDIENCE,
        "iss": auth_utils.SESSION_ISSUER,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    payload.update(claims)
    return pyjwt.encode(payload, auth_utils.SECRET_KEY, algorithm=auth_utils.ALGORITHM)


# ─────────────────────────────────────────────────────────────────────
# create_access_token / decode_access_token roundtrip
# ─────────────────────────────────────────────────────────────────────


def test_roundtrip_carries_claims_and_session_domain(clean_auth_state):
    token = auth_utils.create_access_token({"sub": "user-1", "tenant_id": "t-1"})

    decoded = auth_utils.decode_access_token(token)

    assert decoded["sub"] == "user-1"
    assert decoded["tenant_id"] == "t-1"
    assert decoded["jti"], "every minted token must carry a revocable jti"
    assert decoded["aud"] == auth_utils.SESSION_AUDIENCE
    assert decoded["iss"] == auth_utils.SESSION_ISSUER
    assert decoded["exp"] > datetime.now(timezone.utc).timestamp()


def test_create_preserves_caller_supplied_jti(clean_auth_state):
    token = auth_utils.create_access_token({"sub": "user-1", "jti": "caller-jti-1"})

    assert auth_utils.decode_access_token(token)["jti"] == "caller-jti-1"


def test_create_custom_expiry_delta_sets_exp(clean_auth_state):
    before = datetime.now(timezone.utc)

    token = auth_utils.create_access_token({"sub": "user-1"}, expires_delta=timedelta(minutes=10))

    exp = auth_utils.decode_access_token(token)["exp"]
    expected = (before + timedelta(minutes=10)).timestamp()
    assert abs(exp - expected) < 60


def test_create_rejects_non_positive_expiry_delta(clean_auth_state):
    with pytest.raises(AuthRuntimeConfigurationError):
        auth_utils.create_access_token({"sub": "user-1"}, expires_delta=timedelta(seconds=0))
    with pytest.raises(AuthRuntimeConfigurationError):
        auth_utils.create_access_token({"sub": "user-1"}, expires_delta=timedelta(minutes=-1))


# ─────────────────────────────────────────────────────────────────────
# decode_access_token — error cases
# ─────────────────────────────────────────────────────────────────────


def test_decode_rejects_tampered_token(clean_auth_state):
    token = auth_utils.create_access_token({"sub": "user-1"})
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")

    with pytest.raises(pyjwt.exceptions.InvalidTokenError):
        auth_utils.decode_access_token(tampered)


def test_decode_rejects_malformed_token(clean_auth_state):
    with pytest.raises(pyjwt.exceptions.InvalidTokenError):
        auth_utils.decode_access_token("not-a-token")


def test_decode_rejects_expired_token(clean_auth_state):
    expired = _mint(exp=datetime.now(timezone.utc) - timedelta(minutes=1))

    with pytest.raises(pyjwt.exceptions.ExpiredSignatureError):
        auth_utils.decode_access_token(expired)


def test_decode_rejects_wrong_audience_token(clean_auth_state):
    """A token minted for another domain (e.g. tool access) must not pass
    as a session token even when its signature verifies."""
    foreign = _mint(aud=auth_utils.TOOL_ACCESS_AUDIENCE)

    with pytest.raises(pyjwt.exceptions.InvalidAudienceError):
        auth_utils.decode_access_token(foreign)


# ─────────────────────────────────────────────────────────────────────
# revocation — local path
# ─────────────────────────────────────────────────────────────────────


async def test_revoke_then_decode_rejects_token(clean_auth_state):
    token = auth_utils.create_access_token({"sub": "user-1"})
    jti = auth_utils.decode_access_token(token)["jti"]

    await auth_utils.revoke_token(jti)
    assert await auth_utils.check_revoked_async(jti) is True

    with pytest.raises(pyjwt.exceptions.InvalidTokenError, match="revoked"):
        auth_utils.decode_access_token(token)


async def test_check_revoked_async_false_for_unknown_jti_without_redis(clean_auth_state):
    assert await auth_utils.check_revoked_async(f"jti-{uuid.uuid4()}") is False


async def test_revoke_clamps_zero_ttl_to_one_second(clean_auth_state, monkeypatch):
    redis_mock = MagicMock()
    redis_mock.eval = AsyncMock(return_value=1)
    redis_mock.get = AsyncMock(return_value=None)
    monkeypatch.setattr(clean_auth_state, "_revocation_redis", redis_mock)
    jti = f"jti-{uuid.uuid4()}"

    await auth_utils.revoke_token(jti, ttl_seconds=0)

    assert jti in clean_auth_state._revoked_jtis
    redis_mock.eval.assert_awaited_once()
    requested_ttl = redis_mock.eval.await_args.args[3]
    assert requested_ttl == 1


# ─────────────────────────────────────────────────────────────────────
# helpers — revocation keys, refresh tokens, hashing, redis wiring
# ─────────────────────────────────────────────────────────────────────


def test_revocation_key_is_fixed_width_hash_that_hides_jti():
    jti = f"jti-{uuid.uuid4()}"

    key = auth_utils._revocation_key(jti)

    assert key == f"regengine:jwt:revoked:{sha256(jti.encode()).hexdigest()}"
    assert jti not in key
    assert len(key.split(":")[-1]) == 64
    assert auth_utils._revocation_key(jti) == key
    assert auth_utils._revocation_key(f"jti-{uuid.uuid4()}") != key


def test_refresh_tokens_are_unique_and_hash_is_stable_sha256():
    first = auth_utils.create_refresh_token()
    second = auth_utils.create_refresh_token()

    assert first and second and first != second
    assert auth_utils.hash_token(first) == sha256(first.encode()).hexdigest()
    assert len(auth_utils.hash_token(first)) == 64
    assert auth_utils.hash_token(first) != auth_utils.hash_token(second)


def test_set_revocation_redis_wires_client(clean_auth_state):
    client = object()

    auth_utils.set_revocation_redis(client)

    assert auth_utils._revocation_redis is client


# ─────────────────────────────────────────────────────────────────────
# key-registry sync — kid path
# ─────────────────────────────────────────────────────────────────────


def test_sync_keys_from_registry_routes_signing_and_verification(clean_auth_state):
    signing = SimpleNamespace(kid="kid-new", secret="secret-new")
    old = SimpleNamespace(kid="kid-old", secret="secret-old")

    auth_utils._sync_keys_from_registry(signing, [old, signing])

    assert auth_utils._active_kid == "kid-new"
    assert auth_utils._active_secret == "secret-new"
    assert auth_utils._verification_keys == {"kid-old": "secret-old", "kid-new": "secret-new"}

    token = auth_utils.create_access_token({"sub": "user-1"})
    assert pyjwt.get_unverified_header(token)["kid"] == "kid-new"
    assert auth_utils.decode_access_token(token)["sub"] == "user-1"


def test_decode_rejects_unknown_kid(clean_auth_state):
    signing = SimpleNamespace(kid="kid-new", secret="secret-new")
    auth_utils._sync_keys_from_registry(signing, [signing])

    forged = pyjwt.encode(
        {
            "sub": "user-1",
            "jti": f"jti-{uuid.uuid4()}",
            "aud": auth_utils.SESSION_AUDIENCE,
            "iss": auth_utils.SESSION_ISSUER,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        "some-other-secret",
        algorithm=auth_utils.ALGORITHM,
        headers={"kid": "kid-unknown"},
    )

    with pytest.raises(pyjwt.exceptions.InvalidSignatureError):
        auth_utils.decode_access_token(forged)
