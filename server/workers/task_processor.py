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

# How long a task can be locked before it's considered abandoned
LOCK_TIMEOUT_MINUTES = int(os.getenv("TASK_LOCK_TIMEOUT_MINUTES", "15"))

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
    """
    from sqlalchemy import text

    now = datetime.now(timezone.utc)
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
                      status = 'pending'
                      OR (status = 'processing' AND locked_until < :now)
                  )
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id, task_type, payload, attempts, max_attempts
        """),
        {
            "now": now,
            "worker": WORKER_ID,
            "lock_until": lock_until,
            "handler_types": handler_types,
        },
    ).fetchone()

    if row:
        db.commit()
        return {
            "id": row[0],
            "task_type": row[1],
            "payload": row[2] if isinstance(row[2], dict) else {},
            "attempts": row[3],
            "max_attempts": row[4],
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


def _fail_task(db, task_id: int, error: str, attempts: int, max_attempts: int) -> None:
    from sqlalchemy import text
    new_status = "dead" if attempts >= max_attempts else "failed"
    if new_status == "failed":
        # Return to pending for retry
        new_status = "pending"
    db.execute(
        text("""
            UPDATE fsma.task_queue
            SET status = :status, last_error = :error, locked_by = NULL, locked_until = NULL
            WHERE id = :id
        """),
        {"id": task_id, "status": new_status, "error": error[:2000]},
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
                handler(task["payload"])
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
) -> Optional[int]:
    """Enqueue a task into the PostgreSQL task queue.

    This is the producer-side replacement for Kafka's send().
    Returns the task ID on success, None on failure.
    """
    try:
        from shared.database import SessionLocal
        from sqlalchemy import text
        import json

        db = SessionLocal()
        try:
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
