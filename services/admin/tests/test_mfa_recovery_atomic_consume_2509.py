"""Regression tests for atomic MFA recovery-code consumption — issue #2509.

The recovery-code redemption path consumed a one-time code with a non-atomic
read-then-write (SELECT unused codes, match in Python, set ``used_at`` and
commit). Two concurrent redemptions of the same valid code could both observe
``used_at IS NULL`` and both succeed, defeating the one-time-use invariant.

The fix consumes the code via a conditional ``UPDATE ... WHERE id = :id AND
used_at IS NULL`` and treats ``rowcount != 1`` as already-used. These tests run
against a real SQLite engine so the conditional-update / compare-and-set
semantics are actually exercised, not mocked.
"""

from __future__ import annotations

import asyncio
import sys
import types as _types
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

# Stub pyotp before importing the mfa module (pyotp may not be installed).
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

import inspect  # noqa: E402

from sqlalchemy import create_engine, select, update  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from services.admin.app.mfa import hash_recovery_code, require_mfa  # noqa: E402
from services.admin.app.sqlalchemy_models import MFARecoveryCodeModel  # noqa: E402

_USER_ID = uuid.uuid4()


def _make_user():
    return SimpleNamespace(id=_USER_ID, email="recovery@example.com", mfa_secret="TESTBASE32SECRET")


def _engine_with_one_code(code: str = "ABCD-EFGH"):
    """Create a shared in-memory SQLite engine seeded with one unused code."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    MFARecoveryCodeModel.__table__.create(engine)
    code_id = uuid.uuid4()
    Session = sessionmaker(bind=engine)
    with Session() as s:
        s.execute(
            MFARecoveryCodeModel.__table__.insert().values(
                id=code_id,
                user_id=_USER_ID,
                code_hash=hash_recovery_code(code),
                used_at=None,
                created_at=datetime.now(timezone.utc),
            )
        )
        s.commit()
    return engine, code_id, Session


def _unused_count(Session) -> int:
    with Session() as s:
        return len(
            s.execute(select(MFARecoveryCodeModel).where(MFARecoveryCodeModel.used_at.is_(None))).scalars().all()
        )


def test_interleaved_consume_only_one_update_flips_the_row():
    """Model the exact race the old read-then-write was vulnerable to.

    Two independent sessions both SELECT the row and both observe
    ``used_at IS NULL`` (the in-memory match the old code relied on). They then
    each attempt to consume it. With the fix this is a conditional
    ``UPDATE ... WHERE used_at IS NULL``: the first flips exactly one row
    (rowcount == 1, the winner) and the second flips zero (rowcount == 0,
    rejected as already-used). The old unconditional write would have let both
    "succeed", granting two sessions from one one-time code.
    """
    engine, code_id, Session = _engine_with_one_code()

    s1 = Session()
    s2 = Session()
    try:
        # Both readers see the code as unused — the interleave point.
        row1 = s1.execute(
            select(MFARecoveryCodeModel).where(
                MFARecoveryCodeModel.id == code_id,
                MFARecoveryCodeModel.used_at.is_(None),
            )
        ).scalar_one()
        row2 = s2.execute(
            select(MFARecoveryCodeModel).where(
                MFARecoveryCodeModel.id == code_id,
                MFARecoveryCodeModel.used_at.is_(None),
            )
        ).scalar_one()
        assert row1 is not None and row2 is not None

        def _consume(session) -> int:
            res = session.execute(
                update(MFARecoveryCodeModel)
                .where(
                    MFARecoveryCodeModel.id == code_id,
                    MFARecoveryCodeModel.used_at.is_(None),
                )
                .values(used_at=datetime.now(timezone.utc))
            )
            session.commit()
            return res.rowcount

        first_rowcount = _consume(s1)
        second_rowcount = _consume(s2)

        # Exactly one wins; the other is a no-op the consume path rejects.
        assert {first_rowcount, second_rowcount} == {0, 1}, (
            f"expected one winner and one no-op, got {first_rowcount} and {second_rowcount}"
        )
        assert _unused_count(Session) == 0
    finally:
        s1.close()
        s2.close()


@pytest.mark.asyncio
async def test_concurrent_redemptions_only_one_wins():
    """Two redemptions of the same code via require_mfa → exactly one succeeds.

    Each call uses its own session (mirroring the per-request session lifecycle).
    Even back-to-back, the second redemption must be rejected because the
    conditional UPDATE finds no unused row to flip.
    """
    from fastapi import HTTPException

    engine, _code_id, Session = _engine_with_one_code()

    async def _attempt():
        db = Session()
        try:
            return await require_mfa(
                x_mfa_token="ABCD-EFGH",
                current_user=_make_user(),
                db=db,
                session_store=None,
            )
        except HTTPException as exc:
            return exc
        finally:
            db.close()

    results = await asyncio.gather(_attempt(), _attempt())

    successes = [r for r in results if r == "ABCD-EFGH"]
    failures = [r for r in results if isinstance(r, HTTPException)]
    assert len(successes) == 1, f"expected exactly one success, got {results!r}"
    assert len(failures) == 1, f"expected exactly one rejection, got {results!r}"
    assert failures[0].status_code == 403
    # The code is fully consumed — no unused rows remain.
    assert _unused_count(Session) == 0


@pytest.mark.asyncio
async def test_sequential_reuse_is_rejected():
    """A second redemption of an already-used code is rejected (single-use)."""
    from fastapi import HTTPException

    engine, _code_id, Session = _engine_with_one_code()

    db1 = Session()
    try:
        first = await require_mfa(
            x_mfa_token="ABCD-EFGH",
            current_user=_make_user(),
            db=db1,
            session_store=None,
        )
    finally:
        db1.close()
    assert first == "ABCD-EFGH"

    db2 = Session()
    try:
        with pytest.raises(HTTPException) as exc_info:
            await require_mfa(
                x_mfa_token="ABCD-EFGH",
                current_user=_make_user(),
                db=db2,
                session_store=None,
            )
    finally:
        db2.close()
    assert exc_info.value.status_code == 403


def test_consume_path_uses_conditional_update_not_unlocked_write():
    """Source-level guard: the consume must be a conditional UPDATE keyed on
    ``used_at IS NULL`` with a rowcount check, not an unconditional ORM write."""
    source = inspect.getsource(require_mfa)
    assert "update(MFARecoveryCodeModel)" in source, "consume no longer uses a conditional UPDATE"
    assert ".rowcount" in source, "consume no longer checks the affected rowcount"
    # The old read-then-write assigned the ORM attribute directly. Ensure that
    # racy pattern is gone.
    assert "recovery.used_at =" not in source, "consume still relies on an unconditional in-memory write"
