"""PostgreSQL-backed task processor — replaces Kafka consumers.

Polls the fsma.task_queue table and optionally listens via pg_notify
for real-time wakeups. Handles three task types that previously
required separate Kafka consumers:

  1. nlp_extraction — extract entities from ingested documents
  2. graph_update   — upsert extracted entities into the knowledge graph
  3. review_item    — record low-confidence extractions for human review

Usage:
    from app.workers.task_processor import start_task_worker, stop_task_worker
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

# How often to poll when pg_notify is unavailable (seconds)
POLL_INTERVAL = float(os.getenv("TASK_POLL_INTERVAL", "2.0"))

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


# ── Core worker loop ─────────────────────────────────────────────

def _claim_task(db) -> Optional[Dict[str, Any]]:
    """Atomically claim the next pending task.

    Respects ``scheduled_at`` (#1181 — rows with a future ``scheduled_at``
    are deferred) and per-row ``visibility_timeout_seconds`` (#1210 — so
    a short task's lock does not hold the slot for 15 minutes on crash).

    Falls back to the legacy claim SQL if the v059 migration has not yet
    run (the new columns don't exist) — the fallback matches the shape
    committed in v050 so the worker continues to function during a
    rolling deploy.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import ProgrammingError

    now = datetime.now(timezone.utc)
    default_timeout_seconds = DEFAULT_TIMEOUT_SECONDS

    try:
        row = db.execute(
            text(
                """
                UPDATE fsma.task_queue AS tq
                SET status = 'processing',
                    started_at = :now,
                    locked_by = :worker,
                    locked_until = :now + (
                        COALESCE(tq.visibility_timeout_seconds, :default_timeout)
                        || ' seconds'
                    )::interval,
                    attempts = tq.attempts + 1
                FROM (
                    SELECT id FROM fsma.task_queue
                    WHERE (
                            status = 'pending'
                            AND COALESCE(scheduled_at, created_at) <= :now
                          )
                       OR (status = 'processing' AND locked_until < :now)
                    ORDER BY priority DESC, created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                ) AS picked
                WHERE tq.id = picked.id
                RETURNING tq.id, tq.task_type, tq.payload, tq.attempts,
                          tq.max_attempts, tq.visibility_timeout_seconds
                """
            ),
            {"now": now, "worker": WORKER_ID, "default_timeout": default_timeout_seconds},
        ).fetchone()
    except ProgrammingError:
        # Migration v059 not applied — columns scheduled_at /
        # visibility_timeout_seconds don't exist. Use the legacy shape.
        db.rollback()
        lock_until = now + timedelta(minutes=LOCK_TIMEOUT_MINUTES)
        row = db.execute(
            text(
                """
                UPDATE fsma.task_queue
                SET status = 'processing',
                    started_at = :now,
                    locked_by = :worker,
                    locked_until = :lock_until,
                    attempts = attempts + 1
                WHERE id = (
                    SELECT id FROM fsma.task_queue
                    WHERE status = 'pending'
                       OR (status = 'processing' AND locked_until < :now)
                    ORDER BY priority DESC, created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING id, task_type, payload, attempts, max_attempts
                """
            ),
            {"now": now, "worker": WORKER_ID, "lock_until": lock_until},
        ).fetchone()
        if row:
            db.commit()
            return {
                "id": row[0],
                "task_type": row[1],
                "payload": row[2] if isinstance(row[2], dict) else {},
                "attempts": row[3],
                "max_attempts": row[4],
                "visibility_timeout_seconds": default_timeout_seconds,
            }
        return None

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
    try:
        handler(payload)
    finally:
        stop.set()
        heartbeat_thread.join(timeout=HEARTBEAT_INTERVAL_SECONDS + 5)


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


def stop_task_worker() -> None:
    """Stop the background task worker thread gracefully."""
    _shutdown_event.set()
    if _worker_thread is not None:
        _worker_thread.join(timeout=10)
        logger.info("task_worker_joined")
