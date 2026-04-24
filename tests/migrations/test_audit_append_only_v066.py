"""v066 audit_logs append-only trigger — integration test.

Spins up a disposable PostgreSQL container, creates a minimal
``audit_logs`` table, applies the v066 trigger SQL, and verifies:

1. A plain UPDATE raises (trigger rejects).
2. A plain DELETE raises (trigger rejects).
3. UPDATE with ``SET LOCAL audit.allow_break_glass = 'true'`` succeeds
   (break-glass path works).
4. Re-running the migration SQL is idempotent (does not error on the
   second apply).

The test creates the table inline rather than running
``alembic upgrade head`` because ``audit_logs`` is not yet created by
any Alembic migration (it originated in Flyway V30). The migration SQL
itself is idempotent and no-ops when the table is absent, so this test
exercises the trigger behavior independently of the table-creation
path.

Requires Docker for testcontainers. If Docker is unavailable the test
module skips cleanly.

Run via:
    pytest tests/migrations/test_audit_append_only_v066.py -v
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
MIGRATION_SQL = REPO_ROOT / "alembic" / "sql" / "V066__audit_logs_append_only.sql"


@pytest.fixture(scope="module")
def pg_engine():
    with PostgresContainer("postgres:16") as pg:
        engine = create_engine(pg.get_connection_url(), future=True)
        with engine.begin() as conn:
            # Minimal audit_logs shape sufficient to exercise the trigger.
            # Real prod schema has more columns but the trigger is row-scoped
            # and doesn't inspect individual column values.
            conn.execute(text("""
                CREATE TABLE public.audit_logs (
                    id BIGSERIAL PRIMARY KEY,
                    tenant_id UUID NOT NULL,
                    integrity_hash TEXT NOT NULL
                )
            """))
            conn.execute(text(MIGRATION_SQL.read_text()))
        yield engine
        engine.dispose()


@pytest.fixture
def seed_row(pg_engine):
    """Insert one row and yield its id; clean up via break-glass."""
    with pg_engine.begin() as conn:
        row_id = conn.execute(text("""
            INSERT INTO audit_logs (tenant_id, integrity_hash)
            VALUES (gen_random_uuid(), 'seed')
            RETURNING id
        """)).scalar_one()
    yield row_id
    # Teardown: break-glass DELETE so each test starts clean.
    with pg_engine.begin() as conn:
        conn.execute(text("SET LOCAL audit.allow_break_glass = 'true'"))
        conn.execute(text("DELETE FROM audit_logs WHERE id = :id"), {"id": row_id})


def test_update_is_rejected(pg_engine, seed_row):
    with pg_engine.begin() as conn:
        with pytest.raises((InternalError, ProgrammingError, DBAPIError)) as exc_info:
            conn.execute(
                text("UPDATE audit_logs SET integrity_hash = 'tampered' WHERE id = :id"),
                {"id": seed_row},
            )
        assert "append-only" in str(exc_info.value).lower()


def test_delete_is_rejected(pg_engine, seed_row):
    with pg_engine.begin() as conn:
        with pytest.raises((InternalError, ProgrammingError, DBAPIError)) as exc_info:
            conn.execute(text("DELETE FROM audit_logs WHERE id = :id"), {"id": seed_row})
        assert "append-only" in str(exc_info.value).lower()


def test_break_glass_update_succeeds(pg_engine, seed_row):
    with pg_engine.begin() as conn:
        conn.execute(text("SET LOCAL audit.allow_break_glass = 'true'"))
        conn.execute(
            text("UPDATE audit_logs SET integrity_hash = 'corrected' WHERE id = :id"),
            {"id": seed_row},
        )
        result = conn.execute(
            text("SELECT integrity_hash FROM audit_logs WHERE id = :id"),
            {"id": seed_row},
        ).scalar_one()
        assert result == "corrected"


def test_migration_is_idempotent(pg_engine):
    # Re-applying the migration must not raise (CREATE OR REPLACE + DROP IF
    # EXISTS pattern). Covers the case where the same migration runs twice
    # because of a retry or a partial prior apply.
    with pg_engine.begin() as conn:
        conn.execute(text(MIGRATION_SQL.read_text()))
