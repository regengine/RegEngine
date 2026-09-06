"""Rule data migrations must work for a NOBYPASSRLS owner and restore RLS."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.migrations.scratch_db import scratch_database_engine

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = [
    "20260902_e4a7c2d91b06_v116_rule_seeds_enforcement_integrity.py",
    "20260904_c6a120b4e901_v120_rule_citations.py",
]
TABLES = ("rule_definitions", "rule_audit_log")


def posture(conn):
    return conn.execute(
        text("""SELECT relname, relrowsecurity, relforcerowsecurity
        FROM pg_class WHERE oid IN ('fsma.rule_definitions'::regclass,
                                    'fsma.rule_audit_log'::regclass)
        ORDER BY relname""")
    ).all()


@pytest.fixture(params=MIGRATIONS)
def owner_fixture(request, monkeypatch):
    spec = importlib.util.spec_from_file_location("rule_backfill", ROOT / "alembic/versions" / request.param)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with scratch_database_engine("rule_backfill_" + uuid4().hex[:12]) as engine:
        # Role and fixture DDL are rolled back with this connection. No role or
        # object in the borrowed database is changed.
        with engine.connect() as conn:
            transaction = conn.begin()
            try:
                role = "rule_owner_" + uuid4().hex[:12]
                conn.exec_driver_sql(f"CREATE ROLE {role} NOLOGIN NOSUPERUSER NOBYPASSRLS")
                conn.exec_driver_sql(f"CREATE SCHEMA fsma AUTHORIZATION {role}")
                conn.exec_driver_sql(f"SET LOCAL ROLE {role}")
                ddl = (ROOT / "alembic/sql/V044__versioned_rules_engine.sql").read_text()
                conn.exec_driver_sql(ddl.split("BEGIN;", 1)[1].split("-- Row-Level Security", 1)[0])
                conn.execute(
                    text("""INSERT INTO fsma.rule_definitions
                    (title,citation_reference,evaluation_logic)
                    VALUES ('Receiving: Receive Date Required','21 CFR §1.1345(b)(2)',
                            '{"type":"multi_field_presence","field":"kdes.receive_date"}'::jsonb)""")
                )
                for table in TABLES:
                    conn.exec_driver_sql(f"ALTER TABLE fsma.{table} ENABLE ROW LEVEL SECURITY")
                    conn.exec_driver_sql(f"ALTER TABLE fsma.{table} FORCE ROW LEVEL SECURITY")
                monkeypatch.setattr(migration, "op", SimpleNamespace(get_bind=lambda: conn))
                assert conn.execute(text("SELECT count(*) FROM fsma.rule_definitions")).scalar_one() == 0
                yield conn, migration, role

            finally:
                transaction.rollback()


def test_owner_backfill_restores_forced_rls_and_audits(owner_fixture):
    conn, migration, _ = owner_fixture
    before = posture(conn)
    migration.upgrade()
    assert posture(conn) == before
    # Owner remains denied outside the backfill, including writes.
    assert conn.execute(text("SELECT count(*) FROM fsma.rule_definitions")).scalar_one() == 0
    with pytest.raises(DBAPIError), conn.begin_nested():
        conn.execute(text("INSERT INTO fsma.rule_definitions(title) VALUES ('unauthorized')"))
    conn.exec_driver_sql("RESET ROLE")
    assert conn.execute(text("SELECT count(*) FROM fsma.rule_audit_log")).scalar_one() >= 1
    assert (
        conn.execute(
            text("SELECT rule_version FROM fsma.rule_definitions WHERE title = 'Receiving: Receive Date Required'")
        ).scalar_one()
        == 2
    )


def test_failure_rolls_back_rule_data_and_forced_rls(owner_fixture):
    conn, migration, _ = owner_fixture
    before = posture(conn)
    conn.exec_driver_sql("""CREATE FUNCTION fsma.fail_rule_audit() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'injected audit failure'; END $$;
        CREATE TRIGGER fail_audit BEFORE INSERT ON fsma.rule_audit_log
        FOR EACH ROW EXECUTE FUNCTION fsma.fail_rule_audit();""")
    with pytest.raises(DBAPIError, match="injected audit failure"), conn.begin_nested():
        migration.upgrade()
    assert posture(conn) == before
    conn.exec_driver_sql("RESET ROLE")
    assert conn.execute(text("SELECT count(*) FROM fsma.rule_audit_log")).scalar_one() == 0
    assert conn.execute(text("SELECT rule_version FROM fsma.rule_definitions")).scalar_one() == 1


def test_runtime_cannot_invoke_owner_backfill(owner_fixture):
    conn, migration, _ = owner_fixture
    before = posture(conn)
    conn.exec_driver_sql("RESET ROLE")
    runtime = "rule_runtime_" + uuid4().hex[:12]
    conn.exec_driver_sql(f"CREATE ROLE {runtime} NOLOGIN NOSUPERUSER NOBYPASSRLS")
    conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA fsma TO {runtime}")
    conn.exec_driver_sql(f"GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA fsma TO {runtime}")
    conn.exec_driver_sql(f"SET LOCAL ROLE {runtime}")
    with pytest.raises(DBAPIError, match="must be owner"), conn.begin_nested():
        migration.upgrade()
    assert posture(conn) == before
