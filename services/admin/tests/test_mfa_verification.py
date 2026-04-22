"""Tests for MFA cryptographic verification (issue #1036).

Proves that require_mfa rejects arbitrary 6-digit tokens and validates
TOTP codes against the user's enrolled secret, and that recovery codes
are verified against stored hashes and consumed after use.
"""

import sys
import types as _types
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# Stub pyotp before importing mfa module (pyotp may not be installed locally)
if "pyotp" not in sys.modules:

    class _FakeTOTP:
        def __init__(self, secret):
            self._secret = secret

        def verify(self, token, valid_window=1):
            return token == "999111"

        def provisioning_uri(self, name=None, issuer_name=None):
            return f"otpauth://totp/{issuer_name}:{name}?secret={self._secret}"

    _pyotp_stub = _types.ModuleType("pyotp")
    _pyotp_stub.TOTP = _FakeTOTP
    _pyotp_stub.random_base32 = lambda: "JBSWY3DPEHPK3PXP"
    sys.modules["pyotp"] = _pyotp_stub

from services.admin.app.mfa import (  # noqa: E402
    hash_recovery_code,
    require_mfa,
)
from services.admin.app.sqlalchemy_models import MFARecoveryCodeModel  # noqa: E402


class _FakeRedisPipeline:
    def __init__(self, client):
        self._client = client
        self._ops = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def incr(self, key):
        self._ops.append(("incr", key))

    def expire(self, key, ttl):
        self._ops.append(("expire", key, ttl))

    async def execute(self):
        count = None
        for operation in self._ops:
            op_type = operation[0]
            if op_type == "incr":
                key = operation[1]
                count = self._client._counts.get(key, 0) + 1
                self._client._counts[key] = count
            elif op_type == "expire":
                _, key, ttl = operation
                self._client._ttls[key] = ttl
        return [count or 0, True]


class _FakeRedisClient:
    def __init__(self):
        self._counts = {}
        self._ttls = {}
        self._values = {}

    async def get(self, key):
        value = self._counts.get(key)
        return str(value) if value is not None else None

    async def ttl(self, key):
        return self._ttls.get(key, -2)

    async def setex(self, key, ttl, value):
        self._ttls[key] = ttl
        self._values[key] = value

    async def set(self, key, value, ex=None, nx=False):
        if nx and (key in self._values or key in self._counts):
            return None
        self._values[key] = value
        if ex is not None:
            self._ttls[key] = ex
        return True

    async def delete(self, *keys):
        for key in keys:
            self._counts.pop(key, None)
            self._ttls.pop(key, None)
            self._values.pop(key, None)

    def pipeline(self, transaction=False):
        return _FakeRedisPipeline(self)


def _make_session_store():
    client = _FakeRedisClient()

    async def _get_client():
        return client

    return SimpleNamespace(_get_client=_get_client), client


def _make_user(mfa_secret="TESTBASE32SECRET", user_id=None):
    """Create a fake UserModel-like object."""
    return SimpleNamespace(
        id=user_id or uuid.uuid4(),
        email="test@example.com",
        mfa_secret=mfa_secret,
    )


# ── TOTP tests ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rejects_missing_token():
    """Missing X-MFA-Token header → 403."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await require_mfa(x_mfa_token=None, current_user=_make_user(), db=MagicMock())
    assert exc_info.value.status_code == 403
    assert "MFA token required" in exc_info.value.detail


@pytest.mark.asyncio
async def test_rejects_user_without_mfa_enrolled():
    """User has no mfa_secret → 403."""
    from fastapi import HTTPException

    user = _make_user(mfa_secret=None)
    with pytest.raises(HTTPException) as exc_info:
        await require_mfa(x_mfa_token="123456", current_user=user, db=MagicMock())
    assert exc_info.value.status_code == 403
    assert "MFA not enrolled" in exc_info.value.detail


@pytest.mark.asyncio
async def test_rejects_arbitrary_six_digit_token():
    """The old bug: '123456' matched format but was never verified. Must fail now."""
    from fastapi import HTTPException

    user = _make_user()
    session_store, _ = _make_session_store()
    with pytest.raises(HTTPException) as exc_info:
        await require_mfa(
            x_mfa_token="123456",
            current_user=user,
            db=MagicMock(),
            session_store=session_store,
        )
    assert exc_info.value.status_code == 403
    assert "Invalid MFA token" in exc_info.value.detail


@pytest.mark.asyncio
async def test_accepts_valid_totp_token():
    """A token that pyotp.TOTP.verify() accepts should pass."""
    user = _make_user()
    session_store, _ = _make_session_store()
    result = await require_mfa(
        x_mfa_token="999111",
        current_user=user,
        db=MagicMock(),
        session_store=session_store,
    )
    assert result == "999111"


@pytest.mark.asyncio
async def test_rejects_bad_format():
    """Tokens that are neither 6-digit nor XXXX-XXXX → 403."""
    from fastapi import HTTPException

    user = _make_user()
    session_store, _ = _make_session_store()
    with pytest.raises(HTTPException) as exc_info:
        await require_mfa(
            x_mfa_token="bad",
            current_user=user,
            db=MagicMock(),
            session_store=session_store,
        )
    assert exc_info.value.status_code == 403
    assert "Invalid MFA token format" in exc_info.value.detail


# ── Recovery code tests ─────────────────────────────────────


@pytest.mark.asyncio
async def test_rejects_invalid_recovery_code():
    """Recovery code not in DB → 403."""
    from fastapi import HTTPException

    user = _make_user()
    session_store, _ = _make_session_store()
    db = MagicMock()
    # No unused rows in DB — empty list means no match
    db.execute.return_value.scalars.return_value.all.return_value = []

    with pytest.raises(HTTPException) as exc_info:
        await require_mfa(
            x_mfa_token="ABCD-EFGH",
            current_user=user,
            db=db,
            session_store=session_store,
        )
    assert exc_info.value.status_code == 403
    assert "Invalid MFA token" in exc_info.value.detail


@pytest.mark.asyncio
async def test_accepts_valid_recovery_code_and_marks_used():
    """Valid recovery code is accepted and its used_at is set.

    Updated for #1041: argon2 hashes are salted, so the DB lookup now fetches
    all unused rows and calls verify_recovery_code on each. The mock must
    return a list of candidate rows with a real argon2 hash so verification
    can succeed.
    """
    from services.admin.app.mfa import hash_recovery_code

    user = _make_user()
    session_store, _ = _make_session_store()

    recovery_row = MagicMock()
    recovery_row.used_at = None
    # Pre-hash the code with argon2 so verify_recovery_code can verify it
    recovery_row.code_hash = hash_recovery_code("ABCD-EFGH")

    db = MagicMock()
    # New query pattern: .scalars().all() returns a list of candidate rows
    db.execute.return_value.scalars.return_value.all.return_value = [recovery_row]

    result = await require_mfa(
        x_mfa_token="ABCD-EFGH",
        current_user=user,
        db=db,
        session_store=session_store,
    )
    assert result == "ABCD-EFGH"
    assert recovery_row.used_at is not None
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_already_used_recovery_code_rejected():
    """A recovery code whose used_at is set should not match (filtered by query)."""
    from fastapi import HTTPException

    user = _make_user()
    session_store, _ = _make_session_store()
    db = MagicMock()
    # Query filters used_at.is_(None), so already-used codes are excluded → empty list
    db.execute.return_value.scalars.return_value.all.return_value = []

    with pytest.raises(HTTPException) as exc_info:
        await require_mfa(
            x_mfa_token="ABCD-EFGH",
            current_user=user,
            db=db,
            session_store=session_store,
        )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_rejects_totp_replay_within_window():
    """A TOTP already seen in the replay cache must be rejected."""
    from fastapi import HTTPException

    user = _make_user()
    session_store, _ = _make_session_store()
    db = MagicMock()

    first = await require_mfa(
        x_mfa_token="999111",
        current_user=user,
        db=db,
        session_store=session_store,
    )
    assert first == "999111"

    with pytest.raises(HTTPException) as exc_info:
        await require_mfa(
            x_mfa_token="999111",
            current_user=user,
            db=db,
            session_store=session_store,
        )
    assert exc_info.value.status_code == 403
    assert "Invalid MFA token" in exc_info.value.detail


@pytest.mark.asyncio
async def test_emits_failed_mfa_audit_and_tracks_lockout_attempt():
    """Failed MFA verification emits audit hook and increments lockout state."""
    from fastapi import HTTPException
    from services.admin.app import mfa as mfa_module

    user = _make_user()
    session_store, redis_client = _make_session_store()
    db = MagicMock()

    with pytest.MonkeyPatch.context() as monkeypatch:
        audit_spy = MagicMock()
        monkeypatch.setattr(mfa_module, "_emit_mfa_verification_failed_audit", audit_spy)
        with pytest.raises(HTTPException):
            await require_mfa(
                x_mfa_token="123456",
                current_user=user,
                db=db,
                session_store=session_store,
            )

    audit_spy.assert_called_once()
    assert redis_client._counts, "failed MFA should increment lockout counter"


@pytest.mark.asyncio
async def test_mfa_lockout_enforced_with_retry_after():
    """Reached threshold should block MFA verification with 423 + Retry-After."""
    from fastapi import HTTPException
    from services.admin.app import mfa as mfa_module

    user = _make_user()
    session_store, redis_client = _make_session_store()
    subject_key = mfa_module._mfa_subject_key(user)
    redis_client._counts[mfa_module._mfa_lockout_key(subject_key)] = mfa_module._MFA_LOCKOUT_THRESHOLD

    with pytest.raises(HTTPException) as exc_info:
        await require_mfa(
            x_mfa_token="999111",
            current_user=user,
            db=MagicMock(),
            session_store=session_store,
        )

    assert exc_info.value.status_code == 423
    assert exc_info.value.headers["Retry-After"] == str(mfa_module._MFA_LOCKOUT_DURATION)
