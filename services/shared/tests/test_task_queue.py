"""Tests for :mod:`shared.task_queue` — the PR-A infrastructure for
ADR-002 (migrating FastAPI BackgroundTasks to fsma.task_queue).

Layered in two tiers:

1. **Pure-unit tests** — exercise the registry API and the backoff
   computation. Run on any machine.
2. **Testcontainers integration** — spins up a real Postgres, runs
   the V050 migration, and validates the full claim/dispatch/retry
   lifecycle. Skipped cleanly if Docker isn't reachable or
   testcontainers/psycopg aren't installed.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

_SHARED_DIR = Path(__file__).resolve().parent.parent
_SERVICES_DIR = _SHARED_DIR.parent
for _p in (_SHARED_DIR, _SERVICES_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from shared.task_queue import (  # noqa: E402
    TASK_HANDLERS,
    TaskWorker,
    clear_task_handlers,
    compute_backoff_seconds,
    enqueue_task,
    register_task_handler,
)


# ===========================================================================
# Pure-unit tier — no DB required
# ===========================================================================


@pytest.fixture(autouse=True)
def _reset_handlers():
    """Every test starts with an empty registry."""
    clear_task_handlers()
    yield
    clear_task_handlers()


# --- register_task_handler -------------------------------------------------


def test_register_task_handler_adds_to_registry():
    def handler(**kwargs):  # noqa: ARG001
        return None

    register_task_handler("some_type", handler)
    assert TASK_HANDLERS["some_type"] is handler


def test_register_task_handler_allows_same_handler_twice():
    """Reloading a module registers again with the same function object —
    must not warn or error."""
    def handler(**kwargs):  # noqa: ARG001
        return None

    register_task_handler("some_type", handler)
    register_task_handler("some_type", handler)  # same object
    assert TASK_HANDLERS["some_type"] is handler


def test_register_task_handler_warns_on_conflicting_reregistration(caplog):
    def handler_a(**kwargs):  # noqa: ARG001
        return "a"

    def handler_b(**kwargs):  # noqa: ARG001
        return "b"

    register_task_handler("some_type", handler_a)
    with caplog.at_level("WARNING", logger="task_queue"):
        register_task_handler("some_type", handler_b)
    assert TASK_HANDLERS["some_type"] is handler_b
    assert any(
        "task_handler_reregistered" in rec.message for rec in caplog.records
    )


def test_clear_task_handlers_empties_registry():
    register_task_handler("x", lambda **kw: None)
    assert "x" in TASK_HANDLERS
    clear_task_handlers()
    assert TASK_HANDLERS == {}


# --- compute_backoff_seconds -----------------------------------------------


@pytest.mark.parametrize(
    "attempts,expected",
    [
        (0, 30),     # 30 * 2^0
        (1, 60),     # 30 * 2^1
        (2, 120),    # 30 * 2^2
        (3, 240),    # 30 * 2^3
        (4, 480),    # 30 * 2^4
        (5, 600),    # capped
        (10, 600),   # capped
    ],
)
def test_compute_backoff_seconds(attempts, expected):
    assert compute_backoff_seconds(attempts) == expected


def test_compute_backoff_seconds_respects_cap():
    assert compute_backoff_seconds(20, cap_seconds=120) == 120


def test_compute_backoff_seconds_negative_clamps_to_zero():
    """Defensive: negative attempts shouldn't produce weird fractional
    seconds."""
    assert compute_backoff_seconds(-5) == 30  # treated as 0


# --- TaskWorker._invoke (sync/async adapter) -------------------------------


def test_invoke_runs_sync_handler():
    captured = {}

    def handler(**kwargs):
        captured.update(kwargs)

    TaskWorker._invoke(handler, {"foo": "bar"})
    assert captured == {"foo": "bar"}


def test_invoke_runs_async_handler():
    captured = {}

    async def handler(**kwargs):
        await asyncio.sleep(0)
        captured.update(kwargs)

    TaskWorker._invoke(handler, {"x": 1})
    assert captured == {"x": 1}


def test_invoke_propagates_handler_exception():
    def handler(**kwargs):  # noqa: ARG001
        raise ValueError("kaboom")

    with pytest.raises(ValueError, match="kaboom"):
        TaskWorker._invoke(handler, {})


# ===========================================================================
# Integration tier — requires Docker + testcontainers + psycopg
# ===========================================================================

try:
    from testcontainers.postgres import PostgresContainer  # type: ignore[import]
    _HAS_TESTCONTAINERS = True
except ImportError:
    _HAS_TESTCONTAINERS = False

try:
    import psycopg  # type: ignore[import]  # noqa: F401
    _HAS_PSYCOPG = True
except ImportError:
    _HAS_PSYCOPG = False


def _docker_available() -> bool:
    try:
        import docker  # type: ignore[import]
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


_INTEGRATION_SKIP_REASON = (
    "integration tests require Docker + testcontainers[postgresql] + psycopg[binary]"
)

integration_only = pytest.mark.skipif(
    not (_HAS_TESTCONTAINERS and _HAS_PSYCOPG and _docker_available()),
    reason=_INTEGRATION_SKIP_REASON,
)


_V050_MIGRATION_SQL = """
CREATE SCHEMA IF NOT EXISTS fsma;

CREATE TABLE IF NOT EXISTS fsma.task_queue (
    id              BIGSERIAL PRIMARY KEY,
    task_type       TEXT NOT NULL,
    payload         JSONB NOT NULL DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'dead')),
    priority        INT NOT NULL DEFAULT 0,
    tenant_id       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    attempts        INT NOT NULL DEFAULT 0,
    max_attempts    INT NOT NULL DEFAULT 3,
    last_error      TEXT,
    locked_by       TEXT,
    locked_until    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_task_queue_pending
    ON fsma.task_queue (priority DESC, created_at ASC)
    WHERE status = 'pending';
"""


@pytest.fixture(scope="module")
def pg_engine():
    """Spin up a Postgres container and apply the V050-compatible schema."""
    if not (_HAS_TESTCONTAINERS and _HAS_PSYCOPG and _docker_available()):
        pytest.skip(_INTEGRATION_SKIP_REASON)

    from sqlalchemy import create_engine, text

    with PostgresContainer("postgres:16-alpine", driver="psycopg") as pg:
        url = pg.get_connection_url()
        # testcontainers returns postgresql+psycopg2 for older clients;
        # rewrite to psycopg v3 which this project uses.
        url = url.replace("postgresql+psycopg2://", "postgresql+psycopg://")
        engine = create_engine(url, future=True)
        with engine.begin() as conn:
            for stmt in _V050_MIGRATION_SQL.split(";"):
                stmt = stmt.strip()
                if stmt:
                    conn.execute(text(stmt))
        yield engine
        engine.dispose()


@pytest.fixture()
def clean_queue(pg_engine):
    """Truncate the task_queue between tests."""
    from sqlalchemy import text
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE fsma.task_queue"))
    yield
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE fsma.task_queue"))


# --- enqueue_task + full round-trip ----------------------------------------


@integration_only
def test_enqueue_task_inserts_row_and_returns_id(pg_engine, clean_queue):
    from sqlalchemy.orm import sessionmaker

    SessionLocal = sessionmaker(bind=pg_engine, future=True)
    with SessionLocal.begin() as session:
        task_id = enqueue_task(
            session,
            task_type="fixture",
            payload={"hello": "world"},
            tenant_id="tenant-1",
        )

    assert isinstance(task_id, int)
    assert task_id > 0

    from sqlalchemy import text
    with pg_engine.begin() as conn:
        row = conn.execute(
            text("SELECT task_type, payload, tenant_id, status FROM fsma.task_queue WHERE id = :id"),
            {"id": task_id},
        ).fetchone()
    assert row.task_type == "fixture"
    assert row.payload == {"hello": "world"}
    assert row.tenant_id == "tenant-1"
    assert row.status == "pending"


@integration_only
def test_worker_claims_and_completes_task(pg_engine, clean_queue):
    """Happy path: enqueue → run_once → row is 'completed', handler ran."""
    from sqlalchemy.orm import sessionmaker

    ran = {}

    def handler(**kwargs):
        ran.update(kwargs)

    register_task_handler("fixture.ok", handler)

    SessionLocal = sessionmaker(bind=pg_engine, future=True)
    with SessionLocal.begin() as session:
        task_id = enqueue_task(
            session, task_type="fixture.ok", payload={"value": 42},
        )

    worker = TaskWorker(pg_engine, poll_interval_seconds=0.1)
    assert worker.run_once() == task_id
    assert ran == {"value": 42}

    from sqlalchemy import text
    with pg_engine.begin() as conn:
        row = conn.execute(
            text("SELECT status, locked_by, completed_at FROM fsma.task_queue WHERE id = :id"),
            {"id": task_id},
        ).fetchone()
    assert row.status == "completed"
    assert row.locked_by is None
    assert row.completed_at is not None


@integration_only
def test_worker_retries_on_handler_exception(pg_engine, clean_queue):
    """Raising handler → row back to 'pending' with attempts++ and
    locked_until in the future (backoff marker). Still below max_attempts."""
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    def bad_handler(**kwargs):  # noqa: ARG001
        raise RuntimeError("transient failure")

    register_task_handler("fixture.fail", bad_handler)

    SessionLocal = sessionmaker(bind=pg_engine, future=True)
    with SessionLocal.begin() as session:
        task_id = enqueue_task(
            session, task_type="fixture.fail", payload={}, max_attempts=3,
        )

    worker = TaskWorker(pg_engine, poll_interval_seconds=0.1)
    worker.run_once()

    with pg_engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT status, attempts, last_error, locked_until, locked_by "
                "FROM fsma.task_queue WHERE id = :id"
            ),
            {"id": task_id},
        ).fetchone()
    assert row.status == "pending"
    assert row.attempts == 1
    assert "transient failure" in (row.last_error or "")
    assert row.locked_by is None
    assert row.locked_until is not None  # backoff "not before" marker


@integration_only
def test_worker_transitions_to_dead_after_max_attempts(pg_engine, clean_queue):
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    def bad_handler(**kwargs):  # noqa: ARG001
        raise RuntimeError("still broken")

    register_task_handler("fixture.dead", bad_handler)

    SessionLocal = sessionmaker(bind=pg_engine, future=True)
    with SessionLocal.begin() as session:
        task_id = enqueue_task(
            session, task_type="fixture.dead", payload={}, max_attempts=2,
        )

    worker = TaskWorker(pg_engine, poll_interval_seconds=0.1)
    # Attempt 1: fail → pending
    worker.run_once()
    # Fast-forward the backoff so the next claim sees the row as eligible.
    with pg_engine.begin() as conn:
        conn.execute(
            text("UPDATE fsma.task_queue SET locked_until = NULL WHERE id = :id"),
            {"id": task_id},
        )
    # Attempt 2: fail → dead (attempts now >= max_attempts)
    worker.run_once()

    with pg_engine.begin() as conn:
        row = conn.execute(
            text("SELECT status, attempts FROM fsma.task_queue WHERE id = :id"),
            {"id": task_id},
        ).fetchone()
    assert row.status == "dead"
    assert row.attempts == 2


@integration_only
def test_missing_handler_transitions_straight_to_dead(pg_engine, clean_queue):
    """No handler → row is immediately 'dead' — retry can't produce a
    handler that isn't there."""
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    SessionLocal = sessionmaker(bind=pg_engine, future=True)
    with SessionLocal.begin() as session:
        task_id = enqueue_task(
            session, task_type="fixture.no_handler", payload={}, max_attempts=3,
        )

    worker = TaskWorker(pg_engine, poll_interval_seconds=0.1)
    worker.run_once()

    with pg_engine.begin() as conn:
        row = conn.execute(
            text("SELECT status, last_error FROM fsma.task_queue WHERE id = :id"),
            {"id": task_id},
        ).fetchone()
    assert row.status == "dead"
    assert "No handler registered" in (row.last_error or "")


@integration_only
def test_release_stale_locks_returns_row_to_pending(pg_engine, clean_queue):
    """Worker died mid-task → row was 'processing' with locked_until in
    the past → a subsequent claim cycle flips it back to 'pending'."""
    from sqlalchemy import text

    # Simulate a dead worker's leftover row: status='processing',
    # locked_until already expired.
    with pg_engine.begin() as conn:
        row = conn.execute(
            text(
                """
                INSERT INTO fsma.task_queue
                    (task_type, payload, status, locked_by, locked_until)
                VALUES
                    ('fixture.stale', '{}'::jsonb, 'processing',
                     'dead-worker', NOW() - INTERVAL '10 minutes')
                RETURNING id
                """
            )
        ).fetchone()
        task_id = row.id

    worker = TaskWorker(pg_engine, poll_interval_seconds=0.1)
    worker._release_stale_locks()

    with pg_engine.begin() as conn:
        row = conn.execute(
            text("SELECT status, locked_by FROM fsma.task_queue WHERE id = :id"),
            {"id": task_id},
        ).fetchone()
    assert row.status == "pending"
    assert row.locked_by is None


@integration_only
def test_priority_ordering(pg_engine, clean_queue):
    """Higher-priority rows are claimed first."""
    from sqlalchemy.orm import sessionmaker

    seen: list[int] = []

    def handler(priority_rank, **_kwargs):
        seen.append(priority_rank)

    register_task_handler("fixture.priority", handler)

    SessionLocal = sessionmaker(bind=pg_engine, future=True)
    with SessionLocal.begin() as session:
        for i, p in enumerate([0, 5, 2, 9, 1]):
            enqueue_task(
                session,
                task_type="fixture.priority",
                payload={"priority_rank": p},
                priority=p,
            )

    worker = TaskWorker(pg_engine, poll_interval_seconds=0.1)
    for _ in range(5):
        worker.run_once()

    assert seen == [9, 5, 2, 1, 0]


@integration_only
def test_async_handler_round_trip(pg_engine, clean_queue):
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    ran = {}

    async def async_handler(**kwargs):
        await asyncio.sleep(0)
        ran.update(kwargs)

    register_task_handler("fixture.async", async_handler)

    SessionLocal = sessionmaker(bind=pg_engine, future=True)
    with SessionLocal.begin() as session:
        task_id = enqueue_task(
            session, task_type="fixture.async", payload={"async_v": True},
        )

    worker = TaskWorker(pg_engine, poll_interval_seconds=0.1)
    worker.run_once()

    assert ran == {"async_v": True}
    with pg_engine.begin() as conn:
        row = conn.execute(
            text("SELECT status FROM fsma.task_queue WHERE id = :id"),
            {"id": task_id},
        ).fetchone()
    assert row.status == "completed"


@integration_only
def test_task_type_allowlist(pg_engine, clean_queue):
    """A worker with ``task_types=['a']`` ignores tasks of type ``b``."""
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    ran_a = []

    def handler_a(**kwargs):  # noqa: ARG001
        ran_a.append(True)

    register_task_handler("fixture.a", handler_a)
    # No handler for 'fixture.b' so an unscoped worker would mark it 'dead'.

    SessionLocal = sessionmaker(bind=pg_engine, future=True)
    with SessionLocal.begin() as session:
        task_b = enqueue_task(session, task_type="fixture.b", payload={})
        task_a = enqueue_task(session, task_type="fixture.a", payload={})

    worker = TaskWorker(pg_engine, poll_interval_seconds=0.1, task_types=["fixture.a"])
    claimed_id = worker.run_once()

    assert claimed_id == task_a
    assert ran_a == [True]
    with pg_engine.begin() as conn:
        row_b = conn.execute(
            text("SELECT status FROM fsma.task_queue WHERE id = :id"),
            {"id": task_b},
        ).fetchone()
    assert row_b.status == "pending"  # untouched by the scoped worker
