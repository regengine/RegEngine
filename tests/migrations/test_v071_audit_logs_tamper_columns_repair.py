"""v071 audit_logs tamper-column repair regression test.

Reproduces the Railway production table shape observed on 2026-04-26
after v070: ``actor_ua`` exists, but ``severity``, ``endpoint``,
``request_id``, and ``prev_hash`` are missing. The app's
``AuditLogger`` inserts all four, so this migration must make that insert
shape valid without rewriting historical audit rows.

Requires Docker for testcontainers. If Docker is unavailable the test
module skips cleanly.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

testcontainers = pytest.importorskip("testcontainers")  # noqa: F841
pytest.importorskip("testcontainers.postgres")

from sqlalchemy import create_engine, text  # noqa: E402
from testcontainers.postgres import PostgresContainer  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    REPO_ROOT
    / "alembic"
    / "versions"
    / "20260426_9d60e8724725_v071_audit_logs_tamper_columns_repair.py"
)


def _load_v071_module():
    spec = importlib.util.spec_from_file_location(
        "v071_audit_logs_tamper_columns_repair", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def pg_engine():
    with PostgresContainer("postgres:16") as pg:
        engine = create_engine(pg.get_connection_url(), future=True)
        yield engine
        engine.dispose()


@pytest.fixture
def prod_like_audit_logs(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS public.audit_logs"))
        conn.execute(
            text(
                """
                CREATE TABLE public.audit_logs (
                    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                    tenant_id uuid NOT NULL,
                    actor_id uuid NULL,
                    action varchar NOT NULL,
                    resource_type varchar NOT NULL,
                    resource_id varchar NOT NULL,
                    changes jsonb NULL,
                    metadata jsonb NULL,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    event_type text NULL,
                    event_category text NULL,
                    actor_email text NULL,
                    actor_ip text NULL,
                    integrity_hash text NULL,
                    timestamp timestamptz NULL,
                    actor_ua text NULL
                )
                """
            )
        )
    yield
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS public.audit_logs"))


def _column_names(conn) -> set[str]:
    rows = conn.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'audit_logs'
            """
        )
    ).all()
    return {row[0] for row in rows}


def test_v071_adds_missing_audit_insert_columns(pg_engine, prod_like_audit_logs):
    v071 = _load_v071_module()

    with pg_engine.begin() as conn:
        conn.execute(text(v071._REPAIR_SQL))
        columns = _column_names(conn)

    assert {"severity", "endpoint", "request_id", "prev_hash"} <= columns


def test_v071_allows_current_audit_logger_insert_shape(pg_engine, prod_like_audit_logs):
    v071 = _load_v071_module()

    with pg_engine.begin() as conn:
        conn.execute(text(v071._REPAIR_SQL))
        row_id = conn.execute(
            text(
                """
                INSERT INTO public.audit_logs (
                    tenant_id, timestamp, actor_id, actor_email, actor_ip,
                    actor_ua, event_type, event_category, action, severity,
                    resource_type, resource_id, endpoint, metadata,
                    request_id, prev_hash, integrity_hash
                )
                VALUES (
                    gen_random_uuid(), now(), gen_random_uuid(), NULL, NULL,
                    'pytest', 'user.login', 'authentication', 'session.create',
                    'info', 'session', gen_random_uuid()::text,
                    'POST /auth/login', '{}'::jsonb, gen_random_uuid(),
                    NULL, 'hash'
                )
                RETURNING id
                """
            )
        ).scalar_one()

    assert row_id is not None


def test_v071_is_idempotent(pg_engine, prod_like_audit_logs):
    v071 = _load_v071_module()

    with pg_engine.begin() as conn:
        conn.execute(text(v071._REPAIR_SQL))
        conn.execute(text(v071._REPAIR_SQL))

        severity_default = conn.execute(
            text(
                """
                SELECT column_default
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'audit_logs'
                  AND column_name = 'severity'
                """
            )
        ).scalar_one()

    assert severity_default == "'info'::text"
