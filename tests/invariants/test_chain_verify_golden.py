"""WS-1b (#1335) — chain-verification cutover golden.

Before any environment flips ``CHAIN_VERIFY_READ_CANONICAL``, prove that
on dual-written data the legacy verifier (``CTEPersistence.verify_chain``)
and the canonical verifier (``verify_chain_canonical``, #2506) agree:

* both report ``valid=True`` over a clean dual-written corpus;
* both expose the ``.valid``/``.errors`` surface the consumers
  (compliance_score, FDA export handlers) rely on;
* the ``_verify_chain_for_export`` helper actually switches stores with
  the flag.

Same live-Postgres contract as the other invariants.
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


@pytest.fixture(scope="module")
def chained_corpus(migrated_db):
    from shared.canonical_event import (
        CTEType,
        EventStatus,
        IngestionSource,
        ProvenanceMetadata,
        TraceabilityEvent,
    )
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
                "name": f"chain-{tenant_id.hex[:8]}",
                "slug": f"chain-{tenant_id.hex[:8]}",
            },
        )
    session = sessionmaker(bind=engine, future=True)()
    session.execute(text("SET app.tenant_id = :tid"), {"tid": str(tenant_id)})

    base = datetime(2026, 6, 10, 9, 0, 0, tzinfo=timezone.utc)
    for index in range(5):
        event = TraceabilityEvent(
            event_id=uuid4(),
            tenant_id=tenant_id,
            source_system=IngestionSource.WEBHOOK_API,
            source_record_id=f"chain-rec-{index}",
            event_type=CTEType.SHIPPING,
            event_timestamp=base + timedelta(hours=index),
            event_timezone="UTC",
            product_reference="urn:gs1:01:09506000134352",
            lot_reference=f"LOT-C{index}",
            traceability_lot_code=f"TLC-CHAIN-{index:03d}",
            quantity=5.0 + index,
            unit_of_measure="kg",
            from_entity_reference="urn:gs1:417:0614141000005",
            to_entity_reference="urn:gs1:417:0614141000012",
            from_facility_reference="urn:gs1:414:0614141000005",
            to_facility_reference="urn:gs1:414:0614141000012",
            kdes={"gtin": "09506000134352"},
            status=EventStatus.ACTIVE,
            provenance=ProvenanceMetadata(),
        )
        CanonicalEventStore(session, dual_write=True).persist_event(event)
    session.commit()

    try:
        yield session, tenant_id
    finally:
        session.rollback()
        session.close()
        engine.dispose()


class TestChainVerifyGolden:
    def test_verifiers_agree_on_clean_dual_written_corpus(self, chained_corpus):
        from shared.canonical_persistence import CanonicalEventStore
        from shared.cte_persistence import CTEPersistence

        session, tenant_id = chained_corpus

        legacy = CTEPersistence(session).verify_chain(str(tenant_id))
        canonical = CanonicalEventStore(session, dual_write=False).verify_chain_canonical(str(tenant_id))

        assert legacy.valid is True, f"legacy verifier failed on clean corpus: {legacy.errors}"
        assert canonical.valid is True, f"canonical verifier failed on clean corpus: {canonical.errors}"
        # Consumer surface parity — everything compliance_score / the export
        # handlers touch exists on both result types.
        for result in (legacy, canonical):
            assert hasattr(result, "valid")
            assert hasattr(result, "errors")

    def test_export_helper_switches_stores_with_flag(self, chained_corpus, monkeypatch):
        from shared.cte_persistence import CTEPersistence

        from services.ingestion.app.fda_export.queries import _verify_chain_for_export

        session, tenant_id = chained_corpus
        persistence = CTEPersistence(session)

        # #3039: canonical is now the code default; "0" is the rollback.
        monkeypatch.delenv("CHAIN_VERIFY_READ_CANONICAL", raising=False)
        default_result = _verify_chain_for_export(persistence, session, str(tenant_id))

        monkeypatch.setenv("CHAIN_VERIFY_READ_CANONICAL", "0")
        legacy_result = _verify_chain_for_export(persistence, session, str(tenant_id))

        assert type(legacy_result) is not type(default_result), "flag did not switch verification stores"
        assert type(default_result).__name__ == "CanonicalChainVerification", (
            "#3039: the no-env default must be the canonical (content-recompute) verifier"
        )
        assert legacy_result.valid is True
        assert default_result.valid is True

    def test_content_tampering_detected_by_default_verifier(self, chained_corpus, monkeypatch):
        """#3039 core regression: mutate row content while leaving
        ``hash_chain`` untouched. The legacy verifier cannot see it; the
        default (canonical) verifier must fail the chain."""
        from shared.cte_persistence import CTEPersistence

        from services.ingestion.app.fda_export.queries import _verify_chain_for_export

        session, tenant_id = chained_corpus
        persistence = CTEPersistence(session)

        session.execute(
            text(
                "UPDATE fsma.traceability_events SET quantity = quantity + 1000 "
                "WHERE tenant_id = :tid AND traceability_lot_code = 'TLC-CHAIN-000'"
            ),
            {"tid": str(tenant_id)},
        )
        try:
            monkeypatch.setenv("CHAIN_VERIFY_READ_CANONICAL", "0")
            legacy_result = _verify_chain_for_export(persistence, session, str(tenant_id))
            assert legacy_result.valid is True, (
                "precondition: legacy verifier is blind to content tampering "
                "(it only re-links stored hashes) — if this starts failing, "
                "the legacy verifier learned content recompute and this test "
                "plus the #3039 default flip rationale need revisiting"
            )

            monkeypatch.delenv("CHAIN_VERIFY_READ_CANONICAL", raising=False)
            default_result = _verify_chain_for_export(persistence, session, str(tenant_id))
            assert default_result.valid is False, (
                "content tampering with intact hash_chain rows must fail default chain verification"
            )
        finally:
            session.rollback()

    def test_chain_row_reseal_detected_on_canonical_only_rows(self, migrated_db):
        """CodeRabbit follow-up to the prod-grade run fix: after the event-hash
        recompute moved its comparison target from ``hc.event_hash`` to
        ``te.sha256_hash`` (to stop false tamper flags on webhook dual-write
        rows), the chain row's OWN digest went unchecked. A "re-seal" attack —
        rewrite ``event_hash`` AND ``chain_hash`` consistently on the tail row
        — passes linkage and chain_hash recompute, and the content recompute
        never looks at the chain row. For canonical-only rows (no legacy
        match) the writer guarantees ``hc.event_hash == te.sha256_hash``, so
        the verifier must flag any deviation."""
        from shared.canonical_event import (
            CTEType,
            EventStatus,
            IngestionSource,
            ProvenanceMetadata,
            TraceabilityEvent,
        )
        from shared.canonical_persistence.writer import CanonicalEventStore
        from shared.cte_persistence import compute_chain_hash

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
                    "name": f"reseal-{tenant_id.hex[:8]}",
                    "slug": f"reseal-{tenant_id.hex[:8]}",
                },
            )
        session = sessionmaker(bind=engine, future=True)()
        try:
            session.execute(text("SET app.tenant_id = :tid"), {"tid": str(tenant_id)})

            base = datetime(2026, 7, 1, 9, 0, 0, tzinfo=timezone.utc)
            # dual_write=False → chain rows match ONLY the canonical store,
            # which is the topology the strict event_hash check covers.
            store = CanonicalEventStore(session, dual_write=False)
            for index in range(2):
                store.persist_event(
                    TraceabilityEvent(
                        event_id=uuid4(),
                        tenant_id=tenant_id,
                        source_system=IngestionSource.WEBHOOK_API,
                        source_record_id=f"reseal-rec-{index}",
                        event_type=CTEType.SHIPPING,
                        event_timestamp=base + timedelta(hours=index),
                        event_timezone="UTC",
                        product_reference="urn:gs1:01:09506000134352",
                        lot_reference=f"LOT-R{index}",
                        traceability_lot_code=f"TLC-RESEAL-{index:03d}",
                        quantity=5.0 + index,
                        unit_of_measure="kg",
                        from_entity_reference="urn:gs1:417:0614141000005",
                        to_entity_reference="urn:gs1:417:0614141000012",
                        from_facility_reference="urn:gs1:414:0614141000005",
                        to_facility_reference="urn:gs1:414:0614141000012",
                        kdes={"gtin": "09506000134352"},
                        status=EventStatus.ACTIVE,
                        provenance=ProvenanceMetadata(),
                    )
                )
            session.commit()
            session.execute(text("SET app.tenant_id = :tid"), {"tid": str(tenant_id)})

            clean = store.verify_chain_canonical(str(tenant_id))
            assert clean.valid is True, f"precondition: clean canonical-only chain failed: {clean.errors}"

            # Re-seal the tail row: fake event_hash + CONSISTENT chain_hash,
            # so linkage and chain_hash-recompute checks both still pass.
            tail = session.execute(
                text(
                    "SELECT sequence_num, previous_chain_hash FROM fsma.hash_chain "
                    "WHERE tenant_id = :tid ORDER BY sequence_num DESC LIMIT 1"
                ),
                {"tid": str(tenant_id)},
            ).fetchone()
            fake_event_hash = "f" * 64
            fake_chain_hash = compute_chain_hash(fake_event_hash, tail[1])
            # The append-only trigger's authorized-corrections bypass is the
            # realistic insider tamper vector.
            session.execute(text("SET fsma.allow_mutation = 'true'"))
            session.execute(
                text(
                    "UPDATE fsma.hash_chain SET event_hash = :eh, chain_hash = :ch "
                    "WHERE tenant_id = :tid AND sequence_num = :seq"
                ),
                {"eh": fake_event_hash, "ch": fake_chain_hash, "tid": str(tenant_id), "seq": tail[0]},
            )
            session.execute(text("SET fsma.allow_mutation = 'false'"))

            resealed = store.verify_chain_canonical(str(tenant_id))
            assert resealed.valid is False, (
                "re-sealed chain row (event_hash + consistent chain_hash rewrite) "
                "must fail canonical verification — hc.event_hash is unchecked otherwise"
            )
            assert any("Chain-row tamper" in e for e in resealed.errors), resealed.errors
        finally:
            session.rollback()
            session.close()
            engine.dispose()
