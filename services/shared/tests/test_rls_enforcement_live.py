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
            cur.execute("SELECT prorettype::regtype::text FROM pg_proc WHERE proname = 'get_tenant_context'")
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
            # Either SQLSTATE is acceptable: what matters is that it RAISES
            # at all. v097/admin emit a plain RAISE (P0001); test_rls_coverage's
            # fixture uses ERRCODE='insufficient_privilege' (42501). No app code
            # branches on the code, and asserting one made this test fail purely
            # on how the DB was bootstrapped.
            with pytest.raises((psycopg.errors.RaiseException, psycopg.errors.InsufficientPrivilege)):
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
            cur.execute("CREATE TABLE rls_probe_schema.t (id serial primary key, tenant_id uuid not null, val text)")
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


# ---------------------------------------------------------------------------
# #2461: the ContextVar + Engine "begin" hook (shared.tenant_context)
# ---------------------------------------------------------------------------


def _psycopg_url() -> str:
    url = DATABASE_URL
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


class TestBeginHookAppliesGuc:
    """The class-level Engine 'begin' hook applies app.tenant_id from the
    seeded contextvar as the first statement of EVERY transaction —
    including the autobegin after commit()/rollback(), which is the fix
    for the whole mid-request-commit/rollback-clears-GUC bug class."""

    def test_guc_applied_and_reapplied_after_commit_and_rollback(self, conn):
        import shared.tenant_context as tc
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker

        engine = create_engine(_psycopg_url())
        Session = sessionmaker(bind=engine)
        try:
            with tc.tenant_scope(_T_A):
                s = Session()
                try:
                    q = text("SELECT current_setting('app.tenant_id', true)")
                    assert s.execute(q).scalar() == _T_A
                    # Intervening COMMIT ends the transaction (clearing the
                    # transaction-scoped GUC) — the next statement autobegins
                    # and the hook must re-apply it.
                    s.commit()
                    assert s.execute(q).scalar() == _T_A
                    # Same for ROLLBACK.
                    s.rollback()
                    assert s.execute(q).scalar() == _T_A
                finally:
                    s.rollback()
                    s.close()
        finally:
            engine.dispose()

    def test_unseeded_context_gets_no_guc(self, conn):
        import shared.tenant_context as tc
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker

        assert tc.get_rls_tenant_id() is None
        engine = create_engine(_psycopg_url())
        Session = sessionmaker(bind=engine)
        try:
            s = Session()
            try:
                val = s.execute(text("SELECT current_setting('app.tenant_id', true)")).scalar()
                assert val in (None, "")
            finally:
                s.rollback()
                s.close()
        finally:
            engine.dispose()

    def test_async_engine_parity(self, conn):
        """AsyncEngine coverage: class-level Engine listeners apply to
        AsyncEngine.sync_engine, contextvars propagate through
        SQLAlchemy's greenlet_spawn, and the hook's conn.execute is legal
        under the greenlet."""
        import asyncio

        pytest.importorskip("asyncpg")
        import shared.tenant_context as tc
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        url = DATABASE_URL
        for prefix in ("postgresql+psycopg2://", "postgresql+psycopg://", "postgresql://"):
            if url.startswith(prefix):
                url = url.replace(prefix, "postgresql+asyncpg://", 1)
                break

        async def _run():
            engine = create_async_engine(url)
            try:
                with tc.tenant_scope(_T_A):
                    async with engine.connect() as aconn:
                        result = await aconn.execute(text("SELECT current_setting('app.tenant_id', true)"))
                        return result.scalar()
            finally:
                await engine.dispose()

        assert asyncio.run(_run()) == _T_A


class TestFailClosedOnForcedTable:
    """Without any seeded context, a forced-table query under a
    non-bypass role must RAISE 'app.tenant_id not set' — fail closed.

    A probe row is seeded (as the privileged role, in the rolled-back
    transaction) because Postgres never evaluates the policy predicate
    on an empty table — COUNT(*) over zero rows would 'pass' vacuously.
    """

    def test_unset_context_raises_on_cte_events_as_regengine(self, conn):
        """Probe as the ``regengine`` app role — the tenant-isolation
        policies are ``TO regengine, regengine_sysadmin``, so only that
        role reaches the get_tenant_context() RAISE (any other role gets
        default-deny: silently zero rows, which the previous assertion
        style could not distinguish from a vacuous pass)."""
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('fsma.cte_events')")
            if cur.fetchone()[0] is None:
                conn.rollback()
                pytest.skip("fsma.cte_events not present — needs a migrated DB")
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = 'regengine' AND NOT rolbypassrls AND NOT rolsuper")
            if cur.fetchone() is None:
                conn.rollback()
                pytest.skip("non-bypass 'regengine' role not present")
            try:
                cur.execute("GRANT USAGE ON SCHEMA fsma TO regengine")
                cur.execute("GRANT SELECT ON fsma.cte_events TO regengine")
            except psycopg.errors.InsufficientPrivilege:
                conn.rollback()
                pytest.skip("connection role cannot GRANT")
            # Seed a row so the policy predicate actually evaluates
            # (Postgres never runs the predicate over an empty table).
            cur.execute(
                """
                INSERT INTO fsma.cte_events
                    (tenant_id, event_type, traceability_lot_code, product_description,
                     quantity, unit_of_measure, event_timestamp, sha256_hash, chain_hash)
                VALUES (%s, 'shipping', 'RLS-PROBE-TLC', 'rls probe', 1, 'case', NOW(),
                        'rls-probe-sha', 'rls-probe-chain')
                """,
                (_T_A,),
            )
            cur.execute("SET LOCAL ROLE regengine")
            with pytest.raises((psycopg.errors.RaiseException, psycopg.errors.InsufficientPrivilege)) as exc_info:
                cur.execute("SELECT COUNT(*) FROM fsma.cte_events")
            assert "app.tenant_id not set" in str(exc_info.value)
        conn.rollback()


class TestV095SystemContextArm:
    """v095 gives fsma.task_queue / fsma.fsma_audit_trail a
    ``regengine.system_context`` arm in CASE form. The CASE form is the
    OR-ordering regression test: with ONLY the system GUC set the
    predicate must NOT raise (Postgres does not short-circuit OR, and
    get_tenant_context() raises on an unset tenant GUC)."""

    def _v095_applied(self, cur) -> bool:
        cur.execute(
            """
            SELECT COUNT(*) FROM pg_policies
            WHERE schemaname = 'fsma'
              AND tablename IN ('task_queue', 'fsma_audit_trail')
              AND (qual LIKE '%regengine.system_context%' OR with_check LIKE '%regengine.system_context%')
            """
        )
        return cur.fetchone()[0] >= 2

    def _provision_probe(self, cur) -> None:
        """Create the probe role, seed cross-tenant rows (as the privileged
        role — the policy predicate is never evaluated on empty tables),
        then drop to the probe role."""
        cur.execute("CREATE ROLE rls_probe_v095 NOLOGIN NOSUPERUSER NOBYPASSRLS")
        cur.execute("GRANT USAGE ON SCHEMA fsma TO rls_probe_v095")
        cur.execute("GRANT SELECT, UPDATE ON fsma.task_queue TO rls_probe_v095")
        cur.execute("GRANT SELECT ON fsma.fsma_audit_trail TO rls_probe_v095")
        cur.execute(
            "INSERT INTO fsma.task_queue (task_type, tenant_id) VALUES ('rls_probe', %s), ('rls_probe', %s)",
            (_T_A, _T_B),
        )
        cur.execute(
            """
            INSERT INTO fsma.fsma_audit_trail
                (event_id, actor, actor_type, action, tenant_id, checksum)
            VALUES (%s, 'rls-probe', 'System', 'CREATED', %s, 'rls-probe-checksum')
            """,
            ("00000000-0000-4000-8000-00000000f095", _T_A),
        )
        cur.execute("SET LOCAL ROLE rls_probe_v095")

    def test_system_scope_admits_cross_tenant_queue_and_audit_reads(self, conn):
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('fsma.task_queue')")
            if cur.fetchone()[0] is None:
                conn.rollback()
                pytest.skip("fsma.task_queue not present — needs a migrated DB")
            if not self._v095_applied(cur):
                conn.rollback()
                pytest.skip("v095 system-context policies not applied")
            try:
                self._provision_probe(cur)
            except psycopg.errors.InsufficientPrivilege:
                conn.rollback()
                pytest.skip("connection role cannot CREATE ROLE")

            # Only the SYSTEM GUC is set — app.tenant_id stays unset. The
            # CASE form must evaluate to true WITHOUT touching
            # get_tenant_context() (which would raise), and the scan must
            # see BOTH tenants' rows (cross-tenant queue mechanics).
            cur.execute("SELECT set_config('regengine.system_context', 'true', true)")
            cur.execute("SELECT COUNT(*) FROM fsma.task_queue WHERE task_type = 'rls_probe'")
            assert cur.fetchone()[0] == 2, "system arm must admit BOTH tenants' queue rows"
            cur.execute(
                "UPDATE fsma.task_queue SET locked_by = NULL "
                "WHERE status = 'processing' AND locked_until < NOW() - INTERVAL '100 years'"
            )
            cur.execute("SELECT COUNT(*) FROM fsma.fsma_audit_trail WHERE actor = 'rls-probe'")
            assert cur.fetchone()[0] == 1
        conn.rollback()

    def test_without_system_scope_same_statements_raise(self, conn):
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('fsma.task_queue')")
            if cur.fetchone()[0] is None:
                conn.rollback()
                pytest.skip("fsma.task_queue not present — needs a migrated DB")
            if not self._v095_applied(cur):
                conn.rollback()
                pytest.skip("v095 system-context policies not applied")
            try:
                self._provision_probe(cur)
            except psycopg.errors.InsufficientPrivilege:
                conn.rollback()
                pytest.skip("connection role cannot CREATE ROLE")

            with pytest.raises((psycopg.errors.RaiseException, psycopg.errors.InsufficientPrivilege)) as exc_info:
                cur.execute("SELECT COUNT(*) FROM fsma.task_queue")
            assert "app.tenant_id not set" in str(exc_info.value)
        conn.rollback()

        # fsma_audit_trail in a fresh transaction (the raise aborted the
        # previous one).
        with conn.cursor() as cur:
            try:
                self._provision_probe(cur)
            except psycopg.errors.InsufficientPrivilege:
                conn.rollback()
                pytest.skip("connection role cannot CREATE ROLE")
            with pytest.raises(
                (
                    psycopg.errors.RaiseException,
                    psycopg.errors.InsufficientPrivilege,
                )
            ):
                cur.execute("SELECT COUNT(*) FROM fsma.fsma_audit_trail")
        conn.rollback()
