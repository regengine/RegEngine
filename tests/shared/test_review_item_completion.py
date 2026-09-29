"""Review tasks complete only after durable persistence or a known duplicate.

The real handler, tracker, and worker transitions run against disposable SQLite
review storage. Only the PostgreSQL queue session and unavailable dependencies
are simulated; these tests do not establish PostgreSQL RLS behavior.
"""

from __future__ import annotations

import builtins
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from server.workers import task_processor
from services.admin.app import metrics
from services.admin.app.sqlalchemy_models import ReviewItemModel

TENANT_ID = "11111111-2222-3333-4444-555555555555"
OTHER_TENANT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _payload():
    return {
        "document_id": "doc-review",
        "doc_hash": "hash-review",
        "entity_type": "OBLIGATION",
        "confidence": 0.42,
        "text": "<script>remove()</script>Facilities must retain records.",
        "tenant_id": OTHER_TENANT_ID,
    }


@pytest.fixture
def review_worker(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    ReviewItemModel.__table__.create(engine)

    class ReviewSession(Session):
        pass

    factory = sessionmaker(bind=engine, class_=ReviewSession)
    tracker = metrics.HallucinationTracker(factory)
    monkeypatch.setattr(metrics, "get_hallucination_tracker", lambda: tracker)
    queue_db = MagicMock()
    queue_db.execute.return_value.rowcount = 1
    database = ModuleType("services.admin.app.database")
    database.SessionLocal = lambda: queue_db
    database.arm_global_admin_context = lambda session: None
    monkeypatch.setitem(sys.modules, "services.admin.app.database", database)

    def run(payload, attempts=1, tenant_id=TENANT_ID):
        queue_db.reset_mock()
        task = {
            "id": 71,
            "task_type": "review_item",
            "payload": payload,
            "tenant_id": tenant_id,
            "attempts": attempts,
            "max_attempts": 3,
        }
        with (
            patch.object(task_processor, "_shutdown_event") as shutdown,
            patch.object(task_processor, "_claim_task", return_value=task),
        ):
            shutdown.is_set.side_effect = [False, True]
            task_processor._worker_loop()
        queue_db.execute.assert_called_once()
        queue_db.commit.assert_called_once()
        sql, params = queue_db.execute.call_args.args
        return str(sql), params

    yield engine, ReviewSession, run
    engine.dispose()


@pytest.mark.parametrize("attempts,want_status", [(1, "pending"), (3, "dead")])
@pytest.mark.parametrize(
    "failure",
    [
        "metrics_import",
        "sanitizer_import",
        "flush_import",
        "commit_import",
        "flush_runtime",
        "commit_runtime",
        "duplicate_not_found",
    ],
)
def test_review_failure_never_completes(review_worker, monkeypatch, failure, attempts, want_status):
    engine, review_session, run = review_worker
    payload = _payload()
    if failure in {"metrics_import", "sanitizer_import"}:
        missing_module = (
            "services.admin.app.metrics" if failure == "metrics_import" else "services.admin.app.text_sanitize"
        )
        original_import = builtins.__import__

        def missing_dependency(name, *args, **kwargs):
            if name == missing_module:
                raise ImportError("review dependency unavailable")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", missing_dependency)
    elif failure == "duplicate_not_found":
        # A real NOT NULL violation enters the tracker's duplicate recovery;
        # no matching durable record exists, so LookupError must reach retries.
        payload["confidence"] = None
    else:
        error_type = ImportError if failure.endswith("import") else RuntimeError

        def fail_storage(*args, **kwargs):
            raise error_type("review storage unavailable")

        monkeypatch.setattr(review_session, failure.split("_")[0], fail_storage)

    sql, params = run(payload, attempts)

    assert f"status = '{want_status}'" in sql
    assert "status = 'completed'" not in sql
    assert params["id"] == 71
    assert params["error"]
    if want_status == "pending":
        assert params["delay_seconds"] == 60
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(ReviewItemModel)) == 0


def test_review_completion_preserves_storage_tenant_and_duplicate_replay(review_worker):
    engine, _, run = review_worker
    for tenant_id in (TENANT_ID, TENANT_ID, OTHER_TENANT_ID):
        sql, _ = run(_payload(), tenant_id=tenant_id)
        assert "status = 'completed'" in sql

    with Session(engine) as session:
        rows = session.scalars(select(ReviewItemModel)).all()
        assert len(rows) == 2
        assert {row.tenant_id for row in rows} == {UUID(TENANT_ID), UUID(OTHER_TENANT_ID)}
        assert all(row.status == "PENDING" for row in rows)
        assert all(row.text_raw == "Facilities must retain records." for row in rows)
        assert all(row.extraction["attributes"]["document_id"] == "doc-review" for row in rows)
