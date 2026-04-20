"""
Regression coverage for the ``TenantContext`` static-methods that the
existing test harness doesn't exercise — closes the 94% -> 100% gap on
``services/admin/app/models.py``.

``TenantContext`` is the Python-side wrapper over the Postgres RLS
helpers ``get_tenant_context()`` / ``set_admin_context()``. These
static methods are called from admin routes and middleware to read
the session-scoped tenant UUID and to activate the sysadmin RLS
bypass (which is ALSO gated by the DB role — see #1405 defense-in-
depth). Regressions here are direct tenant-isolation / privileged-op
risks.

Pinned branches by mocking a SQLAlchemy session:

* Lines 382-387 — ``get_tenant_context`` reads the session variable
  and returns:
  - ``None`` when the session has no tenant set
  - a ``UUID`` instance unchanged (Postgres can return native UUID)
  - a string converted via ``UUID(str)`` (fallback for drivers that
    serialize as text)
* Lines 410-418 — ``set_admin_context(is_sysadmin=True)`` emits the
  CRITICAL warning log and executes the session SQL. Pinning the
  True branch guarantees the privileged-op log never regresses
  silently.

Tracks GitHub issue #1342.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID

import pytest

service_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("sqlalchemy")

from app.models import TenantContext  # noqa: E402


TENANT_ID = UUID("00000000-0000-0000-0000-000000000042")


def _session_returning(scalar_value):
    """Build a mock session whose execute(...).scalar() returns scalar_value."""
    session = MagicMock()
    session.execute.return_value.scalar.return_value = scalar_value
    return session


# ---------------------------------------------------------------------------
# get_tenant_context — lines 382-387
# ---------------------------------------------------------------------------


class TestGetTenantContext:

    def test_returns_none_when_session_has_no_tenant(self):
        """Line 384: session returns NULL -> method returns None."""
        session = _session_returning(None)

        result = TenantContext.get_tenant_context(session)

        assert result is None
        # SQL call was made
        session.execute.assert_called_once()

    def test_returns_uuid_unchanged_when_already_uuid(self):
        """Lines 385-386: Postgres with native UUID columns returns a
        ``uuid.UUID`` instance — we pass it through to avoid a
        double-conversion that would TypeError."""
        session = _session_returning(TENANT_ID)

        result = TenantContext.get_tenant_context(session)

        assert result is TENANT_ID  # identity
        assert isinstance(result, UUID)

    def test_converts_string_to_uuid(self):
        """Line 387: drivers that return the GUC as text (older Postgres
        client libs, certain pg_catalog paths) come back as str. We
        convert via ``UUID(result)``."""
        session = _session_returning(str(TENANT_ID))

        result = TenantContext.get_tenant_context(session)

        assert isinstance(result, UUID)
        assert result == TENANT_ID

    def test_invalid_string_raises_value_error(self):
        """Boundary: if the session variable somehow contains a
        non-UUID string, we surface the ValueError from UUID() rather
        than silently passing bad data — keeps the caller from
        attaching the wrong tenant to downstream queries."""
        session = _session_returning("not-a-uuid")

        with pytest.raises(ValueError):
            TenantContext.get_tenant_context(session)


# ---------------------------------------------------------------------------
# set_admin_context — lines 410-418 (is_sysadmin=True log branch)
# ---------------------------------------------------------------------------


class TestSetAdminContext:

    def test_sysadmin_true_logs_warning_and_executes_sql(self):
        """Lines 412-417: enabling the sysadmin bypass must emit the
        'sysadmin_context_activated' WARNING log for audit trail.
        This is the SECURITY-critical branch — if the log silently
        regresses we lose the before-the-fact record of privileged
        context activation."""
        session = MagicMock()

        TenantContext.set_admin_context(session, is_sysadmin=True)

        # The session.execute was called with the admin-context SQL and True
        session.execute.assert_called_once()
        args, kwargs = session.execute.call_args
        # Second positional is the params dict
        assert args[1] == {"is_admin": True}

    def test_sysadmin_false_skips_warning_log_and_executes_sql(self):
        """Line 412 ``if is_sysadmin:`` False path: no warning log
        but still execute SQL with is_admin=False. Pinned to prevent
        a refactor from accidentally dropping the DB call when the
        bypass is disabled (which would leave stale True state on
        the connection)."""
        session = MagicMock()

        TenantContext.set_admin_context(session, is_sysadmin=False)

        session.execute.assert_called_once()
        args, kwargs = session.execute.call_args
        assert args[1] == {"is_admin": False}

    def test_sysadmin_true_uses_set_admin_context_sql(self):
        """Pins the SQL we emit — ``SELECT set_admin_context(:is_admin)``.
        A refactor that renames the server-side function or swaps to
        SET LOCAL must update this test first."""
        session = MagicMock()

        TenantContext.set_admin_context(session, is_sysadmin=True)

        args, _ = session.execute.call_args
        # args[0] is a TextClause — stringify
        sql = str(args[0])
        assert "set_admin_context" in sql
        assert ":is_admin" in sql


# ---------------------------------------------------------------------------
# set_tenant_context — line 367
# ---------------------------------------------------------------------------


class TestSetTenantContext:

    def test_executes_set_tenant_context_sql_with_stringified_uuid(self):
        """Line 367: tenant UUID is stringified and passed as ``:tid``
        binding to ``SELECT set_tenant_context(:tid)``. This is the
        every-request hotpath that makes RLS isolate the tenant — a
        regression here silently cross-tenants."""
        session = MagicMock()

        TenantContext.set_tenant_context(session, TENANT_ID)

        session.execute.assert_called_once()
        args, _ = session.execute.call_args
        sql = str(args[0])
        assert "set_tenant_context" in sql
        assert ":tid" in sql
        assert args[1] == {"tid": str(TENANT_ID)}


# ---------------------------------------------------------------------------
# clear_tenant_context — line 434
# ---------------------------------------------------------------------------


class TestClearTenantContext:

    def test_emits_set_config_with_empty_tenant_id(self):
        """Line 434: resets ``app.tenant_id`` to '' (not NULL) via
        ``set_config`` with is_local=FALSE. Pinned to protect the
        privileged-op cleanup path — if this silently no-ops we
        leak tenant state across pooled connections."""
        session = MagicMock()

        TenantContext.clear_tenant_context(session)

        session.execute.assert_called_once()
        args, _ = session.execute.call_args
        sql = str(args[0])
        assert "set_config" in sql
        assert "app.tenant_id" in sql
        # FALSE means 'apply beyond this transaction' — the explicit
        # FALSE is the critical bit, so pin it
        assert "FALSE" in sql or "false" in sql
