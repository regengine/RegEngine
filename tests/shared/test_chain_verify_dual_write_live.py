"""Live-DB regression: canonical chain verification under real dual-write.

Until ``webhook_compat.ingest_events`` (CSV, EDI, supplier portal, Sensitech)
moved to one shared ledger row per event, it composed the legacy writer
(``CTEPersistence.store_event`` — appends a ``fsma.hash_chain`` row bound to
the ``cte_events`` id) with the canonical writer
(``CanonicalEventStore(dual_write=False)`` — appends a second chain row bound
to the ``traceability_events`` id). One event, TWO interleaved chain rows,
one per store. The chain is append-only, so chains written that way keep that
shape and the first two tests keep covering it. The compat tests at the end
cover what ``ingest_events`` writes now.

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

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from shared.db_url import sync_postgres_url

from tests.migrations.rls_db import guarded_live_database_url

DATABASE_URL = guarded_live_database_url()
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="no designated live test DB (CI DATABASE_URL or REGENGINE_MIGRATION_TEST_DB) — skipping live dual-write chain test",
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
    engine = create_engine(sync_postgres_url(DATABASE_URL), connect_args={"options": "-c timezone=UTC"})
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


# ---------------------------------------------------------------------------
# webhook_compat.ingest_events: one ledger row per event, shared by both stores
# ---------------------------------------------------------------------------


def _shipped_yesterday() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=1)


def _ingest_through_compat(
    session,
    tenant_id: str,
    monkeypatch,
    lots: list[str],
    *,
    shipped: datetime | None = None,
    all_or_nothing: bool = False,
):
    """Run the real ``ingest_events`` loop and both real writers on the test's transaction.

    Only what needs a network or a second connection is stubbed: the API-key
    lookup, the Redis rate limit, the graph publish and the data-gap writer.
    The event time is part of both stores' duplicate keys, so a test that
    sends the same events twice passes one ``shipped`` to both calls.
    """
    from services.ingestion.app import webhook_compat
    from services.ingestion.app.webhook_models import IngestEvent, WebhookCTEType, WebhookPayload

    shipped = shipped or _shipped_yesterday()
    payload = WebhookPayload(
        source="edi_inbound_945",
        tenant_id=tenant_id,
        events=[
            IngestEvent(
                cte_type=WebhookCTEType.SHIPPING,
                traceability_lot_code=lot,
                product_description="Romaine Hearts 12ct",
                quantity=10.0 + index,
                unit_of_measure="cases",
                location_name="Valley Cold Storage",
                timestamp=shipped.isoformat(),
                kdes={
                    "ship_date": shipped.date().isoformat(),
                    "ship_from_location": "Valley Cold Storage",
                    "ship_to_location": "Metro Distribution Center",
                    "reference_document": f"BOL-{lot}",
                    "tlc_source_reference": "Valley Cold Storage, 100 Farm Rd, Salinas, CA 93901",
                },
            )
            for index, lot in enumerate(lots)
        ],
    )

    def _session():
        yield session

    monkeypatch.setattr(webhook_compat, "_get_db_session", _session)
    monkeypatch.setattr(webhook_compat, "_verify_api_key_sync", lambda **kwargs: None)
    monkeypatch.setattr(webhook_compat, "_check_rate_limit", lambda tenant: None)
    monkeypatch.setattr(webhook_compat, "record_outcomes", lambda *args: None)
    monkeypatch.setattr(webhook_compat, "_publish_graph_sync", lambda *args: None)
    # The fixture rolls the transaction back; a real commit would leave rows behind.
    monkeypatch.setattr(session, "commit", session.flush)
    # No API key is passed: the key lookup is stubbed above.
    return asyncio.run(
        webhook_compat.ingest_events(payload, principal_tenant_id=tenant_id, all_or_nothing=all_or_nothing)
    )


def _ledger_rows(session, tenant_id: str):
    """Each chain row: its event id, and whether each store holds that id."""
    from sqlalchemy import text

    return session.execute(
        text("""
            SELECT hc.cte_event_id::text,
                   ce.id IS NOT NULL AS in_cte_events,
                   te.event_id IS NOT NULL AS in_traceability_events,
                   hc.event_hash = te.sha256_hash AS ledger_hash_is_canonical_hash
            FROM fsma.hash_chain hc
            LEFT JOIN fsma.cte_events ce
                   ON ce.id = hc.cte_event_id AND ce.tenant_id = hc.tenant_id
            LEFT JOIN fsma.traceability_events te
                   ON te.event_id = hc.cte_event_id AND te.tenant_id = hc.tenant_id
            WHERE hc.tenant_id = :t
            ORDER BY hc.sequence_num
        """),
        {"t": tenant_id},
    ).fetchall()


def test_compat_ingest_writes_one_ledger_row_shared_by_both_stores(db_session, monkeypatch) -> None:
    """Accepted events must leave every chain verifier valid.

    ``GET /api/v1/webhooks/chain/verify`` runs ``CTEPersistence.verify_chain``.
    It joins the chain to ``fsma.cte_events`` only, so the canonical write's
    own chain row read as an orphan: ``chain_valid:false`` after every accepted
    CSV, EDI, supplier-portal or Sensitech event.
    """
    from shared.canonical_persistence import CanonicalEventStore
    from shared.cte_persistence import CTEPersistence

    session, tenant_id = db_session
    lots = [f"TLC-COMPAT-{i:03d}" for i in range(3)]
    shipped = _shipped_yesterday()
    response = _ingest_through_compat(session, tenant_id, monkeypatch, lots, shipped=shipped)
    assert (response.accepted, response.rejected) == (3, 0), [e.errors for e in response.events]

    rows = _ledger_rows(session, tenant_id)
    assert [row[0] for row in rows] == [e.event_id for e in response.events], (
        "expected exactly one chain row per accepted event, under the id the response returns"
    )
    assert [tuple(row[1:]) for row in rows] == [(True, True, True)] * 3, (
        "each chain row must match both stores and carry the canonical content hash"
    )

    legacy = CTEPersistence(session).verify_chain(tenant_id)
    assert legacy.orphan_chain_rows == []
    assert legacy.valid is True, legacy.errors
    canonical = CanonicalEventStore(session, dual_write=False).verify_chain_canonical(tenant_id)
    assert canonical.legacy_chain_rows == [], "no row may be attested by the legacy store alone"
    assert canonical.tamper_rows == []
    assert canonical.valid is True, canonical.errors
    assert canonical.events_without_chain_row == 0
    merkle = CTEPersistence(session).verify_chain_merkle(tenant_id)
    assert merkle.valid is True, merkle.errors

    # An exact resend stores nothing and must not disturb the chain.
    replay = _ingest_through_compat(session, tenant_id, monkeypatch, lots, shipped=shipped)
    assert [e.event_id for e in replay.events] == [e.event_id for e in response.events]
    assert _ledger_rows(session, tenant_id) == rows


def test_compat_ingest_adds_no_orphan_to_a_chain_written_before_the_change(db_session, monkeypatch) -> None:
    """Older two-row events stay as they are; new events add one valid row each."""
    from shared.canonical_persistence import CanonicalEventStore
    from shared.cte_persistence import CTEPersistence

    session, tenant_id = db_session
    _ingest_one_dual_write(session, tenant_id, 0)
    before = CTEPersistence(session).verify_chain(tenant_id)

    response = _ingest_through_compat(session, tenant_id, monkeypatch, ["TLC-COMPAT-AFTER"])
    assert response.accepted == 1, [e.errors for e in response.events]

    rows = _ledger_rows(session, tenant_id)
    assert len(rows) == 3, "two rows from the older event, one from the new one"
    assert tuple(rows[-1]) == (response.events[0].event_id, True, True, True)
    after = CTEPersistence(session).verify_chain(tenant_id)
    assert after.orphan_chain_rows == before.orphan_chain_rows
    canonical = CanonicalEventStore(session, dual_write=False).verify_chain_canonical(tenant_id)
    assert canonical.valid is True, canonical.errors
    assert canonical.orphan_chain_rows == []


def test_compat_batch_that_is_undone_leaves_no_ledger_row(db_session, monkeypatch) -> None:
    """EDI stores an interchange completely or not at all, and the shared row goes with it."""
    from sqlalchemy import text

    session, tenant_id = db_session
    # The second event repeats the first, so it is rejected after the first was written.
    response = _ingest_through_compat(
        session, tenant_id, monkeypatch, ["TLC-COMPAT-UNDO", "TLC-COMPAT-UNDO"], all_or_nothing=True
    )
    assert (response.accepted, response.rejected) == (0, 2), [e.errors for e in response.events]

    assert _ledger_rows(session, tenant_id) == []
    stored = session.execute(
        text("""
            SELECT (SELECT COUNT(*) FROM fsma.cte_events WHERE tenant_id = :t),
                   (SELECT COUNT(*) FROM fsma.traceability_events WHERE tenant_id = :t)
        """),
        {"t": tenant_id},
    ).one()
    assert tuple(stored) == (0, 0)


# ---------------------------------------------------------------------------
# Canonical content rewritten together with its stored hash
# ---------------------------------------------------------------------------


def _rewrite_canonical_content_and_hash(session, tenant_id: str, event_id: str) -> None:
    """Change one canonical row's quantity and store the hash of the new content.

    What a writer with table access and the break-glass setting could do while
    leaving ``fsma.hash_chain`` alone. The row then agrees with itself.
    """
    from shared.canonical_persistence.verification import _kdes_object, _recompute_event_sha256
    from sqlalchemy import text

    key = {"t": tenant_id, "e": event_id}
    session.execute(text("SET LOCAL fsma.allow_mutation = 'true'"))
    session.execute(
        text("UPDATE fsma.traceability_events SET quantity = quantity + 1 WHERE tenant_id = :t AND event_id = :e"),
        key,
    )
    row = session.execute(
        text("""
            SELECT event_type, traceability_lot_code, product_reference, quantity,
                   unit_of_measure, from_facility_reference, to_facility_reference,
                   event_timestamp, kdes, normalized_payload->>'event_timestamp'
            FROM fsma.traceability_events
            WHERE tenant_id = :t AND event_id = :e
        """),
        key,
    ).one()
    rewritten_hash = _recompute_event_sha256(
        event_id=event_id,
        event_type=row[0],
        traceability_lot_code=row[1],
        product_reference=row[2],
        quantity=row[3],
        unit_of_measure=row[4],
        from_facility_reference=row[5],
        to_facility_reference=row[6],
        event_timestamp=row[7],
        kdes=_kdes_object(row[8]),
        timestamp_hint=row[9],
    )
    session.execute(
        text("UPDATE fsma.traceability_events SET sha256_hash = :h WHERE tenant_id = :t AND event_id = :e"),
        {"h": rewritten_hash, **key},
    )
    session.execute(text("SET LOCAL fsma.allow_mutation = 'false'"))


def test_two_row_chain_reports_canonical_content_rewritten_with_its_hash(db_session) -> None:
    """In the older layout the canonical row has its own chain row, which still holds the first hash."""
    from shared.canonical_persistence import CanonicalEventStore
    from sqlalchemy import text

    session, tenant_id = db_session
    _ingest_one_dual_write(session, tenant_id, 0)
    canonical_id = session.execute(
        text("SELECT event_id::text FROM fsma.traceability_events WHERE tenant_id = :t"), {"t": tenant_id}
    ).scalar_one()

    _rewrite_canonical_content_and_hash(session, tenant_id, canonical_id)

    result = CanonicalEventStore(session, dual_write=False).verify_chain_canonical(tenant_id)
    assert result.valid is False
    assert result.tamper_rows, result.errors


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "verify_chain_canonical skips the chain-row digest comparison for a row present in both "
        "stores, so a shared row does not bind canonical content. The webhook route's rows have "
        "the same gap. Remove this marker with the verifier fix (raised in review of PR 3851)."
    ),
)
def test_shared_row_reports_canonical_content_rewritten_with_its_hash(db_session, monkeypatch) -> None:
    """A chain row shared by both stores must still bind the canonical content."""
    from shared.canonical_persistence import CanonicalEventStore

    session, tenant_id = db_session
    response = _ingest_through_compat(session, tenant_id, monkeypatch, ["TLC-COMPAT-REWRITTEN"])
    assert response.accepted == 1, [e.errors for e in response.events]

    _rewrite_canonical_content_and_hash(session, tenant_id, response.events[0].event_id)

    result = CanonicalEventStore(session, dual_write=False).verify_chain_canonical(tenant_id)
    assert result.valid is False
    assert result.tamper_rows, result.errors
