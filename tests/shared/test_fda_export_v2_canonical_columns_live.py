"""Live-DB regression: FDA export v2 reads real canonical column names.

``fetch_v2_events`` selected legacy ``cte_events`` column names
(``product_description``, ``location_gln``, ``location_name``,
``source``, ``provenance``) from ``fsma.traceability_events``, plus
``rd.rule_name`` / ``re.passed`` which do not exist on
``fsma.rule_definitions`` / ``fsma.rule_evaluations`` either
(``title`` / text ``result``). GET /api/v1/fda/export/v2 500'd in
production on 2026-07-24 with UndefinedColumn: e.product_description.

The pre-existing v2 tests mock the session, which is exactly why this
shipped — only a real Postgres objects to a bad column name. This test
seeds a minimal tenant + canonical rows and executes the real query
path (``build_v2_where_clause`` + ``fetch_v2_events`` +
``v2_rows_to_event_dicts``) against a live schema-at-head database.
Requires DATABASE_URL and skips without it (same pattern as
test_exception_queue_uuid_arrays_live.py).
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("ADMIN_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping live FDA export v2 column test",
)

EVENT_TS = datetime(2026, 7, 20, 12, 0, 0, tzinfo=timezone.utc)


def _seed_tenant(session, tenant_id: str, label: str) -> None:
    from sqlalchemy import text

    session.execute(
        text("INSERT INTO tenants (id, name, slug, created_at) VALUES (CAST(:id AS uuid), :name, :slug, :now)"),
        {
            "id": tenant_id,
            "name": f"fda-v2-live-{label}",
            "slug": f"fda-v2-live-{label}-{tenant_id[:8]}",
            "now": datetime.now(timezone.utc),
        },
    )


def _seed_event(session, tenant_id: str, event_id: str, tlc: str) -> None:
    from sqlalchemy import text

    session.execute(
        text("""
            INSERT INTO fsma.traceability_events
                (event_id, tenant_id, source_system, event_type, event_timestamp,
                 product_reference, traceability_lot_code, quantity, unit_of_measure,
                 from_facility_reference, to_facility_reference, kdes,
                 provenance_metadata, sha256_hash, chain_hash)
            VALUES
                (CAST(:eid AS uuid), CAST(:tid AS uuid), 'csv_upload', 'shipping', :ts,
                 'Romaine Lettuce', :tlc, 42.0, 'kg',
                 'urn:gs1:414:0614141000005', 'urn:gs1:414:0614141000012',
                 '{"gtin": "09506000134352"}'::jsonb,
                 '{"ingest": "live-test"}'::jsonb, 'deadbeef', 'cafebabe')
        """),
        {"eid": event_id, "tid": tenant_id, "ts": EVENT_TS, "tlc": tlc},
    )


def test_fetch_v2_events_executes_against_canonical_schema() -> None:
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    from services.ingestion.app.fda_export.queries import (
        build_v2_where_clause,
        fetch_v2_events,
        v2_rows_to_event_dicts,
    )

    engine = create_engine(DATABASE_URL)
    tenant_id = str(uuid.uuid4())
    other_tenant_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())
    other_event_id = str(uuid.uuid4())
    rule_id = str(uuid.uuid4())

    with Session(engine) as session:
        # Minimal seed: two tenants, one canonical event each, and a
        # rule definition + pass/fail evaluations on the first event.
        # Everything rolls back at the end — nothing is committed.
        _seed_tenant(session, tenant_id, "a")
        _seed_tenant(session, other_tenant_id, "b")
        _seed_event(session, tenant_id, event_id, "TLC-V2-LIVE-001")
        _seed_event(session, other_tenant_id, other_event_id, "TLC-V2-LIVE-OTHER")

        session.execute(
            text("""
                INSERT INTO fsma.rule_definitions (rule_id, rule_version, title)
                VALUES (CAST(:rid AS uuid), 1, 'KDE completeness')
            """),
            {"rid": rule_id},
        )
        for result, why in (("pass", None), ("fail", "missing harvest_date")):
            session.execute(
                text("""
                    INSERT INTO fsma.rule_evaluations
                        (tenant_id, event_id, rule_id, rule_version, result, why_failed)
                    VALUES (CAST(:tid AS uuid), CAST(:eid AS uuid), CAST(:rid AS uuid), 1, :res, :why)
                """),
                {"tid": tenant_id, "eid": event_id, "rid": rule_id, "res": result, "why": why},
            )

        # No-filter query: the crash path from production.
        where_clause, params = build_v2_where_clause(
            tenant_id=tenant_id, tlc=None, event_type=None, start_date=None, end_date=None
        )
        rows = fetch_v2_events(session, where_clause, params)
        assert len(rows) == 1, "expected exactly the seeded tenant's event"

        events = v2_rows_to_event_dicts(rows)
        event = events[0]
        assert event["id"] == event_id
        assert event["product_description"] == "Romaine Lettuce"
        assert event["location_gln"] == "urn:gs1:414:0614141000005"
        assert event["location_name"] == "urn:gs1:414:0614141000005"
        assert event["source"] == "csv_upload"
        assert event["sha256_hash"] == "deadbeef"
        assert event["chain_hash"] == "cafebabe"
        assert event["kdes"] == {"gtin": "09506000134352"}
        assert event["provenance"] == {"ingest": "live-test"}

        rule_results = sorted(event["rule_results"], key=lambda r: r["passed"])
        assert rule_results == [
            {"rule_name": "KDE completeness", "passed": False, "why_failed": "missing harvest_date"},
            {"rule_name": "KDE completeness", "passed": True, "why_failed": None},
        ]

        # Fully-filtered query: exercises every branch of the WHERE builder.
        where_clause, params = build_v2_where_clause(
            tenant_id=tenant_id,
            tlc="TLC-V2-LIVE-001",
            event_type="shipping",
            start_date="2026-07-20",
            end_date="2026-07-20",
        )
        rows = fetch_v2_events(session, where_clause, params)
        assert len(rows) == 1
        assert str(tuple(rows[0])[0]) == event_id

        session.rollback()
