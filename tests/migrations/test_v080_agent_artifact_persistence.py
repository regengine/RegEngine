"""v080 agent artifact persistence regression tests.

The operator view needs durable, tenant-scoped storage for advisory artifacts
and human review outcomes. Existing ingestion run and receipt tables remain
the ledger source of truth; v080 adds the missing agent-side persistence and
safe links back to that ledger.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

REPO_ROOT = Path(__file__).resolve().parents[2]
V079_PATH = REPO_ROOT / "alembic" / "versions" / "20260513_c1d2e3f4a5b6_v079_ingestion_run_receipts.py"
V080_PATH = REPO_ROOT / "alembic" / "versions" / "20260513_d2e3f4a5b6c7_v080_agent_artifact_operator_persistence.py"
SHA256 = "a" * 64


def _load_module(path: Path, name: str):
    assert path.exists(), f"{name} migration not found at {path}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v080_migration_declares_agent_operator_persistence_contract():
    source = V080_PATH.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS fsma.agent_artifacts" in source
    assert "CREATE TABLE IF NOT EXISTS fsma.agent_artifact_reviews" in source
    assert "artifact_hash" in source
    assert "BEFORE UPDATE OR DELETE ON fsma.agent_artifacts" in source
    assert "fk_agent_artifacts_run_tenant" in source
    assert "fk_agent_reviews_receipt_tenant" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "tenant_id = get_tenant_context()" in source


@pytest.fixture(scope="module")
def pg_engine() -> Engine:
    testcontainers = pytest.importorskip("testcontainers")
    pytest.importorskip("testcontainers.postgres")
    from docker.errors import DockerException
    from testcontainers.postgres import PostgresContainer

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
def persistence_schema(pg_engine: Engine):
    v079 = _load_module(V079_PATH, "v079_ingestion_run_receipts")
    v080 = _load_module(V080_PATH, "v080_agent_artifact_operator_persistence")
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
                source_system text,
                source_file_name text,
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
        conn.execute(text(v080._AGENT_ARTIFACT_OPERATOR_PERSISTENCE_SQL))
    yield


def _seed_run_and_receipt(conn, tenant_id):
    run_id = conn.execute(
        text("INSERT INTO fsma.ingestion_runs (tenant_id) VALUES (:tid) RETURNING id"),
        {"tid": tenant_id},
    ).scalar_one()
    receipt = conn.execute(
        text("""
            INSERT INTO fsma.ingestion_run_receipts (
                tenant_id, ingestion_run_id, state, actor, metadata
            )
            VALUES (
                :tid, :run_id, 'needs_review', 'agent:test-agent',
                '{"agent_artifact": {"artifact_id": "placeholder"}}'::jsonb
            )
            RETURNING receipt_id
        """),
        {"tid": tenant_id, "run_id": run_id},
    ).scalar_one()
    return run_id, receipt


def _insert_artifact(conn, *, tenant_id, run_id, artifact_id=None, source_hash=SHA256):
    artifact_id = artifact_id or uuid4()
    artifact_json = {
        "artifact_id": str(artifact_id),
        "artifact_version": "agent-artifact.v1",
        "artifact_type": "field_mapping_suggestion",
        "tenant_id": str(tenant_id),
        "created_at": "2026-05-13T13:30:00Z",
        "agent_name": "fsma-field-mapper",
        "agent_version": "1.0.0",
        "model_name": "gpt-5",
        "suggestion": "Map Supplier TLC to traceability_lot_code.",
        "confidence": 0.91,
        "requires_human_review": False,
        "context": {"ingestion_run_id": str(run_id), "source_hashes": [source_hash]},
        "payload": {"source_field": "Supplier TLC"},
    }
    return (
        conn.execute(
            text("""
            INSERT INTO fsma.agent_artifacts (
                artifact_id, tenant_id, artifact_version, artifact_type,
                created_at, agent_name, agent_version, model_name, suggestion,
                confidence, requires_human_review, ingestion_run_id,
                source_hashes, artifact, payload
            )
            VALUES (
                :artifact_id, :tenant_id, 'agent-artifact.v1',
                'field_mapping_suggestion', '2026-05-13T13:30:00Z',
                'fsma-field-mapper', '1.0.0', 'gpt-5',
                'Map Supplier TLC to traceability_lot_code.',
                0.91, false, :run_id, ARRAY[:source_hash]::text[],
                CAST(:artifact AS jsonb), '{"source_field": "Supplier TLC"}'::jsonb
            )
            RETURNING artifact_id, artifact_hash
        """),
            {
                "artifact_id": artifact_id,
                "tenant_id": tenant_id,
                "run_id": run_id,
                "source_hash": source_hash,
                "artifact": __import__("json").dumps(artifact_json),
            },
        )
        .mappings()
        .one()
    )


def test_agent_artifacts_are_hashed_and_append_only(pg_engine: Engine, persistence_schema):
    tenant_id = uuid4()
    with pg_engine.begin() as conn:
        run_id, _ = _seed_run_and_receipt(conn, tenant_id)
        artifact = _insert_artifact(conn, tenant_id=tenant_id, run_id=run_id)

        assert artifact["artifact_hash"]
        assert len(artifact["artifact_hash"]) == 64

    with pg_engine.begin() as conn:
        with pytest.raises(DBAPIError):
            conn.execute(
                text("UPDATE fsma.agent_artifacts SET suggestion = 'changed' WHERE artifact_id = :artifact_id"),
                {"artifact_id": artifact["artifact_id"]},
            )

    with pg_engine.begin() as conn:
        with pytest.raises(DBAPIError):
            conn.execute(
                text("DELETE FROM fsma.agent_artifacts WHERE artifact_id = :artifact_id"),
                {"artifact_id": artifact["artifact_id"]},
            )


def test_agent_artifacts_validate_traceability_and_source_hashes(
    pg_engine: Engine,
    persistence_schema,
):
    tenant_id = uuid4()
    with pg_engine.begin() as conn:
        run_id, _ = _seed_run_and_receipt(conn, tenant_id)

        with pytest.raises(DBAPIError):
            _insert_artifact(
                conn,
                tenant_id=tenant_id,
                run_id=run_id,
                source_hash="not-a-sha",
            )

    with pg_engine.begin() as conn:
        with pytest.raises(DBAPIError):
            conn.execute(
                text("""
                    INSERT INTO fsma.agent_artifacts (
                        artifact_id, tenant_id, artifact_version, artifact_type,
                        created_at, agent_name, agent_version, suggestion,
                        confidence, requires_human_review, artifact, payload
                    )
                    VALUES (
                        gen_random_uuid(), :tenant_id, 'agent-artifact.v1',
                        'field_mapping_suggestion', now(), 'agent', '1',
                        'No anchors', 0.9, false,
                        '{"artifact_id": "missing"}'::jsonb, '{}'::jsonb
                    )
                """),
                {"tenant_id": tenant_id},
            )


def test_agent_reviews_link_to_artifact_run_and_receipt_by_tenant(
    pg_engine: Engine,
    persistence_schema,
):
    tenant_id = uuid4()
    other_tenant_id = uuid4()
    reviewer_id = uuid4()
    with pg_engine.begin() as conn:
        run_id, receipt_id = _seed_run_and_receipt(conn, tenant_id)
        _insert_artifact(conn, tenant_id=tenant_id, run_id=run_id)
        artifact_id = conn.execute(
            text("SELECT artifact_id FROM fsma.agent_artifacts WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        ).scalar_one()

        review = (
            conn.execute(
                text("""
                INSERT INTO fsma.agent_artifact_reviews (
                    tenant_id, artifact_id, ingestion_run_id, advisory_receipt_id,
                    status, reviewed_by, reviewed_at, review_reason, operator_notes,
                    decision_metadata
                )
                VALUES (
                    :tenant_id, :artifact_id, :run_id, :receipt_id, 'accepted',
                    :reviewer_id, now(), 'Evidence verified', 'Looks correct',
                    '{"risk_score": 18}'::jsonb
                )
                RETURNING review_id, status
            """),
                {
                    "tenant_id": tenant_id,
                    "artifact_id": artifact_id,
                    "run_id": run_id,
                    "receipt_id": receipt_id,
                    "reviewer_id": reviewer_id,
                },
            )
            .mappings()
            .one()
        )

        assert review["status"] == "accepted"

        with pytest.raises(DBAPIError):
            conn.execute(
                text("""
                    INSERT INTO fsma.agent_artifact_reviews (
                        tenant_id, artifact_id, ingestion_run_id, advisory_receipt_id,
                        status, reviewed_by, reviewed_at
                    )
                    VALUES (
                        :other_tenant_id, :artifact_id, :run_id, :receipt_id,
                        'accepted', :reviewer_id, now()
                    )
                """),
                {
                    "other_tenant_id": other_tenant_id,
                    "artifact_id": artifact_id,
                    "run_id": run_id,
                    "receipt_id": receipt_id,
                    "reviewer_id": reviewer_id,
                },
            )


def test_agent_reviews_require_terminal_reviewer_metadata(
    pg_engine: Engine,
    persistence_schema,
):
    tenant_id = uuid4()
    with pg_engine.begin() as conn:
        run_id, _ = _seed_run_and_receipt(conn, tenant_id)
        artifact = _insert_artifact(conn, tenant_id=tenant_id, run_id=run_id)

        with pytest.raises(DBAPIError):
            conn.execute(
                text("""
                    INSERT INTO fsma.agent_artifact_reviews (
                        tenant_id, artifact_id, status
                    )
                    VALUES (:tenant_id, :artifact_id, 'rejected')
                """),
                {
                    "tenant_id": tenant_id,
                    "artifact_id": artifact["artifact_id"],
                },
            )


def test_agent_operator_tables_force_rls(pg_engine: Engine, persistence_schema):
    with pg_engine.connect() as conn:
        rows = (
            conn.execute(
                text("""
                SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
                FROM pg_class c
                JOIN pg_namespace n ON c.relnamespace = n.oid
                WHERE n.nspname = 'fsma'
                  AND c.relname IN ('agent_artifacts', 'agent_artifact_reviews')
            """)
            )
            .mappings()
            .all()
        )

    assert {row["relname"] for row in rows} == {
        "agent_artifacts",
        "agent_artifact_reviews",
    }
    assert all(row["relrowsecurity"] for row in rows)
    assert all(row["relforcerowsecurity"] for row in rows)
