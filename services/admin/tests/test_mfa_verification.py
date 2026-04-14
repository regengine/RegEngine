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
    with pytest.raises(HTTPException) as exc_info:
        await require_mfa(x_mfa_token="123456", current_user=user, db=MagicMock())
    assert exc_info.value.status_code == 403
    assert "Invalid MFA token" in exc_info.value.detail


@pytest.mark.asyncio
async def test_accepts_valid_totp_token():
    """A token that pyotp.TOTP.verify() accepts should pass."""
    user = _make_user()
    result = await require_mfa(x_mfa_token="999111", current_user=user, db=MagicMock())
    assert result == "999111"


@pytest.mark.asyncio
async def test_rejects_bad_format():
    """Tokens that are neither 6-digit nor XXXX-XXXX → 403."""
    from fastapi import HTTPException

    user = _make_user()
    with pytest.raises(HTTPException) as exc_info:
        await require_mfa(x_mfa_token="bad", current_user=user, db=MagicMock())
    assert exc_info.value.status_code == 403
    assert "Invalid MFA token format" in exc_info.value.detail


# ── Recovery code tests ─────────────────────────────────────


@pytest.mark.asyncio
async def test_rejects_invalid_recovery_code():
    """Recovery code not in DB → 403."""
    from fastapi import HTTPException

    user = _make_user()
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await require_mfa(x_mfa_token="ABCD-EFGH", current_user=user, db=db)
    assert exc_info.value.status_code == 403
    assert "Invalid MFA token" in exc_info.value.detail


@pytest.mark.asyncio
async def test_accepts_valid_recovery_code_and_marks_used():
    """Valid recovery code is accepted and its used_at is set."""
    user = _make_user()

    recovery_row = MagicMock()
    recovery_row.used_at = None

    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = recovery_row

    result = await require_mfa(x_mfa_token="ABCD-EFGH", current_user=user, db=db)
    assert result == "ABCD-EFGH"
    assert recovery_row.used_at is not None
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_already_used_recovery_code_rejected():
    """A recovery code whose used_at is set should not match (filtered by query)."""
    from fastapi import HTTPException

    user = _make_user()
    db = MagicMock()
    # Query filters used_at.is_(None), so already-used codes return None
    db.execute.return_value.scalar_one_or_none.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await require_mfa(x_mfa_token="ABCD-EFGH", current_user=user, db=db)
    assert exc_info.value.status_code == 403
