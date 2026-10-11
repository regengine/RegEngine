"""FK-aware autogenerate drift gate (audit-low: FK comparison in alembic/env.py).

``alembic/env.py:include_object`` used to exclude every foreign-key
constraint from autogenerate and ``alembic check``, so an ORM model could
add, drop, or re-option an FK (ondelete, deferrability) without any gate
noticing. With FK comparison enabled, this module proves two things on a
throwaway local Postgres database:

1. ``alembic check`` passes on a clean alembic-head database, meaning
   autogenerate produces no diff, FKs included.
2. The gate is not vacuous: a deliberately drifted FK option on the same
   database makes ``alembic check`` fail. On the old include_object this
   second assertion fails because the drift goes unnoticed, which is the
   regression proof for the fix.

The database is disposable: created on the same server as the designated
test Postgres under a fixed ``fleet_*`` name and dropped afterwards. It is
never the dev stack and never anything non-local (see
tests/migrations/rls_db.py for the reuse policy). Without a reachable
Postgres the module skips, or fails under REGENGINE_REQUIRE_DB=1.

Run via:
    pytest tests/migrations/test_alembic_fk_autogenerate_no_diff.py -v

Locally, point REGENGINE_MIGRATION_TEST_DB at a disposable Postgres
server you own (any database on it except the fleet_* scratch name; the
test creates and drops its own database there). In CI the job's
DATABASE_URL is reused automatically.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url

from tests.migrations.rls_db import _normalize_psycopg, rls_postgres_or_skip

REPO_ROOT = Path(__file__).resolve().parents[2]

# Fixed scratch name (safe-identifier shape, never a dev-stack name).
SCRATCH_DB = "fleet_alembic_fk_check"

# A stable ORM-declared FK present since the baseline chain, declared the
# same way on both sides: services/admin/app/sqlalchemy_models.py
# (organization_memberships.organization_id -> organizations.id,
# ondelete=CASCADE) and the v077 DDL. Drifting its ON DELETE option is
# DDL-legal on any column and is exactly the option-level change the old
# FK exclusion used to hide.
DRIFT_TABLE = "public.organization_memberships"
DRIFT_REF_TABLE = "public.organizations"
DRIFT_COLUMN = "organization_id"
DRIFT_REF_COLUMN = "id"
DRIFT_ORIGINAL_ONDELETE = "CASCADE"
DRIFTED_ONDELETE = "RESTRICT"


def _run_alembic(cmd: list[str], database_url: str) -> subprocess.CompletedProcess:
    """Invoke Alembic in a subprocess against the given throwaway database."""
    env = os.environ.copy()
    env["MIGRATIONS_DATABASE_URL"] = database_url
    env["DATABASE_URL"] = database_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", *cmd],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def _plain_url(driver_url: str) -> str:
    return driver_url.replace("postgresql+psycopg://", "postgresql://", 1)


@pytest.fixture(scope="module")
def fk_check_db() -> Iterator[str]:
    """Throwaway database migrated to alembic head, dropped afterwards."""
    with rls_postgres_or_skip() as (plain_url, _engine):
        target = make_url(plain_url).set(database=SCRATCH_DB)
        if (target.database or "") == (make_url(plain_url).database or ""):
            pytest.fail("scratch database must differ from the borrowed database")
        driver_target = _normalize_psycopg(target.render_as_string(hide_password=False))
        plain_target = _plain_url(driver_target)

        admin = create_engine(
            _normalize_psycopg(make_url(plain_url).set(database="postgres").render_as_string(hide_password=False)),
            isolation_level="AUTOCOMMIT",
            future=True,
        )
        try:
            with admin.connect() as conn:
                conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}"')
                conn.exec_driver_sql(f'CREATE DATABASE "{SCRATCH_DB}"')
        finally:
            admin.dispose()

        # Fresh databases lack the pre-baseline state production carries:
        # the regengine roles referenced by RLS policies and the
        # get_tenant_context() function the baseline policies call. Seed
        # them exactly as scripts/init-postgres.sh does (mirrors
        # test_rls_coverage._provision_app_roles), or upgrade head fails.
        seed = _engine_for(plain_target)
        try:
            with seed.begin() as conn:
                conn.execute(
                    text(
                        """
                        DO $$
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1 FROM pg_roles WHERE rolname = 'regengine'
                            ) THEN
                                CREATE ROLE regengine NOLOGIN;
                            END IF;
                            IF NOT EXISTS (
                                SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin'
                            ) THEN
                                CREATE ROLE regengine_sysadmin NOLOGIN;
                            END IF;
                        END$$;
                        """
                    )
                )
                conn.execute(
                    text(
                        """
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
                        """
                    )
                )
        finally:
            seed.dispose()

        try:
            upgraded = _run_alembic(["upgrade", "head"], plain_target)
            assert upgraded.returncode == 0, (
                "alembic upgrade head failed on the throwaway FK-check database.\n"
                f"stdout:\n{upgraded.stdout}\n\nstderr:\n{upgraded.stderr}"
            )
            yield plain_target
        finally:
            cleanup = create_engine(
                _normalize_psycopg(make_url(plain_url).set(database="postgres").render_as_string(hide_password=False)),
                isolation_level="AUTOCOMMIT",
                future=True,
            )
            try:
                with cleanup.connect() as conn:
                    conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)')
            except Exception:  # best effort cleanup
                pass
            finally:
                cleanup.dispose()


def _engine_for(url: str) -> Engine:
    return create_engine(_normalize_psycopg(url), future=True)


def test_check_passes_on_clean_head(fk_check_db: str) -> None:
    """Autogenerate produces no diff on a clean head database, FKs included."""
    result = _run_alembic(["check"], fk_check_db)
    assert result.returncode == 0, (
        "alembic check reported model/schema drift on a clean alembic-head "
        "database (FK comparison is now on; see alembic/env.py). Baseline "
        f"any intentional drift with notes before merging.\nstdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
    )


def test_check_catches_fk_option_drift(fk_check_db: str) -> None:
    """The gate notices a drifted FK ON DELETE option (old code does not)."""
    engine = _engine_for(fk_check_db)
    try:
        with engine.begin() as conn:
            row = conn.execute(
                # to_regclass(text) avoids the `:param::type` cast spelling,
                # which SQLAlchemy's text() leaves unconverted (it treats
                # `::` as an escaped colon).
                text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conrelid = to_regclass(:table) AND confrelid = to_regclass(:ref) "
                    "AND conkey = ARRAY[(SELECT attnum FROM pg_attribute "
                    "WHERE attrelid = to_regclass(:table) AND attname = :column)]"
                ),
                {"table": DRIFT_TABLE, "ref": DRIFT_REF_TABLE, "column": DRIFT_COLUMN},
            ).fetchone()
            assert row is not None, (
                f"expected FK {DRIFT_TABLE}({DRIFT_COLUMN}) -> "
                f"{DRIFT_REF_TABLE}({DRIFT_REF_COLUMN}) missing at alembic head"
            )
            conname = row.conname
            conn.execute(text(f'ALTER TABLE {DRIFT_TABLE} DROP CONSTRAINT "{conname}"'))
            conn.execute(
                text(
                    f'ALTER TABLE {DRIFT_TABLE} ADD CONSTRAINT "{conname}" '
                    f"FOREIGN KEY ({DRIFT_COLUMN}) REFERENCES {DRIFT_REF_TABLE}({DRIFT_REF_COLUMN}) "
                    f"ON DELETE {DRIFTED_ONDELETE}"
                )
            )
    finally:
        engine.dispose()

    try:
        result = _run_alembic(["check"], fk_check_db)
        combined = result.stdout + result.stderr
        assert result.returncode != 0, (
            "alembic check passed despite a drifted FK ON DELETE option on "
            f"{DRIFT_TABLE} (expected {DRIFT_ORIGINAL_ONDELETE}, database has "
            f"{DRIFTED_ONDELETE}). FK comparison is off again; see alembic/env.py."
        )
        assert "organization_memberships" in combined, (
            f"alembic check failed, but not because of the drifted FK; output:\n{combined}"
        )
    finally:
        repair = _engine_for(fk_check_db)
        try:
            with repair.begin() as conn:
                conn.execute(text(f'ALTER TABLE {DRIFT_TABLE} DROP CONSTRAINT "{conname}"'))
                conn.execute(
                    text(
                        f'ALTER TABLE {DRIFT_TABLE} ADD CONSTRAINT "{conname}" '
                        f"FOREIGN KEY ({DRIFT_COLUMN}) REFERENCES {DRIFT_REF_TABLE}({DRIFT_REF_COLUMN}) "
                        f"ON DELETE {DRIFT_ORIGINAL_ONDELETE}"
                    )
                )
        finally:
            repair.dispose()
