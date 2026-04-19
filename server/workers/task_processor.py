"""PostgreSQL-backed task processor — replaces Kafka consumers.

Polls the ``fsma.task_queue`` table for new work. Handles three task
types that previously required separate Kafka consumers:

  1. nlp_extraction — extract entities from ingested documents
  2. graph_update   — upsert extracted entities into the knowledge graph
  3. review_item    — record low-confidence extractions for human review

Delivery mechanism
------------------
This worker is **polling-only** by design (#1185). An earlier revision
of the migration added a ``fsma.notify_new_task()`` trigger that fired
``pg_notify('task_queue', ...)`` on INSERT and the docstring here
claimed the worker "optionally listens" for real-time wakeups — but
nothing ever issued ``LISTEN task_queue`` and the NOTIFYs were
broadcast to nobody. We removed the trigger (migration v059) and
reduced ``POLL_INTERVAL`` default to 500ms so enqueue latency is in
the hundreds of ms rather than seconds.

Usage:
    from server.workers.task_processor import start_task_worker, stop_task_worker
    start_task_worker()   # call in FastAPI lifespan startup
    stop_task_worker()    # call in FastAPI lifespan shutdown
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, Optional

import structlog

logger = structlog.get_logger("task-processor")

_worker_thread: Optional[threading.Thread] = None
_shutdown_event = threading.Event()

# #1225 — drain coordination.
#
# ``_current_task_id`` holds the id of the task currently executing inside
# ``_run_handler_with_heartbeat``. It is set immediately before the handler
# fires and cleared (under the lock) when the handler returns, fails, or
# the worker exits the loop. ``stop_task_worker`` reads this under the same
# lock to decide whether to release the lock on an abandoned row so another
# worker can pick it up immediately instead of waiting ``locked_until``
# minutes for the steal-window to expire.
_inflight_lock = threading.Lock()
_current_task_id: Optional[int] = None
_current_task_attempts: int = 0

# How often to poll the task_queue table (seconds). 500ms default balances
# enqueue latency (worst-case ~500ms) against idle-queue database traffic.
# The previous default of 2.0s combined with the never-consumed pg_notify
# trigger gave us the worst of both worlds: the delay of polling plus the
# overhead of the trigger (#1185).
POLL_INTERVAL = float(os.getenv("TASK_POLL_INTERVAL", "0.5"))

# How long a task can be locked before it's considered abandoned.
# Kept for backwards-compat: the new per-task-type map below is authoritative
# when present, and this value is the legacy global fallback (#1210).
LOCK_TIMEOUT_MINUTES = int(os.getenv("TASK_LOCK_TIMEOUT_MINUTES", "15"))

# Per-task-type visibility timeouts (#1210). Each value is the number of
# seconds a claimed task may hold its lock before another worker is allowed
# to steal it. Short tasks should recover quickly from a crashed worker;
# long tasks need a longer window so they are not re-claimed mid-run
# (which costs duplicate LLM calls / duplicate graph upserts).
TASK_TIMEOUTS_SECONDS: Dict[str, int] = {
    "nlp_extraction": 300,  # up to 5 min for a long document
    "graph_update": 120,    # Neo4j cluster hiccups
    "review_item": 30,      # near-instant, trivial DB write
}

# Fallback for task types not present in TASK_TIMEOUTS_SECONDS.
DEFAULT_TIMEOUT_SECONDS = 120

# How often the heartbeat thread should extend a running task's lock (#1172).
# Chosen so that even if the heartbeat is slightly late, the next tick
# still lands comfortably inside the visibility window.
HEARTBEAT_INTERVAL_SECONDS = 60

# How long ``stop_task_worker`` waits for the in-flight handler to return
# before emitting an "abandoned" log and releasing the row's lock so another
# worker can re-claim it (#1225). Defaults to 30s to match Gunicorn's
# graceful-timeout. Tune up if your handlers regularly run longer than 30s
# and you want clean drains; tune down for local-dev fast restarts.
SHUTDOWN_TIMEOUT_SECONDS = int(os.getenv("TASK_SHUTDOWN_TIMEOUT_SECONDS", "30"))

# Worker identity for distributed locking
WORKER_ID = f"worker-{os.getpid()}"


# ── Task handlers ────────────────────────────────────────────────

def _handle_nlp_extraction(payload: Dict[str, Any]) -> None:
    """Extract entities from an ingested document.

    Replaces Kafka topic: documents.ingested
    """
    try:
        from services.nlp.app.extractor import extract_entities
        doc_id = payload.get("document_id")
        text = payload.get("text", "")
        if not doc_id or not text:
            logger.warning("nlp_extraction_skip_empty", payload_keys=list(payload.keys()))
            return
        result = extract_entities(text)
        logger.info("nlp_extraction_complete", document_id=doc_id, entities=len(result))
    except ImportError:
        logger.debug("nlp_extractor_unavailable", exc_info=True)
    except Exception:
        logger.exception("nlp_extraction_failed")
        raise


def _handle_graph_update(payload: Dict[str, Any]) -> None:
    """Upsert extracted entities into the knowledge graph.

    Replaces Kafka topic: fsma.events.extracted / graph.update
    Falls back gracefully when Neo4j is not configured (PostgreSQL
    recursive CTEs handle lot tracing instead).
    """
    try:
        from services.graph.app.neo4j_utils import upsert_from_entities
        entities = payload.get("entities", [])
        if entities:
            upsert_from_entities(entities)
            logger.info("graph_update_complete", entities=len(entities))
    except ImportError:
        logger.debug("graph_neo4j_unavailable_skipping_upsert")
    except Exception:
        logger.exception("graph_update_failed")
        raise


def _handle_review_item(payload: Dict[str, Any]) -> None:
    """Record a low-confidence extraction for human review.

    Replaces Kafka topic: nlp.needs_review
    """
    try:
        from services.admin.app.metrics import get_hallucination_tracker
        tracker = get_hallucination_tracker()
        tracker.record(
            document_id=payload.get("document_id", ""),
            entity_type=payload.get("entity_type", "unknown"),
            confidence=payload.get("confidence", 0.0),
            extracted_text=payload.get("text", ""),
        )
        logger.info("review_item_recorded", document_id=payload.get("document_id"))
    except ImportError:
        logger.debug("hallucination_tracker_unavailable", exc_info=True)
    except Exception:
        logger.exception("review_item_failed")
        raise


TASK_HANDLERS: Dict[str, Callable[[Dict[str, Any]], None]] = {
    "nlp_extraction": _handle_nlp_extraction,
    "graph_update": _handle_graph_update,
    "review_item": _handle_review_item,
}


# #1199: recall_drill and recall (the state machine row) are persisted in
# fsma.task_queue for historical/state tracking, NOT as background work.
# The worker must never claim them even if they somehow end up with
# status='pending'. Keep this list narrowly scoped and update it when a
# new non-handler task_type starts sharing the queue.
NON_WORKER_TASK_TYPES = frozenset({
    "recall_drill",  # #1199 — recall drill history rows
    "recall",        # #1199 — recall state machine rows (future)
})


# ── Core worker loop ─────────────────────────────────────────────

def _claim_task(db) -> Optional[Dict[str, Any]]:
    """Atomically claim the next pending task using SELECT ... FOR UPDATE SKIP LOCKED.

    #1199: claim only rows whose task_type has a registered handler.
    This prevents the worker from claiming `recall_drill` history rows
    (which are persisted as status='completed' by recall persistence,
    but we keep this belt-and-suspenders guard in case a row ever
    ends up pending).

    #1241: must filter on ``scheduled_at <= NOW()`` so rows that
    :func:`_fail_task` pushed into exponential-backoff are not re-claimed
    before their backoff expires.  Prior to this fix the WHERE clause
    ignored ``scheduled_at`` entirely — _fail_task wrote a future value
    and the next 500ms poll grabbed it anyway, burning attempts in ~2s.

    Also fixes two latent bugs in the same SQL block:
      * ``lock_until`` was referenced but never defined — every call
        raised ``NameError`` under the outer try/except and no task
        was ever claimed in production.
      * ``row[5]`` read a sixth column that RETURNING never projected.
        Added ``visibility_timeout_seconds`` to RETURNING with a
        COALESCE default so ``row[5]`` is always a non-null int.
    """
    from sqlalchemy import text

    now = datetime.now(timezone.utc)
    default_timeout_seconds = DEFAULT_TIMEOUT_SECONDS
    # `lock_until` is the visibility deadline for this claim — after
    # this instant another worker may steal the row if we haven't
    # completed or heartbeated. Kept in minutes for ops ergonomics
    # (LOCK_TIMEOUT_MINUTES env).
    lock_until = now + timedelta(minutes=LOCK_TIMEOUT_MINUTES)

    # Only claim tasks whose task_type has a registered handler.  This
    # prevents us from fighting with recall_drill rows (which are owned
    # by the recall engine, not the worker).
    handler_types = list(TASK_HANDLERS.keys())

    row = db.execute(
        text("""
            UPDATE fsma.task_queue
            SET status = 'processing',
                started_at = :now,
                locked_by = :worker,
                locked_until = :lock_until,
                attempts = attempts + 1
            WHERE id = (
                SELECT id FROM fsma.task_queue
                WHERE task_type = ANY(:handler_types)
                  AND (
                      (status = 'pending' AND scheduled_at <= :now)
                      OR (status = 'processing' AND locked_until < :now)
                  )
                ORDER BY scheduled_at ASC, priority DESC, created_at ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id, task_type, payload, attempts, max_attempts,
                      COALESCE(visibility_timeout_seconds, :default_timeout)
        """),
        {
            "now": now,
            "worker": WORKER_ID,
            "lock_until": lock_until,
            "handler_types": handler_types,
            "default_timeout": default_timeout_seconds,
        },
    ).fetchone()

    if row:
        db.commit()
        task_type = row[1]
        timeout = row[5] or TASK_TIMEOUTS_SECONDS.get(task_type, default_timeout_seconds)
        return {
            "id": row[0],
            "task_type": task_type,
            "payload": row[2] if isinstance(row[2], dict) else {},
            "attempts": row[3],
            "max_attempts": row[4],
            "visibility_timeout_seconds": int(timeout),
        }
    return None


def _complete_task(db, task_id: int) -> None:
    from sqlalchemy import text
    db.execute(
        text("""
            UPDATE fsma.task_queue
            SET status = 'completed', completed_at = NOW(), locked_by = NULL, locked_until = NULL
            WHERE id = :id
        """),
        {"id": task_id},
    )
    db.commit()


def _heartbeat_extend(db, task_id: int, timeout_seconds: int) -> bool:
    """Bump ``locked_until`` on a task currently held by this worker (#1172).

    Returns True if the UPDATE affected one row (we still own the lock),
    False otherwise (another worker stole the task after its lock
    expired — the caller should abort).

    The ``locked_by = :worker`` predicate is the safety: if we no longer
    own the task we must NOT extend the lock.
    """
    from sqlalchemy import text

    result = db.execute(
        text(
            """
            UPDATE fsma.task_queue
            SET locked_until = NOW() + (:seconds || ' seconds')::interval
            WHERE id = :id
              AND locked_by = :worker
            """
        ),
        {"id": task_id, "worker": WORKER_ID, "seconds": int(timeout_seconds)},
    )
    db.commit()
    return bool(result.rowcount)


def _run_handler_with_heartbeat(
    db_factory,
    task_id: int,
    timeout_seconds: int,
    handler: Callable[[Dict[str, Any]], None],
    payload: Dict[str, Any],
    stop_event: Optional[threading.Event] = None,
    attempts: int = 0,
) -> None:
    """Execute ``handler`` while a background thread extends the task lock.

    The heartbeat thread runs every :data:`HEARTBEAT_INTERVAL_SECONDS` and
    bumps ``locked_until`` by ``timeout_seconds``. If the heartbeat UPDATE
    affects zero rows (we lost the lock — another worker stole the task
    after visibility expired), the heartbeat thread exits quietly; the
    handler continues to run but its results will be ignored by
    ``_complete_task`` if the lock was re-claimed.

    Uses ``db_factory`` (a callable returning a fresh Session) to obtain
    its own DB session so the heartbeat does not share state with the
    handler's session.
    """
    stop = stop_event or threading.Event()

    def _heartbeat_loop() -> None:
        while not stop.wait(timeout=HEARTBEAT_INTERVAL_SECONDS):
            hb_db = None
            try:
                hb_db = db_factory()
                still_ours = _heartbeat_extend(hb_db, task_id, timeout_seconds)
                if not still_ours:
                    logger.warning(
                        "heartbeat_lost_lock",
                        task_id=task_id,
                        worker=WORKER_ID,
                    )
                    return
            except Exception:
                logger.exception("heartbeat_error", task_id=task_id)
            finally:
                if hb_db is not None:
                    try:
                        hb_db.close()
                    except Exception:
                        pass

    heartbeat_thread = threading.Thread(
        target=_heartbeat_loop,
        daemon=True,
        name=f"task-heartbeat-{task_id}",
    )
    heartbeat_thread.start()
    # #1225 — publish the in-flight task id so ``stop_task_worker`` can
    # release the lock if the process is torn down mid-handler. We write
    # under ``_inflight_lock`` to serialize with the shutdown reader.
    global _current_task_id, _current_task_attempts
    with _inflight_lock:
        _current_task_id = task_id
        _current_task_attempts = attempts
    try:
        handler(payload)
    finally:
        stop.set()
        heartbeat_thread.join(timeout=HEARTBEAT_INTERVAL_SECONDS + 5)
        # Clear the in-flight marker — once the handler returns (whether
        # success or exception) the task is no longer at risk of mid-run
        # abandonment, so don't let a racing shutdown mistake it for
        # in-flight and double-release the lock.
        with _inflight_lock:
            if _current_task_id == task_id:
                _current_task_id = None
                _current_task_attempts = 0


def _retry_delay_seconds(attempts: int, cap_seconds: int = 3600) -> int:
    """Exponential backoff for failed task retries (#1181).

    1st retry  → ~60s
    2nd retry  → ~120s
    3rd retry  → ~240s
    N-th retry → min(60 * 2**(N-1), cap_seconds)

    Keeping attempts >= 1 gives a reasonable minimum floor even if a
    caller passes 0 or a negative by mistake.
    """
    attempts = max(1, int(attempts))
    # 2 ** (attempts-1) so first retry is 60s rather than 60 * 2 = 120s.
    delay = 60 * (2 ** (attempts - 1))
    return min(int(delay), cap_seconds)


def _fail_task(db, task_id: int, error: str, attempts: int, max_attempts: int) -> None:
    """Transition a task to a retry or terminal state.

    When ``attempts < max_attempts``:
        - status  → 'pending'
        - scheduled_at → NOW() + exponential backoff (#1181)
        - locked_by / locked_until cleared
    When ``attempts >= max_attempts``:
        - status  → 'dead'
        - locks cleared; scheduled_at left alone (dead never runs again).
    """
    from sqlalchemy import text

    if attempts >= max_attempts:
        db.execute(
            text(
                """
                UPDATE fsma.task_queue
                SET status = 'dead',
                    last_error = :error,
                    locked_by = NULL,
                    locked_until = NULL
                WHERE id = :id
                """
            ),
            {"id": task_id, "error": error[:2000]},
        )
    else:
        # Retry path — defer via scheduled_at so the next claim does NOT
        # pick this row up until the backoff window elapses. This is the
        # fix for #1181 — previously we flipped status back to 'pending'
        # and the 2s poller grabbed it within 2s, causing a tight retry
        # loop on persistent errors.
        delay = _retry_delay_seconds(attempts)
        db.execute(
            text(
                """
                UPDATE fsma.task_queue
                SET status = 'pending',
                    last_error = :error,
                    locked_by = NULL,
                    locked_until = NULL,
                    scheduled_at = NOW() + (:delay_seconds || ' seconds')::interval
                WHERE id = :id
                """
            ),
            {"id": task_id, "error": error[:2000], "delay_seconds": int(delay)},
        )
    db.commit()


def _worker_loop() -> None:
    """Main worker loop — poll task_queue and process tasks."""
    logger.info("task_worker_started", worker_id=WORKER_ID, poll_interval=POLL_INTERVAL)

    # Try to get a database session
    try:
        from shared.database import SessionLocal
    except ImportError:
        logger.warning("task_worker_no_database_session_factory")
        return

    while not _shutdown_event.is_set():
        db = None
        try:
            db = SessionLocal()
            task = _claim_task(db)

            if task is None:
                db.close()
                _shutdown_event.wait(timeout=POLL_INTERVAL)
                continue

            task_type = task["task_type"]
            handler = TASK_HANDLERS.get(task_type)

            if handler is None:
                logger.warning("unknown_task_type", task_type=task_type, task_id=task["id"])
                _fail_task(db, task["id"], f"Unknown task type: {task_type}", task["attempts"], task["max_attempts"])
                db.close()
                continue

            try:
                # Run with a heartbeat thread that keeps locked_until fresh
                # while the handler is executing (#1172). The heartbeat
                # uses its own DB session so the handler's session stays
                # uncontended.
                timeout = task.get("visibility_timeout_seconds") or TASK_TIMEOUTS_SECONDS.get(
                    task_type, DEFAULT_TIMEOUT_SECONDS
                )
                _run_handler_with_heartbeat(
                    db_factory=SessionLocal,
                    task_id=task["id"],
                    timeout_seconds=int(timeout),
                    handler=handler,
                    payload=task["payload"],
                    attempts=task["attempts"],
                )
                _complete_task(db, task["id"])
                logger.debug("task_completed", task_id=task["id"], task_type=task_type)
            except Exception as exc:
                logger.warning(
                    "task_failed",
                    task_id=task["id"],
                    task_type=task_type,
                    error=str(exc),
                    attempt=task["attempts"],
                )
                try:
                    _fail_task(db, task["id"], str(exc), task["attempts"], task["max_attempts"])
                except Exception:
                    logger.exception("task_fail_update_error")

        except Exception:
            logger.exception("task_worker_loop_error")
            _shutdown_event.wait(timeout=POLL_INTERVAL)
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception:
                    pass

    logger.info("task_worker_stopped", worker_id=WORKER_ID)


# ── Public API ───────────────────────────────────────────────────

def enqueue_task(
    task_type: str,
    payload: Dict[str, Any],
    tenant_id: Optional[str] = None,
    priority: int = 0,
    idempotency_key: Optional[str] = None,
) -> Optional[int]:
    """Enqueue a task into the PostgreSQL task queue.

    This is the producer-side replacement for Kafka's send().
    Returns the task ID on success, None on failure.

    Idempotency (#1164)
    -------------------
    When ``idempotency_key`` is provided, the insert uses
    ``ON CONFLICT (tenant_id, idempotency_key) DO NOTHING``. A retried
    call with the same (tenant_id, key) pair returns the existing task
    ID — the task is enqueued exactly once. If the key is ``None`` the
    legacy behavior is preserved (duplicates are possible).

    Recommended keys:

    * NLP extraction: ``f"nlp_extraction:{document_id}"``
    * Graph update:   ``f"graph_update:{document_id}"``
    * Review item:    ``f"review_item:{document_id}:{entity_type}"``
    """
    try:
        from shared.database import SessionLocal
        from sqlalchemy import text
        import json

        db = SessionLocal()
        try:
            if idempotency_key is not None:
                # ON CONFLICT … DO NOTHING returns no rows if there was a
                # conflict, so we fall through to a SELECT to retrieve the
                # already-enqueued task's id. This is the at-least-once-safe
                # shape used by the idempotency migration for task_queue.
                row = db.execute(
                    text(
                        """
                        INSERT INTO fsma.task_queue
                            (task_type, payload, tenant_id, priority, idempotency_key)
                        VALUES
                            (:task_type, :payload::jsonb, :tenant_id, :priority, :key)
                        ON CONFLICT (tenant_id, idempotency_key)
                            WHERE idempotency_key IS NOT NULL
                            DO NOTHING
                        RETURNING id
                        """
                    ),
                    {
                        "task_type": task_type,
                        "payload": json.dumps(payload),
                        "tenant_id": tenant_id,
                        "priority": priority,
                        "key": idempotency_key,
                    },
                ).fetchone()
                db.commit()
                if row:
                    return row[0]

                # Conflict hit — look up the existing row and return its id
                existing = db.execute(
                    text(
                        """
                        SELECT id FROM fsma.task_queue
                        WHERE tenant_id IS NOT DISTINCT FROM :tenant_id
                          AND idempotency_key = :key
                        LIMIT 1
                        """
                    ),
                    {"tenant_id": tenant_id, "key": idempotency_key},
                ).fetchone()
                if existing:
                    logger.info(
                        "enqueue_task_idempotent_hit",
                        task_type=task_type,
                        tenant_id=tenant_id,
                        idempotency_key=idempotency_key,
                        task_id=existing[0],
                    )
                    return existing[0]
                # If the partial unique index is missing from the DB (e.g.
                # migration not yet applied), fall back to the legacy path
                # below. This keeps enqueue semantically correct during a
                # rolling deploy at the cost of allowing duplicates until
                # the migration lands.
                logger.warning(
                    "enqueue_task_idempotency_fallback",
                    task_type=task_type,
                    hint="idempotency_key column or partial index not present",
                )

            row = db.execute(
                text("""
                    INSERT INTO fsma.task_queue (task_type, payload, tenant_id, priority)
                    VALUES (:task_type, :payload::jsonb, :tenant_id, :priority)
                    RETURNING id
                """),
                {
                    "task_type": task_type,
                    "payload": json.dumps(payload),
                    "tenant_id": tenant_id,
                    "priority": priority,
                },
            ).fetchone()
            db.commit()
            return row[0] if row else None
        finally:
            db.close()
    except Exception:
        logger.exception("enqueue_task_failed", task_type=task_type)
        return None


def start_task_worker() -> None:
    """Start the background task worker thread."""
    global _worker_thread
    if os.getenv("DISABLE_TASK_WORKER", "false").lower() in ("1", "true", "yes"):
        logger.info("task_worker_disabled_by_env")
        return

    _shutdown_event.clear()
    _worker_thread = threading.Thread(target=_worker_loop, daemon=True, name="task-worker")
    _worker_thread.start()


def _release_abandoned_task_lock(task_id: int, attempts: int) -> None:
    """Best-effort release of the lock on a task we abandoned at shutdown (#1225).

    If the process is torn down mid-handler, the claimed row stays in
    ``status='processing'`` until ``locked_until`` expires — anywhere
    from 30s to 5 minutes depending on task_type. That latency is
    unnecessary when we KNOW we're abandoning: flip the row straight
    back to ``pending`` and decrement ``attempts`` so the graceful
    handover does not count against the task's ``max_attempts`` budget.

    This runs in the ``stop_task_worker`` thread, so it intentionally
    opens its own short-lived session and swallows all errors — the
    caller is already on its way out the door and a DB blip here must
    not block process exit.
    """
    try:
        from shared.database import SessionLocal
        from sqlalchemy import text
    except ImportError:
        logger.warning("abandoned_task_release_no_db_module", task_id=task_id)
        return

    db = None
    try:
        db = SessionLocal()
        result = db.execute(
            text(
                """
                UPDATE fsma.task_queue
                SET status = 'pending',
                    locked_by = NULL,
                    locked_until = NULL,
                    attempts = GREATEST(attempts - 1, 0)
                WHERE id = :id
                  AND locked_by = :worker
                  AND status = 'processing'
                """
            ),
            {"id": task_id, "worker": WORKER_ID},
        )
        db.commit()
        released = bool(result.rowcount)
        logger.warning(
            "task_abandoned_on_shutdown",
            task_id=task_id,
            worker=WORKER_ID,
            attempts=attempts,
            released=released,
        )
    except Exception:
        logger.exception("abandoned_task_release_failed", task_id=task_id)
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


def stop_task_worker(timeout_seconds: Optional[int] = None) -> None:
    """Stop the background task worker thread gracefully (#1225).

    Flow:
      1. Set the shutdown event. The worker loop observes it between
         iterations and exits after the current handler returns.
      2. Join the worker thread with ``timeout_seconds`` (default
         ``SHUTDOWN_TIMEOUT_SECONDS`` env, 30s) — matched to Gunicorn's
         graceful-timeout so we don't get SIGKILL'd mid-drain.
      3. If the thread is STILL alive after the timeout, the handler
         is wedged. Consult ``_current_task_id`` under lock: if a task
         is in flight we emit a loud "abandoned" telemetry event AND
         issue a best-effort ``UPDATE`` to release the row's lock so
         another worker can re-claim it immediately (no wait for the
         visibility window to expire).

    The ``attempts - 1`` decrement on release is the key correctness
    bit: a graceful hand-off between workers must not count as a
    failed attempt, otherwise a deploy-heavy day would burn through
    ``max_attempts`` on perfectly healthy tasks (#1225).
    """
    _shutdown_event.set()
    if _worker_thread is None:
        return

    effective_timeout = (
        timeout_seconds if timeout_seconds is not None else SHUTDOWN_TIMEOUT_SECONDS
    )
    _worker_thread.join(timeout=effective_timeout)

    # If the worker is still alive the handler is stuck — sample the
    # in-flight state and hand the task back to the queue.
    if _worker_thread.is_alive():
        with _inflight_lock:
            stranded_id = _current_task_id
            stranded_attempts = _current_task_attempts
        if stranded_id is not None:
            _release_abandoned_task_lock(stranded_id, stranded_attempts)
        else:
            logger.warning(
                "task_worker_join_timeout_no_inflight",
                worker=WORKER_ID,
                timeout=effective_timeout,
            )
    else:
        logger.info(
            "task_worker_joined",
            worker=WORKER_ID,
            timeout=effective_timeout,
        )
