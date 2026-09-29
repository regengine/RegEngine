"""v079 ingestion-run receipt ledger regression tests.

The receipt ledger extends existing ``fsma.ingestion_runs`` with append-only,
hash-chained state receipts. It must be tenant-scoped, deterministic, and
safe to apply to databases that already have the compliance-control-plane
tables.

Requires Docker for behavioral tests. Static migration-file checks still run
without Docker.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest

testcontainers = pytest.importorskip("testcontainers")  # noqa: F841
pytest.importorskip("testcontainers.postgres")

from docker.errors import DockerException  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402
from sqlalchemy.exc import DBAPIError  # noqa: E402
from testcontainers.postgres import PostgresContainer  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = REPO_ROOT / "alembic" / "versions" / "20260513_c1d2e3f4a5b6_v079_ingestion_run_receipts.py"


def _load_v079_module():
    assert MIGRATION_PATH.exists(), f"v079 migration not found at {MIGRATION_PATH}"
    spec = importlib.util.spec_from_file_location("v079_ingestion_run_receipts", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def pg_engine() -> Engine:
    try:
        container = PostgresContainer("postgres:16")
        pg = container.start()
    except DockerException as exc:
        pytest.skip(f"PostgresContainer unavailable: {exc}")

    engine = create_engine(pg.get_connection_url(driver="psycopg"), future=True)
    try:
        yield engine
    finally:
        engine.dispose()
        container.stop()


@pytest.fixture
def receipt_schema(pg_engine: Engine):
    v079 = _load_v079_module()
    with pg_engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS fsma CASCADE"))
        conn.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto"'))
        conn.execute(text("CREATE SCHEMA fsma"))
        conn.execute(
            text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_roles WHERE rolname = 'regengine'
                ) THEN
                    CREATE ROLE regengine NOLOGIN;
                END IF;
            END$$;
        """)
        )
        conn.execute(
            text("""
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
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE fsma.ingestion_runs (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id uuid NOT NULL,
                status text NOT NULL DEFAULT 'processing',
                started_at timestamptz NOT NULL DEFAULT now()
            );
            CREATE TABLE fsma.traceability_events (
                event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id uuid NOT NULL
            );
            CREATE TABLE fsma.evidence_attachments (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id uuid NOT NULL
            );
            CREATE TABLE fsma.rule_evaluations (
                evaluation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id uuid NOT NULL
            );
            CREATE TABLE fsma.fda_export_log (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id uuid NOT NULL
            );
        """)
        )
        conn.execute(text(v079._INGESTION_RUN_RECEIPTS_SQL))
    yield


def _seed_run(conn, tenant_id):
    run_id = conn.execute(
        text("INSERT INTO fsma.ingestion_runs (tenant_id) VALUES (:tid) RETURNING id"),
        {"tid": tenant_id},
    ).scalar_one()
    canonical_event_id = conn.execute(
        text("INSERT INTO fsma.traceability_events (tenant_id) VALUES (:tid) RETURNING event_id"),
        {"tid": tenant_id},
    ).scalar_one()
    evidence_attachment_id = conn.execute(
        text("INSERT INTO fsma.evidence_attachments (tenant_id) VALUES (:tid) RETURNING id"),
        {"tid": tenant_id},
    ).scalar_one()
    rule_evaluation_id = conn.execute(
        text("INSERT INTO fsma.rule_evaluations (tenant_id) VALUES (:tid) RETURNING evaluation_id"),
        {"tid": tenant_id},
    ).scalar_one()
    export_log_id = conn.execute(
        text("INSERT INTO fsma.fda_export_log (tenant_id) VALUES (:tid) RETURNING id"),
        {"tid": tenant_id},
    ).scalar_one()
    return {
        "run_id": run_id,
        "canonical_event_id": canonical_event_id,
        "evidence_attachment_id": evidence_attachment_id,
        "rule_evaluation_id": rule_evaluation_id,
        "export_log_id": export_log_id,
    }


def test_v079_migration_declares_receipt_ledger_contract():
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS fsma.ingestion_run_receipts" in source
    assert "receipt_hash" in source
    assert "previous_receipt_hash" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "BEFORE UPDATE OR DELETE ON fsma.ingestion_run_receipts" in source


def test_receipts_auto_hash_and_chain_to_previous_receipt(pg_engine: Engine, receipt_schema):
    tenant_id = uuid4()
    with pg_engine.begin() as conn:
        ids = _seed_run(conn, tenant_id)
        first = (
            conn.execute(
                text("""
                INSERT INTO fsma.ingestion_run_receipts (
                    tenant_id, ingestion_run_id, state, actor, request_id, metadata
                )
                VALUES (
                    :tid, :run_id, 'received', 'ingestion-api', 'req-1',
                    '{"source": "webhook"}'::jsonb
                )
                RETURNING sequence_num, previous_receipt_hash, payload_hash, receipt_hash
            """),
                {"tid": tenant_id, **ids},
            )
            .mappings()
            .one()
        )
        second = (
            conn.execute(
                text("""
                INSERT INTO fsma.ingestion_run_receipts (
                    tenant_id, ingestion_run_id, state, actor, request_id,
                    canonical_event_id, evidence_attachment_id, rule_evaluation_id,
                    export_log_id, metadata
                )
                VALUES (
                    :tid, :run_id, 'export_generated', 'export-service', 'req-2',
                    :canonical_event_id, :evidence_attachment_id, :rule_evaluation_id,
                    :export_log_id, '{"export_hash": "abc"}'::jsonb
                )
                RETURNING sequence_num, previous_receipt_hash, payload_hash, receipt_hash
            """),
                {"tid": tenant_id, **ids},
            )
            .mappings()
            .one()
        )

        recomputed = conn.execute(
            text("""
                SELECT fsma.compute_ingestion_run_receipt_hash(
                    :tenant_id, :run_id, 2, 'export_generated',
                    (SELECT occurred_at FROM fsma.ingestion_run_receipts
                     WHERE receipt_hash = :receipt_hash),
                    'export-service', 'req-2', :canonical_event_id,
                    :evidence_attachment_id, :rule_evaluation_id, :export_log_id,
                    :payload_hash, :previous_receipt_hash
                )
            """),
            {
                "tenant_id": tenant_id,
                "receipt_hash": second["receipt_hash"],
                "payload_hash": second["payload_hash"],
                "previous_receipt_hash": second["previous_receipt_hash"],
                **ids,
            },
        ).scalar_one()

    assert first["sequence_num"] == 1
    assert first["previous_receipt_hash"] is None
    assert len(first["payload_hash"]) == 64
    assert len(first["receipt_hash"]) == 64
    assert second["sequence_num"] == 2
    assert second["previous_receipt_hash"] == first["receipt_hash"]
    assert recomputed == second["receipt_hash"]


def test_receipts_reject_sequence_gaps_and_wrong_previous_hash(pg_engine: Engine, receipt_schema):
    tenant_id = uuid4()
    with pytest.raises(DBAPIError):
        with pg_engine.begin() as conn:
            ids = _seed_run(conn, tenant_id)
            conn.execute(
                text("""
                    INSERT INTO fsma.ingestion_run_receipts (
                        tenant_id, ingestion_run_id, sequence_num, state, actor, metadata
                    )
                    VALUES (
                        :tid, :run_id, 3, 'received', 'ingestion-api', '{}'::jsonb
                    )
                """),
                {"tid": tenant_id, **ids},
            )

    with pg_engine.begin() as conn:
        ids = _seed_run(conn, tenant_id)
        conn.execute(
            text("""
                INSERT INTO fsma.ingestion_run_receipts (
                    tenant_id, ingestion_run_id, state, actor, metadata
                )
                VALUES (:tid, :run_id, 'received', 'ingestion-api', '{}'::jsonb)
            """),
            {"tid": tenant_id, **ids},
        )
    with pytest.raises(DBAPIError):
        with pg_engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO fsma.ingestion_run_receipts (
                        tenant_id, ingestion_run_id, state, actor,
                        previous_receipt_hash, metadata
                    )
                    VALUES (
                        :tid, :run_id, 'validated', 'validator',
                        :bad_previous, '{}'::jsonb
                    )
                """),
                {"tid": tenant_id, "bad_previous": "f" * 64, **ids},
            )


def test_receipts_are_append_only(pg_engine: Engine, receipt_schema):
    tenant_id = uuid4()
    with pg_engine.begin() as conn:
        ids = _seed_run(conn, tenant_id)
        receipt_id = conn.execute(
            text("""
                INSERT INTO fsma.ingestion_run_receipts (
                    tenant_id, ingestion_run_id, state, actor, metadata
                )
                VALUES (:tid, :run_id, 'received', 'ingestion-api', '{}'::jsonb)
                RETURNING receipt_id
            """),
            {"tid": tenant_id, **ids},
        ).scalar_one()

    with pytest.raises(DBAPIError):
        with pg_engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE fsma.ingestion_run_receipts
                    SET state = 'validated'
                    WHERE receipt_id = :receipt_id
                """),
                {"receipt_id": receipt_id},
            )

    with pytest.raises(DBAPIError):
        with pg_engine.begin() as conn:
            conn.execute(
                text("DELETE FROM fsma.ingestion_run_receipts WHERE receipt_id = :receipt_id"),
                {"receipt_id": receipt_id},
            )


def test_receipts_force_rls_with_tenant_policy(pg_engine: Engine, receipt_schema):
    with pg_engine.connect() as conn:
        rls = conn.execute(
            text("""
                SELECT c.relrowsecurity, c.relforcerowsecurity
                FROM pg_class c
                JOIN pg_namespace n ON c.relnamespace = n.oid
                WHERE n.nspname = 'fsma'
                  AND c.relname = 'ingestion_run_receipts'
            """)
        ).one()
        policies = conn.execute(
            text("""
                SELECT qual, with_check
                FROM pg_policies
                WHERE schemaname = 'fsma'
                  AND tablename = 'ingestion_run_receipts'
            """)
        ).all()

    assert rls.relrowsecurity is True
    assert rls.relforcerowsecurity is True
    assert any("get_tenant_context" in " ".join(part for part in row if part) for row in policies)
