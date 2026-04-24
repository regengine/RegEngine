# ============================================================
# FSMA 204 Recall — DB persistence helpers
# Split from monolithic fsma_recall.py.
#
# #1199: Recall drills are persisted in fsma.task_queue but they are
# NOT background jobs to execute — they are history rows. To prevent
# the generic task_processor worker from claiming and corrupting them:
#
#   1. They use a distinct `task_type='recall_drill'`, separate from
#      the state machine key `'recall'` which may exist elsewhere.
#   2. The task_queue column `status` is ALWAYS one of
#      {'pending', 'processing', 'completed', 'failed', 'dead'} (CHECK
#      constraint). The drill's own lifecycle (pending/in_progress/
#      completed/failed/cancelled) lives inside the JSONB payload under
#      `payload->>'status'`. The task_queue status on a recall_drill
#      row is ALWAYS `'completed'` so the task_processor never claims
#      it: the worker only claims rows with task_queue status 'pending'.
#   3. task_processor enforces a task_type allow-list and sends any
#      unknown task_type to the dead queue — but because recall_drill
#      rows are written as 'completed' they never reach the worker.
# ============================================================
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from .models import (
    RecallDrill,
    RecallSeverity,
    RecallStatus,
    RecallType,
)


# task_queue CHECK constraint values. See
# alembic/versions/20260329_task_queue_v050.py
_TASK_QUEUE_ALLOWED_STATUSES = {
    "pending", "processing", "completed", "failed", "dead"
}

# All recall_drill rows use this as their task_queue.status so the
# generic task_processor never claims them.  The drill's real status
# lives in payload->>'status'.
_RECALL_DRILL_TASK_QUEUE_STATUS = "completed"


def _get_db_engine():
    """Return a SQLAlchemy engine for the shared PostgreSQL DB, or None if unconfigured."""
    import os
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        return None
    try:
        from sqlalchemy import create_engine
        url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1) if db_url.startswith("postgresql://") else db_url
        return create_engine(url, pool_pre_ping=True, pool_size=2, max_overflow=4)
    except Exception:
        import logging
        logging.getLogger("fsma_recall").warning("Recall DB engine creation failed", exc_info=True)
        return None


def _upsert_drill_row(engine, drill: "RecallDrill") -> None:
    """Insert or update a recall drill row in fsma.task_queue.

    #1199: the row's task_queue.status is ALWAYS 'completed' so the
    generic task_processor never claims and corrupts the row. The real
    drill status lives in payload->>'status'.
    """
    import json as _json
    try:
        from sqlalchemy import text as _text
        payload = _json.dumps(drill.to_dict())
        with engine.connect() as conn:
            conn.execute(
                _text("""
                    INSERT INTO fsma.task_queue
                        (task_type, payload, status, tenant_id, created_at,
                         started_at, completed_at)
                    VALUES
                        ('recall_drill', CAST(:payload AS jsonb), :queue_status,
                         :tenant_id, :created_at, :started_at, :completed_at)
                    ON CONFLICT DO NOTHING
                """),
                {
                    "payload": payload,
                    # #1199: Never write drill status (in_progress, cancelled)
                    # into the task_queue status column — those values violate
                    # the CHECK constraint.  Use the sentinel completed status
                    # so the worker skips this row.
                    "queue_status": _RECALL_DRILL_TASK_QUEUE_STATUS,
                    "tenant_id": drill.tenant_id,
                    "created_at": drill.created_at,
                    "started_at": drill.started_at,
                    "completed_at": drill.completed_at,
                },
            )
            conn.commit()
    except Exception as exc:  # pragma: no cover
        import logging
        logging.getLogger("fsma_recall").warning("Failed to persist recall drill: %s", exc)


def _update_drill_row(engine, drill: "RecallDrill") -> None:
    """Update an existing recall drill row by drill_id stored in payload.

    #1199: task_queue.status stays 'completed' regardless of drill status.
    """
    import json as _json
    try:
        from sqlalchemy import text as _text
        payload = _json.dumps(drill.to_dict())
        with engine.connect() as conn:
            conn.execute(
                _text("""
                    UPDATE fsma.task_queue
                    SET payload       = CAST(:payload AS jsonb),
                        status        = :queue_status,
                        started_at    = :started_at,
                        completed_at  = :completed_at
                    WHERE task_type = 'recall_drill'
                      AND tenant_id  = :tenant_id
                      AND payload->>'drill_id' = :drill_id
                """),
                {
                    "payload": payload,
                    "queue_status": _RECALL_DRILL_TASK_QUEUE_STATUS,
                    "tenant_id": drill.tenant_id,
                    "started_at": drill.started_at,
                    "completed_at": drill.completed_at,
                    "drill_id": drill.drill_id,
                },
            )
            conn.commit()
    except Exception as exc:  # pragma: no cover
        import logging
        logging.getLogger("fsma_recall").warning("Failed to update recall drill: %s", exc)


def _load_drills_from_db(engine, tenant_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Query drill rows for a tenant from fsma.task_queue."""
    try:
        from sqlalchemy import text as _text
        with engine.connect() as conn:
            rows = conn.execute(
                _text("""
                    SELECT payload
                    FROM fsma.task_queue
                    WHERE task_type = 'recall_drill'
                      AND tenant_id  = :tenant_id
                    ORDER BY created_at DESC
                    LIMIT :limit
                """),
                {"tenant_id": tenant_id, "limit": limit},
            ).fetchall()
        return [row[0] for row in rows]
    except Exception as exc:  # pragma: no cover
        import logging
        logging.getLogger("fsma_recall").warning("Failed to load recall drills: %s", exc)
        return []


def _load_drill_by_id_from_db(engine, tenant_id: str, drill_id: str) -> Optional[Dict[str, Any]]:
    """Query a single drill row by drill_id from fsma.task_queue."""
    try:
        from sqlalchemy import text as _text
        with engine.connect() as conn:
            row = conn.execute(
                _text("""
                    SELECT payload
                    FROM fsma.task_queue
                    WHERE task_type = 'recall_drill'
                      AND tenant_id  = :tenant_id
                      AND payload->>'drill_id' = :drill_id
                    LIMIT 1
                """),
                {"tenant_id": tenant_id, "drill_id": drill_id},
            ).fetchone()
        return row[0] if row else None
    except Exception as exc:  # pragma: no cover
        import logging
        logging.getLogger("fsma_recall").warning("Failed to load recall drill by id: %s", exc)
        return None


def _dict_to_recall_drill(d: Dict[str, Any]) -> "RecallDrill":
    """Reconstruct a RecallDrill from its serialized dict (from DB payload)."""
    drill = RecallDrill(
        drill_id=d["drill_id"],
        tenant_id=d["tenant_id"],
        created_at=datetime.fromisoformat(d["created_at"]),
        drill_type=RecallType(d["drill_type"]),
        severity=RecallSeverity(d["severity"]),
        target_lot=d.get("target_lot"),
        target_gtin=d.get("target_gtin"),
        target_facility_gln=d.get("target_facility_gln"),
        initiated_by=d.get("initiated_by", "system"),
        reason=d.get("reason", "manual_drill"),
        description=d.get("description"),
        status=RecallStatus(d.get("status", "pending")),
        started_at=datetime.fromisoformat(d["started_at"]) if d.get("started_at") else None,
        completed_at=datetime.fromisoformat(d["completed_at"]) if d.get("completed_at") else None,
    )
    # Skip checksum recalculation side-effects; result is not reconstructed
    return drill
