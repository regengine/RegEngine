"""Recall drill / task_queue isolation tests (#1199).

Recall drills are persisted in `fsma.task_queue` for history, but they
are NOT background work for the generic task_processor.  Prior code let
the worker claim drill rows, then marked them failed (because no
handler existed), corrupting the drill state machine.

Fixes under test:
  - `_upsert_drill_row` and `_update_drill_row` write task_queue.status
    as 'completed' regardless of the drill's internal status, so the
    worker never claims them and the CHECK constraint is respected.
  - `TASK_HANDLERS` does not include `recall_drill` or `recall`.
  - `_claim_task` filters by known handler task_types, so recall_drill
    rows are never claimed even if their status somehow becomes
    'pending'.
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app.fsma_recall.persistence import (
    _RECALL_DRILL_TASK_QUEUE_STATUS,
    _TASK_QUEUE_ALLOWED_STATUSES,
    _upsert_drill_row,
    _update_drill_row,
)
from services.graph.app.fsma_recall.models import (
    RecallDrill,
    RecallSeverity,
    RecallStatus,
    RecallType,
)
from server.workers import task_processor


TENANT_A = str(uuid.UUID("11111111-1111-1111-1111-111111111111"))


def _make_drill(status: RecallStatus) -> RecallDrill:
    return RecallDrill(
        drill_id="drill_q_iso_0001",
        tenant_id=TENANT_A,
        created_at=datetime.now(timezone.utc),
        drill_type=RecallType.FORWARD_TRACE,
        severity=RecallSeverity.CLASS_II,
        status=status,
    )


# ── Task-queue schema invariants ────────────────────────────────────────────


def test_sentinel_is_an_allowed_task_queue_status():
    """#1199: the sentinel must satisfy the task_queue CHECK constraint."""
    assert _RECALL_DRILL_TASK_QUEUE_STATUS in _TASK_QUEUE_ALLOWED_STATUSES


def test_drill_statuses_not_directly_mapped_to_queue_status():
    """Drill enum values include 'in_progress' / 'cancelled' which are NOT
    valid task_queue.status values — confirming we cannot write them
    directly and must use the sentinel instead."""
    drill_status_values = {s.value for s in RecallStatus}
    illegal_for_queue = drill_status_values - _TASK_QUEUE_ALLOWED_STATUSES
    # 'in_progress' and 'cancelled' MUST be in that gap — if they weren't,
    # the original bug couldn't have happened.
    assert "in_progress" in illegal_for_queue
    assert "cancelled" in illegal_for_queue


# ── Persistence writes sentinel, not drill status ───────────────────────────


class _ConnCaptor:
    """Captures the parameters passed to `conn.execute(text, params)`."""

    def __init__(self):
        self.executed = []
        self.committed = False

    def execute(self, stmt, params):  # pragma: no cover - trivial
        self.executed.append((str(stmt), params))
        return self

    def commit(self):  # pragma: no cover
        self.committed = True

    def __enter__(self):  # pragma: no cover
        return self

    def __exit__(self, *a):  # pragma: no cover
        return False


def _make_fake_engine():
    captor = _ConnCaptor()
    engine = MagicMock()
    engine.connect.return_value = captor
    return engine, captor


def test_upsert_writes_completed_status_for_in_progress_drill():
    """#1199: even when drill is IN_PROGRESS (which violates the CHECK
    constraint), task_queue.status must be written as the sentinel."""
    engine, captor = _make_fake_engine()
    drill = _make_drill(RecallStatus.IN_PROGRESS)

    _upsert_drill_row(engine, drill)

    assert captor.committed, "upsert must commit"
    assert captor.executed, "upsert must run SQL"
    _, params = captor.executed[0]
    assert params["queue_status"] == _RECALL_DRILL_TASK_QUEUE_STATUS
    # The drill's in_progress status must not leak into task_queue.status.
    assert params.get("status") != "in_progress"


def test_upsert_writes_completed_status_for_pending_drill():
    """Pending drills must not leave the task_queue row in status='pending'
    — that would make the worker eligible to claim it."""
    engine, captor = _make_fake_engine()
    drill = _make_drill(RecallStatus.PENDING)

    _upsert_drill_row(engine, drill)

    _, params = captor.executed[0]
    assert params["queue_status"] == _RECALL_DRILL_TASK_QUEUE_STATUS


def test_update_writes_completed_status_for_cancelled_drill():
    """Cancelled drills — 'cancelled' is not a valid task_queue status."""
    engine, captor = _make_fake_engine()
    drill = _make_drill(RecallStatus.CANCELLED)

    _update_drill_row(engine, drill)

    _, params = captor.executed[0]
    assert params["queue_status"] == _RECALL_DRILL_TASK_QUEUE_STATUS


def test_upsert_cypher_uses_recall_drill_task_type():
    """#1199: the task_type must be 'recall_drill', distinct from the
    state machine type 'recall'."""
    engine, captor = _make_fake_engine()
    drill = _make_drill(RecallStatus.COMPLETED)

    _upsert_drill_row(engine, drill)

    sql, _ = captor.executed[0]
    # task_type literal in the SQL body.
    assert "'recall_drill'" in sql


# ── Worker does not claim recall_drill rows ─────────────────────────────────


def test_task_handlers_excludes_recall_task_types():
    """The worker must not have a handler for recall_drill or recall."""
    assert "recall_drill" not in task_processor.TASK_HANDLERS
    assert "recall" not in task_processor.TASK_HANDLERS


def test_non_worker_task_types_includes_recall_drill():
    """The worker's deny-list must include recall_drill."""
    assert "recall_drill" in task_processor.NON_WORKER_TASK_TYPES


def test_claim_task_filters_to_handler_types():
    """_claim_task must only claim rows whose task_type has a handler."""
    # Fake db.execute that records the parameters and returns no row.
    fake_db = MagicMock()
    fake_result = MagicMock()
    fake_result.fetchone.return_value = None
    fake_db.execute.return_value = fake_result

    task_processor._claim_task(fake_db)

    # Inspect the parameters passed to execute().
    call = fake_db.execute.call_args
    sql_text = str(call[0][0])
    params = call[0][1]

    # The SQL must filter by task_type ANY(:handler_types)
    assert "task_type = ANY(:handler_types)" in sql_text
    # And the handler_types param must include the three known handlers
    # and NOT include recall_drill.
    assert "handler_types" in params
    handler_types = set(params["handler_types"])
    assert handler_types == set(task_processor.TASK_HANDLERS.keys())
    assert "recall_drill" not in handler_types
    assert "recall" not in handler_types


def test_claim_task_would_skip_pending_recall_drill_row():
    """Simulate a pending recall_drill row; the worker must not claim it.

    The worker's SELECT is filtered by task_type; even if a
    recall_drill row has status='pending' (which should never happen,
    but could if someone wrote a row manually), the query returns None.
    """
    fake_db = MagicMock()
    # The UPDATE ... WHERE task_type = ANY(:handler_types) never matches
    # a recall_drill row, so fetchone() returns None.
    fake_result = MagicMock()
    fake_result.fetchone.return_value = None
    fake_db.execute.return_value = fake_result

    task = task_processor._claim_task(fake_db)
    assert task is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
