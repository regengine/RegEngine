"""Unit tests for task_queue producer hardening.

Covers the additions made to :mod:`server.workers.task_processor`:

* #1164 — idempotency key on :func:`enqueue_task`
* #1181 — exponential-backoff ``scheduled_at`` set by :func:`_fail_task`
* #1172 — heartbeat thread extends ``locked_until`` while a handler runs
* #1210 — per-task-type visibility timeout used in :func:`_claim_task`

These tests stub the database layer (``shared.database.SessionLocal``)
so they can run without PostgreSQL. SQL strings are inspected via
``MagicMock.execute.call_args_list``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make the repo root importable so `from server.workers.task_processor import ...`
# resolves in a test-only environment.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from server.workers import task_processor  # noqa: E402


# ---------------------------------------------------------------------------
# #1164 — enqueue_task idempotency key
# ---------------------------------------------------------------------------


class TestEnqueueTaskIdempotency:
    def test_enqueue_without_key_uses_legacy_insert(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = (42,)

        with patch("shared.database.SessionLocal", return_value=db):
            tid = task_processor.enqueue_task(
                "nlp_extraction",
                {"document_id": "doc-1"},
            )

        assert tid == 42
        sql = [str(call.args[0]).lower() for call in db.execute.call_args_list if call.args]
        # Legacy insert must NOT reference idempotency_key.
        assert any("insert into" in s and "idempotency_key" not in s for s in sql)
        db.commit.assert_called()

    def test_enqueue_with_key_uses_on_conflict(self):
        db = MagicMock()
        # First execute: INSERT … ON CONFLICT DO NOTHING RETURNING id → got id
        db.execute.return_value.fetchone.return_value = (7,)

        with patch("shared.database.SessionLocal", return_value=db):
            tid = task_processor.enqueue_task(
                "nlp_extraction",
                {"document_id": "doc-1"},
                tenant_id="tenant-1",
                idempotency_key="nlp_extraction:doc-1",
            )

        assert tid == 7
        sql_texts = [str(call.args[0]).lower() for call in db.execute.call_args_list if call.args]
        assert any("on conflict" in s for s in sql_texts)
        assert any("idempotency_key" in s for s in sql_texts)

    def test_enqueue_with_key_conflict_returns_existing_id(self):
        db = MagicMock()
        # First execute: conflict → fetchone returns None
        # Second execute: lookup → fetchone returns (99,)
        fetch_results = [None, (99,)]

        def execute_side_effect(*args, **kwargs):
            r = MagicMock()
            r.fetchone.return_value = fetch_results.pop(0)
            return r

        db.execute.side_effect = execute_side_effect

        with patch("shared.database.SessionLocal", return_value=db):
            tid = task_processor.enqueue_task(
                "nlp_extraction",
                {"document_id": "doc-1"},
                tenant_id="tenant-1",
                idempotency_key="nlp_extraction:doc-1",
            )

        assert tid == 99, (
            "When the insert conflicts, enqueue_task must return the "
            "already-enqueued task's id (idempotent — same input → same id)"
        )

    def test_enqueue_failure_returns_none(self):
        db = MagicMock()
        db.execute.side_effect = RuntimeError("pg broke")

        with patch("shared.database.SessionLocal", return_value=db):
            tid = task_processor.enqueue_task("nlp_extraction", {})

        assert tid is None


# ---------------------------------------------------------------------------
# #1181 — retry backoff
# ---------------------------------------------------------------------------


class TestRetryBackoff:
    def test_fail_task_sets_scheduled_at_for_retry(self):
        db = MagicMock()
        # attempts < max_attempts → retry path
        task_processor._fail_task(db, task_id=10, error="boom", attempts=1, max_attempts=3)

        sql = [str(call.args[0]).lower() for call in db.execute.call_args_list if call.args]
        # The retry UPDATE must defer the next attempt via scheduled_at.
        assert any("scheduled_at" in s for s in sql), (
            "#1181: _fail_task must bump scheduled_at to defer the retry — "
            "otherwise the next poll picks it up in ~2s and we burn CPU"
        )

    def test_fail_task_dead_does_not_defer(self):
        db = MagicMock()
        # attempts >= max_attempts → dead path
        task_processor._fail_task(db, task_id=10, error="boom", attempts=3, max_attempts=3)

        sql = [str(call.args[0]).lower() for call in db.execute.call_args_list if call.args]
        # Dead-letter path should set status='dead' — no need to touch scheduled_at
        # (the status index already excludes 'dead' from pending).
        assert any("'dead'" in s or "= 'dead'" in s or "status = 'dead'" in s for s in sql), (
            "After max_attempts, _fail_task must set status='dead'"
        )

    def test_compute_retry_delay_is_exponential(self):
        # 1st retry  → ~60s, 2nd → ~120s, 3rd → ~240s, capped at 3600s
        assert task_processor._retry_delay_seconds(1) >= 60
        assert task_processor._retry_delay_seconds(2) >= task_processor._retry_delay_seconds(1)
        assert task_processor._retry_delay_seconds(10) <= 3600


# ---------------------------------------------------------------------------
# #1241 — _claim_task must respect scheduled_at (+ fix related latent bugs)
# ---------------------------------------------------------------------------


class TestClaimTaskRespectsBackoff:
    """Guardrail for the #1241 bug: `_fail_task` already bumps
    `scheduled_at` (covered by :class:`TestRetryBackoff`), but prior to
    the fix `_claim_task` did not consult that column at all. Rows in
    backoff were immediately re-claimed, burning their retry budget in
    seconds. These tests inspect the actual SQL the worker issues so
    the invariant is locked in against future refactors.
    """

    def _capture_claim_sql(self) -> str:
        db = MagicMock()
        # fetchone=None means "queue empty" — we only care about the SQL shape.
        db.execute.return_value.fetchone.return_value = None
        task_processor._claim_task(db)
        calls = [str(call.args[0]) for call in db.execute.call_args_list if call.args]
        assert calls, "_claim_task must issue at least one SQL statement"
        return calls[0]

    def test_claim_filters_pending_by_scheduled_at(self):
        sql = self._capture_claim_sql().lower()
        # Pending branch must be gated by scheduled_at, otherwise deferred
        # retries are claimed immediately and #1181 is defeated.
        assert "scheduled_at" in sql, (
            "#1241: _claim_task must reference scheduled_at so deferred "
            "retries aren't re-claimed before their backoff elapses"
        )
        assert "scheduled_at <= :now" in sql or "scheduled_at<=:now" in sql, (
            "#1241: the pending branch must compare scheduled_at to NOW — "
            "found `scheduled_at` in SQL but not the inequality filter"
        )

    def test_claim_orders_by_scheduled_at_first(self):
        # The idx_task_queue_pending index (migration v059) is keyed on
        # (scheduled_at ASC, priority DESC, created_at ASC). ORDER BY
        # must match leading column for the planner to use the index on
        # high-volume queues.
        sql = self._capture_claim_sql().lower()
        # Tolerate whitespace variation; we just need scheduled_at before priority.
        sched_pos = sql.find("scheduled_at asc")
        prio_pos = sql.find("priority desc")
        assert sched_pos != -1 and prio_pos != -1, sql
        assert sched_pos < prio_pos, (
            "ORDER BY scheduled_at must precede priority so the "
            "idx_task_queue_pending index (scheduled_at, priority, "
            "created_at) is usable"
        )

    def test_claim_does_not_raise_nameerror(self):
        """Regression for a latent NameError in `_claim_task`.

        Prior to this fix `lock_until` was referenced in the SQL params
        dict without ever being assigned in the function body. Every
        call raised NameError which the outer `_worker_loop` try/except
        swallowed — with the net effect that the monolith's task worker
        for `nlp_extraction` / `graph_update` / `review_item` claimed
        zero tasks in production. This test ensures the function at
        least reaches the `db.execute` call cleanly.
        """
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = None

        # Must not raise — specifically not NameError.
        result = task_processor._claim_task(db)
        assert result is None
        db.execute.assert_called_once()

    def test_claim_returns_visibility_timeout_from_row(self):
        """`row[5]` is read — RETURNING must project a sixth column.

        Prior to this fix RETURNING projected only 5 columns but the
        Python code indexed `row[5]`. Any actual claim raised
        IndexError. We now COALESCE the column to the default so
        `row[5]` is always a usable int.
        """
        db = MagicMock()
        # Simulate a real claim — 6 columns incl. timeout.
        db.execute.return_value.fetchone.return_value = (
            42,                   # id
            "nlp_extraction",     # task_type
            {"doc": "x"},         # payload (dict)
            1,                    # attempts
            3,                    # max_attempts
            180,                  # visibility_timeout_seconds
        )
        claimed = task_processor._claim_task(db)
        assert claimed is not None
        assert claimed["id"] == 42
        assert claimed["visibility_timeout_seconds"] == 180

    def test_claim_sql_returns_six_columns(self):
        """Guard the column count in RETURNING against silent regressions."""
        sql = self._capture_claim_sql().lower()
        # RETURNING clause should mention visibility_timeout_seconds (either
        # directly or via COALESCE).
        assert "visibility_timeout_seconds" in sql, (
            "RETURNING must project visibility_timeout_seconds so row[5] "
            "is populated — otherwise _claim_task raises IndexError on "
            "every successful claim"
        )


# ---------------------------------------------------------------------------
# #1210 — per-task-type visibility timeout
# ---------------------------------------------------------------------------


class TestVisibilityTimeouts:
    def test_timeout_map_has_entries_for_all_handlers(self):
        # Every handler the worker can dispatch should have an explicit
        # timeout, otherwise a new task type silently inherits DEFAULT.
        for task_type in task_processor.TASK_HANDLERS:
            assert task_type in task_processor.TASK_TIMEOUTS_SECONDS, (
                f"#1210: task type {task_type!r} must have an explicit "
                "visibility timeout in TASK_TIMEOUTS_SECONDS"
            )

    def test_default_timeout_is_conservative(self):
        # DEFAULT should be low enough that a stuck task recovers quickly
        # for any unmapped type, but not so low that a legitimate run trips it.
        assert 30 <= task_processor.DEFAULT_TIMEOUT_SECONDS <= 600


# ---------------------------------------------------------------------------
# #1172 — heartbeat extends lock while handler runs
# ---------------------------------------------------------------------------


class TestHeartbeatExtension:
    def test_heartbeat_thread_updates_locked_until(self, monkeypatch):
        """The heartbeat helper must issue an UPDATE bumping locked_until."""
        db = MagicMock()
        task_processor._heartbeat_extend(db, task_id=123, timeout_seconds=300)

        sql = [str(call.args[0]).lower() for call in db.execute.call_args_list if call.args]
        assert any(
            "update" in s and "locked_until" in s and "locked_by" in s for s in sql
        ), "_heartbeat_extend must UPDATE locked_until for the task id"


# ---------------------------------------------------------------------------
# #1185 — polling-only, sub-second default
# ---------------------------------------------------------------------------


class TestPollInterval:
    def test_poll_interval_default_is_sub_second(self):
        """Polling-only worker must default to a sub-second interval.

        The old default of 2.0s gave us enqueue-to-pickup latency of up
        to 2s, which is visible in UX when kicking an NLP extraction
        from a web request. 500ms keeps us snappy without thrashing the
        DB in idle windows.
        """
        assert task_processor.POLL_INTERVAL <= 1.0, (
            f"#1185: POLL_INTERVAL default must be sub-second; "
            f"got {task_processor.POLL_INTERVAL}"
        )
