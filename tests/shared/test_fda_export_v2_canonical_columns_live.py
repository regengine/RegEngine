"""Live-DB regression: the v2 FDA export query runs against the real canonical schema.

GET /api/v1/fda/export/v2 500'd in production on 2026-07-24 with
UndefinedColumn: ``fetch_v2_events`` selected legacy column names
(``product_description``, ``location_gln``, ``location_name``, ``source``,
``provenance``) from ``fsma.traceability_events``, whose canonical columns
are ``product_reference``, ``from/to_facility_reference``,
``source_system``, ``provenance_metadata``. It also referenced
``rule_definitions.rule_name`` and ``rule_evaluations.passed`` — neither
has ever existed (the real columns are ``title`` and ``result``).

The pre-existing unit tests (test_fda_export_queries_1342.py) use a fake
session that never parses the SQL, which is exactly why this shipped —
only a real Postgres can object to an undefined column. This test executes
``fetch_v2_events`` verbatim against an alembic-head database, seeding
through the production writer (``CanonicalEventStore``). Requires
DATABASE_URL and skips without it (same pattern as
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
    reason="DATABASE_URL not set — skipping live v2 export column test",
)


@pytest.fixture()
def db_session():
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    engine = create_engine(DATABASE_URL, connect_args={"options": "-c timezone=UTC"})
    with Session(engine) as session:
        tenant_id = str(uuid.uuid4())
        session.execute(
            text("INSERT INTO tenants (id, name, slug, created_at) VALUES (CAST(:id AS uuid), :tname, :tslug, :now)"),
            {
                "id": tenant_id,
                "tname": "fda-v2-columns-live-test",
                "tslug": f"fda-v2-cols-{tenant_id[:8]}",
                "now": datetime.now(timezone.utc),
            },
        )
        yield session, tenant_id
        session.rollback()
    engine.dispose()


def _seed_canonical_event(session, tenant_id: str) -> str:
    """Write one canonical event through the production writer; return its event_id."""
    from shared.canonical_event import (
        CTEType,
        EventStatus,
        IngestionSource,
        ProvenanceMetadata,
        TraceabilityEvent,
    )
    from shared.canonical_persistence import CanonicalEventStore

    event = TraceabilityEvent(
        event_id=uuid.uuid4(),
        tenant_id=uuid.UUID(tenant_id),
        event_type=CTEType.HARVESTING,
        event_timestamp=datetime.now(timezone.utc),
        source_system=IngestionSource.WEBHOOK_API,
        product_reference="V2 Column Audit Apples",
        traceability_lot_code="TLC-V2-COLS-001",
        quantity=12.5,
        unit_of_measure="cases",
        from_entity_reference="urn:gs1:417:0614141000005",
        to_entity_reference="urn:gs1:417:0614141000012",
        from_facility_reference="urn:gs1:414:0614141000005",
        to_facility_reference="urn:gs1:414:0614141000012",
        kdes={"gtin": "09506000134352"},
        status=EventStatus.ACTIVE,
        provenance=ProvenanceMetadata(),
    )
    CanonicalEventStore(session, dual_write=False).persist_event(event)
    return str(event.event_id)


def _seed_rule_evaluation(session, tenant_id: str, event_id: str, title: str, result: str, why_failed=None) -> None:
    """Insert a rule definition + one evaluation of it against the event."""
    from sqlalchemy import text

    rule_id = str(uuid.uuid4())
    session.execute(
        text("""
            INSERT INTO fsma.rule_definitions (rule_id, title)
            VALUES (CAST(:rid AS uuid), :title)
        """),
        {"rid": rule_id, "title": title},
    )
    session.execute(
        text("""
            INSERT INTO fsma.rule_evaluations
                (tenant_id, event_id, rule_id, rule_version, result, why_failed)
            VALUES
                (CAST(:tid AS uuid), CAST(:eid AS uuid), CAST(:rid AS uuid), 1, :result, :why)
        """),
        {"tid": tenant_id, "eid": event_id, "rid": rule_id, "result": result, "why": why_failed},
    )


def test_fetch_v2_events_executes_against_canonical_schema(db_session) -> None:
    from app.fda_export.queries import (
        build_v2_where_clause,
        fetch_v2_events,
        v2_rows_to_event_dicts,
    )

    session, tenant_id = db_session
    event_id = _seed_canonical_event(session, tenant_id)
    _seed_rule_evaluation(
        session,
        tenant_id,
        event_id,
        title=f"v2-live-kde-presence-{tenant_id[:8]}",
        result="fail",
        why_failed="Receiving event missing tlc_source_reference",
    )
    _seed_rule_evaluation(
        session,
        tenant_id,
        event_id,
        title=f"v2-live-quantity-warn-{tenant_id[:8]}",
        result="warn",
    )

    where_clause, params = build_v2_where_clause(
        tenant_id=tenant_id,
        tlc=None,
        event_type=None,
        start_date=None,
        end_date=None,
    )
    # The real query, verbatim — an UndefinedColumn here is the prod 500.
    rows = fetch_v2_events(session, where_clause, params)
    events = v2_rows_to_event_dicts(rows)

    assert len(events) == 1
    ev = events[0]
    assert ev["id"] == event_id

    # Canonical -> legacy output aliases (the dual-write mapping).
    assert ev["product_description"] == "V2 Column Audit Apples"
    assert ev["location_gln"] == "urn:gs1:414:0614141000005"
    assert ev["location_name"] == "urn:gs1:414:0614141000005"
    assert ev["source"] == "webhook_api"
    assert ev["kdes"] == {"gtin": "09506000134352"}
    assert isinstance(ev["provenance"], dict)
    assert ev["sha256_hash"], "writer must have stored an event hash"
    assert ev["chain_hash"], "writer must have stored a chain hash"

    # Rule results: rule_name <- rule_definitions.title, passed <- (result <> 'fail').
    results = {r["rule_name"]: r for r in ev["rule_results"]}
    assert len(results) == 2
    fail_rule = results[f"v2-live-kde-presence-{tenant_id[:8]}"]
    assert fail_rule["passed"] is False
    assert fail_rule["why_failed"] == "Receiving event missing tlc_source_reference"
    warn_rule = results[f"v2-live-quantity-warn-{tenant_id[:8]}"]
    assert warn_rule["passed"] is True, "warn/skip must not render as FAIL in the FDA export"
