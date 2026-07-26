"""Live-DB regression: exception_cases uuid[] columns accept list[str] binds.

fsma.exception_cases.linked_event_ids / linked_rule_evaluation_ids are
``uuid[]``. psycopg2 renders a Python ``list[str]`` parameter as ``text[]``,
and Postgres has no implicit text[]→uuid[] coercion, so without an explicit
``CAST(... AS uuid[])`` the INSERT in
``ExceptionQueueService.create_exception`` fails with DatatypeMismatch —
which took down /api/v1/ingest/csv in production on 2026-07-24 the first
time real CSV validation raised an exception case (same defect class as
``identity_resolution/merging.py``, fixed in #2629;
``agent_task_bridge.py`` already casts).

The pre-existing unit test (test_exception_queue_tenant_context.py) uses a
fake session, which is exactly why this shipped — a type mismatch only a
real Postgres can object to. This test requires DATABASE_URL and skips
without it (same pattern as the root e2e suites).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from tests.migrations.rls_db import guarded_live_database_url

DATABASE_URL = guarded_live_database_url()
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="no designated live test DB (CI DATABASE_URL or REGENGINE_MIGRATION_TEST_DB) — skipping live uuid[] bind test",
)


def test_create_exception_binds_uuid_arrays() -> None:
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    from services.shared.exception_queue import ExceptionQueueService

    engine = create_engine(DATABASE_URL)
    tenant_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())
    eval_id = str(uuid.uuid4())

    with Session(engine) as session:
        # Minimal tenant so FK constraints (if present) hold; everything
        # rolls back at the end — nothing is committed.
        session.execute(
            text("INSERT INTO tenants (id, name, slug, created_at) VALUES (CAST(:id AS uuid), :name, :slug, :now)"),
            {
                "id": tenant_id,
                "name": "uuid-array-live-test",
                "slug": f"uuid-array-live-{tenant_id[:8]}",
                "now": datetime.now(timezone.utc),
            },
        )

        svc = ExceptionQueueService(session)
        case = svc.create_exception(
            tenant_id=tenant_id,
            severity="critical",
            linked_event_ids=[event_id],
            linked_rule_evaluation_ids=[eval_id],
            rule_category="kde_completeness",
            source_supplier="Live Test Supplier",
        )

        row = session.execute(
            text(
                "SELECT linked_event_ids, linked_rule_evaluation_ids "
                "FROM fsma.exception_cases WHERE case_id = CAST(:cid AS uuid)"
            ),
            {"cid": case.case_id},
        ).fetchone()

        assert row is not None, "exception case row not persisted"
        assert [str(v) for v in row[0]] == [event_id]
        assert [str(v) for v in row[1]] == [eval_id]

        session.rollback()
