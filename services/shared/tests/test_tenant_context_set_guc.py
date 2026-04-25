"""Unit tests for ``set_tenant_guc`` and ``apply_tenant_context``.

These are the canonical primitives added in Phase B of the
tenant-isolation convergence plan. They will replace the 8+ ad-hoc
``SET LOCAL app.tenant_id`` call sites scattered across services in
follow-up sprints.

Coverage:
  - ``set_tenant_guc`` issues exactly one ``SET LOCAL`` with the right
    binding when given a valid UUID
  - Validates the UUID client-side BEFORE executing any SQL — bad input
    raises ``ValueError`` and never touches the session
  - ``apply_tenant_context`` accepts a ``TenantContext`` and forwards
    its ``tenant_id`` to ``set_tenant_guc``
  - Calling twice in the same transaction is fine (the underlying
    ``SET LOCAL`` is idempotent at the DB layer; we just re-execute)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, List, Tuple

import pytest

# Repo root on sys.path so ``services.shared.tenant_context`` resolves
# without depending on the parent test harness's pythonpath. Same
# pattern as the sibling ``test_tenant_context.py``.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.shared.tenant_context import (  # noqa: E402
    TenantContext,
    apply_tenant_context,
    set_tenant_guc,
)


# ---------------------------------------------------------------------------
# Recording fake session
# ---------------------------------------------------------------------------

class _RecordingSession:
    """Minimal SQLAlchemy-session-like object that records every
    ``execute()`` call so tests can assert exact bindings.

    Captures the rendered SQL string of the ``text()`` clause and the
    params dict separately; that's enough to verify the helper does
    what it claims without needing a real DB.
    """

    def __init__(self) -> None:
        self.calls: List[Tuple[str, dict]] = []

    def execute(self, stmt: Any, params: dict) -> None:
        self.calls.append((str(stmt), params))


# ---------------------------------------------------------------------------
# set_tenant_guc — happy path
# ---------------------------------------------------------------------------

class TestSetTenantGucHappy:

    def test_issues_set_local_with_correct_binding(self):
        session = _RecordingSession()
        tid = "11111111-1111-1111-1111-111111111111"

        set_tenant_guc(session, tid)

        assert len(session.calls) == 1
        sql, params = session.calls[0]
        assert "SET LOCAL app.tenant_id" in sql
        assert params == {"tid": tid}

    def test_uses_set_local_not_set_session(self):
        """Transaction-scoped scope is load-bearing — pool-bleed safety
        relies on the GUC auto-resetting at COMMIT/ROLLBACK. The legacy
        V3 SQL function used ``set_config(..., FALSE)`` which is
        session-scoped; that pattern is dangerous under pool reuse and
        must not be reintroduced via this helper."""
        session = _RecordingSession()
        set_tenant_guc(session, "22222222-2222-2222-2222-222222222222")
        sql = session.calls[0][0]
        assert "SET LOCAL" in sql
        assert "set_config" not in sql

    def test_calling_twice_in_same_transaction_is_fine(self):
        """Idempotent at the call site — handlers that re-resolve
        context (e.g. after a savepoint rollback) can re-set the GUC
        without special handling."""
        session = _RecordingSession()
        set_tenant_guc(session, "11111111-1111-1111-1111-111111111111")
        set_tenant_guc(session, "22222222-2222-2222-2222-222222222222")
        assert len(session.calls) == 2
        assert session.calls[0][1]["tid"] == "11111111-1111-1111-1111-111111111111"
        assert session.calls[1][1]["tid"] == "22222222-2222-2222-2222-222222222222"


# ---------------------------------------------------------------------------
# set_tenant_guc — validation
# ---------------------------------------------------------------------------

class TestSetTenantGucValidation:
    """Bad input must raise ``ValueError`` BEFORE issuing any SQL.

    The bind is parameterized so SQL injection is impossible regardless
    of input shape — but a non-UUID string would silently break RLS
    (Postgres GUC stores any text) without raising. We validate up
    front so the failure is loud.
    """

    def test_empty_string_rejected(self):
        session = _RecordingSession()
        with pytest.raises(ValueError, match="non-empty"):
            set_tenant_guc(session, "")
        assert session.calls == []

    def test_none_rejected(self):
        session = _RecordingSession()
        with pytest.raises(ValueError, match="non-empty"):
            set_tenant_guc(session, None)  # type: ignore[arg-type]
        assert session.calls == []

    def test_non_string_rejected(self):
        session = _RecordingSession()
        with pytest.raises(ValueError, match="non-empty"):
            set_tenant_guc(session, 12345)  # type: ignore[arg-type]
        assert session.calls == []

    @pytest.mark.parametrize("bad", [
        "not-a-uuid",
        "11111111-1111-1111-1111-",  # truncated
        "1111111111111111111111111111111111",  # no dashes, wrong length
        "0xdeadbeef",
        "00000000-0000-0000-0000-00000000000g",  # non-hex char
    ])
    def test_non_uuid_rejected(self, bad: str):
        session = _RecordingSession()
        with pytest.raises(ValueError, match="not a valid UUID"):
            set_tenant_guc(session, bad)
        assert session.calls == [], (
            "validation must reject before any SQL runs — bad inputs that "
            "leak through to the bind layer would silently set a non-UUID "
            "GUC and break RLS comparisons against get_tenant_context()"
        )

    def test_uuid_with_uppercase_accepted(self):
        """Postgres normalizes UUID case; both forms are valid input."""
        session = _RecordingSession()
        set_tenant_guc(session, "11111111-AAAA-1111-1111-111111111111")
        assert len(session.calls) == 1


# ---------------------------------------------------------------------------
# apply_tenant_context — convenience wrapper
# ---------------------------------------------------------------------------

class TestApplyTenantContext:

    def test_forwards_tenant_id_from_context(self):
        session = _RecordingSession()
        ctx = TenantContext(
            tenant_id="33333333-3333-3333-3333-333333333333",
            principal_kind="api_key",
            principal_id="key-abc",
            actor_email=None,
        )

        apply_tenant_context(session, ctx)

        assert len(session.calls) == 1
        assert session.calls[0][1]["tid"] == ctx.tenant_id

    def test_invalid_tenant_id_in_context_still_validates(self):
        """If the resolver somehow produced a TenantContext with an
        invalid tenant_id (it shouldn't — there's no path that allows
        it — but defense-in-depth), the helper still rejects rather
        than passing garbage to the GUC."""
        session = _RecordingSession()
        ctx = TenantContext(
            tenant_id="garbage",
            principal_kind="api_key",
            principal_id="key-abc",
            actor_email=None,
        )
        with pytest.raises(ValueError, match="not a valid UUID"):
            apply_tenant_context(session, ctx)
        assert session.calls == []
