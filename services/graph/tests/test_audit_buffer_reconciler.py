"""Tests for audit_log_buffer reconciliation job (#2257 follow-up).

We use an in-memory SQLite DB rather than the real Postgres fixture: the
reconciler's SQL is intentionally portable (no jsonb/uuid in the
write-path predicates), and the test surface we care about is the loop
logic — what the writer is called with, when attempts are incremented,
when dead-letter fires.

Why SQLite instead of mocking the DB layer: the reconciler issues real
SQL UPDATEs against the same connection that owns the SELECT, so a pure
mock would leave the most likely-to-break code path (the WHERE
predicate, the per-row commit) untested.
"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Make sure services/ is importable for the `from shared` lazy imports.
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "services"))

from services.graph.app import audit_buffer_reconciler as r  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine():
    """In-memory SQLite engine with the buffer table created.

    Use a shared StaticPool so every session sees the same in-memory DB.
    """
    from sqlalchemy.pool import StaticPool

    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE audit_log_buffer (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    originally_failed_at TIMESTAMP NOT NULL,
                    primary_error TEXT,
                    replayed_at TIMESTAMP NULL,
                    replay_attempts INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
    return eng


@pytest.fixture
def Session(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def session_factory(Session):
    """Return a session factory the reconciler will use to open sessions."""

    def _factory():
        return Session()

    return _factory


def _seed(session, *, count=1, replay_attempts=0, age_hours=1):
    """Seed `count` rows into audit_log_buffer."""
    now = datetime.now(timezone.utc)
    ofa = now - timedelta(hours=age_hours)
    ids = []
    for i in range(count):
        rid = str(uuid.uuid4())
        ids.append(rid)
        session.execute(
            text(
                """
                INSERT INTO audit_log_buffer (
                    id, tenant_id, actor, event_type, payload,
                    originally_failed_at, replay_attempts
                ) VALUES (
                    :id, :tenant_id, :actor, :event_type, :payload,
                    :ofa, :attempts
                )
                """
            ),
            {
                "id": rid,
                "tenant_id": f"tenant_{i % 3}",
                "actor": "user@example.com",
                "event_type": "kde_read",
                "payload": json.dumps(
                    {"target_type": "Lot", "target_id": f"lot_{i}"}
                ),
                "ofa": ofa,
                "attempts": replay_attempts,
            },
        )
    session.commit()
    return ids


def _row(session, row_id):
    return session.execute(
        text(
            "SELECT replayed_at, replay_attempts FROM audit_log_buffer "
            "WHERE id = :id"
        ),
        {"id": row_id},
    ).fetchone()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_reconciler_replays_unreplayed_events(Session, session_factory):
    s = Session()
    ids = _seed(s, count=5)
    s.close()

    calls: List[dict] = []

    def writer(**kwargs):
        calls.append(kwargs)

    result = r.reconcile_audit_buffer(
        primary_writer=writer,
        session_factory=session_factory,
    )

    assert result.scanned == 5
    assert result.replayed == 5
    assert result.failed_will_retry == 0
    assert result.dead_lettered == 0
    assert len(calls) == 5
    # Every row stamped.
    s = Session()
    for rid in ids:
        replayed_at, _ = _row(s, rid)
        assert replayed_at is not None, f"row {rid} not stamped"
    s.close()


def test_reconciler_increments_attempts_on_primary_failure(
    Session, session_factory
):
    s = Session()
    ids = _seed(s, count=1)
    s.close()

    def writer(**kwargs):
        raise RuntimeError("primary down")

    result = r.reconcile_audit_buffer(
        primary_writer=writer,
        session_factory=session_factory,
        max_attempts_per_event=5,
    )
    assert result.replayed == 0
    assert result.failed_will_retry == 1
    assert result.dead_lettered == 0

    s = Session()
    replayed_at, attempts = _row(s, ids[0])
    assert replayed_at is None
    assert attempts == 1
    s.close()


def test_reconciler_dead_letters_after_max_attempts(
    Session, session_factory, monkeypatch
):
    s = Session()
    # Seed with replay_attempts=4; max=5 means the next failure becomes
    # the 5th attempt and trips the dead-letter threshold.
    ids = _seed(s, count=1, replay_attempts=4)
    s.close()

    def writer(**kwargs):
        raise RuntimeError("still down")

    # Capture structlog events directly via the logger surface so we
    # don't depend on caplog/structlog routing details.
    captured: List[tuple] = []
    real_logger = r.logger

    class _SpyLogger:
        def __getattr__(self, name):
            def _emit(event=None, **kwargs):
                captured.append((name, event, kwargs))
            return _emit

    monkeypatch.setattr(r, "logger", _SpyLogger())
    try:
        result = r.reconcile_audit_buffer(
            primary_writer=writer,
            session_factory=session_factory,
            max_attempts_per_event=5,
        )
    finally:
        monkeypatch.setattr(r, "logger", real_logger)

    assert result.dead_lettered == 1
    assert result.failed_will_retry == 0

    # Row still exists for forensics.
    s = Session()
    replayed_at, attempts = _row(s, ids[0])
    assert replayed_at is None
    assert attempts == 5
    s.close()

    # Dead-letter event was emitted with full context.
    dl_events = [c for c in captured if c[1] == "audit_buffer_event_dead_lettered"]
    assert len(dl_events) == 1
    _, _, kwargs = dl_events[0]
    assert kwargs["replay_attempts"] == 5
    assert kwargs["replay_error"] == "still down"
    assert "operator_action" in kwargs


def test_reconciler_warns_on_old_events(Session, session_factory):
    s = Session()
    _seed(s, count=1, age_hours=25)  # older than default max_age_hours=24
    s.close()

    calls = []

    def writer(**kwargs):
        calls.append(kwargs)

    result = r.reconcile_audit_buffer(
        primary_writer=writer,
        session_factory=session_factory,
        max_age_hours=24,
    )
    # Aged warning emitted AND replay still attempted (and succeeded here).
    assert result.aged_warnings == 1
    assert result.replayed == 1


def test_reconciler_respects_batch_size(Session, session_factory):
    s = Session()
    _seed(s, count=200)
    s.close()

    calls = []

    def writer(**kwargs):
        calls.append(kwargs)

    result = r.reconcile_audit_buffer(
        primary_writer=writer,
        session_factory=session_factory,
        batch_size=50,
    )
    assert result.scanned == 50
    assert result.replayed == 50
    assert len(calls) == 50


def test_reconciler_handles_empty_buffer(Session, session_factory):
    result = r.reconcile_audit_buffer(
        primary_writer=lambda **_: None,
        session_factory=session_factory,
    )
    assert result.scanned == 0
    assert result.replayed == 0
    assert result.failed_will_retry == 0
    assert result.dead_lettered == 0


def test_reconciler_is_idempotent(Session, session_factory):
    """Running twice on the same buffer must not double-replay."""
    s = Session()
    _seed(s, count=3)
    s.close()

    calls = []

    def writer(**kwargs):
        calls.append(kwargs)

    r1 = r.reconcile_audit_buffer(
        primary_writer=writer, session_factory=session_factory
    )
    r2 = r.reconcile_audit_buffer(
        primary_writer=writer, session_factory=session_factory
    )
    assert r1.replayed == 3
    assert r2.scanned == 0  # all rows now have replayed_at set
    assert r2.replayed == 0
    assert len(calls) == 3  # writer not invoked a second time


def test_get_interval_seconds_default(monkeypatch):
    monkeypatch.delenv(r.ENV_INTERVAL_SECONDS, raising=False)
    assert r.get_interval_seconds() == r.DEFAULT_INTERVAL_SECONDS


def test_get_interval_seconds_override(monkeypatch):
    monkeypatch.setenv(r.ENV_INTERVAL_SECONDS, "60")
    assert r.get_interval_seconds() == 60


def test_get_interval_seconds_invalid(monkeypatch):
    monkeypatch.setenv(r.ENV_INTERVAL_SECONDS, "garbage")
    assert r.get_interval_seconds() == r.DEFAULT_INTERVAL_SECONDS


def test_run_reconcile_tick_swallows_exceptions(monkeypatch):
    """Tick wrapper must never raise — scheduler depends on this."""

    def boom(**_kwargs):
        raise RuntimeError("db is on fire")

    monkeypatch.setattr(r, "reconcile_audit_buffer", boom)
    # Must not raise.
    r.run_reconcile_tick()
