"""Real PostgreSQL tests for the EDI line identity registry (ADR-007).

Run with REGENGINE_MIGRATION_TEST_DB pointing to a disposable Postgres server.
CI runs this via the existing live test_*_pg.py gate. The event writers are
replaced with SQL inserts into a stand-in ``fsma.cte_events``, so the registry's
join, lock, row security and transaction are the real ones.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app import webhook_compat as compat
from app.edi_line_identity import EDILine, EDILineRegistry
from app.webhook_models import IngestEvent, WebhookCTEType, WebhookPayload
from fastapi import HTTPException
from shared.canonical_persistence import CanonicalEventStore
from shared.cte_persistence import CTEPersistence
from shared.cte_persistence.models import StoreResult
from shared.rules_engine import RulesEngine
from shared.tenant_context import set_tenant_guc
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from tests.migrations.scratch_db import scratch_database_engine

ROOT = Path(__file__).resolve().parents[3]
MIGRATION = ROOT / "alembic/versions/20261114_62355c37e367_v144_edi_line_identities.py"
SUPABASE_TWIN = ROOT / "supabase/migrations/20261114000000_v144_edi_line_identities.sql"
TABLE = "fsma.edi_line_identities"
TENANT = "11111111-1111-1111-1111-111111111111"
OTHER_TENANT = "22222222-2222-2222-2222-222222222222"
LINE = EDILine("identity-a", "digest-1")
REGISTRY = EDILineRegistry()


def _migration():
    spec = importlib.util.spec_from_file_location("edi_line_identity_migration", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def database():
    if not os.getenv("REGENGINE_MIGRATION_TEST_DB") and not (
        os.getenv("CI") == "true" and os.getenv("REGENGINE_REQUIRE_DB") == "1"
    ):
        pytest.skip("set REGENGINE_MIGRATION_TEST_DB to run live EDI line identity tests")
    with scratch_database_engine("edi_lines_" + uuid4().hex[:12]) as engine:
        with engine.begin() as conn:
            conn.execute(
                text("""
                DO $$ BEGIN
                    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'regengine') THEN
                        CREATE ROLE regengine NOLOGIN NOSUPERUSER NOBYPASSRLS;
                    END IF;
                END $$;
                CREATE SCHEMA fsma;
                GRANT USAGE ON SCHEMA fsma TO regengine;
                CREATE FUNCTION public.get_tenant_context() RETURNS uuid LANGUAGE sql STABLE
                    AS $$ SELECT nullif(current_setting('app.tenant_id', true), '')::uuid $$;
                CREATE TABLE fsma.cte_events (
                    id uuid PRIMARY KEY,
                    tenant_id uuid NOT NULL,
                    quantity double precision NOT NULL,
                    sha256_hash text NOT NULL,
                    chain_hash text NOT NULL
                );
                GRANT SELECT, INSERT ON fsma.cte_events TO regengine;
            """)
            )
            with Operations.context(MigrationContext.configure(conn)):
                _migration().upgrade()
        yield engine


@pytest.fixture()
def db(database):
    with database.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLE}, fsma.cte_events"))
    return database


def _session(db):
    session = Session(db)
    session.execute(text("SET LOCAL ROLE regengine"))
    return session


def _counts(db) -> tuple[int, int]:
    """(registry rows, event rows), read as the owner."""
    with db.connect() as conn:
        return (
            conn.execute(text(f"SELECT count(*) FROM {TABLE}")).scalar_one(),
            conn.execute(text("SELECT count(*) FROM fsma.cte_events")).scalar_one(),
        )


def _store_event(session, tenant_id: str = TENANT, quantity: float = 1.0) -> str:
    event_id = str(uuid4())
    session.execute(
        text("INSERT INTO fsma.cte_events VALUES (CAST(:id AS uuid), CAST(:tenant AS uuid), :qty, 'sha', 'chain')"),
        {"id": event_id, "tenant": tenant_id, "qty": quantity},
    )
    return event_id


def _registered(db, line: EDILine = LINE, tenant_id: str = TENANT) -> str:
    with _session(db) as session:
        set_tenant_guc(session, tenant_id)
        event_id = _store_event(session, tenant_id)
        REGISTRY.record(session, tenant_id, line, event_id)
        session.commit()
    return event_id


def test_a_recorded_line_is_found_with_its_event(db):
    event_id = _registered(db)
    with _session(db) as session:
        found = REGISTRY.lookup(session, TENANT, [LINE, None, EDILine("identity-unknown", "digest-9")])
    assert list(found) == ["identity-a"]
    stored = found["identity-a"]
    assert (stored.content_digest, stored.event_id, stored.sha256_hash, stored.chain_hash) == (
        "digest-1",
        event_id,
        "sha",
        "chain",
    )


def test_tenants_do_not_share_identities_and_rls_denies_cross_tenant_writes(db):
    _registered(db)
    other_event = _registered(db, tenant_id=OTHER_TENANT)
    assert _counts(db) == (2, 2)
    with _session(db) as session:
        assert REGISTRY.lookup(session, OTHER_TENANT, [LINE])["identity-a"].event_id == other_event
    with _session(db) as session:
        set_tenant_guc(session, TENANT)
        rows = session.execute(text(f"SELECT tenant_id FROM {TABLE}")).scalars().all()
        assert [str(row) for row in rows] == [TENANT]
        with pytest.raises(DBAPIError):
            REGISTRY.record(session, OTHER_TENANT, EDILine("identity-b", "digest-1"), str(uuid4()))
    with _session(db) as session:
        set_tenant_guc(session, TENANT)
        with pytest.raises(DBAPIError):
            session.execute(text(f"DELETE FROM {TABLE}"))
    with _session(db) as session:
        # No tenant bound: forced row security shows nothing.
        assert session.execute(text(f"SELECT count(*) FROM {TABLE}")).scalar_one() == 0


def test_the_identity_of_a_live_event_cannot_be_pointed_elsewhere(db):
    _registered(db)
    with _session(db) as session:
        set_tenant_guc(session, TENANT)
        with pytest.raises(RuntimeError, match="already registered"):
            REGISTRY.record(session, TENANT, EDILine("identity-a", "digest-2"), _store_event(session))
    with db.connect() as conn:
        assert conn.execute(text(f"SELECT content_digest FROM {TABLE}")).scalar_one() == "digest-1"


def test_a_purged_event_is_hidden_and_its_identity_is_reused(db):
    _registered(db)
    with db.begin() as conn:
        conn.execute(text("DELETE FROM fsma.cte_events"))
    with _session(db) as session:
        assert REGISTRY.lookup(session, TENANT, [LINE]) == {}
        replacement = _store_event(session)
        REGISTRY.record(session, TENANT, EDILine("identity-a", "digest-2"), replacement)
        session.commit()
    assert _counts(db) == (1, 1)
    with _session(db) as session:
        stored = REGISTRY.lookup(session, TENANT, [LINE])["identity-a"]
    assert (stored.content_digest, stored.event_id) == ("digest-2", replacement)


def test_lookup_serializes_one_tenant_and_not_another(db):
    with _session(db) as first, _session(db) as second, _session(db) as other:
        assert REGISTRY.lookup(first, TENANT, [LINE]) == {}
        second.execute(text("SET LOCAL lock_timeout = '300ms'"))
        with pytest.raises(DBAPIError):
            REGISTRY.lookup(second, TENANT, [LINE])
        second.rollback()
        assert REGISTRY.lookup(other, OTHER_TENANT, [LINE]) == {}
        REGISTRY.record(first, TENANT, LINE, _store_event(first))
        first.commit()
        second.execute(text("SET LOCAL ROLE regengine"))
        assert list(REGISTRY.lookup(second, TENANT, [LINE])) == ["identity-a"]


def test_lookup_normalizes_the_tenant_id(db):
    tenant = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    _registered(db, tenant_id=tenant)
    with _session(db) as session:
        assert list(REGISTRY.lookup(session, tenant.upper(), [LINE])) == ["identity-a"]


def test_lookup_handles_more_identities_than_one_query_holds(db):
    lines = [EDILine(f"identity-{index:04d}", "digest") for index in range(1100)]
    event_id = _registered(db, line=lines[1050])
    with _session(db) as session:
        found = REGISTRY.lookup(session, TENANT, lines)
    assert {key: stored.event_id for key, stored in found.items()} == {"identity-1050": event_id}


@pytest.fixture()
def ingest_db(db, monkeypatch):
    """The real ingest and its transaction, with controllable event writes."""
    faults = {"commit": None, "reject_lot": None}

    def sessions():
        with _session(db) as session:
            real_commit = session.commit

            def commit():
                if faults["commit"] == "before":
                    raise RuntimeError("commit failed")
                real_commit()

            session.commit = commit
            yield session

    def store(self, **kwargs):
        if kwargs["traceability_lot_code"] == faults["reject_lot"]:
            raise ValueError("storage refused")
        event_id = _store_event(self.session, kwargs["tenant_id"], kwargs["quantity"])
        return StoreResult(success=True, event_id=event_id, sha256_hash="sha", chain_hash="chain", idempotent=False)

    monkeypatch.setattr(compat, "_get_db_session", sessions)
    monkeypatch.setattr(compat, "_verify_api_key_sync", lambda **kwargs: None)
    monkeypatch.setattr(compat, "_check_rate_limit", lambda *args: None)
    monkeypatch.setattr(compat, "_validate_event_kdes", lambda *args: [])
    monkeypatch.setattr(compat, "_generate_alerts", lambda *args: [])
    monkeypatch.setattr(compat, "_publish_graph_sync", lambda *args: None)
    monkeypatch.setattr(compat, "record_outcomes", lambda *args: None)
    monkeypatch.setattr(CTEPersistence, "store_event", store)
    monkeypatch.setattr(CanonicalEventStore, "persist_event", lambda self, event: SimpleNamespace(idempotent=False))
    monkeypatch.setattr(RulesEngine, "evaluate_event", lambda *args, **kwargs: SimpleNamespace(compliant=True))
    monkeypatch.setenv("RULES_ENGINE_ENFORCE", "off")
    return faults


def _ingest(lines, isa13="000000001", registry=REGISTRY):
    """Ingest one synthetic advice: ``lines`` are ``(lot, quantity)``."""
    events = [
        IngestEvent(
            cte_type=WebhookCTEType.SHIPPING,
            traceability_lot_code=lot,
            quantity=quantity,
            unit_of_measure="cases",
            location_name="Synthetic warehouse",
            timestamp="2026-01-01T00:00:00Z",
            product_description="synthetic",
            kdes={
                "edi_transaction_set": "945",
                "edi_sender_id": "SENDER",
                "edi_receiver_id": "RECEIVER",
                "edi_isa13": isa13,
                "edi_line_index": index,
                "shipment_id": "SHIP-1",
            },
        )
        for index, (lot, quantity) in enumerate(lines, start=1)
    ]
    payload = WebhookPayload(tenant_id=TENANT, source="edi_test", events=events)
    return asyncio.run(
        compat.ingest_events(
            payload, principal_tenant_id=TENANT, all_or_nothing=registry is not None, edi_lines=registry
        )
    )


def test_a_resend_in_another_envelope_and_order_writes_nothing(db, ingest_db):
    first = _ingest([("SYNTHETIC-LOT-1", 5), ("SYNTHETIC-LOT-2", 7)])
    assert (first.accepted, first.rejected) == (2, 0)
    assert _counts(db) == (2, 2)

    resend = _ingest([("SYNTHETIC-LOT-2", 7), ("SYNTHETIC-LOT-1", 5)], isa13="000000002")

    assert (resend.accepted, resend.rejected) == (2, 0)
    assert _counts(db) == (2, 2)
    assert [event.event_id for event in resend.events] == [first.events[1].event_id, first.events[0].event_id]
    assert [event.sha256_hash for event in resend.events] == ["sha", "sha"]


def test_a_changed_line_is_refused_before_anything_is_written(db, ingest_db):
    first = _ingest([("SYNTHETIC-LOT-1", 5), ("SYNTHETIC-LOT-2", 7)])

    with pytest.raises(HTTPException) as refused:
        _ingest([("SYNTHETIC-LOT-1", 5), ("SYNTHETIC-LOT-2", 9), ("SYNTHETIC-LOT-3", 1)], isa13="000000002")

    assert refused.value.status_code == 409
    assert refused.value.detail["error"] == "edi_line_content_conflict"
    assert refused.value.detail["conflicts"] == [
        {"line": 2, "traceability_lot_code": "SYNTHETIC-LOT-2", "stored_event_id": first.events[1].event_id}
    ]
    assert _counts(db) == (2, 2)
    with db.connect() as conn:
        assert sorted(conn.execute(text("SELECT quantity FROM fsma.cte_events")).scalars()) == [5.0, 7.0]


def test_a_rejected_batch_leaves_no_identity_and_the_corrected_resend_stores(db, ingest_db):
    ingest_db["reject_lot"] = "SYNTHETIC-LOT-2"
    first = _ingest([("SYNTHETIC-LOT-1", 5), ("SYNTHETIC-LOT-2", 7)])
    assert (first.accepted, first.rejected) == (0, 2)
    assert _counts(db) == (0, 0)

    ingest_db["reject_lot"] = None
    # Nothing was stored, so the corrected quantity is not a conflict.
    corrected = _ingest([("SYNTHETIC-LOT-1", 6), ("SYNTHETIC-LOT-2", 7)])
    assert (corrected.accepted, corrected.rejected) == (2, 0)
    assert _counts(db) == (2, 2)


def test_a_failed_commit_rolls_back_events_and_identities(db, ingest_db):
    ingest_db["commit"] = "before"
    with pytest.raises(RuntimeError, match="commit failed"):
        _ingest([("SYNTHETIC-LOT-1", 5)])
    assert _counts(db) == (0, 0)
    ingest_db["commit"] = None
    assert _ingest([("SYNTHETIC-LOT-1", 5)]).accepted == 1
    assert _counts(db) == (1, 1)


def test_a_registry_write_failure_stores_no_event(db, ingest_db, monkeypatch):
    def fail(*args):
        raise RuntimeError("registry write failed")

    monkeypatch.setattr(EDILineRegistry, "record", fail)
    result = _ingest([("SYNTHETIC-LOT-1", 5), ("SYNTHETIC-LOT-2", 7)])
    assert (result.accepted, result.rejected) == (0, 2)
    assert _counts(db) == (0, 0)


def test_other_ingestion_does_not_touch_the_registry(db, ingest_db):
    result = _ingest([("SYNTHETIC-LOT-1", 5)], registry=None)
    assert result.accepted == 1
    assert _counts(db) == (0, 1)


def test_migration_rerun_downgrade_reupgrade_and_cutover_grants(db):
    """Exercise both migration forms and the inventory used on every deploy."""
    with db.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            _migration().upgrade()
            _migration().downgrade()
            assert conn.execute(text(f"SELECT to_regclass('{TABLE}')")).scalar_one() is None
            _migration().upgrade()
        conn.execute(text(SUPABASE_TWIN.read_text()))
        # The cutover revokes all table AND column grants before rebuilding them.
        conn.execute(text(f"REVOKE ALL ON {TABLE} FROM regengine"))
        conn.execute(text(f"REVOKE UPDATE (content_digest, event_id, stored_at) ON {TABLE} FROM regengine"))
        path = ROOT / "alembic/versions/20260803_b71d9e4c2a60_v111_runtime_role_grants.py"
        spec = importlib.util.spec_from_file_location("edi_line_runtime_grant_inventory", path)
        inventory = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(inventory)
        assert "edi_line_identities" in inventory.APPLICATION_TABLES["fsma"]
        conn.execute(text(inventory._grant_sql("regengine", TABLE, inventory.REGENGINE_TABLE_GRANTS[TABLE], "TABLE")))
        for privilege, columns in inventory.REGENGINE_COLUMN_GRANTS[TABLE].items():
            conn.execute(text(inventory._column_grant_sql("regengine", TABLE, privilege, columns)))
        assert conn.execute(
            text(f"SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid = '{TABLE}'::regclass")
        ).scalar_one()
        assert not conn.execute(text(f"SELECT has_table_privilege('regengine', '{TABLE}', 'DELETE')")).scalar_one()
        for column in ("tenant_id", "identity_key"):
            assert not conn.execute(
                text(f"SELECT has_column_privilege('regengine', '{TABLE}', '{column}', 'UPDATE')")
            ).scalar_one()
    # The rebuilt grants are enough for the write, the conditional update and the read.
    _registered(db)
    with db.begin() as conn:
        conn.execute(text("DELETE FROM fsma.cte_events"))
    with _session(db) as session:
        assert REGISTRY.lookup(session, TENANT, [LINE]) == {}
        REGISTRY.record(session, TENANT, LINE, _store_event(session))
        session.commit()
    assert _counts(db) == (1, 1)
