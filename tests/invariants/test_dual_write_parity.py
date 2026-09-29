"""WS-1a — dual-write parity invariant (freeze the divergence, #1335 step 1).

Two live write paths persist traceability events with different
idempotency-key formulas: the canonical writer
(``fsma.traceability_events``) and the legacy dual-write shim
(``fsma.cte_events``). The only field that joins one real-world event
across both stores is ``sha256_hash``. Until the legacy path is retired
(WS-1d), this suite is the standing CI invariant that the two stores
cannot silently desync:

1. ``test_ingest_writes_both_stores_with_matching_hash`` — a real ingest
   through ``CanonicalEventStore(dual_write=True)`` against a migrated
   Postgres must produce BOTH rows, joined by identical ``sha256_hash``.
2. ``test_no_legacy_orphans_after_ingest`` — the reconciliation
   invariant promoted from ``scripts/validate_data_integrity.py``
   (#2521): a ``cte_events`` row with no canonical twin means a canonical
   write was lost or swallowed (#1277) and is a hard failure. The
   reverse direction (canonical-only rows) is expected — several
   ingestion paths run ``dual_write=False`` by design.

Needs a real Postgres (same contract as the RLS gates): reuses
``DATABASE_URL`` when reachable, else testcontainers; with
``REGENGINE_REQUIRE_DB=1`` an unavailable database FAILS instead of
skipping (#2530).
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from shared.db_url import sync_postgres_url
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from tests.migrations.rls_db import rls_postgres_or_skip, skip_or_fail_db

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def migrated_db():
    """A real Postgres at alembic head, with tenant GUC plumbing provisioned."""
    with rls_postgres_or_skip() as (database_url, engine):
        from tests.migrations.test_rls_coverage import _provision_app_roles

        _provision_app_roles(database_url)
        env = dict(os.environ)
        env["DATABASE_URL"] = database_url
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            skip_or_fail_db(f"alembic upgrade head failed: {result.stderr[-2000:]}")
        yield database_url, engine


def _make_event(tenant_id):
    from shared.canonical_event import (
        CTEType,
        EventStatus,
        IngestionSource,
        ProvenanceMetadata,
        TraceabilityEvent,
    )

    return TraceabilityEvent(
        event_id=uuid4(),
        tenant_id=tenant_id,
        source_system=IngestionSource.WEBHOOK_API,
        source_record_id=f"rec-{uuid4().hex[:8]}",
        event_type=CTEType.SHIPPING,
        event_timestamp=datetime.now(timezone.utc),
        event_timezone="UTC",
        product_reference="urn:gs1:01:09506000134352",
        lot_reference="LOT-PARITY-1",
        traceability_lot_code=f"TLC-PARITY-{uuid4().hex[:8]}",
        quantity=10.0,
        unit_of_measure="kg",
        from_entity_reference="urn:gs1:417:0614141000005",
        to_entity_reference="urn:gs1:417:0614141000012",
        from_facility_reference="urn:gs1:414:0614141000005",
        to_facility_reference="urn:gs1:414:0614141000012",
        kdes={"gtin": "09506000134352"},
        status=EventStatus.ACTIVE,
        provenance=ProvenanceMetadata(),
    )


@pytest.fixture()
def tenant_session(migrated_db):
    """A session with a seeded tenant and the RLS GUC set."""
    database_url, _ = migrated_db
    engine = create_engine(sync_postgres_url(database_url), future=True)
    tenant_id = uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tenants (id, name, slug, status) "
                "VALUES (:id, :name, :slug, 'active') ON CONFLICT DO NOTHING"
            ),
            {"id": str(tenant_id), "name": f"parity-{tenant_id.hex[:8]}", "slug": f"parity-{tenant_id.hex[:8]}"},
        )
    session_factory = sessionmaker(bind=engine, future=True)
    session = session_factory()
    session.execute(text("SELECT set_config('app.tenant_id', :tid, false)"), {"tid": str(tenant_id)})
    try:
        yield session, tenant_id
    finally:
        session.rollback()
        session.close()
        engine.dispose()


class TestDualWriteParity:
    def test_ingest_writes_both_stores_with_matching_hash(self, tenant_session):
        from shared.canonical_persistence.writer import CanonicalEventStore

        session, tenant_id = tenant_session
        event = _make_event(tenant_id)

        store = CanonicalEventStore(session, dual_write=True)
        store.persist_event(event)
        session.commit()

        canonical = session.execute(
            text(
                "SELECT sha256_hash FROM fsma.traceability_events "
                "WHERE tenant_id = :tid AND event_id = :eid"
            ),
            {"tid": str(tenant_id), "eid": str(event.event_id)},
        ).fetchall()
        assert len(canonical) == 1, "canonical row missing after persist_event"

        legacy = session.execute(
            text(
                "SELECT sha256_hash FROM fsma.cte_events "
                "WHERE tenant_id = :tid AND sha256_hash = :h"
            ),
            {"tid": str(tenant_id), "h": canonical[0][0]},
        ).fetchall()
        assert len(legacy) == 1, (
            "dual_write=True ingest produced no legacy cte_events twin — the "
            "#1277 'both tables or neither' invariant is broken"
        )
        assert legacy[0][0] == canonical[0][0]

    def test_no_legacy_orphans_after_ingest(self, tenant_session):
        """Promoted from scripts/validate_data_integrity.py (#2521).

        Directionality matters: only legacy-without-canonical is a hard
        failure. dual_write_legacy runs INSIDE persist_event AFTER the
        canonical INSERT, so a legacy orphan means the canonical write
        was lost. Canonical-only rows are produced by intentional
        dual_write=False paths and are NOT failures.
        """
        from shared.canonical_persistence.writer import CanonicalEventStore

        session, tenant_id = tenant_session
        for _ in range(3):
            store = CanonicalEventStore(session, dual_write=True)
            store.persist_event(_make_event(tenant_id))
        session.commit()

        orphan_legacy = session.execute(
            text("""
                SELECT COUNT(*)
                FROM fsma.cte_events c
                WHERE c.tenant_id = :tid
                  AND NOT EXISTS (
                    SELECT 1 FROM fsma.traceability_events t
                    WHERE t.tenant_id = c.tenant_id
                      AND t.sha256_hash = c.sha256_hash
                  )
            """),
            {"tid": str(tenant_id)},
        ).scalar()
        assert (orphan_legacy or 0) == 0, (
            f"{orphan_legacy} legacy cte_events row(s) have no canonical twin "
            "by sha256_hash — a swallowed canonical write (#1277/#1335)"
        )
