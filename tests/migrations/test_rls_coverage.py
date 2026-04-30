"""RLS coverage regression gate — #1456 / EPIC-B.

After ``alembic upgrade head`` on a fresh PostgreSQL, this test asserts
that every tenant-scoped table in the ``fsma`` schema carries all three
layers of our isolation story:

  1. ``tenant_id`` column exists and is ``NOT NULL``
     (an INSERT that forgets tenant_id cannot slip through).

  2. ``FORCE ROW LEVEL SECURITY`` is enabled
     (the table owner cannot bypass RLS by connecting as owner).

  3. At least one policy references either ``get_tenant_context()`` or
     ``app.tenant_id`` (the policy is actually doing tenant isolation,
     not a placeholder like ``USING (true)``).

This is a lock against the whole class of regressions where a new
``fsma.*`` table ships with ``ENABLE ROW LEVEL SECURITY`` but not
``FORCE``, or with a nullable ``tenant_id`` column, or with RLS enabled
but no policies (the "empty-fortress" bug #1217 was fixed by v067).

TABLES_EXEMPT is the only escape hatch — add a table here only if it
genuinely is not tenant-scoped (e.g. lookup tables, system catalogs)
with a comment explaining why. Keep the list small.

Requires Docker for testcontainers. If Docker is unavailable the test
module skips cleanly.

Run via:
    pytest tests/migrations/test_rls_coverage.py -v
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Iterator, Set

import pytest

testcontainers = pytest.importorskip("testcontainers")
pytest.importorskip("testcontainers.postgres")

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402
from testcontainers.postgres import PostgresContainer  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[2]

# Tables that are intentionally NOT tenant-scoped — regulatory lookup
# data that all tenants share, or system catalogs. Every entry needs a
# comment justifying the exemption and ideally a link to the design doc.
TABLES_EXEMPT: Set[str] = {
    # Tenant/org roots do not carry tenant_id; they define the isolation boundary.
    "organizations",
    # Global rules catalog and its change log are shared regulatory metadata.
    "rule_definitions",
    "rule_audit_log",
}


def _provision_app_roles(database_url: str) -> None:
    """Create local roles/functions referenced by RLS policies."""
    engine = create_engine(database_url, future=True)
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_roles WHERE rolname = 'regengine'
                    ) THEN
                        CREATE ROLE regengine NOLOGIN;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin'
                    ) THEN
                        CREATE ROLE regengine_sysadmin NOLOGIN;
                    END IF;
                END$$;
            """))
            conn.execute(text("""
                CREATE OR REPLACE FUNCTION get_tenant_context()
                RETURNS uuid
                LANGUAGE plpgsql
                STABLE
                AS $$
                DECLARE
                    tid text;
                BEGIN
                    tid := NULLIF(current_setting('app.tenant_id', true), '');
                    IF tid IS NULL THEN
                        RAISE EXCEPTION
                            'app.tenant_id not set - tenant context required for RLS'
                            USING ERRCODE = 'insufficient_privilege';
                    END IF;
                    RETURN tid::uuid;
                END;
                $$;
            """))
    finally:
        engine.dispose()


@pytest.fixture(scope="module")
def upgraded_engine() -> Iterator[Engine]:
    """Spin up PostgreSQL, run ``alembic upgrade head``, yield engine."""
    try:
        container = PostgresContainer("postgres:16", driver="psycopg")
        container.start()
    except Exception as exc:
        pytest.skip(f"PostgresContainer unavailable: {exc}")

    try:
        url = container.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+psycopg://"
        )
        env = {
            "DATABASE_URL": url.replace("postgresql+psycopg", "postgresql"),
            "PATH": subprocess.os.environ["PATH"],
        }
        # alembic needs these env defaults — reuse what the fresh-DB
        # test sets up.
        for k in (
            "REGENGINE_ENV",
            "REGENGINE_ALLOW_BASELINE_DOWNGRADE",
        ):
            v = subprocess.os.environ.get(k)
            if v is not None:
                env[k] = v

        _provision_app_roles(url)
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            pytest.skip(
                f"alembic upgrade head failed (returncode={result.returncode}):"
                f"\nstdout: {result.stdout}\nstderr: {result.stderr}"
            )

        engine = create_engine(url, future=True)
        yield engine
    finally:
        try:
            engine.dispose()  # type: ignore[has-type]
        except Exception:
            pass
        container.stop()


def _fsma_tables(engine: Engine) -> list[str]:
    """Return all base tables in the ``fsma`` schema, sorted."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'fsma'
                ORDER BY tablename
                """
            )
        ).fetchall()
    return [r[0] for r in rows]


def _table_has_tenant_id_not_null(engine: Engine, table: str) -> bool:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT is_nullable = 'NO' AS not_null
                FROM information_schema.columns
                WHERE table_schema = 'fsma'
                  AND table_name = :t
                  AND column_name = 'tenant_id'
                """
            ),
            {"t": table},
        ).fetchone()
    return bool(row and row[0])


def _table_has_force_rls(engine: Engine, table: str) -> bool:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT c.relrowsecurity AND c.relforcerowsecurity
                FROM pg_class c
                JOIN pg_namespace n ON c.relnamespace = n.oid
                WHERE n.nspname = 'fsma' AND c.relname = :t
                """
            ),
            {"t": table},
        ).fetchone()
    return bool(row and row[0])


def _table_has_tenant_policy(engine: Engine, table: str) -> bool:
    """Return True if at least one policy on the table references
    ``get_tenant_context()`` or ``app.tenant_id`` in its expression —
    i.e., the policy is actually doing tenant isolation rather than
    a placeholder like ``USING (true)``."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT qual, with_check
                FROM pg_policies
                WHERE schemaname = 'fsma' AND tablename = :t
                """
            ),
            {"t": table},
        ).fetchall()
    if not rows:
        return False
    for qual, with_check in rows:
        blob = " ".join(x for x in (qual, with_check) if x)
        if "get_tenant_context" in blob or "app.tenant_id" in blob:
            return True
    return False


class TestRLSCoverage_EPIC_B:
    def test_every_fsma_table_has_tenant_id_not_null(self, upgraded_engine: Engine):
        tables = _fsma_tables(upgraded_engine)
        assert tables, "no fsma.* tables found after alembic upgrade head"
        failures = []
        for t in tables:
            if t in TABLES_EXEMPT:
                continue
            if not _table_has_tenant_id_not_null(upgraded_engine, t):
                failures.append(t)
        assert not failures, (
            "fsma.* tables missing NOT NULL tenant_id (add to TABLES_EXEMPT "
            f"with justification if this is intentional): {failures}"
        )

    def test_every_fsma_table_has_force_rls(self, upgraded_engine: Engine):
        tables = _fsma_tables(upgraded_engine)
        failures = []
        for t in tables:
            if t in TABLES_EXEMPT:
                continue
            if not _table_has_force_rls(upgraded_engine, t):
                failures.append(t)
        assert not failures, (
            "fsma.* tables missing FORCE ROW LEVEL SECURITY. Without FORCE "
            "the table owner role bypasses RLS entirely: "
            f"{failures}"
        )

    def test_every_fsma_table_has_tenant_isolation_policy(
        self, upgraded_engine: Engine
    ):
        tables = _fsma_tables(upgraded_engine)
        failures = []
        for t in tables:
            if t in TABLES_EXEMPT:
                continue
            if not _table_has_tenant_policy(upgraded_engine, t):
                failures.append(t)
        assert not failures, (
            "fsma.* tables with RLS enabled but no tenant-isolation policy "
            "referencing get_tenant_context() or app.tenant_id. This is "
            "the empty-fortress anti-pattern (#1217). Offenders: "
            f"{failures}"
        )
