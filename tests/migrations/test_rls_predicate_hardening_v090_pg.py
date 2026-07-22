"""v090 RLS predicate convergence — behavioral test (#2526).

Spins up a disposable PostgreSQL container, creates a representative
tenant_* feature table and ``fsma.task_queue`` in their pre-v090 shape
(v051 four-policy text-compare on the feature table, v050/v063 fail-open
``OR ... = ''`` policy on task_queue), applies v090's conversion helpers,
and asserts the fail-hard contract:

  1. A session scoped to tenant A sees only A's rows.
  2. A session scoped to tenant B does not see A's rows.
  3. A session with ``app.tenant_id`` UNSET RAISES (fail-hard) — it must
     NEVER return another tenant's rows (the exact task_queue leak from
     the v050/v063 ``OR current_setting('app.tenant_id', true) = ''``
     clause).

Skips cleanly if Docker / testcontainers are unavailable; the static
guard (``test_rls_predicate_hardening_v090.py`` +
``scripts/check_tenant_id_uuid_only.py``) is the no-Docker safety net.

Run via:
    pytest tests/migrations/test_rls_predicate_hardening_v090_pg.py -v
"""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path
from typing import Iterator

import pytest

testcontainers = pytest.importorskip("testcontainers")  # noqa: F841
pytest.importorskip("testcontainers.postgres")

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402
from sqlalchemy.exc import InternalError, ProgrammingError  # noqa: E402
from testcontainers.postgres import PostgresContainer  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
V090_PATH = REPO_ROOT / "alembic" / "versions" / "20260629_a128f7f95db8_v090_rls_predicate_hardening.py"

# Representative feature table (all 8 share the id uuid / tenant_id uuid shape).
FEATURE_TABLE = "tenant_suppliers"


def _load_v090():
    spec = importlib.util.spec_from_file_location("v090_rls_predicate_hardening", V090_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def pg_engine() -> Iterator[Engine]:
    try:
        container = PostgresContainer("postgres:16", driver="psycopg")
        container.start()
    except Exception as exc:  # Docker missing, image pull fails, etc.
        pytest.skip(f"PostgresContainer unavailable: {exc}")

    try:
        url = container.get_connection_url().replace("postgresql+psycopg2://", "postgresql+psycopg://")
        engine = create_engine(url, future=True)
        _bootstrap_pre_v090(engine)
        _apply_v090(engine)
        yield engine
    finally:
        engine.dispose()
        container.stop()


def _bootstrap_pre_v090(engine: Engine) -> None:
    """Create get_tenant_context(), the regengine role, and the two target
    tables with their pre-v090 fail-open policies."""
    v090 = _load_v090()
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS fsma"))
        # Canonical fail-hard helper (v056 shape).
        conn.execute(
            text("""
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
        """)
        )
        conn.execute(
            text("""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine') THEN
                    CREATE ROLE regengine;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin') THEN
                    CREATE ROLE regengine_sysadmin;
                END IF;
            END $$
        """)
        )

        # Feature table with v051's four text-compare policies.
        conn.execute(
            text(f"""
            CREATE TABLE fsma.{FEATURE_TABLE} (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id uuid NOT NULL,
                name text NOT NULL
            )
        """)
        )
        conn.execute(text(f"ALTER TABLE fsma.{FEATURE_TABLE} ENABLE ROW LEVEL SECURITY"))
        conn.execute(text(f"ALTER TABLE fsma.{FEATURE_TABLE} FORCE ROW LEVEL SECURITY"))
        conn.execute(text(f"GRANT SELECT, INSERT ON fsma.{FEATURE_TABLE} TO regengine"))
        for action, clause in (
            ("select", "USING"),
            ("delete", "USING"),
        ):
            conn.execute(
                text(
                    f"CREATE POLICY tenant_isolation_{action} ON fsma.{FEATURE_TABLE} "
                    f"FOR {action.upper()} "
                    f"{clause} (tenant_id::text = current_setting('app.tenant_id', true))"
                )
            )

        # task_queue with the v050/v063 fail-open OR-empty-string policy.
        conn.execute(
            text("""
            CREATE TABLE fsma.task_queue (
                id BIGSERIAL PRIMARY KEY,
                tenant_id uuid,
                task_type text,
                status text
            )
        """)
        )
        conn.execute(text("ALTER TABLE fsma.task_queue ENABLE ROW LEVEL SECURITY"))
        conn.execute(text("ALTER TABLE fsma.task_queue FORCE ROW LEVEL SECURITY"))
        conn.execute(text("GRANT SELECT, INSERT ON fsma.task_queue TO regengine"))
        conn.execute(
            text(
                "CREATE POLICY tenant_isolation_tasks ON fsma.task_queue "
                "USING (tenant_id::text = current_setting('app.tenant_id', true) "
                "       OR current_setting('app.tenant_id', true) = '')"
            )
        )


def _apply_v090(engine: Engine) -> None:
    v090 = _load_v090()
    with engine.begin() as conn:
        conn.execute(text(v090._converge_feature_table(FEATURE_TABLE)))
        # task_queue re-assertion block (verbatim from v090.upgrade).
        conn.execute(
            text("""
            DO $mig$
            BEGIN
                IF to_regclass('fsma.task_queue') IS NULL THEN
                    RETURN;
                END IF;
                EXECUTE 'ALTER TABLE fsma.task_queue ENABLE ROW LEVEL SECURITY';
                EXECUTE 'ALTER TABLE fsma.task_queue FORCE ROW LEVEL SECURITY';
                EXECUTE 'DROP POLICY IF EXISTS tenant_isolation_tasks ON fsma.task_queue';
                EXECUTE 'CREATE POLICY tenant_isolation_tasks ON fsma.task_queue '
                        'USING (tenant_id = get_tenant_context())';
            END
            $mig$;
        """)
        )


def _set_tenant(conn, tenant_id: uuid.UUID) -> None:
    conn.execute(text("SELECT set_config('app.tenant_id', :tid, false)"), {"tid": str(tenant_id)})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

TENANT_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TENANT_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@pytest.fixture(scope="module", autouse=True)
def _seed(pg_engine: Engine):
    """Insert one row for tenant A and one for tenant B in each table.

    Inserts run as the table owner (superuser) so RLS does not block the
    seed; the assertions below set ROLE regengine to exercise the policy.
    """
    with pg_engine.begin() as conn:
        conn.execute(
            text(f"INSERT INTO fsma.{FEATURE_TABLE} (tenant_id, name) VALUES (:a, 'A'), (:b, 'B')"),
            {"a": TENANT_A, "b": TENANT_B},
        )
        conn.execute(
            text(
                "INSERT INTO fsma.task_queue (tenant_id, task_type, status) "
                "VALUES (:a, 'noop', 'pending'), (:b, 'noop', 'pending')"
            ),
            {"a": TENANT_A, "b": TENANT_B},
        )


@pytest.mark.parametrize("table", [FEATURE_TABLE, "task_queue"])
def test_tenant_a_sees_only_a(pg_engine: Engine, table: str):
    with pg_engine.connect() as conn:
        _set_tenant(conn, TENANT_A)
        conn.execute(text("SET ROLE regengine"))
        rows = conn.execute(text(f"SELECT tenant_id FROM fsma.{table}")).scalars().all()
        assert rows == [TENANT_A], f"{table}: tenant A should see only A's row, saw {rows}"


@pytest.mark.parametrize("table", [FEATURE_TABLE, "task_queue"])
def test_tenant_b_does_not_see_a(pg_engine: Engine, table: str):
    with pg_engine.connect() as conn:
        _set_tenant(conn, TENANT_B)
        conn.execute(text("SET ROLE regengine"))
        rows = conn.execute(text(f"SELECT tenant_id FROM fsma.{table}")).scalars().all()
        assert TENANT_A not in rows, f"{table}: cross-tenant leak — tenant B saw A's row"


@pytest.mark.parametrize("table", [FEATURE_TABLE, "task_queue"])
def test_unset_guc_fails_hard(pg_engine: Engine, table: str):
    """Unset app.tenant_id must RAISE — never return other tenants' rows.

    This is the regression for the task_queue ``OR ... = ''`` fail-open
    clause: before v090, an unset GUC on task_queue returned EVERY
    tenant's rows.
    """
    with pg_engine.connect() as conn:
        conn.execute(text("RESET app.tenant_id"))
        conn.execute(text("SET ROLE regengine"))
        with pytest.raises((InternalError, ProgrammingError)) as exc_info:
            conn.execute(text(f"SELECT COUNT(*) FROM fsma.{table}")).scalar()
        assert "app.tenant_id not set" in str(exc_info.value), (
            f"{table}: expected fail-hard raise on unset GUC, got: {exc_info.value}"
        )
