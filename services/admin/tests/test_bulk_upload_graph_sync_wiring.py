"""Regression tests for #1411 — bulk_upload graph-sync wiring.

Context
-------
Before #1411, ``execute_bulk_commit`` synced the first 100 events to Neo4j
via ``supplier_graph_sync.record_cte_event`` and appended a warning claiming
a background worker would sync the rest. No such worker wiring existed:
the bulk-upload path never enqueued anything to Redis ``neo4j-sync``, and
``fsma_sync_worker`` was fed exclusively by
``shared/canonical_persistence/migration.publish_graph_sync``. Net effect:
a 500-event bulk import silently dropped 400 Neo4j nodes (facility, TLC,
CTEEvent) — the warning was response-body-only cover.

Fix
---
Events 1..100 still sync through the live Neo4j driver (fast path for
small imports). Events 101..N are enqueued into ``graph_outbox`` via
``enqueue_graph_write``; the existing ``GraphOutboxDrainer`` replays them
with retry + backoff. graph_outbox was built for exactly this use case
(#1398) and has been idling since — admin bulk-upload is its first real
caller.

Invariants under test
---------------------
* Small import (≤100 events): every event goes through the synchronous
  path; nothing lands in graph_outbox.
* Large import (>100 events): first 100 sync, remainder enqueued to
  graph_outbox with the correct Cypher + params and a stable dedupe key.
* Warning text is accurate: ``graph_sync_deferred`` now reflects the
  enqueued-for-async-replay reality, not a phantom worker.
* Enqueue failures degrade gracefully — the bulk import succeeds and a
  warning is surfaced so the user knows some events didn't make the
  outbox.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.bulk_upload.transaction_manager import execute_bulk_commit
from app.sqlalchemy_models import (
    SupplierCTEEventModel,
    SupplierFacilityFTLCategoryModel,
    SupplierFacilityModel,
    SupplierTraceabilityLotModel,
    TenantModel,
    UserModel,
)


TEST_TENANT_ID = UUID("00000000-0000-0000-0000-000000000010")
TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000011")


# ---------------------------------------------------------------------------
# Fixture: in-memory SQLite with the bulk_upload tables *and* graph_outbox
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    table_bindings = [
        TenantModel.__table__,
        UserModel.__table__,
        SupplierFacilityModel.__table__,
        SupplierFacilityFTLCategoryModel.__table__,
        SupplierTraceabilityLotModel.__table__,
        SupplierCTEEventModel.__table__,
    ]
    for table in table_bindings:
        table.create(bind=engine)

    # Mirror the Postgres ``graph_outbox`` migration as SQLite TEXT columns.
    # This matches tests/test_graph_outbox.py so we exercise the same dev
    # fallback path ``enqueue_graph_write`` takes on non-Postgres sessions.
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE graph_outbox (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id       TEXT NULL,
                operation       TEXT NOT NULL,
                cypher          TEXT NOT NULL,
                params          TEXT NOT NULL DEFAULT '{}',
                status          TEXT NOT NULL DEFAULT 'pending',
                attempts        INTEGER NOT NULL DEFAULT 0,
                max_attempts    INTEGER NOT NULL DEFAULT 10,
                last_error      TEXT NULL,
                enqueued_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                drained_at      TEXT NULL,
                next_attempt_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                dedupe_key      TEXT NULL
            )
        """))

    SessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )
    session = SessionLocal()
    session.add(
        TenantModel(
            id=TEST_TENANT_ID,
            name="Test Tenant",
            slug="test-tenant",
            status="active",
            settings={},
        )
    )
    session.add(
        UserModel(
            id=TEST_USER_ID,
            email="supplier@example.com",
            password_hash="hashed-password",
            status="active",
            is_sysadmin=False,
        )
    )
    session.commit()

    try:
        yield session
    finally:
        session.close()
        try:
            with engine.begin() as conn:
                conn.execute(text("DROP TABLE graph_outbox"))
        except Exception:
            pass
        for table in reversed(table_bindings):
            table.drop(bind=engine)
        engine.dispose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_payload(event_count: int) -> dict[str, list[dict[str, Any]]]:
    """Build a minimal normalized payload with ``event_count`` events.

    All events belong to a single facility and a single TLC; this is
    sufficient to exercise the graph-sync fanout without dragging in
    facility-level validation noise.
    """
    base_time = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
    events = []
    for i in range(event_count):
        # Distinct event_time per row so the sort in execute_bulk_commit
        # produces a deterministic ordering, and distinct timestamps land
        # distinct payload hashes (avoids duplicate-Merkle edge cases).
        t = base_time.replace(minute=i % 60, second=(i // 60) % 60)
        events.append({
            "facility_name": "Bulk Test Packhouse",
            "tlc_code": "TLC-2026-BULK-1001",
            "cte_type": "shipping",
            "event_time": t.isoformat(),
            "kde_data": {"quantity": i + 1, "unit_of_measure": "cases"},
            "obligation_ids": [],
        })
    return {
        "facilities": [
            {
                "name": "Bulk Test Packhouse",
                "street": "500 Harvest Rd",
                "city": "Salinas",
                "state": "CA",
                "postal_code": "93901",
                "roles": ["Packer"],
            },
        ],
        "ftl_scopes": [],
        "tlcs": [
            {
                "facility_name": "Bulk Test Packhouse",
                "tlc_code": "TLC-2026-BULK-1001",
                "product_description": "Baby Spinach",
                "status": "active",
            },
        ],
        "events": events,
    }


def _outbox_rows(session: Session) -> list[dict[str, Any]]:
    return [
        dict(r) for r in session.execute(
            text(
                "SELECT id, tenant_id, operation, cypher, params, status, "
                "dedupe_key FROM graph_outbox ORDER BY id ASC"
            )
        ).mappings().all()
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_small_import_all_sync_no_outbox_enqueue(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    """50 events → all sync via record_cte_event, outbox stays empty.

    The fast path is preserved for imports that fit under the
    ``MAX_SYNC_EVENTS`` cap. We assert:
      * every event hit the live Neo4j driver,
      * no rows landed in ``graph_outbox``,
      * no ``graph_sync_deferred`` warning (there's nothing deferred).
    """
    import app.bulk_upload.transaction_manager as tx_manager

    sync_calls: list[dict[str, Any]] = []

    def _record_event(**kwargs: Any) -> None:
        sync_calls.append(kwargs)

    monkeypatch.setattr(
        tx_manager.supplier_graph_sync, "record_cte_event", _record_event
    )
    monkeypatch.setattr(
        tx_manager.supplier_graph_sync,
        "record_facility_ftl_scoping",
        lambda **_kwargs: None,
    )

    current_user = db_session.get(UserModel, TEST_USER_ID)
    assert current_user is not None

    payload = _build_payload(event_count=50)
    summary = execute_bulk_commit(
        db_session,
        tenant_id=TEST_TENANT_ID,
        current_user=current_user,
        normalized_payload=payload,
    )

    # All 50 events chained.
    assert summary["events_chained"] == 50

    # All 50 sent through the sync path.
    assert len(sync_calls) == 50

    # No outbox rows.
    assert _outbox_rows(db_session) == []

    # No graph_sync_deferred warning — nothing was deferred.
    for warning in summary.get("sync_warnings", []):
        assert not warning.startswith("graph_sync_deferred:"), (
            f"Unexpected deferred-sync warning on small import: {warning}"
        )


def test_large_import_first_100_sync_remainder_enqueued(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    """500 events → 100 sync, 400 in graph_outbox with correct payload.

    This is the exact scenario #1411 describes: pre-fix, a 500-event
    import silently dropped 400 Neo4j nodes. Post-fix:
      * first 100 hit the sync path,
      * remaining 400 are durable graph_outbox rows,
      * each row carries the exact Cypher (``CTE_EVENT_QUERY``) and a
        parameter dict the drainer can replay,
      * each row has a stable ``bulk_upload:<event_id>`` dedupe_key so
        bulk-commit retries don't double-enqueue,
      * the warning text now describes the real behavior.
    """
    import app.bulk_upload.transaction_manager as tx_manager
    from app.supplier_graph_sync import CTE_EVENT_QUERY

    sync_calls: list[dict[str, Any]] = []

    def _record_event(**kwargs: Any) -> None:
        sync_calls.append(kwargs)

    monkeypatch.setattr(
        tx_manager.supplier_graph_sync, "record_cte_event", _record_event
    )
    monkeypatch.setattr(
        tx_manager.supplier_graph_sync,
        "record_facility_ftl_scoping",
        lambda **_kwargs: None,
    )

    current_user = db_session.get(UserModel, TEST_USER_ID)
    assert current_user is not None

    payload = _build_payload(event_count=500)
    summary = execute_bulk_commit(
        db_session,
        tenant_id=TEST_TENANT_ID,
        current_user=current_user,
        normalized_payload=payload,
    )

    # Postgres truth: all 500 events chained.
    assert summary["events_chained"] == 500

    # Fast path: exactly MAX_SYNC_EVENTS (100) hit Neo4j synchronously.
    assert len(sync_calls) == 100

    # Durable path: 400 rows in graph_outbox.
    rows = _outbox_rows(db_session)
    assert len(rows) == 400, (
        f"expected 400 outbox rows for the overflow beyond MAX_SYNC_EVENTS=100; "
        f"got {len(rows)}"
    )

    # Every row carries the exact Cypher the production Neo4j writer
    # uses. Drift between the sync path's Cypher and the outbox Cypher
    # would produce divergent graph shapes depending on import size —
    # that's exactly what #1411 wanted to eliminate.
    for row in rows:
        assert row["cypher"] == CTE_EVENT_QUERY
        assert row["operation"] == "cte_event_recorded"
        assert row["status"] == "pending"
        assert row["tenant_id"] == str(TEST_TENANT_ID)
        # Stable, retry-safe dedupe tied to the canonical event id.
        assert row["dedupe_key"] is not None
        assert row["dedupe_key"].startswith("bulk_upload:")

        params = json.loads(row["params"])
        # Every required Cypher parameter is present and tenant-tagged.
        assert params["tenant_id"] == str(TEST_TENANT_ID)
        assert params["cte_type"] == "shipping"
        assert params["tlc_code"] == "TLC-2026-BULK-1001"
        assert params["facility_name"] == "Bulk Test Packhouse"
        # CTEEvent merkle metadata must survive the JSON round-trip so
        # the drainer can replay graph writes with the same audit
        # fingerprint the Postgres row carries.
        assert params["merkle_hash"]
        assert isinstance(params["sequence_number"], int)
        # Dedupe key must reference the same cte_event_id in the params.
        assert row["dedupe_key"] == f"bulk_upload:{params['cte_event_id']}"

    # Every enqueued row's dedupe key is unique (no accidental collision
    # that would silently collapse two distinct events).
    dedupe_keys = [row["dedupe_key"] for row in rows]
    assert len(set(dedupe_keys)) == len(dedupe_keys)

    # Every enqueued event is one of the Postgres-chained events (the
    # drainer will never replay a phantom event).
    db_events = db_session.execute(
        text("SELECT id FROM supplier_cte_events")
    ).scalars().all()
    db_event_ids = {str(eid) for eid in db_events}
    for row in rows:
        params = json.loads(row["params"])
        assert params["cte_event_id"] in db_event_ids

    # The warning now describes the real behavior — async replay via
    # graph_outbox, not the pre-fix phantom "background worker".
    deferred_warnings = [
        w for w in summary.get("sync_warnings", [])
        if w.startswith("graph_sync_deferred:")
    ]
    assert len(deferred_warnings) == 1
    assert "400" in deferred_warnings[0]
    assert "graph_outbox" in deferred_warnings[0], (
        "warning text must reflect the real async-replay mechanism "
        "(graph_outbox) so operators can find the drainer; prior to "
        "#1411 the warning claimed a 'background worker' that didn't exist"
    )


def test_outbox_enqueue_failure_rolls_back_bulk_import(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    """If graph_outbox enqueue raises, the whole bulk import rolls back.

    Contract (graph_outbox.py lines 14-19): the outbox enqueue shares the
    canonical transaction — "either both land or neither lands." An enqueue
    failure must therefore roll back every canonical Postgres row the same
    commit would have written, so the caller can safely retry the entire
    payload without producing drift between Postgres and the graph mirror.

    This test replaces a pre-fix test that asserted the opposite (enqueue
    failure silently swallowed, canonical rows committed anyway). #1695
    flagged that behavior as a contract violation.
    """
    import app.bulk_upload.transaction_manager as tx_manager

    monkeypatch.setattr(
        tx_manager.supplier_graph_sync, "record_cte_event", lambda **_kw: None
    )
    monkeypatch.setattr(
        tx_manager.supplier_graph_sync,
        "record_facility_ftl_scoping",
        lambda **_kw: None,
    )

    def _boom(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("simulated outbox insert failure")

    monkeypatch.setattr(tx_manager, "enqueue_graph_write", _boom)

    current_user = db_session.get(UserModel, TEST_USER_ID)
    assert current_user is not None

    payload = _build_payload(event_count=150)  # > MAX_SYNC_EVENTS so enqueue runs

    with pytest.raises(RuntimeError, match="simulated outbox insert failure"):
        execute_bulk_commit(
            db_session,
            tenant_id=TEST_TENANT_ID,
            current_user=current_user,
            normalized_payload=payload,
        )

    # Rollback guarantee: NO canonical event rows landed. Before the #1695
    # fix this assertion read `== 150` because the canonical commit ran
    # before the (post-commit) outbox enqueue; that ordering produced the
    # drift the outbox was designed to close.
    db_session.rollback()
    db_events = db_session.execute(
        text("SELECT count(*) FROM supplier_cte_events")
    ).scalar()
    assert db_events == 0

    # And no outbox rows either — same transaction, same rollback.
    assert _outbox_rows(db_session) == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
