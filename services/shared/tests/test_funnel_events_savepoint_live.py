"""Live-Postgres regression test: a failing funnel-event insert must not
poison the caller's transaction.

Before the savepoint fix, ``emit_funnel_event()`` ran its INSERT directly
on the borrowed session. On Postgres a failed statement (e.g. a
``funnel_events_tenant_id_fkey`` violation when the tenant row doesn't
exist) aborts the enclosing transaction, and the webhook ingest path's
later ``commit()`` then silently discarded every evidence row flushed
before it — ``fsma.cte_events``, ``fsma.cte_kdes``, ``fsma.hash_chain`` —
while still returning HTTP 200 "accepted" with hashes to the sender.
Observed live against the Inflow Lab signed ingest contract: the
simulator recorded ``delivery_status=posted`` while RegEngine kept
nothing.

sqlite does not share Postgres's aborted-transaction semantics, so the
sqlite unit tests in ``test_funnel_events.py`` cannot catch this.
Requires a Postgres ``DATABASE_URL`` with the migrated ``funnel_events``
table (skipped otherwise).
"""

from __future__ import annotations

import os
import uuid

import pytest
from shared.db_url import sync_postgres_url
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from services.shared.funnel_events import emit_funnel_event

DATABASE_URL = os.environ.get("DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL.startswith("postgresql"),
    reason="Postgres DATABASE_URL required — aborted-transaction semantics are Postgres-specific",
)


def test_failed_funnel_insert_does_not_poison_borrowed_transaction() -> None:
    engine = create_engine(sync_postgres_url(DATABASE_URL))
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        fk_present = session.execute(
            text(
                """
                SELECT 1 FROM information_schema.table_constraints
                WHERE table_name = 'funnel_events'
                  AND constraint_name = 'funnel_events_tenant_id_fkey'
                """
            )
        ).fetchone()
        session.rollback()
        if fk_present is None:
            pytest.skip(
                "funnel_events tenants FK not present — cannot force the failing insert"
            )

        # Session-local temp table; committed before the scenario so it
        # survives regardless of what happens to the next transaction.
        session.execute(
            text(
                "CREATE TEMPORARY TABLE funnel_savepoint_proof (marker TEXT NOT NULL)"
            )
        )
        session.commit()

        # Work flushed on the borrowed session BEFORE the failing emit —
        # stands in for the ingest path's evidence rows.
        marker = f"proof-{uuid.uuid4().hex}"
        session.execute(
            text("INSERT INTO funnel_savepoint_proof (marker) VALUES (:m)"),
            {"m": marker},
        )

        # Random tenant UUID with no tenants row → FK violation inside
        # emit_funnel_event. Best-effort telemetry must swallow it.
        inserted = emit_funnel_event(
            tenant_id=str(uuid.uuid4()),
            event_name="first_ingest",
            metadata={"source": "savepoint-regression"},
            db_session=session,
        )
        assert inserted is False

        # The caller's commit must succeed AND keep the earlier work. With
        # the pre-fix behavior this commit "succeeds" on an aborted
        # transaction and the row silently vanishes.
        session.commit()

        count = session.execute(
            text("SELECT COUNT(*) FROM funnel_savepoint_proof WHERE marker = :m"),
            {"m": marker},
        ).scalar_one()
        assert count == 1, (
            "row flushed before the failing funnel insert was lost — the "
            "borrowed transaction was poisoned by emit_funnel_event"
        )
    finally:
        session.close()
        engine.dispose()
