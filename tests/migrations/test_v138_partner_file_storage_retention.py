"""v138 partner file storage retention — structure + stub PG16 behavior.

Covers the Codex FAIL fixes on #3729:

1. No runtime semicolon splitter — statements are an explicit tuple (v137
   shape). Structure tests assert a commented ``;`` and a ``$$`` function
   body both live inside single statement strings.
2. ``delete_after`` trigger is ``BEFORE INSERT OR UPDATE`` (no ``OF`` list)
   and always recomputes from ``report_delivered_at``, so a direct UPDATE of
   ``delete_after`` is overwritten.
3. Stub PG16: apply ``upgrade()`` twice (idempotent) against a minimal
   schema, then exercise the retention clock.

Uses a disposable local Postgres database (Homebrew / CI service) via
``scratch_database_engine``. Skips when no Postgres is available; fails under
``REGENGINE_REQUIRE_DB=1``.
"""

from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from tests.migrations.scratch_db import scratch_database_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    REPO_ROOT
    / "alembic"
    / "versions"
    / "20261028_b8c1e4f2a901_v138_partner_file_storage_retention.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        f"v138_partner_{uuid4().hex}", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _statement_strings() -> list[str]:
    tree = ast.parse(MIGRATION_PATH.read_text())
    for node in tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "_UPGRADE_STATEMENTS"
        ):
            assert isinstance(node.value, ast.Tuple)
            out: list[str] = []
            for elt in node.value.elts:
                assert isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                out.append(elt.value)
            return out
    raise AssertionError("_UPGRADE_STATEMENTS not found")


def test_no_runtime_semicolon_splitter() -> None:
    src = MIGRATION_PATH.read_text()
    assert "def _statements" not in src
    assert "_UPGRADE_STATEMENTS" in src
    tree = ast.parse(src)
    names = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "upgrade" in names and "downgrade" in names
    assert "_statements" not in names


def test_commented_semicolon_and_dollar_body_are_single_statements() -> None:
    """Authoring regression: comment `;` and `$$` bodies must not be split."""
    stmts = _statement_strings()
    # Header comment with an intentional semicolon survives inside a statement.
    assert any("trigger-maintained; UTC" in s for s in stmts)
    # Function body is one statement containing the dollar-quoted block.
    fn = [
        s
        for s in stmts
        if "CREATE OR REPLACE FUNCTION public.partner_files_set_delete_after" in s
    ]
    assert len(fn) == 1
    assert "AS $$" in fn[0]
    assert "interval '30 days'" in fn[0]
    assert fn[0].count("$$") >= 2
    # DO $$ role grants stay intact as one statement.
    dos = [s for s in stmts if s.lstrip().startswith("DO $$")]
    assert dos
    assert all("END $$" in s for s in dos)


def test_delete_after_trigger_is_before_any_update() -> None:
    stmts = _statement_strings()
    trig = next(s for s in stmts if "CREATE TRIGGER partner_files_set_delete_after" in s)
    assert "BEFORE INSERT OR UPDATE" in trig
    assert "OF report_delivered_at" not in trig


def _bootstrap_minimal_schema(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE public.tenants (
                    id uuid PRIMARY KEY DEFAULT gen_random_uuid()
                );
                CREATE OR REPLACE FUNCTION public.get_tenant_context()
                RETURNS uuid
                LANGUAGE sql
                STABLE
                AS $$
                    SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid
                $$;
                CREATE SCHEMA IF NOT EXISTS fsma;
                CREATE TABLE fsma.manifest_blobs (
                    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                    tenant_id uuid NOT NULL,
                    raw_bytes bytea NOT NULL,
                    storage_url text
                );
                """
            )
        )


def _apply_upgrade(engine, monkeypatch) -> None:
    module = _load_migration()

    class _Operations:
        @staticmethod
        def execute(statement: str) -> None:
            with engine.begin() as conn:
                conn.execute(text(statement))

    monkeypatch.setattr(module, "op", _Operations())
    module.upgrade()


@pytest.fixture(scope="module")
def pg_engine():
    """Disposable PG16 database with v138 minimal deps, or skip/fail."""
    # Prefer an explicit scratch URL; otherwise peer-auth local Homebrew PG.
    if not os.environ.get("REGENGINE_MIGRATION_TEST_DB"):
        os.environ["REGENGINE_MIGRATION_TEST_DB"] = "postgresql://sellers@/postgres?host=/tmp"
    db_name = "inc2_scratch_v138_" + uuid4().hex[:12]
    with scratch_database_engine(db_name) as engine:
        _bootstrap_minimal_schema(engine)
        yield engine


def test_upgrade_idempotent_on_stub_pg16(pg_engine, monkeypatch) -> None:
    _apply_upgrade(pg_engine, monkeypatch)
    _apply_upgrade(pg_engine, monkeypatch)  # second apply must be a no-op
    with pg_engine.connect() as conn:
        exists = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                      'partner_files',
                      'partner_file_derived',
                      'partner_file_deletion_log'
                  )
                """
            )
        ).scalar_one()
        assert exists == 3
        version = conn.execute(text("SHOW server_version")).scalar_one()
        assert version.startswith("16."), version
        tgtype = conn.execute(
            text(
                """
                SELECT pg_get_triggerdef(t.oid)
                FROM pg_trigger t
                JOIN pg_class c ON c.oid = t.tgrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relname = 'partner_files'
                  AND t.tgname = 'partner_files_set_delete_after'
                  AND NOT t.tgisinternal
                """
            )
        ).scalar_one()
        assert "BEFORE INSERT OR UPDATE" in tgtype
        assert "OF report_delivered_at" not in tgtype


def test_delete_after_recomputed_on_direct_update(pg_engine, monkeypatch) -> None:
    # Ensure schema is present (idempotent with the previous test).
    _apply_upgrade(pg_engine, monkeypatch)
    tenant_id = str(uuid4())
    file_id = str(uuid4())
    engagement_id = str(uuid4())
    with pg_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO public.tenants (id) VALUES (CAST(:id AS uuid))"),
            {"id": tenant_id},
        )
        # Bypass RLS for the owning role on a fresh stub.
        conn.execute(text("ALTER TABLE public.partner_files DISABLE ROW LEVEL SECURITY"))
        row = conn.execute(
            text(
                """
                INSERT INTO public.partner_files (
                    id, tenant_id, engagement_id, storage_path, content_sha256,
                    original_filename, byte_size, content_type, status,
                    report_delivered_at
                ) VALUES (
                    CAST(:id AS uuid),
                    CAST(:tenant_id AS uuid),
                    CAST(:engagement_id AS uuid),
                    'tenants/' || :tenant_id || '/synthetic.csv',
                    repeat('a', 64),
                    'synthetic.csv',
                    12,
                    'text/csv',
                    'delivered',
                    TIMESTAMPTZ '2026-10-01 00:00:00+00'
                )
                RETURNING delete_after
                """
            ),
            {
                "id": file_id,
                "tenant_id": tenant_id,
                "engagement_id": engagement_id,
            },
        ).scalar_one()
        assert row.utctimetuple()[:3] == (2026, 10, 31)

        # Direct UPDATE of delete_after must be overwritten by the trigger.
        overwritten = conn.execute(
            text(
                """
                UPDATE public.partner_files
                   SET delete_after = TIMESTAMPTZ '2099-01-01 00:00:00+00'
                 WHERE id = CAST(:id AS uuid)
             RETURNING delete_after AT TIME ZONE 'UTC'
                """
            ),
            {"id": file_id},
        ).scalar_one()
        assert str(overwritten)[:10] == "2026-10-31"

        # Clearing delivery clears the clock.
        cleared = conn.execute(
            text(
                """
                UPDATE public.partner_files
                   SET report_delivered_at = NULL
                 WHERE id = CAST(:id AS uuid)
             RETURNING delete_after
                """
            ),
            {"id": file_id},
        ).scalar_one()
        assert cleared is None
