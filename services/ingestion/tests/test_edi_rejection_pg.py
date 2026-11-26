"""PostgreSQL durability and tenant isolation for EDI rejection evidence.

The ingestion CI gate runs test_*_pg.py against a disposable database.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.edi_ingestion import rejection_log
from shared import database as shared_database, tenant_context
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from tests.migrations.scratch_db import scratch_database_engine

ROOT = Path(__file__).resolve().parents[3]
TENANT = "11111111-1111-1111-1111-111111111111"
OTHER_TENANT = "22222222-2222-2222-2222-222222222222"


def _migration(filename):
    spec = importlib.util.spec_from_file_location("edi_rejection_migration", ROOT / "alembic/versions" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def database():
    if not os.getenv("REGENGINE_MIGRATION_TEST_DB") and not (
        os.getenv("CI") == "true" and os.getenv("REGENGINE_REQUIRE_DB") == "1"
    ):
        pytest.skip("set REGENGINE_MIGRATION_TEST_DB to run live EDI rejection tests")
    with scratch_database_engine("edi_rejections_" + uuid4().hex[:12]) as engine:
        with engine.begin() as conn:
            conn.execute(text("""
                DO $$ BEGIN
                    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'regengine') THEN
                        CREATE ROLE regengine NOLOGIN NOSUPERUSER NOBYPASSRLS;
                    END IF;
                END $$;
                CREATE FUNCTION public.get_tenant_context() RETURNS uuid LANGUAGE sql STABLE
                    AS $$ SELECT nullif(current_setting('app.tenant_id', true), '')::uuid $$;
                """))
            with Operations.context(MigrationContext.configure(conn)):
                _migration("20260512_8a9b0c1d2e3f_v080_rule_rejections_audit.py").upgrade()
                _migration("20260613_e3f4a5b6c7d8_v083_fsma_rls_coverage_repair.py").upgrade()
            grants = _migration("20260803_b71d9e4c2a60_v111_runtime_role_grants.py").REGENGINE_TABLE_GRANTS
            assert grants["fsma.rule_rejections"] == ("INSERT",)
            assert conn.execute(
                text(
                    "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid = 'fsma.rule_rejections'::regclass"
                )
            ).scalar_one()
            conn.execute(text("GRANT USAGE ON SCHEMA fsma TO regengine"))
            conn.execute(text("GRANT INSERT ON fsma.rule_rejections TO regengine"))
        yield engine


def _runtime_session(database):
    session = Session(database)
    session.execute(text("SET LOCAL ROLE regengine"))
    return session


@pytest.fixture()
def db(database, monkeypatch):
    with database.begin() as conn:
        conn.execute(text("TRUNCATE fsma.rule_rejections"))
    rejection_log.reset_edi_rejections()
    monkeypatch.setattr(shared_database, "SessionLocal", lambda: _runtime_session(database))
    yield database
    rejection_log.reset_edi_rejections()


def _record(tenant_id=TENANT):
    return rejection_log.record_edi_rejection(
        tenant_id=tenant_id,
        transaction_set="856",
        traceability_lot_code=None,
        errors=[{"loc": ["ship_date_raw"], "type": "invalid_edi_date"}],
        extracted={"ship_date_raw": "20261345", "line_items": [{"lot_number": "LOT-A"}]},
        source_document="ST*856*0001~BSN*00*ASN-A*20261345~SE*3*0001~",
        rejected_date="20261345",
        reason="invalid_edi_date",
        needs_review=True,
    )


def test_durable_evidence_survives_cache_eviction_and_request_rollback(db, monkeypatch):
    monkeypatch.setattr(rejection_log, "_EDI_REJECTION_CAP_PER_TENANT", 1)
    with _runtime_session(db) as request_session:
        tenant_context.set_tenant_guc(request_session, TENANT)
        first = _record()
        second = _record()
        other = _record(OTHER_TENANT)
        request_session.rollback()
    assert rejection_log.list_edi_rejections(TENANT) == [second]
    rejection_log.reset_edi_rejections()
    for tenant_id, expected in ((TENANT, [first, second]), (OTHER_TENANT, [other])):
        with Session(db) as reader:
            tenant_context.set_tenant_guc(reader, tenant_id)
            rows = (
                reader.execute(
                    text(
                        "SELECT reasons FROM fsma.rule_rejections WHERE tenant_id = :tenant AND source = 'edi_rejection'"
                    ),
                    {"tenant": tenant_id},
                )
                .scalars()
                .all()
            )
        assert {row["rejection_id"]: row for row in rows} == {row["rejection_id"]: row for row in expected}


def test_wrong_tenant_binding_rejects_append_without_cached_success(db, monkeypatch):
    real_set_tenant = tenant_context.set_tenant_guc
    monkeypatch.setattr(
        tenant_context, "set_tenant_guc", lambda session, tenant: real_set_tenant(session, OTHER_TENANT)
    )
    with pytest.raises(rejection_log.EDIRejectionUnavailable):
        _record()
    assert rejection_log.list_edi_rejections(TENANT) == []
    with Session(db) as reader:
        real_set_tenant(reader, TENANT)
        assert reader.execute(text("SELECT count(*) FROM fsma.rule_rejections")).scalar_one() == 0


@pytest.mark.parametrize(
    "sql", ["UPDATE fsma.rule_rejections SET source = 'changed'", "DELETE FROM fsma.rule_rejections"]
)
def test_runtime_cannot_change_durable_evidence(db, sql):
    _record()
    with _runtime_session(db) as session:
        tenant_context.set_tenant_guc(session, TENANT)
        with pytest.raises(DBAPIError) as exc:
            session.execute(text(sql))
        assert exc.value.orig.sqlstate == "42501"
