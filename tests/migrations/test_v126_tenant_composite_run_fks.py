"""v126: evidence rows may only reference an ingestion run of their own tenant.

Runs the real v126 upgrade/downgrade against an alembic-head database, as its
NOBYPASSRLS schema owner with FORCE RLS in place, inside a transaction that is
always rolled back -- nothing in the borrowed database changes. CI runs this in
live-db-suite, whose owner matches production migration jobs. Locally, point
REGENGINE_MIGRATION_TEST_DB at a superuser URL for such a database (the
restricted-role scratch cluster).
"""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from tests.migrations.rls_db import _normalize_psycopg, guarded_live_database_url, skip_or_fail_db

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "alembic/versions/20260927_2db4f1d7b4ca_v126_tenant_composite_ingestion_run_fks.py"
CHILDREN = ("traceability_events", "manifest_records", "manifest_blobs")
ON_DELETE = {"traceability_events": "a", "manifest_records": "c", "manifest_blobs": "c"}  # NO ACTION / CASCADE

INSERT_CHILD = {
    "traceability_events": """INSERT INTO fsma.traceability_events
        (tenant_id, ingestion_run_id, source_system, event_type, event_timestamp,
         traceability_lot_code, quantity, unit_of_measure)
        VALUES (:tenant, :run, 'v126-test', 'shipping', now(), 'LOT-V126', 1, 'case')""",
    "manifest_records": """INSERT INTO fsma.manifest_records
        (tenant_id, ingestion_run_id, row_number, raw_row, row_fingerprint)
        VALUES (:tenant, :run, 1, '{}'::jsonb, 'v126-test')""",
    "manifest_blobs": """INSERT INTO fsma.manifest_blobs
        (tenant_id, ingestion_run_id, raw_bytes, sha256, original_filename)
        VALUES (:tenant, :run, '\\x00'::bytea, 'v126-test', 'v126.csv')""",
}


@pytest.fixture
def migration():
    spec = importlib.util.spec_from_file_location("v126", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def db(migration, monkeypatch):
    url = guarded_live_database_url()
    if not url:
        pytest.skip("needs an alembic-head Postgres: REGENGINE_MIGRATION_TEST_DB, or DATABASE_URL in CI")
    engine = create_engine(_normalize_psycopg(url), future=True)
    try:
        with engine.connect() as conn:
            transaction = conn.begin()
            try:
                if conn.execute(text("SELECT to_regclass('fsma.manifest_blobs')")).scalar() is None:
                    skip_or_fail_db("v126 tests need a database migrated to alembic head")
                owner, bypasses_rls = conn.execute(
                    text("""SELECT r.rolname, r.rolsuper OR r.rolbypassrls FROM pg_class c
                            JOIN pg_roles r ON r.oid = c.relowner
                            WHERE c.oid = 'fsma.traceability_events'::regclass""")
                ).one()
                # A superuser-owned schema would pass without ever taking the
                # FORCE-RLS path this migration exists to handle.
                assert not bypasses_rls, f"schema owner {owner} bypasses RLS; migrate as a NOBYPASSRLS owner"
                monkeypatch.setattr(migration, "op", SimpleNamespace(get_bind=lambda: conn))
                yield conn, owner
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def run_fks(conn):
    """Every FK into fsma.ingestion_runs, independent of search_path rendering."""
    return conn.execute(
        text("""SELECT cl.relname, c.conname, c.convalidated, c.confdeltype, c.confupdtype,
                       c.confmatchtype, c.condeferrable, ix.relname AS backing_index,
                       ARRAY(SELECT a.attname FROM unnest(c.conkey) WITH ORDINALITY k(n, i)
                             JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.n
                             ORDER BY k.i)::text[] AS columns
                FROM pg_constraint c
                JOIN pg_class cl ON cl.oid = c.conrelid
                JOIN pg_class ix ON ix.oid = c.conindid
                WHERE c.confrelid = 'fsma.ingestion_runs'::regclass
                ORDER BY 1, 2""")
    ).all()


def posture(conn):
    return conn.execute(
        text("""SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class
                WHERE oid IN ('fsma.ingestion_runs'::regclass, 'fsma.traceability_events'::regclass,
                              'fsma.manifest_records'::regclass, 'fsma.manifest_blobs'::regclass)
                ORDER BY relname""")
    ).all()


def lock_timeout(conn):
    return conn.execute(text("SELECT current_setting('lock_timeout')")).scalar_one()


def child_fks(conn):
    return {row.relname: row for row in run_fks(conn) if row.relname in CHILDREN}


def add_run(conn, tenant):
    return conn.execute(
        text("INSERT INTO fsma.ingestion_runs (tenant_id, source_system) VALUES (:tenant, 'v126-test') RETURNING id"),
        {"tenant": tenant},
    ).scalar_one()


def add_child(conn, table, tenant, run):
    conn.execute(text(INSERT_CHILD[table]), {"tenant": tenant, "run": run})


def act_as(conn, role, tenant=None):
    conn.exec_driver_sql(f'SET LOCAL ROLE "{role}"')
    conn.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenant or "")})


def test_head_carries_composite_keys(db, migration):
    conn, _ = db
    for table, fk in child_fks(conn).items():
        assert fk.conname == migration.composite_fk_name(table)
        assert fk.columns == ["ingestion_run_id", "tenant_id"]
        assert fk.backing_index == "ux_ingestion_runs_id_tenant"
        assert (fk.convalidated, fk.confdeltype, fk.confmatchtype) == (True, ON_DELETE[table], "s")
    assert set(child_fks(conn)) == set(CHILDREN)


def test_downgrade_then_upgrade_is_exact_over_populated_tables(db, migration):
    conn, owner = db
    # Rows in every tenant make validation scan real data, not an empty table.
    for tenant in (uuid4(), uuid4()):
        run = add_run(conn, tenant)
        for table in CHILDREN:
            add_child(conn, table, tenant, run)
    at_head = run_fks(conn)
    act_as(conn, owner)
    before_posture, before_timeout = posture(conn), lock_timeout(conn)

    migration.downgrade()
    legacy = child_fks(conn)
    for table, fk in legacy.items():
        assert fk.conname == f"{table}_ingestion_run_id_fkey"
        assert fk.columns == ["ingestion_run_id"]
        assert fk.backing_index == "ingestion_runs_pkey"
        assert (fk.convalidated, fk.confdeltype, fk.confmatchtype) == (True, ON_DELETE[table], "s")
    assert set(legacy) == set(CHILDREN)
    assert (posture(conn), lock_timeout(conn)) == (before_posture, before_timeout)

    migration.upgrade()
    assert run_fks(conn) == at_head
    assert (posture(conn), lock_timeout(conn)) == (before_posture, before_timeout)


def test_cross_tenant_attach_rejected_same_tenant_accepted(db, migration):
    conn, owner = db
    tenant_a, tenant_b = uuid4(), uuid4()
    run_a, run_b = add_run(conn, tenant_a), add_run(conn, tenant_b)
    # traceability_events is written by the runtime role; the v095 manifest
    # tables have no runtime grant, so their writer is the owner. Neither
    # needs a grant for the FK check itself.
    for table, writer in (
        ("traceability_events", "regengine"),
        ("manifest_records", owner),
        ("manifest_blobs", owner),
    ):
        act_as(conn, writer, tenant_b)
        with pytest.raises(IntegrityError, match=migration.composite_fk_name(table)), conn.begin_nested():
            add_child(conn, table, tenant_b, run_a)
        add_child(conn, table, tenant_b, run_b)
        conn.exec_driver_sql("RESET ROLE")


def test_upgrade_refuses_misattached_rows_and_changes_nothing(db, migration):
    conn, owner = db
    act_as(conn, owner)
    migration.downgrade()
    conn.exec_driver_sql("RESET ROLE")
    tenant_a, tenant_b = uuid4(), uuid4()
    run_a, run_b = add_run(conn, tenant_a), add_run(conn, tenant_b)
    for table in CHILDREN:
        # The single-column keys accept a tenant B row naming tenant A's run.
        add_child(conn, table, tenant_b, run_a)
        add_child(conn, table, tenant_b, run_b)

    # The pre-deploy query, from a superuser session, names every bad row.
    found = conn.execute(text(migration.PREDEPLOY_CHECK_SQL)).all()
    found = [row for row in found if row.row_tenant_id == tenant_b]
    assert sorted(row.table_name for row in found) == [f"fsma.{t}" for t in sorted(CHILDREN)]
    assert {row.run_tenant_id for row in found} == {tenant_a}

    act_as(conn, owner)
    # The same query as the owner under FORCE RLS cannot see them.
    with pytest.raises(DBAPIError, match="tenant context required"), conn.begin_nested():
        conn.execute(text(migration.PREDEPLOY_CHECK_SQL)).all()
    before = (run_fks(conn), posture(conn), lock_timeout(conn))
    with pytest.raises(RuntimeError) as refused, conn.begin_nested():
        migration.upgrade()
    message = str(refused.value)
    for table in CHILDREN:
        assert f"fsma.{table}=1" in message
    assert migration.PREDEPLOY_CHECK_SQL in message
    assert (run_fks(conn), posture(conn), lock_timeout(conn)) == before
