"""v097 (e4d7b2a9c561) -- get_tenant_context() is pinned fail-hard AND STABLE.

Covers the branch nothing else exercises. Every other fixture in the repo
(``tests/migrations/test_rls_coverage.py::_provision_app_roles``,
``test_migration_fresh_db.py``, ``scripts/init-postgres.sh``,
``.github/workflows/backend-ci.yml``) now seeds an already-fail-hard function,
so v097's ``CREATE OR REPLACE`` never fires in any of them. Without this file
its first ever execution would be against production.

Each test seeds a deliberately WRONG definition into a throwaway schema, runs
v097's real SQL (imported from the migration module, not a copy), and asserts
the three properties the migration promises:

  1. the body becomes fail-hard (RAISE on unset ``app.tenant_id``),
  2. the function is STABLE -- so ``tenant_id = get_tenant_context()`` can still
     be used as an index condition rather than a per-row filter (#2461 shipped
     a 38x seq-scan regression on exactly this),
  3. dependent RLS policies SURVIVE -- the #1247 hazard, where a
     ``DROP FUNCTION ... CASCADE`` silently un-protected every dependent table.

Everything runs inside one transaction that is rolled back, so no schema, role
or function outlives the test.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

from tests.migrations.rls_db import guarded_live_database_url

psycopg = pytest.importorskip("psycopg")

DATABASE_URL = guarded_live_database_url()

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="no designated live test DB (CI DATABASE_URL or REGENGINE_MIGRATION_TEST_DB) — live DB required",
)

_PROBE_SCHEMA = "rls_v097_probe"

# The fail-soft body this migration exists to eradicate: returns NULL instead of
# raising, which makes `tenant_id = get_tenant_context()` evaluate to NULL and
# silently filter every row.
_FAIL_SOFT = """
CREATE OR REPLACE FUNCTION {schema}.get_tenant_context()
RETURNS UUID AS $fn$
BEGIN
    RETURN current_setting('app.tenant_id', true)::uuid;
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END;
$fn$ LANGUAGE plpgsql STABLE;
"""

# Fail-hard but VOLATILE — the shape v056 and services/admin/app/database.py
# historically emitted. Correct semantics, wrong planner behaviour.
_FAIL_HARD_VOLATILE = """
CREATE OR REPLACE FUNCTION {schema}.get_tenant_context()
RETURNS UUID AS $fn$
DECLARE
    tid TEXT;
BEGIN
    tid := NULLIF(current_setting('app.tenant_id', TRUE), '');
    IF tid IS NULL THEN
        RAISE EXCEPTION 'app.tenant_id not set - tenant context required for RLS';
    END IF;
    RETURN tid::UUID;
END;
$fn$ LANGUAGE plpgsql;
"""


def _load_migration_sql() -> str:
    """Import the migration module and return its real SQL.

    Deliberately not a copy-paste of the DDL: if the migration changes, these
    assertions must track it or fail.
    """
    versions = pathlib.Path(__file__).resolve().parents[2] / "alembic" / "versions"
    matches = sorted(versions.glob("*e4d7b2a9c561*.py"))
    assert matches, f"v097 migration not found in {versions}"
    spec = importlib.util.spec_from_file_location("_v097_mig", matches[0])
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module._PIN_FAIL_HARD


@pytest.fixture()
def conn():
    with psycopg.connect(DATABASE_URL, connect_timeout=5) as c:
        yield c
        c.rollback()


def _setup_probe(cur, seed_sql: str) -> None:
    """Isolated schema + a seeded function + a policy that depends on it."""
    cur.execute(f"CREATE SCHEMA {_PROBE_SCHEMA}")
    # Pin search_path so the migration's current_schemas() lookup resolves to
    # the probe copy and never touches the real public.get_tenant_context().
    cur.execute(f"SET LOCAL search_path = {_PROBE_SCHEMA}")
    cur.execute(seed_sql.format(schema=_PROBE_SCHEMA))
    cur.execute(f"CREATE TABLE {_PROBE_SCHEMA}.t (tenant_id uuid, val text)")
    cur.execute(f"ALTER TABLE {_PROBE_SCHEMA}.t ENABLE ROW LEVEL SECURITY")
    cur.execute(f"ALTER TABLE {_PROBE_SCHEMA}.t FORCE ROW LEVEL SECURITY")
    cur.execute(
        f"CREATE POLICY tenant_isolation_probe ON {_PROBE_SCHEMA}.t "
        f"USING (tenant_id = {_PROBE_SCHEMA}.get_tenant_context())"
    )


def _fn_facts(cur) -> tuple[str, str]:
    """Return (prosrc, provolatile) for the probe function."""
    cur.execute(
        """
        SELECT p.prosrc, p.provolatile
          FROM pg_proc p
          JOIN pg_namespace n ON p.pronamespace = n.oid
         WHERE p.proname = 'get_tenant_context' AND n.nspname = %s
        """,
        (_PROBE_SCHEMA,),
    )
    return cur.fetchone()


def _policy_count(cur) -> int:
    cur.execute("SELECT count(*) FROM pg_policies WHERE schemaname = %s", (_PROBE_SCHEMA,))
    return cur.fetchone()[0]


class TestV097PinsFailHard:
    def test_fail_soft_body_is_replaced_and_policies_survive(self, conn):
        """The headline claim: fail-soft -> fail-hard with ZERO policy loss."""
        sql = _load_migration_sql()
        with conn.cursor() as cur:
            _setup_probe(cur, _FAIL_SOFT)

            before_src, _ = _fn_facts(cur)
            assert "RAISE EXCEPTION" not in before_src, "probe should start fail-soft"
            assert _policy_count(cur) == 1

            cur.execute(sql)

            after_src, after_vol = _fn_facts(cur)
            assert "RAISE EXCEPTION" in after_src, "v097 must pin the fail-hard body"
            # 's' = STABLE. 'v' = VOLATILE would kill index quals on every
            # tenant-scoped table (measured 38x on 200k rows).
            assert after_vol == "s", f"must be STABLE, got provolatile={after_vol!r}"
            # #1247: CREATE OR REPLACE keeps the pg_proc OID, so the dependent
            # policy must still be attached. A DROP ... CASCADE would zero this.
            assert _policy_count(cur) == 1, "dependent RLS policy was dropped (#1247 regression)"
        conn.rollback()

    def test_unset_guc_raises_after_pin(self, conn):
        """Behavioural proof, not a substring check on prosrc."""
        sql = _load_migration_sql()
        with conn.cursor() as cur:
            _setup_probe(cur, _FAIL_SOFT)
            cur.execute(sql)

            # Fail-soft returned NULL here; pinned it must raise.
            with pytest.raises((psycopg.errors.RaiseException, psycopg.errors.InsufficientPrivilege)):
                cur.execute(f"SELECT {_PROBE_SCHEMA}.get_tenant_context()")
        conn.rollback()

    def test_volatile_fail_hard_body_is_upgraded_to_stable(self, conn):
        """v056 / admin database.py emitted fail-hard but VOLATILE.

        A source-text guard would call this "already hardened" and skip it,
        leaving the planner regression in place. v097 is unconditional, so it
        repairs the volatility too.
        """
        sql = _load_migration_sql()
        with conn.cursor() as cur:
            _setup_probe(cur, _FAIL_HARD_VOLATILE)

            _, before_vol = _fn_facts(cur)
            assert before_vol == "v", "probe should start VOLATILE"

            cur.execute(sql)

            _, after_vol = _fn_facts(cur)
            assert after_vol == "s", "v097 must repair VOLATILE -> STABLE"
            assert _policy_count(cur) == 1
        conn.rollback()

    def test_is_idempotent(self, conn):
        """Running twice changes nothing and drops no policy."""
        sql = _load_migration_sql()
        with conn.cursor() as cur:
            _setup_probe(cur, _FAIL_SOFT)
            cur.execute(sql)
            first_src, first_vol = _fn_facts(cur)

            cur.execute(sql)
            second_src, second_vol = _fn_facts(cur)

            assert (first_src, first_vol) == (second_src, second_vol)
            assert _policy_count(cur) == 1
        conn.rollback()

    def test_refuses_non_uuid_return_type_without_dropping_anything(self, conn):
        """The defensive branch must refuse, NOT reach for DROP ... CASCADE."""
        sql = _load_migration_sql()
        with conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA {_PROBE_SCHEMA}")
            cur.execute(f"SET LOCAL search_path = {_PROBE_SCHEMA}")
            cur.execute(
                f"CREATE FUNCTION {_PROBE_SCHEMA}.get_tenant_context() RETURNS TEXT "
                f"AS $fn$ BEGIN RETURN 'x'; END; $fn$ LANGUAGE plpgsql"
            )

            with pytest.raises(psycopg.errors.RaiseException) as exc:
                cur.execute(sql)
            assert "expected uuid" in str(exc.value)
        conn.rollback()
