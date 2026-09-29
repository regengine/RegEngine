"""WS-1b (#1335) — FDA export v1 golden: legacy read ≡ canonical read.

The v1 recall export is the compliance-critical FDA reader (21 CFR
1.1455). Before any environment flips ``FDA_EXPORT_V1_READ_CANONICAL``,
this suite proves the canonical reader reproduces the legacy reader's
output EXACTLY on dual-written data:

* a varied corpus (all mapping edge cases: from-only / to-only / no
  facility, None-valued KDEs, empty product, mixed event types and
  timestamps) is ingested through the real
  ``CanonicalEventStore(dual_write=True)`` writer;
* ``fetch_recall_events`` (legacy) and ``fetch_recall_events_canonical``
  are run with the same filters, through their respective WHERE-clause
  builders, across several filter combinations;
* ``rows_to_event_dicts`` output must be exactly equal — every field,
  every row, every ordering — which makes the downstream CSV bytes
  identical since the formatter is a pure function of these dicts.

Same live-Postgres contract as the other invariants
(``REGENGINE_REQUIRE_DB=1`` fails instead of skipping).
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from shared.db_url import sync_postgres_url
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from tests.migrations.rls_db import rls_postgres_or_skip, skip_or_fail_db

REPO_ROOT = Path(__file__).resolve().parents[2]

BASE_TS = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def migrated_db():
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


def _corpus_event(tenant_id, index, **overrides):
    from shared.canonical_event import (
        CTEType,
        EventStatus,
        IngestionSource,
        ProvenanceMetadata,
        TraceabilityEvent,
    )

    defaults = dict(
        event_id=uuid4(),
        tenant_id=tenant_id,
        source_system=IngestionSource.WEBHOOK_API,
        source_record_id=f"golden-rec-{index}",
        event_type=CTEType.SHIPPING,
        event_timestamp=BASE_TS + timedelta(hours=index),
        event_timezone="UTC",
        product_reference=f"urn:gs1:01:0950600013435{index}",
        lot_reference=f"LOT-G{index}",
        traceability_lot_code=f"TLC-GOLD-{index:03d}",
        quantity=10.0 + index,
        unit_of_measure="kg",
        from_entity_reference="urn:gs1:417:0614141000005",
        to_entity_reference="urn:gs1:417:0614141000012",
        from_facility_reference="urn:gs1:414:0614141000005",
        to_facility_reference="urn:gs1:414:0614141000012",
        kdes={"gtin": f"0950600013435{index}", "harvest_date": "2026-05-30"},
        status=EventStatus.ACTIVE,
        provenance=ProvenanceMetadata(),
    )
    defaults.update(overrides)
    return TraceabilityEvent(**defaults)


@pytest.fixture(scope="module")
def seeded_corpus(migrated_db):
    """A tenant with a dual-written corpus covering the mapping edge cases."""
    from shared.canonical_event import CTEType
    from shared.canonical_persistence.writer import CanonicalEventStore

    database_url, _ = migrated_db
    engine = create_engine(sync_postgres_url(database_url), future=True)
    tenant_id = uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tenants (id, name, slug, status) "
                "VALUES (:id, :name, :slug, 'active') ON CONFLICT DO NOTHING"
            ),
            {
                "id": str(tenant_id),
                "name": f"golden-{tenant_id.hex[:8]}",
                "slug": f"golden-{tenant_id.hex[:8]}",
            },
        )

    session = sessionmaker(bind=engine, future=True)()
    session.execute(text("SELECT set_config('app.tenant_id', :tid, false)"), {"tid": str(tenant_id)})

    events = [
        # 0: fully-populated baseline
        _corpus_event(tenant_id, 0),
        # 1: to-facility only (#2535 fallback path)
        _corpus_event(tenant_id, 1, from_facility_reference=None),
        # 2: NO facility at all (location columns NULL)
        _corpus_event(tenant_id, 2, from_facility_reference=None, to_facility_reference=None),
        # 3: None-valued KDE (dual_write skips it; canonical reader must strip it)
        _corpus_event(tenant_id, 3, kdes={"gtin": "095", "lot_size_unit": None}),
        # 4: empty product_reference (legacy stores '')
        _corpus_event(tenant_id, 4, product_reference=None),
        # 5: different event type, SGLN-URN read point
        _corpus_event(
            tenant_id,
            5,
            event_type=CTEType.RECEIVING,
            from_facility_reference="urn:epc:id:sgln:0614141.00005.0",
        ),
        # 6: transformation, empty KDEs
        _corpus_event(tenant_id, 6, event_type=CTEType.TRANSFORMATION, kdes={}),
    ]
    for event in events:
        CanonicalEventStore(session, dual_write=True).persist_event(event)
    session.commit()

    try:
        yield session, tenant_id
    finally:
        session.rollback()
        session.close()
        engine.dispose()


FILTER_CASES = [
    pytest.param(dict(), id="no-filters"),
    pytest.param(dict(event_type="shipping"), id="event-type"),
    pytest.param(dict(tlc="TLC-GOLD-00"), id="tlc-prefix"),
    pytest.param(dict(product="0950600013435"), id="product"),
    pytest.param(dict(location="0614141000005"), id="location"),
    pytest.param(dict(location="sgln"), id="location-sgln-urn"),
    pytest.param(
        dict(start_date="2026-06-01", end_date="2026-06-01"), id="date-window"
    ),
]


class TestExportV1Golden:
    @pytest.mark.parametrize("filters", FILTER_CASES)
    def test_legacy_and_canonical_readers_are_byte_identical(self, seeded_corpus, filters):
        from services.ingestion.app.fda_export.queries import (
            build_recall_where_clause,
            build_recall_where_clause_canonical,
            fetch_recall_events,
            fetch_recall_events_canonical,
            rows_to_event_dicts,
        )

        session, tenant_id = seeded_corpus
        kwargs = dict(
            tenant_id=str(tenant_id),
            product=None,
            location=None,
            tlc=None,
            event_type=None,
            start_date=None,
            end_date=None,
        )
        kwargs.update(filters)

        legacy_where, legacy_params = build_recall_where_clause(**kwargs)
        legacy = rows_to_event_dicts(fetch_recall_events(session, legacy_where, legacy_params))

        canon_where, canon_params = build_recall_where_clause_canonical(**kwargs)
        canonical = rows_to_event_dicts(
            fetch_recall_events_canonical(session, canon_where, canon_params)
        )

        assert legacy, f"filter {filters!r} matched nothing — corpus/filters out of sync"
        assert canonical == legacy, (
            "canonical v1 reader diverged from legacy on dual-written data — "
            "DO NOT flip FDA_EXPORT_V1_READ_CANONICAL until this is fixed"
        )

    def test_corpus_exercises_the_edge_cases(self, seeded_corpus):
        """The golden is only as strong as its corpus — pin the edge cases."""
        from services.ingestion.app.fda_export.queries import (
            build_recall_where_clause,
            fetch_recall_events,
            rows_to_event_dicts,
        )

        session, tenant_id = seeded_corpus
        where, params = build_recall_where_clause(
            tenant_id=str(tenant_id),
            product=None,
            location=None,
            tlc=None,
            event_type=None,
            start_date=None,
            end_date=None,
        )
        events = rows_to_event_dicts(fetch_recall_events(session, where, params))
        assert len(events) == 7
        # NULL-location row survived (no-facility event)
        assert any(e["location_gln"] is None for e in events)
        # None-valued KDE was skipped by the dual write
        kde_sets = [set(e["kdes"].keys()) for e in events]
        assert any("lot_size_unit" not in k and "gtin" in k for k in kde_sets)
        # empty product stored as ''
        assert any(e["product_description"] == "" for e in events)
