"""Stolen-lock guarantees for _complete_task / _fail_task — #2831.

``_run_handler_with_heartbeat`` documents that when a worker loses its
lock "the handler continues to run but its results will be ignored by
``_complete_task``". Nothing enforced that until the ``locked_by =
:worker`` predicates were added: the UPDATEs keyed on ``id`` alone, so a
worker whose lock had expired mid-handler still stamped ``completed`` —
or dead-lettered — a row a second worker was actively re-executing. The
second worker's genuine failure was then masked as the first worker's
success, breaking the at-least-once retry guarantee.

The predicates exist in ``server/workers/task_processor.py`` today but
were covered only indirectly: the one test asserting ``locked_by =
:worker`` (``test_task_worker_drain_1225.py``) pins the SQL *string* of
``_release_abandoned_task_lock``, a different function, and does it
against a mock. Nothing exercised ``_complete_task`` or ``_fail_task``
with a lock that had actually moved to another worker.

These tests do, against a real PostgreSQL: a second worker takes the row,
then the stale worker tries to finalize it and must be refused. A string
assertion cannot show that, because what matters is how many rows the
UPDATE touched.

Requires a live Postgres; skips without one unless
``REGENGINE_REQUIRE_DB=1``. See ``tests/migrations/rls_db.py``.

Run via:
    pytest tests/shared/test_task_processor_stolen_lock_2831_live.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from tests.migrations.rls_db import rls_engine_or_skip

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from server.workers import task_processor  # noqa: E402

THIS_WORKER = "worker-A-2831"
THIEF = "worker-B-2831"

# Only the columns the two transitions read or write.
_TABLE_DDL = """
    CREATE TABLE fsma.task_queue (
        id              BIGSERIAL PRIMARY KEY,
        task_type       TEXT NOT NULL DEFAULT 'review_item',
        status          TEXT NOT NULL DEFAULT 'pending',
        attempts        INT NOT NULL DEFAULT 0,
        max_attempts    INT NOT NULL DEFAULT 3,
        last_error      TEXT,
        locked_by       TEXT,
        locked_until    TIMESTAMPTZ,
        scheduled_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        completed_at    TIMESTAMPTZ,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
"""


@pytest.fixture(scope="module")
def session_factory() -> Iterator[object]:
    with rls_engine_or_skip() as engine:
        with engine.connect() as conn:
            conn.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS fsma")
            conn.exec_driver_sql("DROP TABLE IF EXISTS fsma.task_queue CASCADE")
            conn.exec_driver_sql(_TABLE_DDL)
            conn.commit()
        yield sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def _as_this_worker(monkeypatch) -> None:
    """Pin WORKER_ID — both transitions read the module global."""
    monkeypatch.setattr(task_processor, "WORKER_ID", THIS_WORKER)


@pytest.fixture
def db(session_factory):
    session = session_factory()
    try:
        session.execute(text("DELETE FROM fsma.task_queue"))
        session.commit()
        yield session
    finally:
        session.close()


def _insert_task(db, *, locked_by: str) -> int:
    task_id = db.execute(
        text(
            """
            INSERT INTO fsma.task_queue (status, attempts, locked_by, locked_until)
            VALUES ('processing', 1, :locked_by, NOW() + interval '30 seconds')
            RETURNING id
            """
        ),
        {"locked_by": locked_by},
    ).scalar_one()
    db.commit()
    return task_id


def _row(db, task_id: int) -> dict:
    row = db.execute(
        text("SELECT status, locked_by, last_error, completed_at FROM fsma.task_queue WHERE id = :id"),
        {"id": task_id},
    ).mappings().one()
    db.commit()
    return dict(row)


# ---------------------------------------------------------------------------
# _complete_task
# ---------------------------------------------------------------------------


def test_complete_task_refuses_a_stolen_row(db) -> None:
    """The #2831 core case: a stale worker must not mark another's row done.

    Worker B holds the lock and is re-executing. Worker A's handler — still
    running on an expired lock — returns and calls _complete_task. Without
    the predicate this stamped 'completed' and cleared the lock out from
    under B, masking whatever B went on to conclude.
    """
    task_id = _insert_task(db, locked_by=THIEF)

    landed = task_processor._complete_task(db, task_id)

    assert landed is False, "_complete_task must report that its completion did not land"
    after = _row(db, task_id)
    assert after["status"] == "processing", "the stolen row must stay in the state its true owner left it"
    assert after["locked_by"] == THIEF, "the stale worker must not clear the current owner's lock"
    assert after["completed_at"] is None


def test_complete_task_succeeds_while_the_lock_is_held(db) -> None:
    """Control: the predicate must not break the ordinary path."""
    task_id = _insert_task(db, locked_by=THIS_WORKER)

    landed = task_processor._complete_task(db, task_id)

    assert landed is True
    after = _row(db, task_id)
    assert after["status"] == "completed"
    assert after["locked_by"] is None
    assert after["completed_at"] is not None


# ---------------------------------------------------------------------------
# _fail_task — retry and terminal branches
# ---------------------------------------------------------------------------


def test_fail_task_retry_branch_refuses_a_stolen_row(db) -> None:
    """A stale worker must not push another worker's row into backoff."""
    task_id = _insert_task(db, locked_by=THIEF)

    landed = task_processor._fail_task(db, task_id, "stale worker error", attempts=1, max_attempts=3)

    assert landed is False
    after = _row(db, task_id)
    assert after["status"] == "processing"
    assert after["locked_by"] == THIEF
    assert after["last_error"] is None, "the stale worker's error must not overwrite the live attempt"


def test_fail_task_terminal_branch_refuses_a_stolen_row(db) -> None:
    """The costly case: dead-lettering a row another worker may yet complete.

    'dead' is terminal — no retry follows — so a stale worker reaching the
    terminal branch on an expired lock would permanently destroy work the
    current owner was still executing.
    """
    task_id = _insert_task(db, locked_by=THIEF)

    landed = task_processor._fail_task(db, task_id, "stale worker error", attempts=3, max_attempts=3)

    assert landed is False
    after = _row(db, task_id)
    assert after["status"] == "processing", "a stale worker must never dead-letter a re-claimed row"
    assert after["locked_by"] == THIEF


def test_fail_task_succeeds_while_the_lock_is_held(db) -> None:
    """Control: the owning worker still transitions its own row."""
    task_id = _insert_task(db, locked_by=THIS_WORKER)

    landed = task_processor._fail_task(db, task_id, "real error", attempts=1, max_attempts=3)

    assert landed is True
    after = _row(db, task_id)
    assert after["status"] == "pending", "retry branch returns the row to the queue"
    assert after["locked_by"] is None
    assert after["last_error"] == "real error"


def test_unlocked_row_is_also_refused(db) -> None:
    """A row already finalized (lock cleared) must not be resurrected.

    ``locked_by IS NULL`` never equals ``:worker``, so the same predicate
    that stops a steal also stops a double-finalize.
    """
    task_id = _insert_task(db, locked_by=THIS_WORKER)
    db.execute(
        text("UPDATE fsma.task_queue SET status = 'completed', locked_by = NULL WHERE id = :id"),
        {"id": task_id},
    )
    db.commit()

    assert task_processor._complete_task(db, task_id) is False
    assert task_processor._fail_task(db, task_id, "late", attempts=3, max_attempts=3) is False
    assert _row(db, task_id)["status"] == "completed"
