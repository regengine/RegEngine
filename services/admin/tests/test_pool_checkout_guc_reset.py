"""Pool-checkout tenant-GUC reset must fail closed (silent-failure sweep).

#1381's mitigation clears the session-scoped ``app.tenant_id`` GUC when a
pooled connection is handed out. Before this fix, a failure in that reset
was logged and the connection handed out anyway — carrying the PREVIOUS
tenant's GUC, so RLS reads ran under the wrong tenant scope on exactly the
error path of the isolation mitigation. Raising ``DisconnectionError``
makes the pool discard the connection and retry the checkout on a fresh
one instead.
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
    def test_reset_failure_discards_connection(self, _postgres_engine):
        dbapi_connection = MagicMock()
        dbapi_connection.cursor.side_effect = RuntimeError("socket torn down")

        with pytest.raises(DisconnectionError):
            admin_database._reset_tenant_guc_on_checkout(dbapi_connection, MagicMock(), MagicMock())

    def test_cursor_error_mid_reset_discards_connection(self, _postgres_engine):
        cursor = MagicMock()
        cursor.execute.side_effect = RuntimeError("server closed the connection")
        dbapi_connection = MagicMock()
        dbapi_connection.cursor.return_value = cursor

        with pytest.raises(DisconnectionError):
            admin_database._reset_tenant_guc_on_checkout(dbapi_connection, MagicMock(), MagicMock())
        cursor.close.assert_called_once()

    def test_successful_reset_hands_out_connection(self, _postgres_engine):
        cursor = MagicMock()
        dbapi_connection = MagicMock()
        dbapi_connection.cursor.return_value = cursor

        # No exception — checkout proceeds.
        admin_database._reset_tenant_guc_on_checkout(dbapi_connection, MagicMock(), MagicMock())

        executed = " ".join(str(c.args[0]) for c in cursor.execute.call_args_list)
        assert "app.tenant_id" in executed
        assert "regengine.is_sysadmin" in executed
        cursor.close.assert_called_once()

    def test_sqlite_engine_skips_silently(self):
        # Default test engine is sqlite — listener is a no-op and must not
        # touch the connection.
        dbapi_connection = MagicMock()
        admin_database._reset_tenant_guc_on_checkout(dbapi_connection, MagicMock(), MagicMock())
        dbapi_connection.cursor.assert_not_called()
