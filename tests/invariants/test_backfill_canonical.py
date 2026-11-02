"""WS-1c — canonical backfill invariants (#1335 step 3).

Covers ``scripts/backfill_canonical_from_legacy.py``, which gives every
``fsma.cte_events`` row a canonical ``fsma.traceability_events`` twin so the
canonical store is a complete superset before the legacy write path is
retired (WS-1d). The join key is ``sha256_hash``.

What is asserted here is deliberately the *safety* contract, not merely the
happy path:

1. ``test_dry_run_mutates_nothing`` — the default invocation writes nothing.
2. ``test_execute_backfills_orphan`` — a deliberately orphaned legacy row gets
   a canonical twin whose ``sha256_hash`` is byte-identical AND whose stored
   columns recompute to that same hash (so ``verify_chain_canonical`` still
   passes over the backfilled row).
3. ``test_second_run_is_a_noop`` — idempotent/resumable.
4. ``test_to_facility_only_orphan_resolves_to_to_facility`` — the ambiguity
   case. ``dual_write_legacy`` collapses ``from_facility_reference`` and
   ``to_facility_reference`` into ``location_gln``; the script must recover
   the ``to``-only shape from the hash preimage rather than defaulting to
   ``from``.
5. ``test_legacy_native_row_is_refused`` — a row written by the legacy-native
   ``CTEPersistence.store_event`` path carries a DIFFERENT hash formula. It
   must be refused (synthesizing it would duplicate an FDA event and inject a
   hash the canonical verifier cannot reproduce), not backfilled.

Needs a real Postgres — same contract as the sibling invariant suites.
"""

from __future__ import annotations

import importlib.util
import json
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


def _load_backfill_module():
    """Import the script by path — ``scripts/`` is not an importable package."""
    path = REPO_ROOT / "scripts" / "backfill_canonical_from_legacy.py"
    spec = importlib.util.spec_from_file_location("ws1c_backfill", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["ws1c_backfill"] = module
    spec.loader.exec_module(module)
    return module


backfill = _load_backfill_module()


def _legacy_row_from(event, **overrides):
    """Project a canonical event through the dual_write_legacy mapping.

    Mirrors ``legacy_dual_write.dual_write_legacy`` exactly, so these cases
    exercise the real forward mapping without needing a database.
    """
    from shared.canonical_event import EventStatus

    row = backfill.LegacyRow(
        id=str(event.event_id),
        tenant_id=str(event.tenant_id),
        event_type=event.event_type.value,
        traceability_lot_code=event.traceability_lot_code,
        product_description=event.product_reference or "",
        quantity=event.quantity,
        unit_of_measure=event.unit_of_measure,
        location_gln=event.from_facility_reference or event.to_facility_reference,
        location_name=event.from_facility_reference or event.to_facility_reference,
        event_timestamp=event.event_timestamp,
        source=event.source_system.value,
        source_event_id=event.source_record_id,
        sha256_hash=event.compute_sha256_hash(),
        chain_hash="0" * 64,
        epcis_event_type=None,
        epcis_action=None,
        epcis_biz_step=None,
        validation_status="valid",
        ingested_at=datetime.now(timezone.utc),
        kdes=dict(event.kdes),
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    _ = EventStatus  # imported for symmetry with the caller's status arg
    return row


class TestFacilityAmbiguityResolution:
    """No database: the ambiguity oracle is pure computation over the preimage."""

    @pytest.mark.parametrize(
        ("from_facility", "to_facility", "expected"),
        [
            ("urn:gs1:414:0614141000005", None, backfill.H_FROM_ONLY),
            (None, "urn:gs1:414:0614141000012", backfill.H_TO_ONLY),
            ("urn:gs1:414:0614141000005", "urn:gs1:414:0614141000005", backfill.H_FROM_AND_TO),
            (None, None, backfill.H_NEITHER),
        ],
    )
    def test_every_recoverable_split_is_proven(self, from_facility, to_facility, expected):
        from shared.canonical_event import EventStatus

        event = _make_event(uuid4(), from_facility=from_facility, to_facility=to_facility)
        row = _legacy_row_from(event)

        rec, reason = backfill.reconstruct(row, EventStatus.ACTIVE)

        assert reason is None
        assert rec is not None
        assert rec.hypothesis == expected
        assert rec.event.from_facility_reference == from_facility
        assert rec.event.to_facility_reference == to_facility
        # The reconstruction reproduces the preserved hash exactly.
        assert rec.event.compute_sha256_hash() == row.sha256_hash

    def test_distinct_from_and_to_is_refused_not_guessed(self):
        """The one split the forward mapping truly destroys.

        ``location_gln`` keeps only ``from``; ``to`` is a third value nothing
        can derive. The script must refuse rather than invent a to_facility
        (or silently drop it and write a row whose columns no longer hash to
        its own sha256_hash).
        """
        from shared.canonical_event import EventStatus

        event = _make_event(
            uuid4(),
            from_facility="urn:gs1:414:0614141000005",
            to_facility="urn:gs1:414:0614141000012",
        )
        row = _legacy_row_from(event)

        rec, reason = backfill.reconstruct(row, EventStatus.ACTIVE)

        assert rec is None
        assert reason == backfill.R_HASH_UNRECONSTRUCTIBLE

    def test_dropped_none_valued_kde_is_refused(self):
        """dual_write_legacy drops None-valued KDE keys; the hash covers them."""
        from shared.canonical_event import EventStatus

        event = _make_event(uuid4(), from_facility="urn:gs1:414:0614141000005")
        event.kdes["harvest_date"] = None
        row = _legacy_row_from(event)
        row.kdes = {k: v for k, v in event.kdes.items() if v is not None}

        rec, reason = backfill.reconstruct(row, EventStatus.ACTIVE)

        assert rec is None
        assert reason == backfill.R_HASH_UNRECONSTRUCTIBLE


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


@pytest.fixture()
def tenant_session(migrated_db):
    """A fresh tenant plus a session with the RLS GUC set."""
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
                "name": f"ws1c-{tenant_id.hex[:8]}",
                "slug": f"ws1c-{tenant_id.hex[:8]}",
            },
        )
    session_factory = sessionmaker(bind=engine, future=True)
    session = session_factory()
    session.execute(text("SELECT set_config('app.tenant_id', :tid, false)"), {"tid": str(tenant_id)})
    try:
        yield session, tenant_id, database_url
    finally:
        session.rollback()
        session.close()
        engine.dispose()


def _make_event(tenant_id, *, from_facility=None, to_facility=None, tlc_suffix=""):
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
        lot_reference="LOT-WS1C",
        traceability_lot_code=f"TLC-WS1C-{tlc_suffix}{uuid4().hex[:8]}",
        quantity=12.5,
        unit_of_measure="kg",
        from_facility_reference=from_facility,
        to_facility_reference=to_facility,
        kdes={"gtin": "09506000134352", "temperature_celsius": 4},
        status=EventStatus.ACTIVE,
        provenance=ProvenanceMetadata(),
    )


def _persist_dual(session, event):
    from shared.canonical_persistence.writer import CanonicalEventStore

    CanonicalEventStore(session, dual_write=True).persist_event(event)
    session.commit()


def _orphan_the_canonical_row(session, tenant_id, event_id):
    """Simulate the #1277 failure: legacy row survives, canonical row is lost."""
    # v141 append-only trigger: the simulated loss needs the break-glass GUC.
    session.execute(text("SET LOCAL fsma.allow_mutation = 'true'"))
    session.execute(
        text(
            "DELETE FROM fsma.traceability_events "
            "WHERE tenant_id = :tid AND event_id = :eid"
        ),
        {"tid": str(tenant_id), "eid": str(event_id)},
    )
    session.commit()


def _canonical_count(session, tenant_id):
    return session.execute(
        text("SELECT COUNT(*) FROM fsma.traceability_events WHERE tenant_id = :tid"),
        {"tid": str(tenant_id)},
    ).scalar()


def _run(database_url, tenant_id, *extra):
    return backfill.main(
        ["--database-url", database_url, "--tenant-id", str(tenant_id), *extra]
    )


class TestBackfillSafety:
    def test_dry_run_mutates_nothing(self, tenant_session):
        session, tenant_id, database_url = tenant_session
        event = _make_event(tenant_id, from_facility="urn:gs1:414:0614141000005")
        _persist_dual(session, event)
        _orphan_the_canonical_row(session, tenant_id, event.event_id)

        before = _canonical_count(session, tenant_id)
        assert before == 0

        # No --execute: the default invocation must not write.
        assert _run(database_url, tenant_id) == 0

        session.rollback()
        assert _canonical_count(session, tenant_id) == before

    def test_execute_backfills_orphan(self, tenant_session):
        session, tenant_id, database_url = tenant_session
        event = _make_event(tenant_id, from_facility="urn:gs1:414:0614141000005")
        _persist_dual(session, event)
        _orphan_the_canonical_row(session, tenant_id, event.event_id)

        assert _run(database_url, tenant_id, "--execute") == 0

        session.rollback()
        row = session.execute(
            text("""
                SELECT event_id, sha256_hash, chain_hash, from_facility_reference,
                       to_facility_reference, product_reference, quantity,
                       unit_of_measure, event_type, traceability_lot_code,
                       kdes, provenance_metadata, status, event_timestamp
                FROM fsma.traceability_events
                WHERE tenant_id = :tid AND event_id = :eid
            """),
            {"tid": str(tenant_id), "eid": str(event.event_id)},
        ).fetchone()
        assert row is not None, "orphaned legacy row was not backfilled"

        # sha256_hash is the join key AND the integrity anchor — verbatim.
        assert row[1] == event.sha256_hash
        assert row[2] == event.chain_hash

        # The ambiguity was resolved to the true shape, proven by the preimage.
        assert row[3] == "urn:gs1:414:0614141000005"
        assert row[4] is None

        # The stored columns must recompute to the stored hash, or
        # verify_chain_canonical would fail forever on this row.
        from shared.canonical_persistence.verification import _recompute_event_sha256

        kdes = row[10] if isinstance(row[10], dict) else json.loads(row[10] or "{}")
        assert (
            _recompute_event_sha256(
                event_id=str(row[0]),
                event_type=row[8],
                traceability_lot_code=row[9],
                product_reference=row[5],
                quantity=row[6],
                unit_of_measure=row[7],
                from_facility_reference=row[3],
                to_facility_reference=row[4],
                event_timestamp=row[13],
                kdes=kdes,
            )
            == row[1]
        )

        # Provenance is explicitly marked as a reconstruction.
        provenance = row[11] if isinstance(row[11], dict) else json.loads(row[11] or "{}")
        assert provenance["mapper_name"] == backfill.BACKFILL_MAPPER_NAME
        assert provenance["backfill"]["sha256_verified"] is True
        assert provenance["backfill"]["source_row_id"] == str(event.event_id)
        resolutions = {a["field"]: a for a in provenance["backfill"]["ambiguities"]}
        assert (
            resolutions["from_facility_reference/to_facility_reference"]["resolution"]
            == backfill.H_FROM_ONLY
        )
        assert provenance["backfill"]["unrecoverable_fields"]

    def test_second_run_is_a_noop(self, tenant_session):
        session, tenant_id, database_url = tenant_session
        event = _make_event(tenant_id, from_facility="urn:gs1:414:0614141000005")
        _persist_dual(session, event)
        _orphan_the_canonical_row(session, tenant_id, event.event_id)

        assert _run(database_url, tenant_id, "--execute") == 0
        session.rollback()
        after_first = _canonical_count(session, tenant_id)

        assert _run(database_url, tenant_id, "--execute") == 0
        session.rollback()
        assert _canonical_count(session, tenant_id) == after_first

    def test_to_facility_only_orphan_resolves_to_to_facility(self, tenant_session):
        """The ambiguity case: location_gln must not be assumed to be `from`."""
        session, tenant_id, database_url = tenant_session
        event = _make_event(tenant_id, to_facility="urn:gs1:414:0614141000012")
        _persist_dual(session, event)

        legacy_gln = session.execute(
            text("SELECT location_gln FROM fsma.cte_events WHERE tenant_id = :tid AND id = :eid"),
            {"tid": str(tenant_id), "eid": str(event.event_id)},
        ).scalar()
        assert legacy_gln == "urn:gs1:414:0614141000012", "forward mapping changed"

        _orphan_the_canonical_row(session, tenant_id, event.event_id)
        assert _run(database_url, tenant_id, "--execute") == 0

        session.rollback()
        row = session.execute(
            text("""
                SELECT from_facility_reference, to_facility_reference, sha256_hash
                FROM fsma.traceability_events
                WHERE tenant_id = :tid AND event_id = :eid
            """),
            {"tid": str(tenant_id), "eid": str(event.event_id)},
        ).fetchone()
        assert row is not None
        assert row[0] is None, "backfill guessed from_facility instead of proving to_facility"
        assert row[1] == "urn:gs1:414:0614141000012"
        assert row[2] == event.sha256_hash

    def test_outer_commit_failure_is_not_recorded_as_backfill(self, tenant_session, tmp_path):
        """A mid-batch outer commit failure must leave the audit trail and the
        summary honest: the batch's rows are rolled back, so none may be counted
        as ``backfilled`` nor emitted to the JSONL trail as a durable ``backfill``.

        This is the #1335 data-integrity contract: a row insert is savepoint-
        committed inside the batch transaction, but ``sp.commit()`` only RELEASES
        the savepoint — durability depends on the OUTER ``session.commit()``. We
        simulate that outer commit raising and assert nothing claims a write the
        database rolled back.
        """
        session, tenant_id, database_url = tenant_session
        # A plain from-facility orphan reconstructs cleanly (see
        # test_execute_backfills_orphan), so absent the commit failure this row
        # WOULD be backfilled — that is what makes the deferral observable.
        event = _make_event(tenant_id, from_facility="urn:gs1:414:0614141000005")
        _persist_dual(session, event)
        _orphan_the_canonical_row(session, tenant_id, event.event_id)

        # A session_factory whose produced sessions raise on the OUTER commit,
        # exactly as a mid-batch commit failure would, while every read query and
        # the savepoint INSERT still succeed.
        engine = create_engine(sync_postgres_url(database_url), future=True)
        real_factory = sessionmaker(
            bind=engine, future=True, autoflush=False, expire_on_commit=False
        )

        def failing_factory():
            s = real_factory()

            def boom():
                raise RuntimeError("simulated outer commit failure")

            s.commit = boom  # shadow the bound method for this session
            return s

        summary = backfill.Summary(tenants=1)
        args = backfill.build_parser().parse_args(
            ["--database-url", database_url, "--tenant-id", str(tenant_id), "--execute"]
        )
        report_path = tmp_path / "decisions.jsonl"

        try:
            with open(report_path, "a", encoding="utf-8") as report:
                # process_tenant re-raises after rolling the batch back.
                with pytest.raises(RuntimeError, match="simulated outer commit failure"):
                    backfill.process_tenant(
                        failing_factory, str(tenant_id), args, summary, report, {}, None
                    )
        finally:
            engine.dispose()

        # The row was examined, but NOT counted as backfilled — the commit that
        # would have made it durable never landed.
        assert summary.orphans_examined == 1
        assert summary.backfilled == 0
        assert not summary.by_hypothesis, "facility-hypothesis counters were bumped for a rolled-back batch"
        assert summary.chain_entry_missing == 0
        assert summary.status_assumed_active == 0

        # The audit trail must not claim a durable backfill for this row. A
        # batch-level 'rolled_back' record is emitted instead.
        decisions = [
            json.loads(line)
            for line in report_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        backfills = [d for d in decisions if d.get("decision") == "backfill"]
        assert backfills == [], "a rolled-back row was emitted to the audit trail as a durable backfill"
        rolled_back = [d for d in decisions if d.get("decision") == "rolled_back"]
        assert len(rolled_back) == 1
        assert str(event.event_id) in rolled_back[0]["rolled_back_legacy_ids"]

        # And the database itself has no canonical twin — the rollback undid the
        # savepoint insert, so the audit trail and the DB agree.
        session.rollback()
        assert _canonical_count(session, tenant_id) == 0

    def test_legacy_native_row_is_refused(self, tenant_session, tmp_path):
        """A ``store_event``-shaped row uses a different hash formula — refuse it."""
        from shared.cte_persistence.hashing import compute_event_hash

        session, tenant_id, database_url = tenant_session
        legacy_id = uuid4()
        ts = datetime.now(timezone.utc)
        kdes = {"gtin": "09506000134352"}
        legacy_hash = compute_event_hash(
            str(legacy_id),
            "shipping",
            "TLC-LEGACY-NATIVE",
            "Romaine lettuce",
            9.0,
            "kg",
            "urn:gs1:414:0614141000005",
            "urn:gs1:414:0614141000005",
            ts.isoformat(),
            kdes,
        )
        session.execute(
            text("""
                INSERT INTO fsma.cte_events (
                    id, tenant_id, event_type, traceability_lot_code,
                    product_description, quantity, unit_of_measure,
                    location_gln, location_name, event_timestamp,
                    source, idempotency_key, sha256_hash, chain_hash,
                    validation_status
                ) VALUES (
                    :id, :tid, 'shipping', 'TLC-LEGACY-NATIVE',
                    'Romaine lettuce', 9.0, 'kg',
                    :gln, :gln, :ts,
                    'api', :idem, :sha, :chain, 'valid'
                )
            """),
            {
                "id": str(legacy_id),
                "tid": str(tenant_id),
                "gln": "urn:gs1:414:0614141000005",
                "ts": ts,
                "idem": f"legacy-native-{legacy_id.hex}",
                "sha": legacy_hash,
                "chain": "0" * 64,
            },
        )
        # store_event writes the KDEs alongside the event; the fixture must
        # too, or the legacy-formula probe would be comparing against {}.
        for key, value in kdes.items():
            session.execute(
                text("""
                    INSERT INTO fsma.cte_kdes (tenant_id, cte_event_id, kde_key, kde_value)
                    VALUES (:tid, :eid, :k, CAST(:v AS jsonb))
                """),
                {"tid": str(tenant_id), "eid": str(legacy_id), "k": key, "v": json.dumps(value)},
            )
        session.commit()

        report_path = tmp_path / "decisions.jsonl"
        assert _run(database_url, tenant_id, "--execute", "--report-path", str(report_path)) == 0

        decisions = [
            json.loads(line)
            for line in report_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        mine = [d for d in decisions if d["legacy_id"] == str(legacy_id)]
        assert len(mine) == 1
        assert mine[0]["decision"] == "skip"
        assert mine[0]["reason"] == backfill.R_LEGACY_NATIVE, (
            "the legacy-native hash formula must be named explicitly — an operator "
            "needs to know this row is not a lost canonical write"
        )

        session.rollback()
        assert (
            session.execute(
                text(
                    "SELECT COUNT(*) FROM fsma.traceability_events "
                    "WHERE tenant_id = :tid AND event_id = :eid"
                ),
                {"tid": str(tenant_id), "eid": str(legacy_id)},
            ).scalar()
            == 0
        ), (
            "a legacy-native cte_events row was synthesized into the canonical "
            "store — its sha256_hash uses the legacy formula and would break "
            "canonical chain verification"
        )
