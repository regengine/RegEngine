"""Unit contracts for side-effect-free admin transaction helpers."""

from __future__ import annotations

from types import SimpleNamespace

from shared.admin_context import (
    arm_global_admin_context,
    bind_authenticated_user_context,
    disarm_global_admin_context,
)


class _SQLiteSession:
    bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    def __init__(self):
        self.info = {}


class _PostgresConnection:
    engine = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    def __init__(self):
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params))


def test_sqlite_context_uses_session_metadata_without_sql():
    session = _SQLiteSession()

    arm_global_admin_context(session)
    bind_authenticated_user_context(session, "user-1")
    assert session.info == {
        "is_admin": True,
        "authenticated_user_id": "user-1",
    }

    disarm_global_admin_context(session)
    assert session.info["is_admin"] is False


def test_postgres_admin_arm_and_disarm_are_transaction_local():
    connection = _PostgresConnection()

    arm_global_admin_context(connection)
    disarm_global_admin_context(connection)

    assert "'true', true" in connection.calls[0][0]
    assert "'false', true" in connection.calls[1][0]


def test_postgres_user_binding_is_transaction_local_and_parameterized():
    connection = _PostgresConnection()

    bind_authenticated_user_context(connection, "user-1")

    statement, params = connection.calls[0]
    assert "regengine.user_id" in statement
    assert ":user_id, true" in statement
    assert params == {"user_id": "user-1"}
