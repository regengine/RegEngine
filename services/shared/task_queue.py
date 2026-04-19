"""Durable task queue backed by the ``fsma.task_queue`` Postgres table.

This is the implementation half of [ADR-002]. Replaces
``fastapi.BackgroundTasks.add_task(...)`` for work the client perceives
as durable — the old pattern lost tasks on SIGTERM during a Railway
deploy because the tasks ran in the request event loop.

Public API:
    - :func:`enqueue_task` — insert a row; returns the task id
    - :func:`register_task_handler` / :data:`TASK_HANDLERS` — handler registry
    - :class:`TaskWorker` — polling loop with ``FOR UPDATE SKIP LOCKED``
      claim semantics, retry with exponential backoff, stale-lock
      recovery

Concurrency model:
    - Single-threaded per worker instance.
    - Multiple worker replicas can run concurrently and claim
      disjoint rows via ``SELECT ... FOR UPDATE SKIP LOCKED`` — no
      Redis leader election required.
    - The V050 migration also installs a ``pg_notify`` trigger that
      fires on insert. This worker does **not** currently LISTEN to
      that channel (would require dropping to raw psycopg); it polls
      at ``poll_interval_seconds``. Wiring LISTEN to collapse the
      poll latency to ~ms is a follow-up once we have evidence that
      2 s wakeup is too slow.

Failure handling:
    - Handler raises → row goes back to ``pending`` with
      ``locked_until = now() + backoff`` and ``attempts`` incremented.
    - After ``max_attempts`` (default 3), row transitions to ``dead``
      and stops retrying.
    - Worker crashes mid-task → row stays ``processing`` with
      ``locked_until`` in the future. On the next poll cycle, any
      worker sees the stale lock (``locked_until < now()``) and
      releases the row back to ``pending``.

Idempotency:
    - This module does NOT enforce idempotency keys — ``enqueue_task``
      will happily write duplicate rows. Adding a unique index on
      ``(task_type, idempotency_key)`` is a follow-up migration noted
      in ADR-002's deferred questions.

[ADR-002]: docs/architecture/decisions/ADR-002-backgroundtasks-to-task-queue.md
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import uuid
from typing import Any, Callable, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger("task_queue")


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

TASK_HANDLERS: dict[str, Callable[..., Any]] = {}


class UnknownTaskType(RuntimeError):
    """Raised when the worker claims a task whose ``task_type`` has no
    registered handler. Such tasks transition straight to ``dead`` —
    retrying won't conjure a handler that isn't there."""


def register_task_handler(task_type: str, handler: Callable[..., Any]) -> None:
    """Register a handler for ``task_type``.

    Handlers can be sync or async. The worker wraps async handlers in
    :func:`asyncio.run` per invocation. Handler signatures must accept
    ``**kwargs`` matching the enqueued payload keys.

    Re-registering a handler for the same ``task_type`` logs a warning
    but is allowed (tests re-import modules; reloads shouldn't crash).
    """
    existing = TASK_HANDLERS.get(task_type)
    if existing is not None and existing is not handler:
        logger.warning(
            "task_handler_reregistered",
            extra={
                "task_type": task_type,
                "was": getattr(existing, "__qualname__", repr(existing)),
                "now": getattr(handler, "__qualname__", repr(handler)),
            },
        )
    TASK_HANDLERS[task_type] = handler


def clear_task_handlers() -> None:
    """Test helper — reset the registry between test cases."""
    TASK_HANDLERS.clear()


# ---------------------------------------------------------------------------
# Enqueue helper
# ---------------------------------------------------------------------------


def enqueue_task(
    db_session: Any,
    task_type: str,
    payload: dict[str, Any],
    *,
    tenant_id: Optional[str] = None,
    priority: int = 0,
    max_attempts: int = 3,
) -> int:
    """Insert a task into ``fsma.task_queue`` and return its id.

    Does NOT commit — the caller owns the session transaction. This lets
    the calling route enqueue a task in the same transaction that writes
    a status row (eliminating the Redis-lies-about-status problem
    described in ADR-002).

    Args:
        db_session: SQLAlchemy session (sync).
        task_type: String key matching a registered handler.
        payload: JSON-serializable kwargs for the handler. Must be
            JSON-round-trippable; e.g., datetimes must be pre-stringified.
        tenant_id: Optional tenant UUID as string. Populates the
            RLS-scoped column on the row.
        priority: Higher values claim earlier within a polling cycle.
        max_attempts: After this many failures the row goes to ``dead``.

    Returns:
        The ``id`` of the inserted row (``BIGSERIAL``).
    """
    result = db_session.execute(
        text(
            """
            INSERT INTO fsma.task_queue
                (task_type, payload, tenant_id, priority, max_attempts, status)
            VALUES
                (:task_type, CAST(:payload AS jsonb), :tenant_id, :priority, :max_attempts, 'pending')
            RETURNING id
            """
        ),
        {
            "task_type": task_type,
            "payload": json.dumps(payload),
            "tenant_id": tenant_id,
            "priority": priority,
            "max_attempts": max_attempts,
        },
    )
    task_id: int = result.scalar_one()
    return task_id


# ---------------------------------------------------------------------------
# Backoff math (pure function — unit-testable)
# ---------------------------------------------------------------------------


def compute_backoff_seconds(attempts: int, *, cap_seconds: int = 600) -> int:
    """Exponential backoff for retries.

    ``attempts`` is the number of PAST failures (0 after first failure,
    1 after second, etc.). Base delay is 30 s, doubles each time,
    capped at ``cap_seconds`` (default 10 min).

    Returns the number of seconds the worker should wait before
    re-attempting this row.
    """
    if attempts < 0:
        attempts = 0
    base = 30 * (2 ** attempts)
    return min(base, cap_seconds)


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------


class TaskWorker:
    """Polls ``fsma.task_queue`` and dispatches claimed rows to handlers.

    Usage (in a service's ``worker.py`` entrypoint)::

        from shared.database import engine
        from shared.task_queue import TaskWorker, register_task_handler
        from myservice.handlers import my_task_handler

        register_task_handler("my_task_type", my_task_handler)
        worker = TaskWorker(engine)
        worker.run()  # blocks until stop() is called or SIGTERM
    """

    DEFAULT_POLL_INTERVAL_SECONDS = 2.0
    DEFAULT_LOCK_DURATION_SECONDS = 300  # 5 minutes — must exceed the longest
    # expected handler wall-clock; stale-lock recovery kicks in after this.

    def __init__(
        self,
        engine: Engine,
        *,
        worker_id: Optional[str] = None,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        lock_duration_seconds: int = DEFAULT_LOCK_DURATION_SECONDS,
        task_types: Optional[list[str]] = None,
    ):
        """Build a worker bound to ``engine``.

        Args:
            engine: SQLAlchemy sync Engine pointed at the Postgres
                database hosting ``fsma.task_queue``.
            worker_id: Identifier written to ``locked_by`` on claim.
                Defaults to ``task_worker-<uuid_hex8>``; visible in
                logs for debugging stuck tasks.
            poll_interval_seconds: How long to sleep when the queue is
                empty before the next poll.
            lock_duration_seconds: How long a claim stays valid. Stale
                claims (worker crashed mid-task) are recovered on the
                next poll cycle of any worker.
            task_types: Optional allowlist. If set, this worker only
                claims rows whose ``task_type`` is in the list. Useful
                for dedicating workers to long-running vs quick tasks.
        """
        self.engine = engine
        self.worker_id = worker_id or f"task_worker-{uuid.uuid4().hex[:8]}"
        self.poll_interval = poll_interval_seconds
        self.lock_duration = lock_duration_seconds
        self.task_types = list(task_types) if task_types else None
        self._stop_event = threading.Event()

    # -- lifecycle ---------------------------------------------------------

    def stop(self) -> None:
        """Signal the run loop to exit after the current iteration."""
        self._stop_event.set()

    def run(self) -> None:
        """Main loop. Blocks until :meth:`stop` is called.

        Each iteration:
        1. Releases stale locks (worker died mid-task).
        2. Attempts to claim one row.
        3. Dispatches to the registered handler if found, else sleeps
           ``poll_interval`` seconds.

        Exceptions inside a single iteration are logged but don't kill
        the loop — the alternative (crash the worker) is worse because
        Railway would restart it and we'd be back to the same state.
        """
        logger.info("task_worker_started", extra={"worker_id": self.worker_id})
        while not self._stop_event.is_set():
            try:
                self._release_stale_locks()
                claimed = self._claim_one()
                if claimed is not None:
                    self._dispatch(claimed)
                    continue  # drain the queue as long as work is pending
                self._stop_event.wait(self.poll_interval)
            except Exception as exc:
                logger.exception(
                    "task_worker_iteration_error",
                    extra={"worker_id": self.worker_id, "error": str(exc)},
                )
                time.sleep(1.0)
        logger.info("task_worker_stopped", extra={"worker_id": self.worker_id})

    def run_once(self) -> Optional[int]:
        """Process up to one task and return its id, or ``None`` if the
        queue is empty. Used by tests and any synchronous caller that
        wants to drain deterministically."""
        self._release_stale_locks()
        claimed = self._claim_one()
        if claimed is None:
            return None
        self._dispatch(claimed)
        return int(claimed["id"])

    # -- claim + state transitions -----------------------------------------

    def _release_stale_locks(self) -> None:
        """Flip ``processing`` rows whose lock expired back to ``pending``."""
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE fsma.task_queue
                    SET status = 'pending',
                        locked_by = NULL,
                        locked_until = NULL,
                        started_at = NULL
                    WHERE status = 'processing'
                      AND locked_until IS NOT NULL
                      AND locked_until < NOW()
                    """
                )
            )

    def _claim_one(self) -> Optional[dict[str, Any]]:
        """Atomically claim the highest-priority eligible pending row.

        Eligible = ``status='pending'`` AND (``locked_until IS NULL``
        OR ``locked_until <= NOW()``). On a retrying row the
        ``locked_until`` serves as a "not-before" marker so backoff is
        observed without a separate column.

        Returns a dict with id/task_type/payload/attempts/max_attempts/
        tenant_id, or ``None`` if nothing is eligible.
        """
        params: dict[str, Any] = {
            "worker_id": self.worker_id,
            "lock_duration": self.lock_duration,
        }
        type_filter = ""
        if self.task_types:
            type_filter = "AND task_type = ANY(:task_types)"
            params["task_types"] = self.task_types

        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    f"""
                    WITH claim AS (
                        SELECT id FROM fsma.task_queue
                        WHERE status = 'pending'
                          AND (locked_until IS NULL OR locked_until <= NOW())
                          {type_filter}
                        ORDER BY priority DESC, created_at ASC
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                    )
                    UPDATE fsma.task_queue q
                    SET status = 'processing',
                        started_at = NOW(),
                        locked_by = :worker_id,
                        locked_until = NOW() + make_interval(secs => :lock_duration)
                    FROM claim
                    WHERE q.id = claim.id
                    RETURNING q.id, q.task_type, q.payload,
                              q.attempts, q.max_attempts, q.tenant_id
                    """
                ),
                params,
            ).fetchone()

        if row is None:
            return None

        payload_raw = row.payload
        payload = payload_raw if isinstance(payload_raw, dict) else json.loads(payload_raw)
        return {
            "id": row.id,
            "task_type": row.task_type,
            "payload": payload,
            "attempts": row.attempts,
            "max_attempts": row.max_attempts,
            "tenant_id": row.tenant_id,
        }

    def _dispatch(self, task: dict[str, Any]) -> None:
        """Run the registered handler and transition state accordingly."""
        handler = TASK_HANDLERS.get(task["task_type"])
        if handler is None:
            logger.error(
                "task_handler_missing",
                extra={"task_id": task["id"], "task_type": task["task_type"]},
            )
            self._mark_dead(
                task["id"],
                f"No handler registered for task_type={task['task_type']!r}",
            )
            return

        try:
            self._invoke(handler, task["payload"])
        except Exception as exc:
            logger.warning(
                "task_handler_raised",
                extra={
                    "task_id": task["id"],
                    "task_type": task["task_type"],
                    "attempts": task["attempts"] + 1,
                    "max_attempts": task["max_attempts"],
                    "error": str(exc),
                },
            )
            self._mark_failed(task, str(exc))
            return

        self._mark_completed(int(task["id"]))

    @staticmethod
    def _invoke(handler: Callable[..., Any], payload: dict[str, Any]) -> Any:
        """Run sync or async handler uniformly.

        ``asyncio.run()`` per task adds ~5 ms of event-loop construction
        overhead. Negligible at our scale (tens of tasks/minute); if
        handler throughput ever matters, swap this for a persistent
        :class:`asyncio.Runner` per worker. Called out in ADR-002
        consequences as the natural scale-up knob.
        """
        if asyncio.iscoroutinefunction(handler):
            return asyncio.run(handler(**payload))
        return handler(**payload)

    def _mark_completed(self, task_id: int) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE fsma.task_queue
                    SET status = 'completed',
                        completed_at = NOW(),
                        locked_by = NULL,
                        locked_until = NULL,
                        last_error = NULL
                    WHERE id = :id
                    """
                ),
                {"id": task_id},
            )

    def _mark_failed(self, task: dict[str, Any], error: str) -> None:
        """After a handler exception: schedule retry or transition to dead."""
        new_attempts = int(task["attempts"]) + 1
        max_attempts = int(task["max_attempts"])
        if new_attempts >= max_attempts:
            self._mark_dead(int(task["id"]), error)
            return

        backoff = compute_backoff_seconds(new_attempts)
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE fsma.task_queue
                    SET status = 'pending',
                        attempts = :attempts,
                        last_error = :error,
                        locked_by = NULL,
                        locked_until = NOW() + make_interval(secs => :backoff),
                        started_at = NULL
                    WHERE id = :id
                    """
                ),
                {
                    "id": int(task["id"]),
                    "attempts": new_attempts,
                    # Clamp to avoid unbounded growth if a handler
                    # returns a massive traceback — the row's
                    # ``last_error`` column is TEXT but operators don't
                    # need megabytes of noise.
                    "error": error[:4000] if error else None,
                    "backoff": backoff,
                },
            )

    def _mark_dead(self, task_id: int, error: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE fsma.task_queue
                    SET status = 'dead',
                        completed_at = NOW(),
                        last_error = :error,
                        locked_by = NULL,
                        locked_until = NULL
                    WHERE id = :id
                    """
                ),
                {"id": task_id, "error": error[:4000] if error else None},
            )
