"""Transaction and tenant-GUC guarantees for the raw ingestion DB manager."""

from __future__ import annotations

import ast
import inspect
import os
from types import SimpleNamespace
from urllib.parse import unquote, urlparse

import psycopg
import pytest
from regengine_ingestion.config import DatabaseConfig
from regengine_ingestion.storage import database as database_module
from regengine_ingestion.storage.database import DatabaseManager

TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"


class RecordingCursor:
    def __init__(self, connection: "RecordingConnection") -> None:
        self.connection = connection

    def __enter__(self) -> "RecordingCursor":
        self.connection.events.append(("cursor_enter",))
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.connection.events.append(("cursor_exit", exc_type))

    def execute(self, statement, params=None) -> None:
        sql = " ".join(str(statement).split())
        self.connection.events.append(("execute", sql, params))
        if self.connection.fail_on and self.connection.fail_on in sql:
            raise RuntimeError("synthetic database failure")

    def fetchone(self):
        return self.connection.fetchone_result

    def fetchall(self):
        return list(self.connection.fetchall_result)


class RecordingTransaction:
    def __init__(self, connection: "RecordingConnection") -> None:
        self.connection = connection

    def __enter__(self) -> "RecordingTransaction":
        self.connection.events.append(("begin",))
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.connection.events.append(("rollback" if exc_type else "commit",))


class RecordingConnection:
    def __init__(self) -> None:
        self.autocommit = None
        self.closed = False
        self.events: list[tuple] = []
        self.fail_on: str | None = None
        self.fetchone_result = {"id": "document-id"}
        self.fetchall_result: list[dict] = []

    def cursor(self) -> RecordingCursor:
        return RecordingCursor(self)

    def transaction(self) -> RecordingTransaction:
        return RecordingTransaction(self)

    def rollback(self) -> None:
        self.events.append(("cleanup_rollback",))

    def close(self) -> None:
        self.events.append(("close",))
        self.closed = True


def _manager(connection: RecordingConnection | None = None) -> tuple[DatabaseManager, RecordingConnection]:
    active_connection = connection or RecordingConnection()
    manager = DatabaseManager(DatabaseConfig())
    manager.conn = active_connection
    return manager, active_connection


def _execute_events(connection: RecordingConnection) -> list[tuple]:
    return [event for event in connection.events if event[0] == "execute"]


def test_every_public_database_operation_uses_tenant_transaction_boundary() -> None:
    """New operations must not bypass the transaction-local GUC helper."""

    tree = ast.parse(inspect.getsource(database_module))
    manager = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "DatabaseManager"
    )
    lifecycle_methods = {"connect", "close", "set_tenant_context"}
    violations: list[str] = []
    for method in (node for node in manager.body if isinstance(node, ast.FunctionDef)):
        if method.name.startswith("_") or method.name in lifecycle_methods:
            continue
        calls_tenant_cursor = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
            and node.func.attr == "_tenant_cursor"
            for node in ast.walk(method)
        )
        if not calls_tenant_cursor:
            violations.append(method.name)

    autocommit_true = [
        node.lineno
        for node in ast.walk(manager)
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant)
        and node.value.value is True
        and any(isinstance(target, ast.Attribute) and target.attr == "autocommit" for target in node.targets)
    ]

    assert violations == [], f"database operations bypass _tenant_cursor: {violations}"
    assert autocommit_true == [], f"security-bearing AUTOCOMMIT assignments at lines {autocommit_true}"


def test_connect_disables_autocommit_and_is_idempotent(monkeypatch) -> None:
    connection = RecordingConnection()
    calls = []

    def _connect(**kwargs):
        calls.append(kwargs)
        return connection

    monkeypatch.setattr(
        "regengine_ingestion.storage.database.psycopg.connect",
        _connect,
    )
    manager = DatabaseManager(DatabaseConfig())

    manager.connect()
    manager.connect()

    assert len(calls) == 1
    assert connection.autocommit is False


def test_tenant_query_sets_local_guc_and_query_in_same_transaction() -> None:
    manager, connection = _manager()

    result = manager.get_document_by_hash("content-hash", tenant_id=TENANT_A)

    assert result == {"id": "document-id"}
    assert [event[0] for event in connection.events] == [
        "begin",
        "cursor_enter",
        "execute",
        "execute",
        "cursor_exit",
        "commit",
    ]
    guc, query = _execute_events(connection)
    assert "set_config('app.tenant_id', %s, true)" in guc[1]
    assert guc[2] == (TENANT_A,)
    assert "SELECT * FROM ingestion.documents" in query[1]


def test_operation_failure_rolls_back_and_next_query_reapplies_tenant() -> None:
    manager, connection = _manager()
    manager.set_tenant_context(TENANT_A)
    connection.fail_on = "INSERT INTO ingestion.audit_log"
    entry = SimpleNamespace(
        timestamp=None,
        job_id=TENANT_A,
        action="fetch",
        resource_type="document",
        resource_id="doc-1",
        status="failed",
        details={},
        error="boom",
    )

    with pytest.raises(RuntimeError, match="synthetic database failure"):
        manager.insert_audit_entry(entry)

    assert ("rollback",) in connection.events
    assert ("cleanup_rollback",) in connection.events
    assert ("commit",) not in connection.events

    connection.fail_on = None
    before_retry = len(connection.events)
    manager.get_document_by_hash("content-hash", tenant_id=TENANT_A)
    retry_events = connection.events[before_retry:]
    retry_executes = [event for event in retry_events if event[0] == "execute"]
    assert "set_config('app.tenant_id', %s, true)" in retry_executes[0][1]
    assert retry_executes[0][2] == (TENANT_A,)
    assert retry_events[-1] == ("commit",)


def test_bound_tenant_rejects_cross_tenant_operation_before_sql() -> None:
    manager, connection = _manager()
    manager.set_tenant_context(TENANT_A)

    with pytest.raises(ValueError, match="does not match"):
        manager.get_document("document-id", tenant_id=TENANT_B)

    assert connection.events == []


def test_tenantless_audit_write_fails_closed() -> None:
    manager, connection = _manager()
    entry = SimpleNamespace(
        timestamp=None,
        job_id=TENANT_A,
        action="fetch",
        resource_type="document",
        resource_id="doc-1",
        status="ok",
        details={},
        error=None,
    )

    with pytest.raises(RuntimeError, match="tenant context"):
        manager.insert_audit_entry(entry)

    assert connection.events == []


def test_close_rolls_back_unknown_work_and_clears_context() -> None:
    manager, connection = _manager()
    manager.set_tenant_context(TENANT_A)

    manager.close()

    assert connection.events == [("cleanup_rollback",), ("close",)]
    assert manager.conn is None
    assert manager._tenant_id is None


@pytest.mark.integration
def test_live_transaction_local_tenant_context() -> None:
    """Opt-in proof for a direct or transaction-pooled PostgreSQL endpoint."""

    database_url = os.getenv("REGENGINE_INGESTION_DATABASE_TEST_URL")
    if not database_url:
        pytest.skip("REGENGINE_INGESTION_DATABASE_TEST_URL is not configured")
    assert database_url is not None

    parsed = urlparse(database_url.replace("postgresql+psycopg://", "postgresql://", 1))
    manager = DatabaseManager(
        DatabaseConfig(
            host=parsed.hostname or "localhost",
            port=parsed.port or 5432,
            database=parsed.path.lstrip("/"),
            user=unquote(parsed.username or ""),
            password=unquote(parsed.password or ""),
        )
    )
    manager.connect()
    try:
        manager.set_tenant_context(TENANT_A)
        with manager._tenant_cursor() as cursor:
            cursor.execute("SELECT current_setting('app.tenant_id', true) AS tenant_id")
            assert cursor.fetchone()["tenant_id"] == TENANT_A

        with pytest.raises(psycopg.Error):
            with manager._tenant_cursor() as cursor:
                cursor.execute("SELECT 1 / 0")

        with manager._tenant_cursor() as cursor:
            cursor.execute("SELECT current_setting('app.tenant_id', true) AS tenant_id")
            assert cursor.fetchone()["tenant_id"] == TENANT_A

        with manager.conn.cursor() as cursor:
            cursor.execute("SELECT current_setting('app.tenant_id', true) AS tenant_id")
            assert cursor.fetchone()["tenant_id"] in (None, "")
        manager.conn.rollback()
    finally:
        manager.close()
