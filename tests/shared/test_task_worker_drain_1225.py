"""Regression tests for #1225 — task_processor drain on deploy.

Before: ``stop_task_worker`` set the shutdown event and joined with
``timeout=10``. If a handler was mid-execution the daemon thread was
killed on process exit. The claimed row stayed in ``status='processing'``
until ``locked_until`` (30s–5min depending on task_type) expired, and
the retry counter was permanently bumped even though no real failure
occurred. Deploys happen multiple times per day, so this silently
shed work on every rollout.

After:
- ``_run_handler_with_heartbeat`` publishes the in-flight task id
  to ``_current_task_id`` under ``_inflight_lock`` while the handler
  is running; clears on return.
- ``stop_task_worker`` joins with a configurable timeout (default
  30s, matching Gunicorn's graceful-timeout) and, if the thread is
  still alive past that, reads ``_current_task_id`` under lock and
  issues ``_release_abandoned_task_lock`` — an UPDATE that flips the
  row back to ``pending``, clears the lock columns, and decrements
  ``attempts`` so the handover does NOT count as a failed retry.

These tests stub the DB so they run without PostgreSQL.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from server.workers import task_processor  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Reset task_processor module globals between tests so state from
    one test cannot bleed into another."""
    task_processor._shutdown_event.clear()
    with task_processor._inflight_lock:
        task_processor._current_task_id = None
        task_processor._current_task_attempts = 0
    task_processor._worker_thread = None
    yield
    task_processor._shutdown_event.clear()
    with task_processor._inflight_lock:
        task_processor._current_task_id = None
        task_processor._current_task_attempts = 0
    task_processor._worker_thread = None


# ===========================================================================
# _current_task_id is published while the handler runs
# ===========================================================================


class TestInFlightPublication_Issue1225:
    def test_current_task_id_set_during_handler(self):
        """The module-level marker must be set while the handler runs
        and cleared afterwards."""
        seen_ids = []

        def _handler(_payload):
            # Snapshot the in-flight marker as the drain path would see it.
            with task_processor._inflight_lock:
                seen_ids.append(task_processor._current_task_id)

        # Stub the db_factory so the heartbeat thread has something to call
        # without reaching real Postgres.
        db_factory = MagicMock(return_value=MagicMock())
        task_processor._run_handler_with_heartbeat(
            db_factory=db_factory,
            task_id=77,
            timeout_seconds=30,
            handler=_handler,
            payload={},
            attempts=1,
        )
        assert seen_ids == [77], (
            f"handler did not observe in-flight marker = 77; got {seen_ids}"
        )
        # Cleared after.
        assert task_processor._current_task_id is None
        assert task_processor._current_task_attempts == 0

    def test_current_task_attempts_published(self):
        """Attempts must be published alongside the id so the drain path
        can decrement-on-release correctly."""
        seen_attempts = []

        def _handler(_payload):
            with task_processor._inflight_lock:
                seen_attempts.append(task_processor._current_task_attempts)

        db_factory = MagicMock(return_value=MagicMock())
        task_processor._run_handler_with_heartbeat(
            db_factory=db_factory,
            task_id=1,
            timeout_seconds=30,
            handler=_handler,
            payload={},
            attempts=3,
        )
        assert seen_attempts == [3]

    def test_current_task_id_cleared_after_handler_exception(self):
        """Even if the handler raises, the marker must be cleared so the
        NEXT task's handler can publish its own id."""
        def _handler(_payload):
            raise RuntimeError("boom")

        db_factory = MagicMock(return_value=MagicMock())
        with pytest.raises(RuntimeError):
            task_processor._run_handler_with_heartbeat(
                db_factory=db_factory,
                task_id=42,
                timeout_seconds=30,
                handler=_handler,
                payload={},
                attempts=1,
            )
        assert task_processor._current_task_id is None
        assert task_processor._current_task_attempts == 0


# ===========================================================================
# stop_task_worker release path
# ===========================================================================


class TestStopTaskWorkerDrain_Issue1225:
    def test_stops_cleanly_when_no_task_in_flight(self):
        """Clean shutdown (no task running) must join and log without
        touching the DB."""
        # Simulate a worker thread that exits immediately when the event
        # is set.
        started = threading.Event()

        def _run():
            started.set()
            task_processor._shutdown_event.wait(timeout=5)

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        started.wait(1)
        task_processor._worker_thread = t

        with patch.object(task_processor, "_release_abandoned_task_lock") as rel:
            task_processor.stop_task_worker(timeout_seconds=2)

        # No in-flight task ⇒ no release attempt.
        rel.assert_not_called()
        assert not t.is_alive()

    def test_releases_lock_when_thread_hangs_with_inflight_task(self):
        """If the worker thread is wedged inside a handler past the join
        timeout, the drain path must call ``_release_abandoned_task_lock``
        with the published task_id + attempts."""
        # Fake a wedged worker by spawning a thread that sleeps through
        # the shutdown event.
        def _run():
            while True:
                time.sleep(0.05)  # never observes the event

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        task_processor._worker_thread = t

        # Publish an in-flight task as the handler would have.
        with task_processor._inflight_lock:
            task_processor._current_task_id = 999
            task_processor._current_task_attempts = 2

        with patch.object(task_processor, "_release_abandoned_task_lock") as rel:
            task_processor.stop_task_worker(timeout_seconds=1)

        rel.assert_called_once_with(999, 2)

    def test_no_release_when_thread_hangs_without_inflight_task(self):
        """If the worker is wedged but no task is marked in flight (e.g.
        handler already cleared it but thread is stuck elsewhere), we
        must NOT guess — log and move on without releasing a random row."""
        def _run():
            while True:
                time.sleep(0.05)

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        task_processor._worker_thread = t

        with patch.object(task_processor, "_release_abandoned_task_lock") as rel:
            task_processor.stop_task_worker(timeout_seconds=1)

        rel.assert_not_called()

    def test_noop_when_worker_thread_never_started(self):
        """``stop_task_worker`` called before ``start_task_worker`` must
        not explode."""
        task_processor._worker_thread = None
        # Should return without raising.
        task_processor.stop_task_worker(timeout_seconds=1)


# ===========================================================================
# _release_abandoned_task_lock — SQL contract
# ===========================================================================


class TestReleaseAbandonedTaskLockSQL_Issue1225:
    def test_update_predicate_is_scoped_to_this_worker_and_processing(self):
        """The UPDATE must pin ``locked_by = :worker`` AND
        ``status = 'processing'`` — a task that was already completed
        or re-claimed by another worker must not be clobbered."""
        captured = {}

        class _FakeSession:
            def execute(self, stmt, params=None):
                captured["sql"] = str(stmt)
                captured["params"] = params or {}
                result = MagicMock()
                result.rowcount = 1
                return result
            def commit(self):
                pass
            def close(self):
                pass

        with patch("shared.database.SessionLocal", _FakeSession):
            task_processor._release_abandoned_task_lock(task_id=123, attempts=2)

        sql = captured["sql"]
        assert "UPDATE fsma.task_queue" in sql
        assert "SET status = 'pending'" in sql
        assert "locked_by = NULL" in sql
        assert "locked_until = NULL" in sql
        # attempts must DECREMENT on graceful handover.
        assert "attempts = GREATEST(attempts - 1, 0)" in sql
        # Guard predicate.
        assert "locked_by = :worker" in sql
        assert "status = 'processing'" in sql
        # Params threaded correctly.
        assert captured["params"]["id"] == 123
        assert captured["params"]["worker"] == task_processor.WORKER_ID

    def test_release_swallows_db_errors(self):
        """The release path runs during shutdown — a DB failure must
        not raise out of ``stop_task_worker`` (the process is already
        on its way out)."""
        class _ExplodingSession:
            def __init__(self):
                raise RuntimeError("db unreachable")

        with patch("shared.database.SessionLocal", _ExplodingSession):
            # Should not raise.
            task_processor._release_abandoned_task_lock(task_id=1, attempts=1)


# ===========================================================================
# SHUTDOWN_TIMEOUT_SECONDS env configurability
# ===========================================================================


class TestShutdownTimeoutConfigurable_Issue1225:
    def test_default_shutdown_timeout_matches_gunicorn_graceful(self):
        """The default must be 30s — matching Gunicorn's graceful-timeout
        so the worker doesn't get SIGKILL'd while still draining."""
        assert task_processor.SHUTDOWN_TIMEOUT_SECONDS == 30

    def test_stop_accepts_explicit_timeout_override(self):
        """Callers can pass an explicit timeout_seconds to override env."""
        t = threading.Thread(target=lambda: None, daemon=True)
        t.start()
        t.join()  # already dead
        task_processor._worker_thread = t

        # Should return fast — the passed timeout is an upper bound.
        start = time.monotonic()
        task_processor.stop_task_worker(timeout_seconds=0.5)
        elapsed = time.monotonic() - start
        assert elapsed < 1.0
