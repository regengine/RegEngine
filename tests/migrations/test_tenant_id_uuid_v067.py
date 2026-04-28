"""v067 tenant_id UUID standardization — integration test.

Spins up a disposable PostgreSQL container, creates the four target
tables in their pre-v067 shape (``tenant_id TEXT`` or ``VARCHAR(36)``),
applies the v067 migration, and verifies:

  1. The migration runs idempotently (re-applying is a no-op).
  2. After the migration, every target column reports ``data_type=uuid``
     in ``information_schema.columns``.
  3. Existing rows (with valid-UUID-shaped strings) survive the cast.
  4. Skips cleanly when a target table doesn't exist (the
     ``IF NULL: RETURN`` guard) — fresh DBs where the upstream creation
     migration hasn't run yet.

The test spins up Postgres directly (not via ``alembic upgrade head``)
because v067 is a delta — it expects the tables to already exist. Use
testcontainers' ``PostgresContainer`` so each test class gets a clean
DB.

Skips cleanly if Docker / testcontainers are unavailable.

Run via:
    pytest tests/migrations/test_tenant_id_uuid_v067.py -v
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

testcontainers = pytest.importorskip("testcontainers")  # noqa: F841
pytest.importorskip("testcontainers.postgres")

from docker.errors import DockerException  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from testcontainers.postgres import PostgresContainer  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_FILE = (
    REPO_ROOT / "alembic" / "versions"
    / "20260424_e9f0a1b2c3d4_v067_tenant_id_uuid_standardization.py"
)


def _load_v067_module():
    """Import the v067 migration module without running Alembic."""
    spec = importlib.util.spec_from_file_location(
        "v067_tenant_id_uuid_standardization", MIGRATION_FILE
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_TARGET_COLUMNS = [
    ("fsma", "fsma_audit_trail", "tenant_id"),
    ("fsma", "task_queue", "tenant_id"),
    ("fsma", "transformation_links", "tenant_id"),
    ("fsma", "dlq_replay", "tenant_id"),
]


@pytest.fixture(scope="module")
def pg_engine():
    try:
        container = PostgresContainer("postgres:16")
        pg = container.start()
    except DockerException as exc:
        pytest.skip(f"PostgresContainer unavailable: {exc}")

    try:
        engine = create_engine(pg.get_connection_url(), future=True)
        yield engine
        engine.dispose()
    finally:
        container.stop()


def _create_pre_v067_tables(engine):
    """Recreate each target table in its pre-v067 shape (TEXT / VARCHAR)."""
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS fsma"))
        # fsma_audit_trail (v049)
        conn.execute(text("""
            DROP TABLE IF EXISTS fsma.fsma_audit_trail CASCADE;
            CREATE TABLE fsma.fsma_audit_trail (
                id BIGSERIAL PRIMARY KEY,
                tenant_id TEXT,
                event_id TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """))
        # task_queue (v050 / v063)
        conn.execute(text("""
            DROP TABLE IF EXISTS fsma.task_queue CASCADE;
            CREATE TABLE fsma.task_queue (
                id BIGSERIAL PRIMARY KEY,
                tenant_id TEXT,
                task_type TEXT,
                status TEXT
            );
        """))
        # transformation_links (v057)
        conn.execute(text("""
            DROP TABLE IF EXISTS fsma.transformation_links CASCADE;
            CREATE TABLE fsma.transformation_links (
                id BIGSERIAL PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                input_tlc TEXT,
                output_tlc TEXT
            );
        """))
        # dlq_replay (v060) — VARCHAR(36)
        conn.execute(text("""
            DROP TABLE IF EXISTS fsma.dlq_replay CASCADE;
            CREATE TABLE fsma.dlq_replay (
                id BIGSERIAL PRIMARY KEY,
                tenant_id VARCHAR(36),
                source VARCHAR(50)
            );
        """))


def _apply_migration(engine):
    v067 = _load_v067_module()
    with engine.begin() as conn:
        conn.execute(text(v067._CREATE_IS_VALID_UUID_FN))
        for fix in v067._FIXES:
            conn.execute(text(v067._scrub_drop_alter_recreate(*fix)))


def _column_type(engine, schema: str, table: str, column: str) -> str:
    with engine.begin() as conn:
        return conn.execute(text("""
            SELECT data_type FROM information_schema.columns
            WHERE table_schema = :schema AND table_name = :table
              AND column_name = :column
        """), {"schema": schema, "table": table, "column": column}).scalar_one()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestUpgrade:

    def test_all_four_columns_become_uuid(self, pg_engine):
        _create_pre_v067_tables(pg_engine)
        # Pre-state: text or character varying.
        for schema, table, column in _TARGET_COLUMNS:
            t = _column_type(pg_engine, schema, table, column)
            assert t in ("text", "character varying"), (
                f"setup invariant: {schema}.{table}.{column} should start as "
                f"text/varchar but is {t}"
            )
        _apply_migration(pg_engine)
        # Post-state: uuid for all four.
        for schema, table, column in _TARGET_COLUMNS:
            t = _column_type(pg_engine, schema, table, column)
            assert t == "uuid", (
                f"v067 should have converted {schema}.{table}.{column} to uuid; "
                f"got {t}"
            )

    def test_existing_uuid_data_survives_cast(self, pg_engine):
        _create_pre_v067_tables(pg_engine)
        # Insert a valid-UUID-shaped string into each table.
        with pg_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO fsma.fsma_audit_trail (tenant_id, event_id)
                VALUES ('11111111-1111-1111-1111-111111111111', 'evt-1');
                INSERT INTO fsma.task_queue (tenant_id, task_type, status)
                VALUES ('22222222-2222-2222-2222-222222222222', 'noop', 'pending');
                INSERT INTO fsma.transformation_links (tenant_id, input_tlc, output_tlc)
                VALUES ('33333333-3333-3333-3333-333333333333', 'in', 'out');
                INSERT INTO fsma.dlq_replay (tenant_id, source)
                VALUES ('44444444-4444-4444-4444-444444444444', 'webhook');
            """))
        _apply_migration(pg_engine)
        # All rows survived; tenant_id is now UUID-typed.
        with pg_engine.begin() as conn:
            tids = conn.execute(text("""
                SELECT tenant_id::text FROM fsma.fsma_audit_trail
                UNION ALL
                SELECT tenant_id::text FROM fsma.task_queue
                UNION ALL
                SELECT tenant_id::text FROM fsma.transformation_links
                UNION ALL
                SELECT tenant_id::text FROM fsma.dlq_replay
                ORDER BY 1
            """)).scalars().all()
            assert tids == [
                "11111111-1111-1111-1111-111111111111",
                "22222222-2222-2222-2222-222222222222",
                "33333333-3333-3333-3333-333333333333",
                "44444444-4444-4444-4444-444444444444",
            ]


class TestIdempotent:

    def test_re_apply_is_noop(self, pg_engine):
        """Running the migration twice on a DB where the tables already
        have ``uuid`` columns must succeed (the ``information_schema``
        guard short-circuits each ALTER)."""
        _create_pre_v067_tables(pg_engine)
        _apply_migration(pg_engine)
        # Apply a second time — must not error.
        _apply_migration(pg_engine)
        # Columns still uuid.
        for schema, table, column in _TARGET_COLUMNS:
            assert _column_type(pg_engine, schema, table, column) == "uuid"


class TestTableMissingGuard:

    def test_missing_table_does_not_error(self, pg_engine):
        """If a target table doesn't exist (fresh DB where the creation
        migration hasn't run yet), the guard short-circuits and the
        migration succeeds. This is the contract that lets v067 land
        before every env has run v063 / v060 / v057 / v049."""
        with pg_engine.begin() as conn:
            conn.execute(text("DROP SCHEMA IF EXISTS fsma CASCADE"))
            conn.execute(text("CREATE SCHEMA fsma"))
            # Create only ONE of the four — confirm v067 still runs and
            # converts the present table while skipping the absent ones.
            conn.execute(text("""
                CREATE TABLE fsma.fsma_audit_trail (
                    id BIGSERIAL PRIMARY KEY,
                    tenant_id TEXT
                );
            """))
        _apply_migration(pg_engine)
        # The one that exists got converted.
        assert _column_type(pg_engine, "fsma", "fsma_audit_trail", "tenant_id") == "uuid"
        # The other three remain absent (no error raised).
        with pg_engine.begin() as conn:
            for schema, table, _ in _TARGET_COLUMNS[1:]:
                rc = conn.execute(text(
                    "SELECT to_regclass(:fq)"
                ), {"fq": f"{schema}.{table}"}).scalar()
                assert rc is None, f"{schema}.{table} should not exist"
