"""Live-Postgres integration test for RLS tenant isolation.

The app sets tenant scope with ``set_config('app.tenant_id', <uuid>, true)``
(``shared.tenant_context.set_tenant_guc`` / ``set_tenant_guc_if_uuid``) and the
RLS policies filter on ``get_tenant_context()`` (which reads that GUC). Unit
tests mock the session and therefore CANNOT prove the policies actually filter
cross-tenant rows. This test does, against a real database.

Requires ``DATABASE_URL`` (skipped otherwise). It only ever runs inside
transactions that are rolled back — no row, role, or schema persists.

IMPORTANT (surfaced by this test): RLS is bypassed by ``SUPERUSER`` /
``BYPASSRLS`` roles. The local dev ``regengine`` role is such a role, so RLS
provides NO enforcement when connecting as it. The enforcement test below runs
under a transient NON-bypassrls role so it validates the policy mechanism
regardless. Operators MUST ensure the production application role is neither
SUPERUSER nor BYPASSRLS, or every RLS policy (and the #2458 backstop) is inert.
"""

from __future__ import annotations

import os

import pytest

psycopg = pytest.importorskip("psycopg")

DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="DATABASE_URL not set — live DB required")

_T_A = "11111111-1111-1111-1111-111111111111"
_T_B = "22222222-2222-2222-2222-222222222222"
_T_C = "33333333-3333-3333-3333-333333333333"

# Tables that the RLS-standardize migrations enable+force RLS on. Kept short and
# core; each is checked only if it exists so the test isn't brittle to drift.
_RLS_TABLES = [
    "traceability_events",
    "canonical_entities",
    "cte_events",
    "exception_cases",
    "hash_chain",
    "fda_export_log",
]


def _connect():
    try:
        conn = psycopg.connect(DATABASE_URL, connect_timeout=3)
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"cannot connect to DATABASE_URL: {exc}")
    conn.autocommit = False
    return conn


def _rls_schema_present(c) -> bool:
    """True only if the DB has had the RLS migrations applied.

    The CI "Test shared" job runs against an empty Postgres service that never
    runs ``alembic upgrade head``, so ``get_tenant_context()`` and the ``fsma.*``
    policies don't exist there. These are live-RLS-config assertions — they are
    only meaningful against a migrated database, so we skip rather than fail
    when the schema is absent (mirrors how the suite already skips without
    DATABASE_URL).
    """
    with c.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_proc WHERE proname = 'get_tenant_context' LIMIT 1")
        present = cur.fetchone() is not None
    c.rollback()  # clear the probe transaction
    return present


@pytest.fixture()
def conn():
    c = _connect()
    if not _rls_schema_present(c):
        c.close()
        pytest.skip("RLS schema not migrated (get_tenant_context absent) — live RLS test needs a migrated DB")
    try:
        yield c
    finally:
        c.rollback()
        c.close()


# ---------------------------------------------------------------------------
# Structural: the production schema is actually configured for RLS
# ---------------------------------------------------------------------------


class TestRlsSchemaConfig:
    def test_get_tenant_context_exists_and_returns_uuid(self, conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT prorettype::regtype::text FROM pg_proc WHERE proname = 'get_tenant_context'"
            )
            rows = cur.fetchall()
        assert rows, "get_tenant_context() must exist — RLS policies depend on it"
        assert any(r[0] == "uuid" for r in rows)

    def test_core_tables_have_rls_enabled_and_forced(self, conn):
        checked = 0
        with conn.cursor() as cur:
            for table in _RLS_TABLES:
                cur.execute("SELECT to_regclass(%s)", (f"fsma.{table}",))
                if cur.fetchone()[0] is None:
                    continue
                cur.execute(
                    """
                    SELECT relrowsecurity, relforcerowsecurity
                    FROM pg_class WHERE oid = %s::regclass
                    """,
                    (f"fsma.{table}",),
                )
                enabled, forced = cur.fetchone()
                assert enabled, f"fsma.{table}: RLS not ENABLED"
                assert forced, f"fsma.{table}: RLS not FORCED (owner would bypass it)"
                checked += 1
        assert checked, "no expected RLS tables found — schema not migrated?"

    def test_trace_policy_filters_on_tenant_context(self, conn):
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('fsma.traceability_events')")
            if cur.fetchone()[0] is None:
                pytest.skip("fsma.traceability_events not present")
            cur.execute(
                """
                SELECT pg_get_expr(polqual, polrelid)
                FROM pg_policy WHERE polrelid = 'fsma.traceability_events'::regclass
                """
            )
            quals = [r[0] for r in cur.fetchall()]
        assert quals, "traceability_events has no RLS policy"
        assert any("get_tenant_context()" in q for q in quals)


# ---------------------------------------------------------------------------
# Behavioral: get_tenant_context() reads the GUC and fails closed when unset
# ---------------------------------------------------------------------------


class TestGetTenantContextBehavior:
    def test_returns_the_guc_value(self, conn):
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('app.tenant_id', %s, true)", (_T_A,))
            cur.execute("SELECT get_tenant_context()::text")
            assert cur.fetchone()[0] == _T_A
        conn.rollback()

    def test_raises_when_guc_unset(self, conn):
        with conn.cursor() as cur:
            # No set_config in this transaction → GUC unset → must RAISE.
            with pytest.raises(psycopg.errors.RaiseException):
                cur.execute("SELECT get_tenant_context()")
        conn.rollback()


# ---------------------------------------------------------------------------
# Enforcement: the GUC + RLS policy actually isolates tenants, proven under a
# transient NON-bypassrls role (the dev app role is bypassrls and would not).
# ---------------------------------------------------------------------------


class TestRlsEnforcesIsolation:
    def test_set_config_guc_isolates_rows_for_non_bypass_role(self, conn):
        with conn.cursor() as cur:
            try:
                cur.execute("CREATE ROLE rls_probe_pytest NOLOGIN NOSUPERUSER NOBYPASSRLS")
            except psycopg.errors.InsufficientPrivilege:
                pytest.skip("connection role cannot CREATE ROLE — run enforcement check in CI as a privileged role")

            cur.execute("CREATE SCHEMA rls_probe_schema")
            cur.execute(
                "CREATE TABLE rls_probe_schema.t (id serial primary key, tenant_id uuid not null, val text)"
            )
            cur.execute("ALTER TABLE rls_probe_schema.t ENABLE ROW LEVEL SECURITY")
            cur.execute("ALTER TABLE rls_probe_schema.t FORCE ROW LEVEL SECURITY")
            cur.execute(
                """
                CREATE POLICY iso ON rls_probe_schema.t
                  USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
                  WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid)
                """
            )
            cur.execute("GRANT USAGE ON SCHEMA rls_probe_schema TO rls_probe_pytest")
            cur.execute("GRANT ALL ON rls_probe_schema.t TO rls_probe_pytest")
            cur.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA rls_probe_schema TO rls_probe_pytest")

            # Drop to the non-bypassrls role for the actual isolation checks.
            cur.execute("SET LOCAL ROLE rls_probe_pytest")

            cur.execute("SELECT set_config('app.tenant_id', %s, true)", (_T_A,))
            cur.execute("INSERT INTO rls_probe_schema.t (tenant_id, val) VALUES (%s, 'A')", (_T_A,))
            cur.execute("SELECT set_config('app.tenant_id', %s, true)", (_T_B,))
            cur.execute("INSERT INTO rls_probe_schema.t (tenant_id, val) VALUES (%s, 'B')", (_T_B,))

            # A sees only A; B sees only B; an unrelated tenant sees nothing —
            # even though both rows physically exist in this transaction.
            cur.execute("SELECT set_config('app.tenant_id', %s, true)", (_T_A,))
            cur.execute("SELECT val FROM rls_probe_schema.t ORDER BY val")
            assert [r[0] for r in cur.fetchall()] == ["A"]

            cur.execute("SELECT set_config('app.tenant_id', %s, true)", (_T_B,))
            cur.execute("SELECT val FROM rls_probe_schema.t ORDER BY val")
            assert [r[0] for r in cur.fetchall()] == ["B"]

            cur.execute("SELECT set_config('app.tenant_id', %s, true)", (_T_C,))
            cur.execute("SELECT count(*) FROM rls_probe_schema.t")
            assert cur.fetchone()[0] == 0

            # WITH CHECK also blocks writing a row for a different tenant than the GUC.
            cur.execute("SELECT set_config('app.tenant_id', %s, true)", (_T_A,))
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute("INSERT INTO rls_probe_schema.t (tenant_id, val) VALUES (%s, 'X')", (_T_B,))

        conn.rollback()  # undoes role, schema, table, and rows
