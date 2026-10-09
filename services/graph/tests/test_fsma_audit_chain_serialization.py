"""Regression tests: the FSMA audit hash chain must stay linear across processes.

Two defects are pinned here:

1. Appends chained to a startup-time in-memory head, so two processes
   appending after the same head inserted siblings with the same predecessor
   and forked the chain. Appends are now serialized database-side (advisory
   lock plus re-chain to the database head inside one transaction).
2. ``verify_chain_integrity`` verified the bounded in-memory window when the
   database was unreachable and reported it as the whole chain. It now raises
   ``AuditPersistenceError`` instead, and labels where a verdict came from.

All doubles are hermetic: a shared in-memory row store stands in for
Postgres, so no database is needed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import app.fsma_audit as fsma_audit  # noqa: E402
from app.fsma_audit import AuditPersistenceError, FSMAAuditAction, FSMAAuditLog  # noqa: E402


class _FakeResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _FakeConnection:
    """One emulated Postgres connection over a shared row store.

    ``store`` is shared across engines so two log instances see one
    database, the way two processes see one Postgres. Statement order is
    recorded on ``events`` so tests can assert the lock/head/insert/commit
    sequence of each append.
    """

    def __init__(self, ctx):
        self._ctx = ctx

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, stmt, params=None):
        sql = str(stmt)
        if "pg_advisory_xact_lock" in sql:
            self._ctx.events.append("lock")
            self._ctx.lock_keys.append((params or {}).get("lock_key"))
            return _FakeResult([])
        if sql.lstrip().upper().startswith("SELECT CHECKSUM"):
            self._ctx.events.append("head")
            if self._ctx.store:
                return _FakeResult([(self._ctx.store[-1]["checksum"],)])
            return _FakeResult([])
        if "INSERT INTO" in sql:
            self._ctx.events.append("insert")
            self._ctx.store.append(dict(params or {}))
            return _FakeResult([])
        raise AssertionError(f"unexpected SQL in test double: {sql[:80]}")

    def commit(self):
        self._ctx.events.append("commit")


class _FakeEngine:
    def __init__(self, ctx):
        self._ctx = ctx
        from types import SimpleNamespace as _NS

        self.dialect = _NS(name="postgresql")

    def connect(self):
        return _FakeConnection(self._ctx)


class _UnreachableEngine:
    from types import SimpleNamespace as _NS

    dialect = _NS(name="postgresql")

    def connect(self):
        raise RuntimeError("db down")


@pytest.fixture()
def fake_db(monkeypatch):
    """One shared fake database with a genesis row, wired as both engines."""
    ctx = SimpleNamespace(
        store=[{"checksum": "genesis", "previous_checksum": None}],
        events=[],
        lock_keys=[],
    )
    engine = _FakeEngine(ctx)
    monkeypatch.setattr(fsma_audit, "_get_audit_db_engine", lambda: engine)
    monkeypatch.setattr(fsma_audit, "_get_audit_admin_engine", lambda: engine)
    return ctx


def _log_one(log, target_id, tenant_id):
    return log.log(
        action=FSMAAuditAction.CREATED,
        target_type="Lot",
        target_id=target_id,
        tenant_id=tenant_id,
    )


def test_two_processes_append_one_linear_chain(fake_db):
    """Two log instances (two processes) start from the same head.

    Before the fix both persisted with the same predecessor and the stored
    chain forked. Now the second append re-chains to the database head.
    """
    first = FSMAAuditLog()
    second = FSMAAuditLog()

    entry_one = _log_one(first, "LOT-1", "tenant-a")
    entry_two = _log_one(second, "LOT-2", "tenant-b")

    assert entry_one.previous_checksum == "genesis"
    assert entry_two.previous_checksum == entry_one.checksum
    assert entry_two.verify_integrity() is True

    predecessors = [row["previous_checksum"] for row in fake_db.store[1:]]
    assert predecessors == ["genesis", entry_one.checksum]
    assert len(set(predecessors)) == len(predecessors), (
        f"chain forked: two stored rows share a predecessor: {predecessors}"
    )


def test_append_holds_database_lock_around_head_read_and_insert(fake_db):
    """Each append must take the advisory lock before reading the head and
    inserting, on one connection, committing last."""
    log = FSMAAuditLog()
    _log_one(log, "LOT-9", "tenant-a")

    assert "lock" in fake_db.events
    assert fake_db.events[-4:] == ["lock", "head", "insert", "commit"]
    assert fake_db.lock_keys[-1] == fsma_audit._AUDIT_APPEND_LOCK_KEY


def test_verify_raises_when_database_unreachable(monkeypatch):
    """Verification must not certify the partial in-memory cache."""
    monkeypatch.setattr(fsma_audit, "_get_audit_admin_engine", lambda: _UnreachableEngine())
    monkeypatch.setattr(fsma_audit, "_get_audit_db_engine", lambda: None)

    log = FSMAAuditLog()
    _log_one(log, "d1", "tenant-a")

    with pytest.raises(AuditPersistenceError):
        log.verify_chain_integrity()


def test_verify_labels_memory_source_when_no_database(monkeypatch):
    """With no database configured the in-memory verdict stays available but
    must say where it came from."""
    monkeypatch.setattr(fsma_audit, "_get_audit_admin_engine", lambda: None)
    monkeypatch.setattr(fsma_audit, "_get_audit_db_engine", lambda: None)

    log = FSMAAuditLog()
    _log_one(log, "d1", "tenant-a")

    result = log.verify_chain_integrity()

    assert result["is_valid"] is True
    assert result["total_entries"] == 1
    assert result["source"] == "memory"
