"""PostgreSQL coverage for ORM/live DB type assertions.

These are incident-shaped tests for #2003: tenant UUID drift and missing
audit hash-chain/hash-input columns must fail before the app serves traffic.
"""

from __future__ import annotations

import pytest

testcontainers = pytest.importorskip("testcontainers")  # noqa: F841
pytest.importorskip("testcontainers.postgres")

from sqlalchemy import create_engine, text  # noqa: E402
from testcontainers.postgres import PostgresContainer  # noqa: E402

from services.admin.app.sqlalchemy_models import Base  # noqa: E402
from shared.db_type_assertions import (  # noqa: E402
    CriticalSchemaDriftError,
    verify_orm_db_type_alignment,
)


class _SilentLogger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


@pytest.fixture(scope="module")
def pg_engine():
    try:
        with PostgresContainer("postgres:16") as pg:
            engine = create_engine(pg.get_connection_url(), future=True)
            yield engine
            engine.dispose()
    except Exception as exc:
        pytest.skip(f"Postgres testcontainer unavailable: {exc}")


def test_live_tenant_id_text_vs_orm_uuid_fails(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS public.audit_logs"))
        conn.execute(
            text(
                """
                CREATE TABLE public.audit_logs (
                    id BIGSERIAL PRIMARY KEY,
                    tenant_id text NOT NULL,
                    timestamp timestamptz,
                    actor_id uuid,
                    actor_email text,
                    event_type text,
                    action text,
                    severity text,
                    resource_id text,
                    endpoint text,
                    metadata jsonb,
                    request_id uuid,
                    prev_hash text,
                    integrity_hash text NOT NULL
                )
                """
            )
        )

    with pytest.raises(CriticalSchemaDriftError, match="audit_logs.tenant_id"):
        verify_orm_db_type_alignment(pg_engine, Base, log=_SilentLogger())


def test_live_missing_audit_hash_input_columns_fail(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS public.audit_logs"))
        conn.execute(
            text(
                """
                CREATE TABLE public.audit_logs (
                    id BIGSERIAL PRIMARY KEY,
                    tenant_id uuid NOT NULL,
                    timestamp timestamptz,
                    actor_id uuid,
                    actor_email text,
                    event_type text,
                    action text,
                    resource_id text,
                    metadata jsonb,
                    integrity_hash text NOT NULL
                )
                """
            )
        )

    with pytest.raises(CriticalSchemaDriftError) as exc_info:
        verify_orm_db_type_alignment(pg_engine, Base, log=_SilentLogger())

    message = str(exc_info.value)
    assert "audit_logs.severity" in message
    assert "audit_logs.endpoint" in message
    assert "audit_logs.request_id" in message
    assert "audit_logs.prev_hash" in message
