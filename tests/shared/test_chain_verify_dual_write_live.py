"""Live-DB regression: canonical chain verification under real dual-write.

The production ingest path (webhook_compat.ingest_events, used by CSV and
webhook ingest) composes the legacy writer (``CTEPersistence.store_event``
— appends a ``fsma.hash_chain`` row bound to the ``cte_events`` id) with
the canonical writer (``CanonicalEventStore(dual_write=False)`` — appends
a second chain row bound to the ``traceability_events`` id). One event,
TWO interleaved chain rows, one per store.

``verify_chain_canonical`` used to orphan every legacy-store row, so the
compliance score's chain_integrity read 0 ("TAMPER DETECTED") for ANY
tenant with API-ingested data once ``CHAIN_VERIFY_READ_CANONICAL`` was
flipped on (observed live in prod 2026-07-24, founder tenant). The
documented rule — chain_verification_job._combine_results: a row is a
TRUE orphan only when BOTH stores miss it — now lives in the verifier.

The invariants golden (test_chain_verify_golden.py) did not catch this
because its corpus writes through ``CanonicalEventStore(dual_write=True)``
only — a single chain row per event — which is not the shape the real
ingest route produces.

Requires DATABASE_URL (alembic-head schema); skips without it.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("ADMIN_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping live dual-write chain test",
)


@pytest.fixture()
def db_session():
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    # Pin the session timezone: the event hash covers
    # event_timestamp.isoformat(), and timestamptz values come back in the
    # SESSION timezone — on a non-UTC workstation the round-tripped string
    # (and thus the recomputed hash) would differ even though the instant
    # is identical. CI and prod both run UTC.
    engine = create_engine(DATABASE_URL, connect_args={"options": "-c timezone=UTC"})
    with Session(engine) as session:
        tenant_id = str(uuid.uuid4())
        session.execute(
            text("INSERT INTO tenants (id, name, slug, created_at) VALUES (CAST(:id AS uuid), :tname, :tslug, :now)"),
            {
                "id": tenant_id,
                "tname": "dual-write-chain-live-test",
                "tslug": f"dw-chain-{tenant_id[:8]}",
                "now": datetime.now(timezone.utc),
            },
        )
        yield session, tenant_id
        session.rollback()
    engine.dispose()


def _ingest_one_dual_write(session, tenant_id: str, index: int) -> None:
    """Mirror webhook_compat.ingest_events: legacy write THEN canonical write."""
    from shared.canonical_event import (
        CTEType,
        EventStatus,
        IngestionSource,
        ProvenanceMetadata,
        TraceabilityEvent,
    )
    from shared.canonical_persistence import CanonicalEventStore
    from shared.cte_persistence import CTEPersistence

    CTEPersistence(session).store_event(
        tenant_id=tenant_id,
        event_type="harvesting",
        traceability_lot_code=f"TLC-DW-{index:03d}",
        product_description="Dual Write Lettuce",
        quantity=10.0 + index,
        unit_of_measure="cases",
        event_timestamp=datetime.now(timezone.utc).isoformat(),
        source="dual-write-live-test",
    )

    # Mirror the invariants golden corpus construction exactly — the
    # writer stores the model's own sha256, and the verifier recomputes
    # from the persisted row, so field shape must be write-faithful.
    event = TraceabilityEvent(
        event_id=uuid.uuid4(),
        tenant_id=uuid.UUID(tenant_id),
        event_type=CTEType.HARVESTING,
        event_timestamp=datetime.now(timezone.utc),
        source_system=IngestionSource.WEBHOOK_API,
        product_reference="Dual Write Lettuce",
        traceability_lot_code=f"TLC-DW-{index:03d}",
        quantity=10.0 + index,
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


def test_dual_written_chain_is_valid_and_legacy_rows_are_not_orphans(db_session) -> None:
    from shared.canonical_persistence import CanonicalEventStore

    session, tenant_id = db_session
    for i in range(3):
        _ingest_one_dual_write(session, tenant_id, i)

    result = CanonicalEventStore(session, dual_write=False).verify_chain_canonical(tenant_id)

    assert result.chain_length == 6, "expected two chain rows per dual-written event"
    assert result.legacy_chain_rows and len(result.legacy_chain_rows) == 3, (
        f"legacy-store rows should be classified, got {result.legacy_chain_rows!r}"
    )
    assert result.orphan_chain_rows == [], f"legacy-store rows must not be orphans: {result.errors}"
    assert result.tamper_rows == []
    assert result.valid is True, f"dual-written chain must verify: {result.errors}"
    # Canonical events all have a chain row — the count must not be skewed
    # by the legacy rows.
    assert result.events_without_chain_row == 0


def test_true_orphan_still_flips_valid(db_session) -> None:
    from shared.canonical_persistence import CanonicalEventStore
    from sqlalchemy import text

    session, tenant_id = db_session
    _ingest_one_dual_write(session, tenant_id, 0)

    # A chain row whose id exists in NEITHER store — genuine corruption.
    last = session.execute(
        text(
            "SELECT sequence_num, chain_hash FROM fsma.hash_chain WHERE tenant_id = :t ORDER BY sequence_num DESC LIMIT 1"
        ),
        {"t": tenant_id},
    ).fetchone()
    session.execute(
        text("""
            INSERT INTO fsma.hash_chain
                (tenant_id, cte_event_id, sequence_num, event_hash,
                 previous_chain_hash, chain_hash, created_at)
            VALUES (CAST(:t AS uuid), CAST(:e AS uuid), :seq, :eh, :prev, :ch, :now)
        """),
        {
            "t": tenant_id,
            "e": str(uuid.uuid4()),
            "seq": int(last[0]) + 1,
            "eh": "0" * 64,
            "prev": last[1],
            "ch": "1" * 64,
            "now": datetime.now(timezone.utc),
        },
    )

    result = CanonicalEventStore(session, dual_write=False).verify_chain_canonical(tenant_id)
    assert result.valid is False
    assert result.orphan_chain_rows == [int(last[0]) + 1]
