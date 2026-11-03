"""Live-DB regression: a replayed waiver does not sign off or comment twice.

``PATCH /api/v1/exceptions/{case_id}/waive`` records the authenticated
principal as the approver (S5, #3717). The route answers 200 whether or not
the case changed, so a retried or replayed request must be a no-op at the
service: ``ExceptionQueueService.waive_exception`` guards the UPDATE with
``status NOT IN ('resolved', 'waived')`` and only writes the signoff and the
status-change comment when a row actually moved. That guard lives in SQL,
which is why the router unit tests (MagicMock service) cannot prove it.

Drives the real router and the real service against a schema-at-head
PostgreSQL inside one transaction that is rolled back at the end. Requires
a designated live DB and skips without it (same gate as
test_exception_queue_uuid_arrays_live.py).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from shared.db_url import sync_postgres_url

from tests.migrations.rls_db import guarded_live_database_url

DATABASE_URL = guarded_live_database_url()
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="no designated live test DB (CI DATABASE_URL or REGENGINE_MIGRATION_TEST_DB) — skipping live waiver replay test",
)


def _count(session, table: str, case_id: str, extra: str = "") -> int:
    from sqlalchemy import text

    return session.execute(
        text(f"SELECT count(*) FROM fsma.{table} WHERE case_id = CAST(:cid AS uuid) {extra}"),  # noqa: S608 - fixed table names
        {"cid": case_id},
    ).scalar_one()


def test_waiver_replay_does_not_duplicate_signoff_or_comment(monkeypatch) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    from services.ingestion.app import authz, exception_router
    from services.ingestion.app.authz import IngestionPrincipal, get_ingestion_principal
    from services.shared.exception_queue import ExceptionQueueService

    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kw: (True, 99))

    engine = create_engine(sync_postgres_url(DATABASE_URL))
    tenant_id = str(uuid.uuid4())
    approver = f"session:{uuid.uuid4()}"
    principal = IngestionPrincipal(
        key_id=approver,
        tenant_id=tenant_id,
        scopes=["exceptions.read", "exceptions.write"],
        auth_mode="test",
    )

    with Session(engine) as session:
        session.execute(
            text("INSERT INTO tenants (id, name, slug, created_at) VALUES (CAST(:id AS uuid), :name, :slug, :now)"),
            {
                "id": tenant_id,
                "name": "waiver-replay-live-test",
                "slug": f"waiver-replay-live-{tenant_id[:8]}",
                "now": datetime.now(timezone.utc),
            },
        )
        svc = ExceptionQueueService(session)
        case = svc.create_exception(
            tenant_id=tenant_id,
            severity="warning",
            rule_category="kde_completeness",
            source_supplier="Live Replay Supplier",
        )
        case_id = case.case_id
        comments_before = _count(session, "exception_comments", case_id)
        assert _count(session, "exception_signoffs", case_id) == 0

        app = FastAPI()
        app.include_router(exception_router.router)
        app.dependency_overrides[get_ingestion_principal] = lambda: principal
        app.dependency_overrides[exception_router._get_db_session] = lambda: session
        client = TestClient(app)

        body = {"waiver_reason": "Low-risk supplier", "waiver_approved_by": "someone-else"}
        first = client.patch(f"/api/v1/exceptions/{case_id}/waive", json=body)
        assert first.status_code == 200, first.text
        replay = client.patch(f"/api/v1/exceptions/{case_id}/waive", json=body)
        assert replay.status_code == 200, replay.text

        row = session.execute(
            text(
                "SELECT status, waiver_approved_by, waiver_reason FROM fsma.exception_cases WHERE case_id = CAST(:cid AS uuid)"
            ),
            {"cid": case_id},
        ).one()
        assert tuple(row) == ("waived", approver, "Low-risk supplier")

        # Exactly one signoff, signed by the principal, never by the body.
        signoffs = session.execute(
            text("SELECT signoff_type, signed_by FROM fsma.exception_signoffs WHERE case_id = CAST(:cid AS uuid)"),
            {"cid": case_id},
        ).all()
        assert [tuple(r) for r in signoffs] == [("waive", approver)]

        # Exactly one status-change comment on top of the creation comment.
        assert _count(session, "exception_comments", case_id) == comments_before + 1
        assert _count(session, "exception_comments", case_id, "AND comment_type = 'status_change'") == 1

        session.rollback()
