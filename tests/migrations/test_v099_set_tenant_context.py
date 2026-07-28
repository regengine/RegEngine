"""v099 (2aa607050c84) -- set_tenant_context() is adopted by the migration chain.

Until v099 the function was created ONLY by runtime boot DDL
(``services/admin/app/database.py::init_db``), which the same PR deletes: no
other fixture in the repo seeds it (``scripts/init-postgres.sh`` and
``backend-ci.yml`` seed only ``get_tenant_context``). On a fresh
least-privilege database v099 is therefore the function's first and only
creator, while on databases the app has booted against (prod, dev, CI) it
replaces the boot-created copy in place.

Each test seeds a throwaway schema, runs v099's real SQL (imported from the
migration module, not a copy), and asserts what the migration promises:

  1. a missing function is created (fresh-database case),
  2. an existing same-signature function is replaced IN PLACE -- pg_proc OID
     preserved, no DROP (v097 precedent),
  3. a non-text overload makes the migration REFUSE rather than add an
     ambiguity-creating second candidate,
  4. the emitted body actually sets the ``app.tenant_id`` GUC,
  5. public.set_admin_context is pinned so the app's unqualified call resolves
     on a fresh database (v051/v056 created it unqualified and a fresh chain
     run strands it in ``fsma`` -- only the deleted boot DDL made ``public``
     resolution work).

Everything runs inside one transaction that is rolled back, so no schema or
function outlives the test.
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

_PROBE_SCHEMA = "rls_v099_probe"

# A drifted same-signature body: right shape, does nothing. v099 must replace
# it in place without a DROP.
_DRIFTED_NOOP = """
CREATE FUNCTION {schema}.set_tenant_context(tenant_id text)
RETURNS void AS $fn$
BEGIN
    NULL;
END;
$fn$ LANGUAGE plpgsql;
"""

# A non-text overload. v099 must refuse rather than CREATE OR REPLACE a text
# variant beside it (two candidates would make untyped calls ambiguous).
_UUID_VARIANT = """
CREATE FUNCTION {schema}.set_tenant_context(tenant_id uuid)
RETURNS void AS $fn$
BEGIN
    PERFORM set_config('app.tenant_id', tenant_id::text, false);
END;
$fn$ LANGUAGE plpgsql;
"""


def _load_migration_sql() -> tuple[str, str]:
    """Import the migration module and return its real SQL.

    Deliberately not a copy-paste of the DDL: if the migration changes, these
    assertions must track it or fail.
    """
    versions = pathlib.Path(__file__).resolve().parents[2] / "alembic" / "versions"
    matches = sorted(versions.glob("*2aa607050c84*.py"))
    assert matches, f"v099 migration not found in {versions}"
    spec = importlib.util.spec_from_file_location("_v099_mig", matches[0])
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module._ADOPT_SET_TENANT_CONTEXT, module._PIN_PUBLIC_SET_ADMIN_CONTEXT


@pytest.fixture()
def conn():
    with psycopg.connect(DATABASE_URL, connect_timeout=5) as c:
        yield c
        c.rollback()


def _setup_probe(cur, seed_sql: str | None) -> None:
    """Isolated schema, optionally seeded with a probe copy of the function."""
    cur.execute(f"CREATE SCHEMA {_PROBE_SCHEMA}")
    # Pin search_path so the migration's current_schemas() lookup resolves to
    # the probe copy and never touches the real public.set_tenant_context().
    cur.execute(f"SET LOCAL search_path = {_PROBE_SCHEMA}")
    if seed_sql is not None:
        cur.execute(seed_sql.format(schema=_PROBE_SCHEMA))


def _fn_row(cur, schema: str):
    """Return (oid, prosrc, argtype, rettype) for the function, or None."""
    cur.execute(
        """
        SELECT p.oid, p.prosrc,
               format_type(p.proargtypes[0], NULL),
               format_type(p.prorettype, NULL)
          FROM pg_proc p
          JOIN pg_namespace n ON p.pronamespace = n.oid
         WHERE p.proname = 'set_tenant_context' AND n.nspname = %s
        """,
        (schema,),
    )
    return cur.fetchone()


class TestV099AdoptsSetTenantContext:
    def test_creates_function_when_missing(self, conn):
        """Fresh-database case: no candidate in scope -> created in public."""
        sql, _ = _load_migration_sql()
        with conn.cursor() as cur:
            _setup_probe(cur, seed_sql=None)
            # public is outside the pinned search_path, so drop any existing
            # copy (signature-qualified, no CASCADE) to prove genuine creation.
            # The whole transaction is rolled back by the fixture.
            cur.execute("DROP FUNCTION IF EXISTS public.set_tenant_context(text)")
            assert _fn_row(cur, "public") is None

            cur.execute(sql)

            row = _fn_row(cur, "public")
            assert row is not None, "v099 must create the function on a fresh database"
            _, prosrc, argtype, rettype = row
            assert (argtype, rettype) == ("text", "void")
            assert "set_config" in prosrc
        conn.rollback()

    def test_replaces_existing_in_place_and_sets_guc(self, conn):
        """Boot-DDL-created copy is replaced in place: same OID, working body."""
        sql, _ = _load_migration_sql()
        with conn.cursor() as cur:
            _setup_probe(cur, _DRIFTED_NOOP)
            before_oid, before_src, _, _ = _fn_row(cur, _PROBE_SCHEMA)
            assert "set_config" not in before_src, "probe should start drifted"

            cur.execute(sql)

            after_oid, after_src, argtype, rettype = _fn_row(cur, _PROBE_SCHEMA)
            assert after_oid == before_oid, "replace must preserve the pg_proc OID (no DROP)"
            assert (argtype, rettype) == ("text", "void")
            assert "set_config" in after_src

            # Behavioural proof, not a substring check on prosrc.
            cur.execute(
                f"SELECT {_PROBE_SCHEMA}.set_tenant_context(%s)",
                ("11111111-1111-1111-1111-111111111111",),
            )
            cur.execute("SELECT current_setting('app.tenant_id', true)")
            assert cur.fetchone()[0] == "11111111-1111-1111-1111-111111111111"
        conn.rollback()

    def test_refuses_non_text_variant(self, conn):
        """A non-text candidate must abort the migration, not gain an overload."""
        sql, _ = _load_migration_sql()
        with conn.cursor() as cur:
            _setup_probe(cur, _UUID_VARIANT)
            with pytest.raises(psycopg.errors.RaiseException, match="refusing to add an overload"):
                cur.execute(sql)
        conn.rollback()

    def test_is_idempotent(self, conn):
        """Running twice changes nothing."""
        sql, _ = _load_migration_sql()
        with conn.cursor() as cur:
            _setup_probe(cur, _DRIFTED_NOOP)
            cur.execute(sql)
            first = _fn_row(cur, _PROBE_SCHEMA)

            cur.execute(sql)
            second = _fn_row(cur, _PROBE_SCHEMA)

            assert first == second
        conn.rollback()


class TestV099PinsPublicSetAdminContext:
    def test_pins_public_copy_resolvable_unqualified(self, conn):
        """Fresh-chain case: v051/v056 stranded the function in fsma.

        The pin must make the app's unqualified call
        (services/admin/app/models.py::set_admin_context executes
        ``SELECT set_admin_context(:is_admin)``) resolve on a default
        search_path with no boot DDL to paper over it.
        """
        _, pin_sql = _load_migration_sql()
        with conn.cursor() as cur:
            # Reproduce the fresh-database state: no public copy. The drop is
            # signature-qualified (no CASCADE) and the fixture rolls back the
            # whole transaction.
            cur.execute("DROP FUNCTION IF EXISTS public.set_admin_context(boolean)")

            cur.execute(pin_sql)

            # Behavioural proof via exactly the app's unqualified call shape.
            cur.execute("SELECT set_admin_context(false)")
            cur.execute("SELECT current_setting('regengine.is_sysadmin', true)")
            assert cur.fetchone()[0] == "false"
        conn.rollback()
