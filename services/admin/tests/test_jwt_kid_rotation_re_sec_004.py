"""RE-SEC-004 — JWT signing-key id ("kid") rotation, production path.

The end-to-end registry behaviour is covered in
``tests/shared/test_jwt_key_registry.py`` by exercising
``JWTKeyRegistry`` + raw ``jwt.encode``/``jwt.decode`` directly. Those
tests do NOT touch the code that actually runs in production:
``auth_utils.create_access_token`` (signing) and
``auth_utils.decode_access_token`` (verification), which read the
module-level key cache populated by ``_sync_keys_from_registry`` at
startup (see ``services/admin/main.py``).

This module pins that production path:

  * an issued token carries a ``kid`` header matching the active key,
  * verification selects the correct secret by ``kid`` from the
    multi-key cache (so a non-active-but-still-valid key still
    verifies — the grace-period guarantee), and
  * a token whose ``kid`` is not in the registry is rejected rather
    than silently falling back to another key.
"""
from __future__ import annotations

import jwt as pyjwt
import pytest

from services.admin.app import auth_utils
from shared.jwt_key_registry import SigningKey


@pytest.fixture
def clean_revocation(monkeypatch):
    """Isolate revocation state so jti checks don't interfere."""
    monkeypatch.setattr(auth_utils, "_revoked_jtis", {})
    yield


def _install_keys(monkeypatch, active: SigningKey, others: list[SigningKey] | None = None):
    """Mimic _sync_keys_from_registry without needing Redis."""
    verification = {active.kid: active.secret}
    for k in others or []:
        verification[k.kid] = k.secret
    monkeypatch.setattr(auth_utils, "_active_kid", active.kid)
    monkeypatch.setattr(auth_utils, "_active_secret", active.secret)
    monkeypatch.setattr(auth_utils, "_verification_keys", verification)


def test_issued_token_carries_active_kid(monkeypatch, clean_revocation):
    """create_access_token stamps the active key's kid in the JWT header."""
    active = SigningKey(kid="re-test-active", secret="active-secret-xyz")
    _install_keys(monkeypatch, active)

    token = auth_utils.create_access_token({"sub": "user-1", "tenant_id": "t-1"})

    header = pyjwt.get_unverified_header(token)
    assert header["kid"] == "re-test-active"


def test_verification_selects_key_by_kid(monkeypatch, clean_revocation):
    """A token signed by the active key verifies via kid lookup."""
    active = SigningKey(kid="re-test-active", secret="active-secret-xyz")
    _install_keys(monkeypatch, active)

    token = auth_utils.create_access_token({"sub": "user-1"})
    payload = auth_utils.decode_access_token(token)

    assert payload["sub"] == "user-1"


def test_token_from_retired_key_still_verifies_during_grace(monkeypatch, clean_revocation):
    """A token signed by a now-inactive (but still valid) key verifies
    by its own kid — the zero-downtime rotation guarantee."""
    old_key = SigningKey(kid="re-test-old", secret="old-secret-aaa")
    new_key = SigningKey(kid="re-test-new", secret="new-secret-bbb")

    # Sign a token while the OLD key was active.
    _install_keys(monkeypatch, old_key)
    old_token = auth_utils.create_access_token({"sub": "user-1"})

    # Rotate: new key is active, old key remains in the verification map.
    _install_keys(monkeypatch, new_key, others=[old_key])

    payload = auth_utils.decode_access_token(old_token)
    assert payload["sub"] == "user-1"


def test_unknown_kid_is_rejected(monkeypatch, clean_revocation):
    """A token whose kid is not in the registry must be rejected, not
    silently verified against another key."""
    active = SigningKey(kid="re-test-active", secret="active-secret-xyz")

    # Forge a token with a kid we do not know, signed by some other secret.
    # nosemgrep: python.jwt.security.jwt-hardcode.jwt-python-hardcoded-secret -- forged-token fixture; literal is the attacker's secret, never a real credential
    forged = pyjwt.encode(
        {
            "sub": "attacker",
            "aud": auth_utils.SESSION_AUDIENCE,
            "iss": auth_utils.SESSION_ISSUER,
            "jti": "forged-jti",
        },
        "attacker-secret",
        algorithm=auth_utils.ALGORITHM,
        headers={"kid": "re-not-in-registry"},
    )

    _install_keys(monkeypatch, active)

    with pytest.raises(pyjwt.exceptions.InvalidSignatureError) as excinfo:
        auth_utils.decode_access_token(forged)
    assert "re-not-in-registry" in str(excinfo.value)
