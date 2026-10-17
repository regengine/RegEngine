"""v128 migrations on a throwaway database: fresh upgrade, re-run, pre-wrapped.

The v128 SQL was applied by hand to some databases (fsma repair, then the
consolidation) and their policies were later rewritten as
``(select get_tenant_context())``. ``alembic upgrade head`` must therefore
do the real work on a fresh pre-v128 schema and be a no-op on an
already-changed one, leaving rewrapped policies exactly as they are. It
must also leave the boot canary's policy manifest unchanged on a database
that passed the canary at ed902d03df45.

Skips cleanly when no Postgres is available; fails under
``REGENGINE_REQUIRE_DB=1`` like the other migration gates.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.command import upgrade
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text

from tests.migrations.rls_db import _normalize_psycopg
from tests.migrations.scratch_db import scratch_database_engine
from tests.migrations.test_head_upgrade_downgrade_roundtrip import _current_revisions, _provision_roles

REPO_ROOT = Path(__file__).resolve().parents[2]
VERSIONS = REPO_ROOT / "alembic" / "versions"
FSMA_REPAIR = VERSIONS / "20261016_a5e7c9b2d341_v128_fsma_rls_policy_repair.py"
CONSOLIDATE = VERSIONS / "20261016_93eb33f262a1_v128_consolidate_permissive_policies.py"
PRE_V128 = "ed902d03df45"  # pragma: allowlist secret
RUNTIME_ROLES = ("regengine", "regengine_sysadmin")

_SNAPSHOT = text(
    """
    SELECT schemaname, tablename, policyname, permissive, roles::text, cmd, qual, with_check
    FROM pg_policies ORDER BY 1, 2, 3
    """
)


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def migrated_db():
    """A scratch DB upgraded to head, plus its canary manifests from before v128."""
    db_name = "inc2_scratch_v128_" + uuid4().hex[:12]
    with scratch_database_engine(db_name) as engine:
        plain_url = str(engine.url.render_as_string(hide_password=False))
        libpq_url = plain_url.replace("postgresql+psycopg://", "postgresql://", 1)
        _provision_roles(libpq_url)
        env_url = libpq_url.replace("%", "%%")
        saved = {key: os.environ.get(key) for key in ("MIGRATIONS_DATABASE_URL", "DATABASE_URL")}
        os.environ.update(MIGRATIONS_DATABASE_URL=env_url, DATABASE_URL=env_url)
        try:
            cfg = Config(str(REPO_ROOT / "alembic.ini"))
            cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
            upgrade(cfg, PRE_V128)
            pre_v128 = _canary_manifests(libpq_url)
            upgrade(cfg, "head")
            yield libpq_url, pre_v128
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


@pytest.fixture(scope="module")
def upgraded_db(migrated_db) -> str:
    return migrated_db[0]


def _canary_manifests(database_url: str) -> dict[str, str]:
    """The policy manifest the boot canary fingerprints, as each runtime role."""
    from shared.database import _RUNTIME_CUTOVER_CANARY_SQL

    engine = create_engine(_normalize_psycopg(database_url), future=True)
    try:
        manifests = {}
        for role in RUNTIME_ROLES:
            with engine.begin() as conn:
                conn.execute(text(f"SET LOCAL ROLE {role}"))
                manifests[role] = conn.execute(text(_RUNTIME_CUTOVER_CANARY_SQL)).one()[1]
        return manifests
    finally:
        engine.dispose()


def _run_upgrade(database_url: str, path: Path) -> None:
    module = _load(path)
    engine = create_engine(_normalize_psycopg(database_url), future=True)
    try:
        with engine.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                module.upgrade()
    finally:
        engine.dispose()


def _snapshot(database_url: str) -> list[tuple]:
    engine = create_engine(_normalize_psycopg(database_url), future=True)
    try:
        with engine.connect() as conn:
            return [tuple(row) for row in conn.execute(_SNAPSHOT)]
    finally:
        engine.dispose()


def _execute(database_url: str, sql: str) -> None:
    engine = create_engine(_normalize_psycopg(database_url), future=True)
    try:
        with engine.begin() as conn:
            conn.execute(text(sql))
    finally:
        engine.dispose()


def test_fresh_upgrade_reaches_single_v128_head(upgraded_db: str) -> None:
    assert _current_revisions(upgraded_db) == {"93eb33f262a1"}  # pragma: allowlist secret
    policies = {(row[1], row[2]) for row in _snapshot(upgraded_db)}
    assert ("cte_events", "v128_client_guard_cte_events") in policies
    consolidate = _load(CONSOLIDATE)
    for table, retained, _, removed, _ in consolidate._PAIRS:
        assert (table, retained) in policies
        assert (table, removed) not in policies


def test_v128_leaves_the_boot_canary_manifest_unchanged(migrated_db) -> None:
    # services/shared/database.py ships the pre-v128 fingerprints and every
    # container checks them at boot, so v128 must not change the manifest.
    database_url, pre_v128 = migrated_db
    assert all(pre_v128.values())
    assert _canary_manifests(database_url) == pre_v128
    policies = {(row[1], row[2]) for row in _snapshot(database_url)}
    assert ("ingestion_runs", "v128_client_guard_ingestion_runs") not in policies


def test_rerunning_each_v128_upgrade_is_a_no_op(upgraded_db: str) -> None:
    before = _snapshot(upgraded_db)
    _run_upgrade(upgraded_db, FSMA_REPAIR)
    assert _snapshot(upgraded_db) == before
    _run_upgrade(upgraded_db, CONSOLIDATE)
    assert _snapshot(upgraded_db) == before


def test_prewrapped_policies_are_left_untouched(upgraded_db: str) -> None:
    wrapped = "(tenant_id = (select get_tenant_context()))"
    _execute(
        upgraded_db,
        f"""
        ALTER POLICY v128_client_guard_canonical_entities ON fsma.canonical_entities
          USING ((tenant_id = (select get_tenant_context())) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])))
          WITH CHECK ((tenant_id = (select get_tenant_context())) AND (CURRENT_USER <> ALL (ARRAY['anon'::name, 'authenticated'::name])));
        ALTER POLICY tenant_isolation_audit_logs ON public.audit_logs USING {wrapped} WITH CHECK {wrapped};
        """,
    )
    before = _snapshot(upgraded_db)
    rows = {(row[1], row[2]): row for row in before}
    assert "SELECT get_tenant_context()" in rows[("canonical_entities", "v128_client_guard_canonical_entities")][6]
    assert "SELECT get_tenant_context()" in rows[("audit_logs", "tenant_isolation_audit_logs")][6]

    _run_upgrade(upgraded_db, FSMA_REPAIR)
    _run_upgrade(upgraded_db, CONSOLIDATE)
    assert _snapshot(upgraded_db) == before


def test_canary_table_guard_is_created_where_a_public_policy_reaches_clients(upgraded_db: str) -> None:
    before = _snapshot(upgraded_db)
    _execute(upgraded_db, "CREATE POLICY legacy_public_read ON fsma.ingestion_runs FOR SELECT TO PUBLIC USING (true)")
    try:
        _run_upgrade(upgraded_db, FSMA_REPAIR)
        policies = {(row[1], row[2]): row for row in _snapshot(upgraded_db)}
        guard = policies[("ingestion_runs", "v128_client_guard_ingestion_runs")]
        assert guard[3:6] == ("RESTRICTIVE", "{public}", "ALL")
    finally:
        _execute(
            upgraded_db,
            """
            DROP POLICY IF EXISTS v128_client_guard_ingestion_runs ON fsma.ingestion_runs;
            DROP POLICY legacy_public_read ON fsma.ingestion_runs;
            """,
        )
    assert _snapshot(upgraded_db) == before
