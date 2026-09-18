"""Pool-checkout GUC reset: fail-closed behaviour, and full GUC coverage.

#1381's mitigation clears the session-scoped ``app.tenant_id`` GUC when a
pooled connection is handed out. Before this fix, a failure in that reset
was logged and the connection handed out anyway — carrying the PREVIOUS
tenant's GUC, so RLS reads ran under the wrong tenant scope on exactly the
error path of the isolation mitigation. Raising ``DisconnectionError``
makes the pool discard the connection and retry the checkout on a fresh
one instead.

#2853 adds the second half: the listener cleared only two of the three RLS
GUCs the admin engine writes. ``regengine.user_id`` — read by the
``user_self_isolation`` / ``sessions_user_isolation`` policies on the
ENABLE+FORCE-RLS ``public.users`` and ``public.sessions`` tables — was
written session-scoped and rode the pooled connection into the next request,
handing it the previous caller's identity scope. Both halves of that fix are
locked below: the write is transaction-scoped, and the listener resets the
GUC anyway for connections orphaned mid-request.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import DisconnectionError

from services.admin.app import database as admin_database


@pytest.fixture
def _postgres_engine(monkeypatch):
    """The module-level engine is sqlite under tests, which short-circuits
    the listener; pretend it is Postgres so the reset path runs."""
    monkeypatch.setattr(
        admin_database,
        "_engine",
        SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
    )


class TestCheckoutGucReset:
    @staticmethod
    def _idle_connection(cursor: MagicMock | None = None) -> MagicMock:
        connection = MagicMock()
        connection.get_transaction_status.return_value = 0
        if cursor is not None:
            connection.cursor.return_value = cursor
        return connection

    def test_reset_failure_discards_connection(self, _postgres_engine):
        dbapi_connection = self._idle_connection()
        dbapi_connection.cursor.side_effect = RuntimeError("socket torn down")

        with pytest.raises(DisconnectionError):
            admin_database._reset_tenant_guc_on_checkout(dbapi_connection, MagicMock(), MagicMock())

    def test_cursor_error_mid_reset_discards_connection(self, _postgres_engine):
        cursor = MagicMock()
        cursor.execute.side_effect = RuntimeError("server closed the connection")
        dbapi_connection = self._idle_connection(cursor)

        with pytest.raises(DisconnectionError):
            admin_database._reset_tenant_guc_on_checkout(dbapi_connection, MagicMock(), MagicMock())
        cursor.close.assert_called_once()

    def test_successful_reset_hands_out_connection(self, _postgres_engine):
        cursor = MagicMock()
        dbapi_connection = self._idle_connection(cursor)

        # No exception — checkout proceeds.
        admin_database._reset_tenant_guc_on_checkout(dbapi_connection, MagicMock(), MagicMock())

        executed = " ".join(str(c.args[0]) for c in cursor.execute.call_args_list)
        assert "services.admin.app.tenant_id" in executed
        assert "regengine.is_sysadmin" in executed
        cursor.close.assert_called_once()
        dbapi_connection.commit.assert_called_once_with()

    def test_non_idle_connection_is_discarded_without_commit(self, _postgres_engine):
        dbapi_connection = MagicMock()
        dbapi_connection.get_transaction_status.return_value = 2

        with pytest.raises(DisconnectionError):
            admin_database._reset_tenant_guc_on_checkout(
                dbapi_connection,
                MagicMock(),
                MagicMock(),
            )

        dbapi_connection.cursor.assert_not_called()
        dbapi_connection.commit.assert_not_called()

    def test_reset_clears_the_per_user_identity_guc(self, _postgres_engine):
        """#2853: ``regengine.user_id`` must be cleared like the other two.

        The listener's docstring promises "every route starts from a clean
        slate". Leaving this GUC set means the next caller on that pooled
        connection evaluates ``user_self_isolation`` against the PREVIOUS
        caller's id — the isolation predicate applied to the wrong principal.
        """
        cursor = MagicMock()
        dbapi_connection = self._idle_connection(cursor)

        admin_database._reset_tenant_guc_on_checkout(dbapi_connection, MagicMock(), MagicMock())

        executed = [str(c.args[0]) for c in cursor.execute.call_args_list]
        resets = [stmt for stmt in executed if "regengine.user_id" in stmt]
        assert resets, f"regengine.user_id is never reset on checkout: {executed}"
        # Reset to '' rather than NULL: the v078 policies read the GUC through
        # NULLIF(current_setting(...), '')::uuid, so '' means "no identity" and
        # fails closed instead of raising an invalid-uuid cast.
        assert any("''" in stmt for stmt in resets), resets


class TestIdentityGucIsTransactionScoped:
    """#2853's preferred remedy: don't write a session-scoped value at all."""

    def test_identity_guc_write_is_transaction_scoped(self):
        """``set_config(name, value, is_local)`` — the third arg must be true.

        ``false`` is SESSION-scoped: it outlives the request and rides the
        pooled connection back into the pool. ``true`` clears automatically on
        COMMIT/ROLLBACK, matching the shared engine's canonical primitive
        (``shared.tenant_context.set_tenant_guc``).
        """
        db = MagicMock()
        db.bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
        user_id = "11111111-1111-4111-8111-111111111111"
        admin_database.bind_authenticated_user_context(db, user_id)
        statement, params = db.execute.call_args.args
        assert "regengine.user_id" in str(statement)
        assert ", true)" in str(statement)
        assert user_id not in str(statement)
        assert params == {"user_id": user_id}

    def test_sqlite_engine_skips_silently(self, monkeypatch):
        # SQLite does not honor set_config and does not use RLS — the
        # listener is a no-op and must not touch the connection. Patch the
        # dialect explicitly rather than relying on the ambient engine: CI
        # runs these tests against Postgres, where the unpatched listener
        # legitimately opens a cursor.
        monkeypatch.setattr(
            admin_database,
            "_engine",
            SimpleNamespace(dialect=SimpleNamespace(name="sqlite")),
        )
        dbapi_connection = MagicMock()
        admin_database._reset_tenant_guc_on_checkout(dbapi_connection, MagicMock(), MagicMock())
        dbapi_connection.cursor.assert_not_called()
