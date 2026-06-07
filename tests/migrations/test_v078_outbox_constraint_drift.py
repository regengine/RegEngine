"""Regression coverage for production outbox dedupe drift in v078.

Production may already have the outbox dedupe name as either a standalone
unique index or as the index backing a table constraint. The migration must
handle both shapes.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Iterator

import pytest

testcontainers = pytest.importorskip("testcontainers")  # noqa: F841
pytest.importorskip("testcontainers.postgres")

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402
from testcontainers.postgres import PostgresContainer  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION_PATH = _REPO_ROOT / "alembic" / "versions" / "20260505_5ac9e7b1d402_v078_orphan_migration_forward_ports.py"


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("migration_v078", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def pg_engine() -> Iterator[Engine]:
    try:
        container = PostgresContainer("postgres:16", driver="psycopg")
        container.start()
    except Exception as exc:
        pytest.skip(f"PostgresContainer unavailable: {exc}")

    url = container.get_connection_url().replace("postgresql+psycopg2://", "postgresql+psycopg://")
    engine = create_engine(url, future=True)
    try:
        yield engine
    finally:
        engine.dispose()
        container.stop()


def _seed_existing_outbox_shape(engine: Engine, dedupe_shape: str) -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS public.graph_outbox CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS public.webhook_outbox CASCADE"))
        conn.execute(
            text(
                """
                CREATE TABLE public.graph_outbox (
                    id BIGSERIAL PRIMARY KEY,
                    tenant_id UUID,
                    operation TEXT NOT NULL,
                    cypher TEXT NOT NULL,
                    params JSONB NOT NULL DEFAULT '{}'::jsonb,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 10,
                    last_error TEXT,
                    enqueued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    drained_at TIMESTAMPTZ,
                    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    dedupe_key TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE public.webhook_outbox (
                    id BIGSERIAL PRIMARY KEY,
                    tenant_id UUID NOT NULL,
                    event_type TEXT NOT NULL,
                    target_url TEXT NOT NULL,
                    payload JSONB NOT NULL,
                    dedupe_key TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 10,
                    last_error TEXT,
                    last_status_code INTEGER,
                    enqueued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    delivered_at TIMESTAMPTZ,
                    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        )

        if dedupe_shape == "constraint":
            conn.execute(
                text(
                    """
                    ALTER TABLE public.graph_outbox
                        ADD CONSTRAINT uq_graph_outbox_dedupe
                        UNIQUE (operation, dedupe_key)
                    """
                )
            )
            conn.execute(
                text(
                    """
                    ALTER TABLE public.webhook_outbox
                        ADD CONSTRAINT uq_webhook_outbox_dedupe
                        UNIQUE (event_type, dedupe_key)
                    """
                )
            )
        elif dedupe_shape == "standalone_index":
            conn.execute(
                text(
                    """
                    CREATE UNIQUE INDEX uq_graph_outbox_dedupe
                    ON public.graph_outbox(operation, dedupe_key)
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE UNIQUE INDEX uq_webhook_outbox_dedupe
                    ON public.webhook_outbox(event_type, dedupe_key)
                    """
                )
            )
        else:  # pragma: no cover - guards future parametrization mistakes.
            raise AssertionError(f"unknown dedupe shape: {dedupe_shape}")


def _run_outbox_tables(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_migration_module()
    with engine.begin() as conn:
        monkeypatch.setattr(
            module.op,
            "execute",
            lambda sql: conn.execute(text(sql)),
        )
        module._outbox_tables()


def _constraint_count(engine: Engine, table_name: str, constraint_name: str) -> int:
    with engine.begin() as conn:
        return conn.execute(
            text(
                """
                SELECT count(*)
                FROM pg_constraint
                WHERE conname = :constraint_name
                  AND conrelid = to_regclass(:table_name)
                """
            ),
            {"constraint_name": constraint_name, "table_name": table_name},
        ).scalar_one()


def _standalone_index_count(engine: Engine, index_name: str) -> int:
    with engine.begin() as conn:
        return conn.execute(
            text(
                """
                SELECT count(*)
                FROM pg_class idx
                JOIN pg_namespace ns ON ns.oid = idx.relnamespace
                LEFT JOIN pg_constraint con ON con.conindid = idx.oid
                WHERE ns.nspname = 'public'
                  AND idx.relname = :index_name
                  AND idx.relkind = 'i'
                  AND con.oid IS NULL
                """
            ),
            {"index_name": index_name},
        ).scalar_one()


@pytest.mark.parametrize("dedupe_shape", ["constraint", "standalone_index"])
def test_outbox_tables_handles_existing_dedupe_shapes(
    pg_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    dedupe_shape: str,
) -> None:
    _seed_existing_outbox_shape(pg_engine, dedupe_shape)

    _run_outbox_tables(pg_engine, monkeypatch)

    assert _constraint_count(pg_engine, "public.graph_outbox", "uq_graph_outbox_dedupe") == 1
    assert _constraint_count(pg_engine, "public.webhook_outbox", "uq_webhook_outbox_dedupe") == 1
    assert _standalone_index_count(pg_engine, "uq_graph_outbox_dedupe") == 0
    assert _standalone_index_count(pg_engine, "uq_webhook_outbox_dedupe") == 0
