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
      ``scheduled_at = now() + backoff`` and ``attempts`` incremented.
    - After ``max_attempts`` (default 3), row transitions to ``dead``
      and stops retrying.
    - Worker crashes mid-task → row stays ``processing`` with
      ``locked_until`` in the future. On the next poll cycle, any
      worker sees the stale lock (``locked_until < now()``) and
      releases the row back to ``pending``.

Idempotency:
    - When callers supply ``idempotency_key``, the queue uses the
      existing partial unique index on ``(tenant_id, idempotency_key)``
      and returns the already-enqueued task id on conflict.

[ADR-002]: docs/architecture/decisions/ADR-002-backgroundtasks-to-task-queue.md
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Callable, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger("task_queue")

TASK_QUEUE_STATUSES = ("pending", "processing", "completed", "failed", "dead")
_TASK_QUEUE_GAUGES: dict[str, Any] = {}


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
    idempotency_key: Optional[str] = None,
    scheduled_at: Optional[datetime] = None,
    visibility_timeout_seconds: Optional[int] = None,
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
        idempotency_key: Optional tenant-scoped dedupe key. When present,
            ``tenant_id`` is required and repeat enqueues return the
            existing task id.
        scheduled_at: Optional not-before timestamp. Defaults to now.
        visibility_timeout_seconds: Optional per-task lock duration for
            long-running handlers.

    Returns:
        The ``id`` of the inserted row (``BIGSERIAL``).
    """
    if idempotency_key is not None and not tenant_id:
        raise ValueError("tenant_id is required when idempotency_key is provided")

    params = {
        "task_type": task_type,
        "payload": json.dumps(payload),
        "tenant_id": tenant_id,
        "priority": priority,
        "max_attempts": max_attempts,
        "idempotency_key": idempotency_key,
        "scheduled_at": scheduled_at,
        "visibility_timeout_seconds": visibility_timeout_seconds,
    }

    if idempotency_key is not None:
        result = db_session.execute(
            text(
                """
                INSERT INTO fsma.task_queue
                    (
                        task_type, payload, tenant_id, priority, max_attempts,
                        status, idempotency_key, scheduled_at,
                        visibility_timeout_seconds
                    )
                VALUES
                    (
                        :task_type, CAST(:payload AS jsonb), :tenant_id,
                        :priority, :max_attempts, 'pending', :idempotency_key,
                        COALESCE(CAST(:scheduled_at AS TIMESTAMPTZ), NOW()),
                        :visibility_timeout_seconds
                    )
                ON CONFLICT (tenant_id, idempotency_key)
                    WHERE idempotency_key IS NOT NULL
                    DO NOTHING
                RETURNING id
                """
            ),
            params,
        )
        row = result.fetchone()
        if row is not None:
            return int(row[0])

        existing = db_session.execute(
            text(
                """
                SELECT id
                FROM fsma.task_queue
                WHERE tenant_id = :tenant_id
                  AND idempotency_key = :idempotency_key
                LIMIT 1
                """
            ),
            {
                "tenant_id": tenant_id,
                "idempotency_key": idempotency_key,
            },
        ).fetchone()
        if existing is None:
            raise RuntimeError("idempotent enqueue conflicted but existing task was not found")
        return int(existing[0])

    result = db_session.execute(
        text(
            """
            INSERT INTO fsma.task_queue
                (
                    task_type, payload, tenant_id, priority, max_attempts,
                    status, scheduled_at, visibility_timeout_seconds
                )
            VALUES
                (
                    :task_type, CAST(:payload AS jsonb), :tenant_id,
                    :priority, :max_attempts, 'pending',
                    COALESCE(CAST(:scheduled_at AS TIMESTAMPTZ), NOW()),
                    :visibility_timeout_seconds
                )
            RETURNING id
            """
        ),
        params,
    )
    task_id: int = result.scalar_one()
    return task_id


# ---------------------------------------------------------------------------
# Operator helpers
# ---------------------------------------------------------------------------


def get_task_queue_summary(db_session: Any) -> dict[str, Any]:
    """Return read-only queue health for operator surfaces and metrics."""

    count_rows = db_session.execute(
        text(
            """
            SELECT status, COUNT(*) AS count
            FROM fsma.task_queue
            GROUP BY status
            """
        )
    ).fetchall()
    counts = {status: 0 for status in TASK_QUEUE_STATUSES}
    counts.update({row[0]: int(row[1]) for row in count_rows})

    row = db_session.execute(
        text(
            """
            SELECT
                COUNT(*) FILTER (
                    WHERE status = 'pending' AND scheduled_at > NOW()
                ) AS retrying_count,
                COUNT(*) FILTER (
                    WHERE status = 'processing'
                      AND locked_until IS NOT NULL
                      AND locked_until < NOW()
                ) AS stale_processing_count,
                EXTRACT(EPOCH FROM (
                    NOW() - MIN(created_at) FILTER (
                        WHERE status = 'pending' AND scheduled_at <= NOW()
                    )
                )) AS oldest_pending_age_seconds,
                EXTRACT(EPOCH FROM (
                    NOW() - MIN(created_at) FILTER (WHERE status = 'dead')
                )) AS oldest_dead_age_seconds
            FROM fsma.task_queue
            """
        )
    ).fetchone()

    summary = {
        "counts_by_status": counts,
        "retrying_count": int(row[0] or 0) if row else 0,
        "stale_processing_count": int(row[1] or 0) if row else 0,
        "oldest_pending_age_seconds": _float_or_none(row[2]) if row else None,
        "oldest_dead_age_seconds": _float_or_none(row[3]) if row else None,
    }
    _update_task_queue_metrics(summary)
    return summary


def replay_dead_tasks(
    db_session: Any,
    *,
    ids: Optional[list[int | str]] = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Reset dead task_queue rows to pending without deleting history."""

    if limit < 1 or limit > 1000:
        raise ValueError("limit must be between 1 and 1000")

    results: list[dict[str, Any]] = []
    target_ids: list[str]

    if ids:
        normalized_ids = [str(task_id) for task_id in ids]
        placeholders = ", ".join(f":id_{idx}" for idx in range(len(normalized_ids)))
        rows = db_session.execute(
            text(
                f"""
                SELECT id::text, status
                FROM fsma.task_queue
                WHERE id::text IN ({placeholders})
                """
            ),
            {f"id_{idx}": task_id for idx, task_id in enumerate(normalized_ids)},
        ).fetchall()
        found = {row[0]: row[1] for row in rows}
        target_ids = []
        for task_id in normalized_ids:
            status = found.get(task_id)
            if status is None:
                results.append({"id": task_id, "success": False, "error": "not_found"})
            elif status != "dead":
                results.append(
                    {
                        "id": task_id,
                        "success": False,
                        "error": f"status_is_{status}_not_dead",
                    }
                )
            else:
                target_ids.append(task_id)
    else:
        rows = db_session.execute(
            text(
                """
                SELECT id::text
                FROM fsma.task_queue
                WHERE status = 'dead'
                ORDER BY created_at ASC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).fetchall()
        target_ids = [row[0] for row in rows]

    for task_id in target_ids:
        update_result = db_session.execute(
            text(
                """
                UPDATE fsma.task_queue
                SET status = 'pending',
                    attempts = 0,
                    last_error = NULL,
                    locked_by = NULL,
                    locked_until = NULL,
                    started_at = NULL,
                    completed_at = NULL,
                    scheduled_at = NOW()
                WHERE id::text = :id
                  AND status = 'dead'
                """
            ),
            {"id": task_id},
        )
        if update_result.rowcount == 1:
            results.append({"id": task_id, "success": True, "error": None})
        else:
            results.append(
                {
                    "id": task_id,
                    "success": False,
                    "error": "no_rows_updated_race_condition",
                }
            )

    replayed = sum(1 for result in results if result["success"])
    return {
        "replayed": replayed,
        "failed": len(results) - replayed,
        "results": results,
    }


def _float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    return float(value)


def _get_task_queue_gauge(name: str, description: str, labelnames: tuple[str, ...] = ()):
    cache_key = f"{name}:{','.join(labelnames)}"
    if cache_key in _TASK_QUEUE_GAUGES:
        return _TASK_QUEUE_GAUGES[cache_key]
    try:
        from prometheus_client import REGISTRY, Gauge

        try:
            gauge = Gauge(name, description, labelnames)
        except ValueError:
            gauge = REGISTRY._names_to_collectors.get(name)  # type: ignore[attr-defined]
        if gauge is not None:
            _TASK_QUEUE_GAUGES[cache_key] = gauge
        return gauge
    except ImportError:
        return None


def _update_task_queue_metrics(summary: dict[str, Any]) -> None:
    depth = _get_task_queue_gauge(
        "regengine_task_queue_depth",
        "Current number of fsma.task_queue rows by status.",
        ("status",),
    )
    if depth is not None:
        for status in TASK_QUEUE_STATUSES:
            depth.labels(status=status).set(summary["counts_by_status"].get(status, 0))

    metric_specs = (
        (
            "regengine_task_queue_retrying",
            "Current pending task_queue rows deferred by scheduled_at.",
            "retrying_count",
            0,
        ),
        (
            "regengine_task_queue_stale_processing",
            "Current processing task_queue rows whose locks have expired.",
            "stale_processing_count",
            0,
        ),
        (
            "regengine_task_queue_oldest_pending_age_seconds",
            "Age in seconds of the oldest eligible pending task_queue row.",
            "oldest_pending_age_seconds",
            0.0,
        ),
        (
            "regengine_task_queue_oldest_dead_age_seconds",
            "Age in seconds of the oldest dead task_queue row.",
            "oldest_dead_age_seconds",
            0.0,
        ),
    )
    for name, description, field, default in metric_specs:
        gauge = _get_task_queue_gauge(name, description)
        if gauge is not None:
            gauge.set(summary[field] if summary[field] is not None else default)


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
    base = 30 * (2**attempts)
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

    def start(self) -> threading.Thread:
        """Start the worker loop in a daemon thread and return it."""
        t = threading.Thread(target=self.run, daemon=True, name=f"task-worker-{self.worker_id}")
        t.start()
        return t

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
                        started_at = NULL,
                        scheduled_at = NOW()
                    WHERE status = 'processing'
                      AND locked_until IS NOT NULL
                      AND locked_until < NOW()
                    """
                )
            )

    def _claim_one(self) -> Optional[dict[str, Any]]:
        """Atomically claim the highest-priority eligible pending row.

        Eligible = ``status='pending'`` and ``scheduled_at <= NOW()``.
        ``locked_until`` remains purely a processing visibility timeout.

        Weighted fair queuing (#1644): instead of a pure global
        ``ORDER BY priority DESC, created_at ASC`` (which lets one
        tenant with a large backlog starve all others), we first pick
        the *tenant* whose oldest eligible task arrived earliest, then
        pick the highest-priority eligible task for that tenant.  This
        gives round-robin fairness across tenants while still honouring
        per-tenant priority ordering.

        The ``DISTINCT ON (tenant_id)`` subquery returns one candidate
        row per tenant (the highest-priority, then oldest, task for that
        tenant).  The outer ``ORDER BY`` picks the winning candidate —
        the tenant whose best task scored highest, breaking ties by
        arrival order.

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
                    WITH per_tenant AS (
                        -- One best candidate per tenant: highest priority,
                        -- then earliest created_at (DISTINCT ON keeps the
                        -- first row per group after ORDER BY).
                        SELECT DISTINCT ON (tenant_id)
                               id, tenant_id, priority, scheduled_at, created_at
                        FROM fsma.task_queue
                        WHERE status = 'pending'
                          AND scheduled_at <= NOW()
                          AND (locked_until IS NULL OR locked_until <= NOW())
                          {type_filter}
                        ORDER BY tenant_id,
                                 priority DESC,
                                 scheduled_at ASC,
                                 created_at ASC
                    ),
                    winner AS (
                        -- Among the per-tenant winners, pick the one whose
                        -- best task scored highest (priority → arrival).
                        SELECT id FROM per_tenant
                        ORDER BY priority DESC, scheduled_at ASC, created_at ASC
                        LIMIT 1
                    ),
                    claim AS (
                        SELECT id FROM fsma.task_queue
                        WHERE id = (SELECT id FROM winner)
                        FOR UPDATE SKIP LOCKED
                    )
                    UPDATE fsma.task_queue q
                    SET status = 'processing',
                        started_at = NOW(),
                        locked_by = :worker_id,
                        locked_until = NOW() + make_interval(
                            secs => COALESCE(q.visibility_timeout_seconds, :lock_duration)
                        )
                    FROM claim
                    WHERE q.id = claim.id
                    RETURNING q.id, q.task_type, q.payload,
                              q.attempts, q.max_attempts, q.tenant_id,
                              q.visibility_timeout_seconds
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
            self._mark_dead(int(task["id"]), error, attempts=new_attempts)
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
                        locked_until = NULL,
                        scheduled_at = NOW() + make_interval(secs => :backoff),
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

    def _mark_dead(self, task_id: int, error: str, *, attempts: Optional[int] = None) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE fsma.task_queue
                    SET status = 'dead',
                        completed_at = NOW(),
                        last_error = :error,
                        locked_by = NULL,
                        locked_until = NULL,
                        attempts = COALESCE(:attempts, attempts)
                    WHERE id = :id
                    """
                ),
                {
                    "id": task_id,
                    "error": error[:4000] if error else None,
                    "attempts": attempts,
                },
            )
