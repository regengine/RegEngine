"""Upgrade-head plus newest-branch downgrade round-trip on a throwaway database.

Spins up a disposable database on the migration-test Postgres server, runs
``alembic upgrade head`` from the absolute starting state, asserts the head
and the objects the newest revisions own, then walks the v125/v126/v127
branch revisions back down to v125 and upgrades again. The walk exercises
the real (non-pass) downgrades of the newest code: the v127 policy restore,
the v126 grants/FK restores, and the v126 table restore. Anything left
behind by a downgrade (a constraint, grant, table or function the matching
re-upgrade then trips over) fails here instead of in production rollback.

Skips cleanly when no Postgres is available; fails under
``REGENGINE_REQUIRE_DB=1`` like the other migration gates.
"""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text

from tests.migrations.rls_db import _normalize_psycopg
from tests.migrations.scratch_db import scratch_database_engine

REPO_ROOT = Path(__file__).resolve().parents[2]

V125 = "22a278f6dc78"  # pragma: allowlist secret


def _alembic_config(database_url: str) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    return cfg


def _current_revisions(database_url: str) -> set[str]:
    engine = create_engine(_normalize_psycopg(database_url), future=True)
    try:
        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            return set(context.get_current_heads())
    finally:
        engine.dispose()


def _provision_roles(database_url: str) -> None:
    """Create the roles RLS policies name, as test_migration_fresh_db does."""
    engine = create_engine(_normalize_psycopg(database_url), future=True)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine') THEN
                        CREATE ROLE regengine NOLOGIN;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin') THEN
                        CREATE ROLE regengine_sysadmin NOLOGIN;
                    END IF;
                END$$;
                """
                )
            )
    finally:
        engine.dispose()


@pytest.fixture(scope="module")
def upgraded_db():
    """A scratch database migrated to head, with its plain URL.

    Only the ``regengine`` roles are provisioned (they are an environment
    prerequisite, as in test_migration_fresh_db). In particular
    ``get_tenant_context()`` is NOT pre-created: the chain itself must
    supply it before V002 needs it, so this fixture is also the regression
    test for a fresh ``alembic upgrade head``.
    """
    db_name = "qa_alembic_head_" + uuid4().hex[:12]
    with scratch_database_engine(db_name) as engine:
        plain_url = str(engine.url.render_as_string(hide_password=False))
        libpq_url = plain_url.replace("postgresql+psycopg://", "postgresql://", 1)
        _provision_roles(libpq_url)
        # Alembic reads its URL back through ConfigParser interpolation, which
        # rejects a bare "%" (a unix-socket "?host=%2Ftmp" URL dies in
        # before_set). SQLAlchemy itself is fine with it, so only the env
        # values alembic consumes get the "%%" escape (read back as "%").
        env_url = libpq_url.replace("%", "%%")
        old_migrations_url = os.environ.get("MIGRATIONS_DATABASE_URL")
        old_database_url = os.environ.get("DATABASE_URL")
        os.environ["MIGRATIONS_DATABASE_URL"] = env_url
        os.environ["DATABASE_URL"] = env_url
        try:
            upgrade(_alembic_config(libpq_url), "head")
            yield libpq_url
        finally:
            if old_migrations_url is None:
                os.environ.pop("MIGRATIONS_DATABASE_URL", None)
            else:
                os.environ["MIGRATIONS_DATABASE_URL"] = old_migrations_url
            if old_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = old_database_url


def test_upgrade_head_stamps_single_head(upgraded_db: str) -> None:
    """After upgrade, exactly one head revision is stamped."""
    assert len(_current_revisions(upgraded_db)) == 1


def test_newest_revision_objects_exist(upgraded_db: str) -> None:
    """Objects owned by the v124-v127 revisions exist after the upgrade."""
    engine = create_engine(_normalize_psycopg(upgraded_db), future=True)
    try:
        with engine.connect() as conn:
            cols = {
                row[0]
                for row in conn.execute(
                    text(
                        """SELECT column_name FROM information_schema.columns
                           WHERE table_schema = 'fsma' AND table_name = 'traceability_events'"""
                    )
                )
            }
            assert {"evaluation_verdict", "no_verdict_reason"} <= cols

            fks = {
                row[0]
                for row in conn.execute(
                    text(
                        """SELECT conname FROM pg_constraint
                           WHERE conrelid IN ('fsma.traceability_events'::regclass,
                                              'fsma.manifest_records'::regclass,
                                              'fsma.manifest_blobs'::regclass)
                             AND contype = 'f'"""
                    )
                )
            }
            assert "fk_traceability_events_run_tenant" in fks
            assert "fk_manifest_records_run_tenant" in fks
            assert "fk_manifest_blobs_run_tenant" in fks

            fns = {
                row[0]
                for row in conn.execute(
                    text(
                        """SELECT p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ')'
                           FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                           WHERE n.nspname = 'fsma'
                             AND p.proname IN ('claim_inbound_email_audit',
                                               'finalize_inbound_email_audit',
                                               'get_tenant_by_inbound_address')"""
                    )
                )
            }
            # pg_get_function_identity_arguments keeps parameter names.
            assert (
                "claim_inbound_email_audit(p_tenant_id uuid, p_message_id text, p_sender text, "
                "p_recipient text, p_subject text, p_attachment_count integer)" in fns
            )
            assert (
                "finalize_inbound_email_audit(p_message_id text, p_tenant_id uuid, p_status text, "
                "p_rejection_reason text, p_attachment_count integer, p_accepted_count integer, "
                "p_rejected_count integer, p_details jsonb)" in fns
            )
            assert "get_tenant_by_inbound_address(p_address text, p_sender text)" in fns
    finally:
        engine.dispose()


def test_branch_downgrade_and_reupgrade_round_trip(upgraded_db: str) -> None:
    """Downgrade the v126/v127 branches to v125, then upgrade back to head.

    This runs the newest non-pass downgrades for real (v127 policy restore,
    v126 grants/FK restores, v126 table restore) and proves the matching
    upgrades converge afterwards. The v085 guard is unrelated to this path
    (v085 stays applied throughout), so no acknowledgement variables are set.
    The fixture already points the migration URLs at this database.

    This test must stay last in this file: it temporarily moves the shared
    module database off head and returns it to head before asserting.
    """
    cfg = _alembic_config(upgraded_db)

    downgrade(cfg, V125)
    assert _current_revisions(upgraded_db) == {V125}

    engine = create_engine(_normalize_psycopg(upgraded_db), future=True)
    try:
        with engine.connect() as conn:
            fks = {
                row[0]
                for row in conn.execute(
                    text(
                        """SELECT conname FROM pg_constraint
                           WHERE conrelid IN ('fsma.traceability_events'::regclass,
                                              'fsma.manifest_records'::regclass)
                             AND contype = 'f'"""
                    )
                )
            }
            assert "traceability_events_ingestion_run_id_fkey" in fks
            assert "manifest_records_ingestion_run_id_fkey" in fks
    finally:
        engine.dispose()

    upgrade(cfg, "head")
    assert len(_current_revisions(upgraded_db)) == 1
