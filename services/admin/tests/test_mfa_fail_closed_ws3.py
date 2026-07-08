"""MFA throttle backend outage must fail closed (remediation plan WS-3).

The lockout / replay guards in ``require_mfa`` are load-bearing brute-force
controls. A Redis outage previously either surfaced as an unhandled 500 (live
path) or was swallowed entirely (the dormant ``*_mfa_counter_*`` helpers,
fail-open). These tests pin the corrected contract:

- backend errors during the lockout check, failure recording, or TOTP replay
  guard reject the attempt with a retryable 503 — verification never proceeds
  with brute-force protection silently disabled;
- backend errors while *clearing* throttle state after a successful
  verification are non-fatal (stale counters err toward more lockout, and on
  the recovery path the one-time code is already consumed).
"""

import sys
import types as _types
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# Stub pyotp before importing mfa module (pyotp may not be installed locally).
# Mirrors services/admin/tests/test_mfa_verification.py.
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

from fastapi import HTTPException  # noqa: E402

from services.admin.app import mfa as mfa_module  # noqa: E402
from services.admin.app.mfa import hash_recovery_code, require_mfa  # noqa: E402


class _BrokenPipeline:
    def __init__(self, exc):
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def incr(self, key):
        pass

    def expire(self, key, ttl):
        pass

    async def execute(self):
        raise self._exc


class _SelectivelyBrokenClient:
    """Fake redis client where individual operations can be broken."""

    def __init__(self, broken_ops=()):
        self._broken_ops = set(broken_ops)
        self._values = {}
        self._ttls = {}

    def _maybe_break(self, op):
        if op in self._broken_ops:
            raise ConnectionError(f"redis unavailable during {op}")

    async def get(self, key):
        self._maybe_break("get")
        return self._values.get(key)

    async def ttl(self, key):
        self._maybe_break("ttl")
        return self._ttls.get(key, -2)

    async def set(self, key, value, ex=None, nx=False):
        self._maybe_break("set")
        if nx and key in self._values:
            return None
        self._values[key] = value
        return True

    async def setex(self, key, ttl, value):
        self._maybe_break("setex")
        self._values[key] = value
        self._ttls[key] = ttl

    async def incr(self, key):
        self._maybe_break("incr")
        value = int(self._values.get(key, 0)) + 1
        self._values[key] = value
        return value

    async def expire(self, key, ttl):
        self._maybe_break("expire")
        self._ttls[key] = ttl

    async def delete(self, *keys):
        self._maybe_break("delete")
        for key in keys:
            self._values.pop(key, None)
            self._ttls.pop(key, None)

    def pipeline(self, transaction=False):
        if "pipeline" in self._broken_ops:
            return _BrokenPipeline(ConnectionError("redis unavailable during pipeline"))
        raise AssertionError("unexpected pipeline use in this test")


def _store_for(client):
    async def _get_client():
        return client

    return SimpleNamespace(_get_client=_get_client)


def _dead_store():
    async def _get_client():
        raise ConnectionError("redis unavailable")

    return SimpleNamespace(_get_client=_get_client)


def _make_user():
    return SimpleNamespace(
        id=uuid.uuid4(),
        email="test@example.com",
        mfa_secret="TESTBASE32SECRET",  # pragma: allowlist secret
    )


@pytest.mark.asyncio
async def test_lockout_check_backend_outage_fails_closed_503():
    """Redis fully down → 503 before any token verification, never fail-open."""
    with pytest.raises(HTTPException) as exc_info:
        await require_mfa(
            x_mfa_token="999111",
            current_user=_make_user(),
            db=MagicMock(),
            session_store=_dead_store(),
        )
    assert exc_info.value.status_code == 503
    assert exc_info.value.headers.get("Retry-After")


@pytest.mark.asyncio
async def test_replay_guard_backend_outage_rejects_valid_totp_503():
    """Lockout check works, but the replay-guard SET fails → 503, not success."""
    client = _SelectivelyBrokenClient(broken_ops={"set"})
    with pytest.raises(HTTPException) as exc_info:
        await require_mfa(
            x_mfa_token="999111",
            current_user=_make_user(),
            db=MagicMock(),
            session_store=_store_for(client),
        )
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_failure_recording_backend_outage_yields_503():
    """An invalid token during a mid-request outage is still denied (503, not

    a silent uncounted 403)."""
    client = _SelectivelyBrokenClient(broken_ops={"pipeline"})
    with pytest.raises(HTTPException) as exc_info:
        await require_mfa(
            x_mfa_token="bad-format-token",
            current_user=_make_user(),
            db=MagicMock(),
            session_store=_store_for(client),
        )
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_clear_after_recovery_success_is_best_effort():
    """DELETE failing after a consumed recovery code must not fail the request."""
    client = _SelectivelyBrokenClient(broken_ops={"delete"})

    recovery_row = MagicMock()
    recovery_row.used_at = None
    recovery_row.code_hash = hash_recovery_code("ABCD-EFGH")

    db = MagicMock()
    select_result = MagicMock()
    select_result.scalars.return_value.all.return_value = [recovery_row]
    update_result = MagicMock()
    update_result.rowcount = 1
    db.execute.side_effect = [select_result, update_result]

    result = await require_mfa(
        x_mfa_token="ABCD-EFGH",
        current_user=_make_user(),
        db=db,
        session_store=_store_for(client),
    )
    assert result == "ABCD-EFGH"
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_clear_after_totp_success_is_best_effort():
    """DELETE failing after a valid, non-replayed TOTP must not fail the request."""
    client = _SelectivelyBrokenClient(broken_ops={"delete"})
    result = await require_mfa(
        x_mfa_token="999111",
        current_user=_make_user(),
        db=MagicMock(),
        session_store=_store_for(client),
    )
    assert result == "999111"


@pytest.mark.asyncio
async def test_dormant_counter_helpers_fail_closed():
    """The previously fail-open ``*_mfa_counter_*`` helpers now raise 503 on

    backend errors instead of silently disabling brute-force protection."""
    with pytest.raises(HTTPException) as exc_info:
        await mfa_module._check_mfa_counter_lockout(_dead_store(), "user-1")
    assert exc_info.value.status_code == 503

    with pytest.raises(HTTPException) as exc_info:
        await mfa_module._record_mfa_counter_failure(_dead_store(), "user-1")
    assert exc_info.value.status_code == 503

    # Reset stays best-effort: never raises.
    await mfa_module._reset_mfa_counter_failures(_dead_store(), "user-1")


@pytest.mark.asyncio
async def test_lockout_http_exceptions_pass_through_unchanged():
    """The 423/429 lockout responses must not be rewritten into 503s."""
    client = _SelectivelyBrokenClient()
    client._values[mfa_module._mfa_lockout_key("test@example.com")] = str(
        mfa_module._MFA_LOCKOUT_THRESHOLD
    )
    with pytest.raises(HTTPException) as exc_info:
        await require_mfa(
            x_mfa_token="999111",
            current_user=_make_user(),
            db=MagicMock(),
            session_store=_store_for(client),
        )
    assert exc_info.value.status_code == 423
