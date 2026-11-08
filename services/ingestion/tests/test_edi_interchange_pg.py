"""Real PostgreSQL transaction, concurrency and RLS tests for ISA13 receipts.

Run with REGENGINE_MIGRATION_TEST_DB pointing to a disposable Postgres server.
CI runs this via the existing live test_*_pg.py gate. Event writers are replaced
with SQL inserts so failures can be injected around the real ingest commit.
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
from app.authz import IngestionPrincipal, get_ingestion_principal
from app.edi_ingestion import dedup, router, routes
from app.edi_interchange import EDIInterchange
from app.webhook_models import IngestEvent, WebhookCTEType, WebhookPayload
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
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
TENANT = "11111111-1111-1111-1111-111111111111"
OTHER_TENANT = "22222222-2222-2222-2222-222222222222"
ENVELOPE = EDIInterchange("sender", "receiver", "000000001")


def _migration():
    path = ROOT / "alembic/versions/20261108_c4a9d2e761b0_v143_edi_interchanges.py"
    spec = importlib.util.spec_from_file_location("edi_receipt_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def database():
    if not os.getenv("REGENGINE_MIGRATION_TEST_DB") and not (
        os.getenv("CI") == "true" and os.getenv("REGENGINE_REQUIRE_DB") == "1"
    ):
        pytest.skip("set REGENGINE_MIGRATION_TEST_DB to run live ISA13 tests")
    with scratch_database_engine("edi_receipts_" + uuid4().hex[:12]) as engine:
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
                CREATE TABLE public.edi_test_events (kind text, tenant_id uuid, quantity float);
                GRANT SELECT, INSERT ON public.edi_test_events TO regengine;
            """)
            )
            with Operations.context(MigrationContext.configure(conn)):
                _migration().upgrade()
        yield engine


@pytest.fixture()
def db(database):
    with database.begin() as conn:
        conn.execute(text("TRUNCATE fsma.edi_interchanges, public.edi_test_events"))
    return database


def _session(db):
    session = Session(db)
    session.execute(text("SET LOCAL ROLE regengine"))
    return session


def _counts(db):
    with db.connect() as conn:
        return (
            conn.execute(text("SELECT count(*) FROM fsma.edi_interchanges")).scalar_one(),
            conn.execute(text("SELECT count(*) FROM public.edi_test_events")).scalar_one(),
        )


def test_concurrent_attempt_retry_then_commit_and_changed_content_replay(db):
    with _session(db) as first, _session(db) as second:
        ENVELOPE.reserve(first, TENANT)
        with pytest.raises(HTTPException) as blocked:
            ENVELOPE.reserve(second, TENANT)
        assert blocked.value.status_code == 503
        assert blocked.value.headers == {"Retry-After": "30"}
        second.rollback()
        ENVELOPE.record_stored(first, TENANT)
        first.commit()
        with pytest.raises(HTTPException) as replay:
            ENVELOPE.reserve(second, TENANT)
        assert replay.value.status_code == 409
        assert replay.value.detail["idempotent_replay"] is True


def test_rollback_releases_lock_and_receipt_for_corrected_retry(db):
    with _session(db) as first:
        ENVELOPE.reserve(first, TENANT)
        ENVELOPE.record_stored(first, TENANT)
        first.rollback()
    assert _counts(db) == (0, 0)
    with _session(db) as retry:
        ENVELOPE.reserve(retry, TENANT)
        ENVELOPE.record_stored(retry, TENANT)
        retry.commit()
    assert _counts(db) == (1, 0)


def test_tenants_do_not_share_lock_or_receipt_and_rls_denies_cross_tenant_write(db):
    with _session(db) as first, _session(db) as second:
        ENVELOPE.reserve(first, TENANT)
        ENVELOPE.reserve(second, OTHER_TENANT)
        ENVELOPE.record_stored(first, TENANT)
        ENVELOPE.record_stored(second, OTHER_TENANT)
        first.commit()
        second.commit()
    with _session(db) as session:
        set_tenant_guc(session, TENANT)
        rows = session.execute(text("SELECT tenant_id FROM fsma.edi_interchanges")).scalars().all()
        assert [str(row) for row in rows] == [TENANT]
        with pytest.raises(DBAPIError):
            ENVELOPE.record_stored(session, OTHER_TENANT)
    with _session(db) as session:
        set_tenant_guc(session, TENANT)
        with pytest.raises(DBAPIError):
            session.execute(text("DELETE FROM fsma.edi_interchanges"))
    with _session(db) as session:
        assert session.execute(text("SELECT count(*) FROM fsma.edi_interchanges")).scalar_one() == 0


def test_expired_receipt_can_be_reused_without_growing_rows(db):
    with db.begin() as conn:
        conn.execute(
            text("""
            INSERT INTO fsma.edi_interchanges VALUES
                (:tenant, 'sender', 'receiver', '000000001', now() - interval '8 days', now() - interval '1 day')
        """),
            {"tenant": TENANT},
        )
    with _session(db) as session:
        ENVELOPE.reserve(session, TENANT)
        ENVELOPE.record_stored(session, TENANT)
        session.commit()
    with db.connect() as conn:
        lifetime = conn.execute(text("SELECT expires_at - stored_at FROM fsma.edi_interchanges")).scalar_one()
        assert 604799 < lifetime.total_seconds() <= 604801
    assert _counts(db) == (1, 0)


@pytest.fixture()
def ingest_db(db, monkeypatch):
    """Real ingest and transaction, with controllable event writes and cleanup."""
    faults = {"cleanup": None, "commit": None, "reject": False, "cancel_before": False}

    def sessions():
        with _session(db) as session:
            real_commit = session.commit

            def commit():
                if faults["commit"] == "before":
                    raise RuntimeError("commit failed")
                real_commit()
                if faults["commit"] == "after":
                    raise RuntimeError("commit acknowledgement lost")

            session.commit = commit
            yield session
            if faults["cleanup"] is not None:
                raise faults["cleanup"]

    def store(self, **kwargs):
        if faults["cancel_before"]:
            raise asyncio.CancelledError()
        if faults["reject"]:
            raise ValueError("storage refused")
        self.session.execute(
            text("INSERT INTO public.edi_test_events VALUES ('cte', :tenant, :qty)"),
            {"tenant": kwargs["tenant_id"], "qty": kwargs["quantity"]},
        )
        return StoreResult(
            success=True, event_id=str(uuid4()), sha256_hash="hash", chain_hash="chain", idempotent=False
        )

    def canonical(self, event):
        self.session.execute(
            text("INSERT INTO public.edi_test_events VALUES ('canonical', :tenant, :qty)"),
            {"tenant": event.tenant_id, "qty": event.quantity},
        )
        return SimpleNamespace(idempotent=False)

    monkeypatch.setattr(compat, "_get_db_session", sessions)
    monkeypatch.setattr(compat, "_verify_api_key_sync", lambda **kwargs: None)
    monkeypatch.setattr(compat, "_check_rate_limit", lambda *args: None)
    monkeypatch.setattr(compat, "_validate_event_kdes", lambda *args: [])
    monkeypatch.setattr(compat, "_generate_alerts", lambda *args: [])
    monkeypatch.setattr(compat, "_publish_graph_sync", lambda *args: None)
    monkeypatch.setattr(compat, "record_outcomes", lambda *args: None)
    monkeypatch.setattr(CTEPersistence, "store_event", store)
    monkeypatch.setattr(CanonicalEventStore, "persist_event", canonical)
    monkeypatch.setattr(RulesEngine, "evaluate_event", lambda *args, **kwargs: SimpleNamespace(compliant=True))
    monkeypatch.setenv("RULES_ENGINE_ENFORCE", "off")
    return faults


def _ingest(quantity=1, interchange=ENVELOPE):
    payload = WebhookPayload(
        tenant_id=TENANT,
        source="edi_test",
        events=[
            IngestEvent(
                cte_type=WebhookCTEType.SHIPPING,
                traceability_lot_code="SYNTHETIC-LOT",
                quantity=quantity,
                unit_of_measure="cases",
                location_name="Synthetic warehouse",
                timestamp="2026-01-01T00:00:00Z",
                product_description="synthetic",
                kdes={},
            )
        ],
    )
    return asyncio.run(compat.ingest_events(payload, principal_tenant_id=TENANT, edi_interchange=interchange))


@pytest.mark.parametrize("failure", ["cleanup", "cancel", "lost_ack"])
def test_post_commit_failure_still_rejects_changed_content(db, ingest_db, failure):
    if failure == "lost_ack":
        ingest_db["commit"] = "after"
    else:
        ingest_db["cleanup"] = asyncio.CancelledError() if failure == "cancel" else RuntimeError("cleanup failed")
    with pytest.raises((RuntimeError, asyncio.CancelledError)):
        _ingest()
    assert _counts(db) == (1, 2)
    ingest_db.update(cleanup=None, commit=None)
    with pytest.raises(HTTPException) as replay:
        _ingest(quantity=99)
    assert replay.value.status_code == 409
    assert _counts(db) == (1, 2)


def test_failed_commit_rolls_back_events_and_receipt(db, ingest_db):
    ingest_db["commit"] = "before"
    with pytest.raises(RuntimeError):
        _ingest()
    assert _counts(db) == (0, 0)
    ingest_db["commit"] = None
    assert _ingest(quantity=99).accepted == 1
    assert _counts(db) == (1, 2)


def test_all_rejected_leaves_no_receipt_and_corrected_retry_stores(db, ingest_db):
    ingest_db["reject"] = True
    assert _ingest().accepted == 0
    assert _counts(db) == (0, 0)
    ingest_db["reject"] = False
    assert _ingest().accepted == 1
    assert _counts(db) == (1, 2)


@pytest.mark.parametrize("route", ["", "/document"])
def test_real_routes_reject_changed_resend_after_post_commit_error_without_redis(db, ingest_db, monkeypatch, route):
    monkeypatch.setattr(dedup, "_redis_client", lambda: None)
    monkeypatch.delenv("EDI_REQUIRE_PARTNER_ID", raising=False)
    monkeypatch.delenv("EDI_PARTNER_ALLOWLIST", raising=False)
    monkeypatch.setattr(routes, "ingest_events", compat.ingest_events)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test-key", tenant_id=TENANT, scopes=["*"], auth_mode="test"
    )
    raw = (Path(__file__).parent / "fixtures/edi_corpus/asn_856.edi").read_bytes()
    data = {"tenant_id": TENANT, "traceability_lot_code": "00012345678901-LOT001"}
    ingest_db["cleanup"] = RuntimeError("cleanup failed")
    with TestClient(app, raise_server_exceptions=False) as client:
        first = client.post(f"/api/v1/ingest/edi{route}", data=data, files={"file": ("asn.edi", raw)})
        assert first.status_code == 500
        assert _counts(db) == (1, 2)
        ingest_db["cleanup"] = None
        changed = raw.replace(b"SN1**200*CA~", b"SN1**201*CA~")
        assert changed != raw
        second = client.post(f"/api/v1/ingest/edi{route}", data=data, files={"file": ("asn.edi", changed)})
        assert second.status_code == 409, second.text
        assert second.json()["detail"]["idempotent_replay"] is True
        assert _counts(db) == (1, 2)


def test_receipt_write_failure_rolls_back_accepted_events(db, ingest_db, monkeypatch):
    def fail(*args):
        raise RuntimeError("receipt write failed")

    monkeypatch.setattr(EDIInterchange, "record_stored", fail)
    with pytest.raises(RuntimeError, match="receipt write failed"):
        _ingest()
    assert _counts(db) == (0, 0)


def test_cancel_before_commit_leaves_corrected_retry_possible(db, ingest_db):
    ingest_db["cancel_before"] = True
    with pytest.raises(asyncio.CancelledError):
        _ingest()
    assert _counts(db) == (0, 0)
    ingest_db["cancel_before"] = False
    assert _ingest().accepted == 1


def test_migration_rerun_downgrade_reupgrade_and_cutover_grants(db):
    """Exercise both migration forms and the inventory used on every deploy."""
    with db.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            _migration().upgrade()
            _migration().downgrade()
            assert conn.execute(text("SELECT to_regclass('fsma.edi_interchanges')")).scalar_one() is None
            _migration().upgrade()
        conn.execute(text((ROOT / "supabase/migrations/20261108000000_v143_edi_interchanges.sql").read_text()))
        # The cutover revokes all table AND column grants before rebuilding them.
        conn.execute(text("REVOKE ALL ON fsma.edi_interchanges FROM regengine"))
        conn.execute(text("REVOKE UPDATE (stored_at, expires_at) ON fsma.edi_interchanges FROM regengine"))
        path = ROOT / "alembic/versions/20260803_b71d9e4c2a60_v111_runtime_role_grants.py"
        spec = importlib.util.spec_from_file_location("edi_runtime_grant_inventory", path)
        inventory = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(inventory)
        assert "edi_interchanges" in inventory.APPLICATION_TABLES["fsma"]
        conn.execute(
            text(
                inventory._grant_sql(
                    "regengine",
                    "fsma.edi_interchanges",
                    inventory.REGENGINE_TABLE_GRANTS["fsma.edi_interchanges"],
                    "TABLE",
                )
            )
        )
        for privilege, columns in inventory.REGENGINE_COLUMN_GRANTS["fsma.edi_interchanges"].items():
            conn.execute(text(inventory._column_grant_sql("regengine", "fsma.edi_interchanges", privilege, columns)))
        assert conn.execute(
            text("""
            SELECT relrowsecurity AND relforcerowsecurity FROM pg_class
            WHERE oid = 'fsma.edi_interchanges'::regclass
        """)
        ).scalar_one()
        assert not conn.execute(
            text("SELECT has_table_privilege('regengine', 'fsma.edi_interchanges', 'DELETE')")
        ).scalar_one()
        assert not conn.execute(
            text("SELECT has_column_privilege('regengine', 'fsma.edi_interchanges', 'tenant_id', 'UPDATE')")
        ).scalar_one()
    with _session(db) as session:
        ENVELOPE.reserve(session, TENANT)
        ENVELOPE.record_stored(session, TENANT)
        session.commit()
    assert _counts(db) == (1, 0)


def test_lock_identity_normalizes_uuid_and_envelope_whitespace(db):
    tenant = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    with _session(db) as first, _session(db) as second:
        ENVELOPE.reserve(first, tenant)
        with pytest.raises(HTTPException) as blocked:
            EDIInterchange(" sender ", " receiver ", " 000000001 ").reserve(second, tenant.upper())
        assert blocked.value.status_code == 503


def test_non_edi_ingestion_does_not_require_an_interchange_receipt(db, ingest_db):
    result = _ingest(interchange=None)
    assert result.accepted == 1
    assert _counts(db) == (0, 2)
