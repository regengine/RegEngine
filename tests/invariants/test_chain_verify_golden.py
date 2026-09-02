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
    engine = create_engine(database_url, future=True)
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
