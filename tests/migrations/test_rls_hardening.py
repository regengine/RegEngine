"""RLS fail-closed hardening verification (#1091).

For representative tenant-scoped tables covered by the active Alembic RLS
hardening chain we assert:

1. A row inserted with ``tenant_id = A`` is visible when
   ``app.tenant_id = A`` is set.
2. The same row is NOT visible when ``app.tenant_id = B`` is set.
3. The same row is NOT visible when ``app.tenant_id`` is UNSET — the
   query must either raise (fail-hard, preferred) or return zero rows
   (fail-closed). It must NEVER fall back to the sandbox
   ``'00000000-0000-0000-0000-000000000001'`` tenant.

Run via:
    pytest tests/migrations/test_rls_hardening.py -v

Requires Docker for testcontainers. If Docker is unavailable the test
module skips cleanly — the CI guard (scripts/check_rls_fallback.py) is
the static safety net.
"""
from __future__ import annotations

import uuid
from typing import Iterator

import pytest

# Skip the whole module if Docker / testcontainers unavailable.
testcontainers = pytest.importorskip("testcontainers")  # noqa: F841
pytest.importorskip("testcontainers.postgres")

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402
from sqlalchemy.exc import InternalError, ProgrammingError  # noqa: E402
from testcontainers.postgres import PostgresContainer  # noqa: E402


# Subset of tenant-scoped tables covered by the active RLS hardening chain.
# We don't need to re-verify every one —
# a representative sample across each source migration is sufficient to
# prove the pattern is correct. Each entry: (table, required_cols)
# where required_cols is the minimum INSERT shape needed.
#
# We pick tables that have a simple shape (id uuid, tenant_id uuid) and
# no heavy FK constraints, so we can exercise RLS without setting up the
# whole schema graph.
SAMPLE_TABLES = [
    # (table_name, insert_columns, values_sql_placeholders)
    # The insert SQL uses :tid for tenant_id and gen_random_uuid() for id.
    ("pcos_companies", "id, tenant_id, legal_name, entity_type",
     "gen_random_uuid(), :tid, 'TestCo', 'llc_single_member'"),
    ("pcos_projects", "id, tenant_id, company_id, project_name",
     "gen_random_uuid(), :tid, gen_random_uuid(), 'TestProject'"),
    ("pcos_evidence", "id, tenant_id",
     "gen_random_uuid(), :tid"),
    ("vertical_projects", "id, tenant_id",
     "gen_random_uuid(), :tid"),
]


def _set_tenant_context(conn, tenant_id: uuid.UUID) -> None:
    conn.execute(
        text("SELECT set_config('app.tenant_id', :tid, false)"),
        {"tid": str(tenant_id)},
    )


@pytest.fixture(scope="module")
def pg_engine() -> Iterator[Engine]:
    """Spin up a disposable PostgreSQL container and apply a focused RLS fixture."""
    try:
        container = PostgresContainer("postgres:16", driver="psycopg")
        container.start()
    except Exception as exc:  # Docker missing, image pull fails, etc.
        pytest.skip(f"PostgresContainer unavailable: {exc}")

    try:
        url = container.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+psycopg://"
        )
        engine = create_engine(url, future=True)

        _bootstrap_schema(engine)
        _apply_rls_hardening_pattern(engine)
        yield engine
    finally:
        engine.dispose()
        container.stop()


def _bootstrap_schema(engine: Engine) -> None:
    """Create a minimal schema with just the tables we test. We avoid
    replaying the real migration chain because it has heavy FK trees and
    assumes a lot of prior state. This is a *focused* test of the
    ``get_tenant_context()`` + FORCE RLS contract, not a full replay."""
    with engine.begin() as conn:
        # Supabase stubs: the `authenticated` role and `auth.uid()` fn.
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS auth"))
        conn.execute(text(
            "CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid "
            "AS $$ SELECT '00000000-0000-0000-0000-000000000000'::uuid $$ "
            "LANGUAGE SQL"
        ))
        conn.execute(text("""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                    CREATE ROLE authenticated;
                END IF;
            END $$
        """))
        # Create the sample tables with the minimal columns we need.
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pcos_companies (
                id uuid PRIMARY KEY,
                tenant_id uuid NOT NULL,
                legal_name text,
                entity_type text
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pcos_projects (
                id uuid PRIMARY KEY,
                tenant_id uuid NOT NULL,
                company_id uuid,
                project_name text
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pcos_evidence (
                id uuid PRIMARY KEY,
                tenant_id uuid NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS vertical_projects (
                id uuid PRIMARY KEY,
                tenant_id uuid NOT NULL
            )
        """))
        for tbl, _, _ in SAMPLE_TABLES:
            conn.execute(text(f"GRANT SELECT ON {tbl} TO authenticated"))


def _apply_rls_hardening_pattern(engine: Engine) -> None:
    """Apply the get_tenant_context() helper + hardened policies +
    FORCE RLS on the sample tables. Mirrors the active hardening shape
    for the subset of tables we test."""
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE OR REPLACE FUNCTION get_tenant_context()
            RETURNS UUID AS $fn$
            DECLARE
                tid TEXT;
            BEGIN
                tid := NULLIF(current_setting('app.tenant_id', TRUE), '');
                IF tid IS NULL THEN
                    RAISE EXCEPTION 'app.tenant_id not set - tenant context required for RLS'
                        USING ERRCODE = 'insufficient_privilege';
                END IF;
                RETURN tid::UUID;
            END;
            $fn$ LANGUAGE plpgsql STABLE
        """))

        for tbl, _, _ in SAMPLE_TABLES:
            conn.execute(text(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY"))
            conn.execute(text(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY"))
            conn.execute(text(f"DROP POLICY IF EXISTS {tbl}_tenant_isolation ON {tbl}"))
            conn.execute(text(
                f'CREATE POLICY {tbl}_tenant_isolation ON {tbl} '
                f'FOR ALL TO public '
                f'USING (tenant_id = get_tenant_context())'
            ))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("table,cols,vals", SAMPLE_TABLES)
def test_same_tenant_context_sees_row(pg_engine: Engine, table: str, cols: str, vals: str):
    """tenant_id = A with app.tenant_id = A → row visible."""
    tenant_a = uuid.uuid4()
    with pg_engine.begin() as conn:
        conn.execute(text(f"INSERT INTO {table} ({cols}) VALUES ({vals})"), {"tid": tenant_a})

    with pg_engine.connect() as conn:
        _set_tenant_context(conn, tenant_a)
        conn.execute(text("SET ROLE authenticated"))
        count = conn.execute(
            text(f"SELECT COUNT(*) FROM {table} WHERE tenant_id = :tid"),
            {"tid": tenant_a},
        ).scalar()
        assert count == 1, f"{table}: row not visible under matching tenant context"


@pytest.mark.parametrize("table,cols,vals", SAMPLE_TABLES)
def test_cross_tenant_context_hides_row(pg_engine: Engine, table: str, cols: str, vals: str):
    """tenant_id = A with app.tenant_id = B → zero rows."""
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    with pg_engine.begin() as conn:
        conn.execute(text(f"INSERT INTO {table} ({cols}) VALUES ({vals})"), {"tid": tenant_a})

    with pg_engine.connect() as conn:
        _set_tenant_context(conn, tenant_b)
        conn.execute(text("SET ROLE authenticated"))
        count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
        assert count == 0, (
            f"{table}: cross-tenant row leaked — got {count} rows under wrong tenant "
            "(fail-open RLS not fixed)"
        )


@pytest.mark.parametrize("table,cols,vals", SAMPLE_TABLES)
def test_unset_tenant_context_raises(pg_engine: Engine, table: str, cols: str, vals: str):
    """app.tenant_id UNSET → policy evaluation RAISES (Option A, fail-hard)."""
    tenant_a = uuid.uuid4()
    with pg_engine.begin() as conn:
        conn.execute(text(f"INSERT INTO {table} ({cols}) VALUES ({vals})"), {"tid": tenant_a})

    with pg_engine.connect() as conn:
        # Explicitly RESET to ensure no prior transaction leaked a setting.
        conn.execute(text("RESET app.tenant_id"))
        conn.execute(text("SET ROLE authenticated"))
        with pytest.raises((InternalError, ProgrammingError)) as exc_info:
            conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
        # Should be our specific RAISE from get_tenant_context().
        assert "app.tenant_id not set" in str(exc_info.value), (
            f"{table}: expected 'app.tenant_id not set' exception, got: {exc_info.value}"
        )


def test_fallback_uuid_context_sees_no_sandbox_data(pg_engine: Engine):
    """Setting app.tenant_id to the old sandbox UUID must NOT return rows
    that belonged to real tenants. Guards against a regression where the
    sandbox UUID accidentally becomes a valid global tenant."""
    real_tenant = uuid.uuid4()
    sandbox = uuid.UUID("00000000-0000-0000-0000-000000000001")
    with pg_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO pcos_companies (id, tenant_id, legal_name, entity_type) "
                 "VALUES (gen_random_uuid(), :tid, 'RealCo', 'llc_single_member')"),
            {"tid": real_tenant},
        )

    with pg_engine.connect() as conn:
        _set_tenant_context(conn, sandbox)
        conn.execute(text("SET ROLE authenticated"))
        count = conn.execute(text("SELECT COUNT(*) FROM pcos_companies")).scalar()
        assert count == 0, (
            f"Using the fallback UUID as tenant context exposed {count} real-tenant row(s). "
            "This is the exact #1091 failure mode."
        )


def test_get_tenant_context_fails_hard_directly(pg_engine: Engine):
    """Direct invocation of get_tenant_context() with no context set
    must raise. Complements the policy-level check."""
    with pg_engine.connect() as conn:
        conn.execute(text("RESET app.tenant_id"))
        with pytest.raises((InternalError, ProgrammingError)) as exc_info:
            conn.execute(text("SELECT get_tenant_context()")).scalar()
        assert "app.tenant_id not set" in str(exc_info.value)
