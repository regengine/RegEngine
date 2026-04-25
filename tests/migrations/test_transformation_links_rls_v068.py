"""v068 — fsma.transformation_links RLS policy integration test.

Spins up a disposable PostgreSQL container, recreates the minimum
schema needed (``get_tenant_context()`` helper, ``audit`` schema +
``log_sysadmin_access()`` stub, ``regengine`` role, ``fsma.
transformation_links`` table from V057), applies v068, and verifies:

  1. Without a tenant context, SELECT returns zero rows (RLS still
     fail-hard) — this is the pre-v068 baseline.
  2. With ``app.tenant_id`` set to tenant A, INSERT for tenant A
     succeeds; SELECT returns only tenant A rows.
  3. With ``app.tenant_id`` set to tenant A, INSERT for tenant B
     fails the WITH CHECK constraint — confirms write-side scoping.
  4. With ``app.tenant_id`` set to tenant A, SELECT for tenant B's
     row returns zero rows — confirms read-side scoping.
  5. Re-applying the migration is idempotent (DROP IF EXISTS + DO
     block guards).

Skips cleanly if Docker / testcontainers is unavailable.

Run via:
    pytest tests/migrations/test_transformation_links_rls_v068.py -v
"""
from __future__ import annotations

from pathlib import Path

import pytest

testcontainers = pytest.importorskip("testcontainers")  # noqa: F841
pytest.importorskip("testcontainers.postgres")

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.exc import DBAPIError, InternalError, ProgrammingError  # noqa: E402
from testcontainers.postgres import PostgresContainer  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_FILE = (
    REPO_ROOT / "alembic" / "versions"
    / "20260424_f0a1b2c3d4e5_v068_transformation_links_rls_policy.py"
)


def _extract_upgrade_sql() -> str:
    """Pull the SQL out of the migration's upgrade() body without
    importing the file (alembic.op needs an env)."""
    src = MIGRATION_FILE.read_text(encoding="utf-8")
    # The upgrade() body is a single op.execute() with a multi-line string.
    import re
    m = re.search(
        r'def upgrade\(\) -> None:.*?op\.execute\(\s*"""(.*?)"""\s*\)',
        src,
        re.DOTALL,
    )
    assert m, "could not extract upgrade SQL from migration file"
    return m.group(1)


_TENANT_A = "11111111-1111-1111-1111-111111111111"
_TENANT_B = "22222222-2222-2222-2222-222222222222"


@pytest.fixture(scope="module")
def pg_engine():
    with PostgresContainer("postgres:16") as pg:
        engine = create_engine(pg.get_connection_url(), future=True)
        with engine.begin() as conn:
            # Create the ``regengine`` role the policy references.
            # autocommit-style DDL: skip CREATE ROLE if it already exists.
            conn.execute(text(
                "DO $$ BEGIN "
                "  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine') THEN "
                "    CREATE ROLE regengine NOLOGIN; "
                "  END IF; "
                "  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin') THEN "
                "    CREATE ROLE regengine_sysadmin NOLOGIN; "
                "  END IF; "
                "END $$;"
            ))

            # Minimal ``get_tenant_context()`` helper matching the
            # canonical v056 fail-hard form (returns NULL if GUC unset
            # so RLS comparisons fail-closed against tenant_id NOT NULL).
            conn.execute(text(
                "CREATE OR REPLACE FUNCTION get_tenant_context() RETURNS UUID "
                "LANGUAGE plpgsql STABLE AS $$ "
                "BEGIN "
                "  RETURN NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID; "
                "EXCEPTION WHEN invalid_text_representation OR data_exception THEN "
                "  RETURN NULL; "
                "END $$;"
            ))

            # Minimal ``audit`` schema + ``log_sysadmin_access()`` stub
            # matching the v056 trigger function shape.
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS audit;"))
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS audit.sysadmin_access_log ("
                "  id BIGSERIAL PRIMARY KEY, "
                "  occurred_at TIMESTAMPTZ DEFAULT NOW(), "
                "  table_name TEXT, op TEXT, current_user_name TEXT"
                ");"
            ))
            conn.execute(text(
                "CREATE OR REPLACE FUNCTION audit.log_sysadmin_access() "
                "RETURNS TRIGGER LANGUAGE plpgsql AS $$ "
                "BEGIN "
                "  IF current_setting('regengine.is_sysadmin', true) = 'true' "
                "     AND current_user = 'regengine_sysadmin' THEN "
                "    INSERT INTO audit.sysadmin_access_log (table_name, op, current_user_name) "
                "    VALUES (TG_TABLE_NAME, TG_OP, current_user); "
                "  END IF; "
                "  RETURN COALESCE(NEW, OLD); "
                "END $$;"
            ))

            # Recreate ``fsma.transformation_links`` in its V057 shape
            # (pre-v067 column types are fine — tenant_id::uuid was
            # added by v067 but for this RLS test the column being
            # UUID is enough).
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS fsma;"))
            conn.execute(text(
                "CREATE TABLE fsma.transformation_links ("
                "  id BIGSERIAL PRIMARY KEY, "
                "  tenant_id UUID NOT NULL, "
                "  input_tlc TEXT, "
                "  output_tlc TEXT, "
                "  transformation_event_id UUID"
                ");"
            ))
            conn.execute(text("ALTER TABLE fsma.transformation_links ENABLE ROW LEVEL SECURITY;"))
            conn.execute(text("ALTER TABLE fsma.transformation_links FORCE ROW LEVEL SECURITY;"))

            # Seed: insert one row per tenant by temporarily switching
            # to a SUPERUSER session that bypasses RLS — easy in
            # testcontainers since the default user IS superuser.
            for tenant in (_TENANT_A, _TENANT_B):
                conn.execute(
                    text(
                        "INSERT INTO fsma.transformation_links "
                        "(tenant_id, input_tlc, output_tlc) "
                        "VALUES (:t, 'IN', 'OUT')"
                    ),
                    {"t": tenant},
                )

            # Apply v068 — this is the migration under test.
            conn.execute(text(_extract_upgrade_sql()))

            # Grant the regengine role read+write on the table so the
            # role-aware RLS policy actually applies (a superuser
            # bypasses RLS regardless of policy).
            conn.execute(text(
                "GRANT USAGE ON SCHEMA fsma TO regengine, regengine_sysadmin;"
            ))
            conn.execute(text(
                "GRANT ALL ON fsma.transformation_links TO regengine, regengine_sysadmin;"
            ))
            conn.execute(text(
                "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA fsma "
                "TO regengine, regengine_sysadmin;"
            ))

        yield engine
        engine.dispose()


def _as_regengine(engine):
    """Open a fresh connection that SETs ROLE to regengine so RLS applies.

    Returns the connection in autocommit-off mode so callers do their work
    inside the auto-begun transaction and ``rollback()`` at the end to
    leave the seed data intact for subsequent tests. ``SET ROLE`` survives
    the rollback because it's session-scoped, not transaction-scoped, but
    we re-set it on every call for clarity.
    """
    conn = engine.connect()
    conn.execute(text("SET ROLE regengine;"))
    return conn


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRLSPolicy:

    def test_select_with_no_tenant_context_returns_zero_rows(self, pg_engine):
        """``app.tenant_id`` unset → ``get_tenant_context()`` returns NULL
        → ``tenant_id = NULL`` is never true → zero rows. The fail-hard
        contract from v056 / v059."""
        with _as_regengine(pg_engine) as conn:
            rows = conn.execute(
                text("SELECT * FROM fsma.transformation_links")
            ).fetchall()
            conn.rollback()
            assert rows == [], (
                "RLS without GUC must return zero rows, not the sandbox "
                "tenant fallback"
            )

    def test_select_with_tenant_a_returns_only_tenant_a_rows(self, pg_engine):
        with _as_regengine(pg_engine) as conn:
            conn.execute(text("SET LOCAL app.tenant_id = :t"), {"t": _TENANT_A})
            rows = conn.execute(
                text("SELECT tenant_id FROM fsma.transformation_links")
            ).fetchall()
            conn.rollback()
            assert len(rows) == 1
            assert str(rows[0][0]) == _TENANT_A

    def test_select_with_tenant_b_returns_only_tenant_b_rows(self, pg_engine):
        with _as_regengine(pg_engine) as conn:
            conn.execute(text("SET LOCAL app.tenant_id = :t"), {"t": _TENANT_B})
            rows = conn.execute(
                text("SELECT tenant_id FROM fsma.transformation_links")
            ).fetchall()
            conn.rollback()
            assert len(rows) == 1
            assert str(rows[0][0]) == _TENANT_B

    def test_insert_with_matching_tenant_succeeds(self, pg_engine):
        with _as_regengine(pg_engine) as conn:
            conn.execute(text("SET LOCAL app.tenant_id = :t"), {"t": _TENANT_A})
            conn.execute(
                text(
                    "INSERT INTO fsma.transformation_links "
                    "(tenant_id, input_tlc, output_tlc) "
                    "VALUES (:t, 'IN-NEW', 'OUT-NEW')"
                ),
                {"t": _TENANT_A},
            )
            # Confirm row landed under tenant A's view.
            count = conn.execute(text(
                "SELECT COUNT(*) FROM fsma.transformation_links "
                "WHERE input_tlc = 'IN-NEW'"
            )).scalar()
            conn.rollback()  # leave seed data intact for the next test
            assert count == 1

    def test_insert_with_mismatched_tenant_is_rejected(self, pg_engine):
        """``WITH CHECK`` clause rejects writes that target a tenant
        other than the GUC. Defends against a buggy app path that
        gets the GUC right but passes the wrong literal in the
        INSERT."""
        with _as_regengine(pg_engine) as conn:
            conn.execute(text("SET LOCAL app.tenant_id = :t"), {"t": _TENANT_A})
            with pytest.raises(
                (InternalError, ProgrammingError, DBAPIError),
                match="row-level security",
            ):
                conn.execute(
                    text(
                        "INSERT INTO fsma.transformation_links "
                        "(tenant_id, input_tlc, output_tlc) "
                        "VALUES (:t, 'IN', 'OUT')"
                    ),
                    {"t": _TENANT_B},
                )
            conn.rollback()

    def test_idempotent_re_apply(self, pg_engine):
        """Re-running the migration must not error — DROP IF EXISTS +
        DO blocks must guard every statement."""
        with pg_engine.begin() as conn:
            conn.execute(text(_extract_upgrade_sql()))
            # Verify the policy still exists.
            count = conn.execute(text(
                "SELECT COUNT(*) FROM pg_policies "
                "WHERE schemaname = 'fsma' "
                "AND tablename = 'transformation_links' "
                "AND policyname = 'tenant_isolation_transformation_links'"
            )).scalar()
            assert count == 1
