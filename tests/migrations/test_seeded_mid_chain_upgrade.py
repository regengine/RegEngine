"""Seeded mid-chain migration rehearsal — #2588 follow-up.

Every other migration gate (`test_rls_coverage.py`, `test_migration_fresh_db.py`)
runs ``alembic upgrade head`` against an EMPTY database, so migrations whose
behaviour depends on existing rows never fail in CI. That is exactly how v090
``44225a26ed58`` shipped: its ``sequence_num`` backfill UPDATE on
``audit_logs`` is rejected by the v066 ``audit_append_only`` trigger on any
populated database — both production deploy attempts on 2026-07-15 failed at
that migration while every CI gate stayed green.

This gate rehearses what production actually experiences:

  1. ``alembic upgrade`` to ``MID_CHAIN_REVISION`` (v089 by default, or the
     deployed v079 revision selected by ``REGENGINE_SEED_REVISION``),
  2. seed a small representative dataset (``seed_mid_chain.sql``: two
     tenants, users, audit_logs rows that arm the append-only trigger,
     fsma.cte_events, fsma.request_cases/request_signoffs),
  3. ``alembic upgrade head`` over the populated tables.

Any migration after the selected seed revision that UPDATEs/DELETEs guarded rows, adds a
constraint existing rows violate, or otherwise assumes empty tables fails
here pre-merge. New migrations are appended after head, so they are always
covered without moving the pin; the seed is executed at exactly
one of the two pinned schemas, so later schema changes cannot invalidate it.

Migrations are also role-sensitive: several revisions (v051, v056, v075,
v092) take different guarded branches depending on whether Supabase-style
client roles (``anon``/``authenticated``) exist in the cluster. Set
``REGENGINE_SEED_CLIENT_ROLES=1`` to pre-create them (CI runs a matrix leg
with and without).

Postgres acquisition follows ``rls_db``: ``DATABASE_URL`` when reachable
(CI service container), else disposable testcontainers, and with
``REGENGINE_REQUIRE_DB=1`` no-Postgres FAILS instead of skipping. The
database must start empty — the module runs the full chain into it.

Run via:
    pytest tests/migrations/test_seeded_mid_chain_upgrade.py -v
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from tests.migrations.rls_db import rls_postgres_or_skip

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_SQL = Path(__file__).resolve().parent / "seed_mid_chain.sql"

# v089 — last revision before the v090 branch point whose audit_logs
# backfill produced the 2026-07-15 production deploy failures. The seed SQL
# is written against this revision's schema; move the pin only together
# with seed_mid_chain.sql.
MID_CHAIN_REVISION = os.getenv("REGENGINE_SEED_REVISION", "38e02636e340")
if MID_CHAIN_REVISION not in {"38e02636e340", "267d8053ced5"}:
    raise ValueError("seed fixture supports only the audited v079 and v089 schemas")


def _seed_sql() -> str:
    sql = SEED_SQL.read_text()
    if MID_CHAIN_REVISION == "267d8053ced5":
        # v079 predates password removal. The fixture never authenticates with
        # these disabled hashes; v084 must still preserve its email identities.
        sql = (
            sql.replace(
                "INSERT INTO public.users (id, email, is_sysadmin)",
                "INSERT INTO public.users (id, email, is_sysadmin, password_hash)",
            )
            .replace(
                "'seed-admin@example.test', true)",
                "'seed-admin@example.test', true, 'disabled-synthetic-password')",
            )
            .replace(
                "'seed-user@example.test', false)",
                "'seed-user@example.test', false, 'disabled-synthetic-password')",
            )
        )
    return sql


SEEDED_TABLES = (
    "public.tenants",
    "public.users",
    "public.audit_logs",
    "fsma.cte_events",
    "fsma.request_cases",
    "fsma.request_signoffs",
)


def _seed_client_roles() -> bool:
    return os.getenv("REGENGINE_SEED_CLIENT_ROLES", "").strip().lower() in {"1", "true", "yes"}


def _provision_cluster(engine: Engine, role_admin_engine: Engine) -> None:
    """Pre-create what the migration chain expects from the cluster.

    The app roles + get_tenant_context() bootstrap mirrors
    test_rls_coverage._provision_app_roles (production clusters have these
    before migrations ever run). The optional anon/authenticated pair
    reproduces a Supabase-style cluster so role-guarded migration branches
    (e.g. v092's REVOKE ... FROM authenticated) execute rather than no-op.
    """
    # Role creation is provider administration, never a migration-owner
    # capability. Legacy scratch runs may use the same superuser URL for both;
    # the dedicated-role CI lane supplies ROLE_ADMIN_DATABASE_URL separately.
    with role_admin_engine.begin() as conn:
        conn.execute(
            text("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine') THEN
                    CREATE ROLE regengine NOLOGIN;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin') THEN
                    CREATE ROLE regengine_sysadmin NOLOGIN;
                END IF;
            END$$;
        """)
        )
        if _seed_client_roles():
            conn.execute(
                text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                        CREATE ROLE anon NOLOGIN;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                        CREATE ROLE authenticated NOLOGIN;
                    END IF;
                END$$;
            """)
            )
    with engine.begin() as conn:
        if _seed_client_roles():
            # A cluster that has the client roles is a Supabase cluster, and
            # Supabase also guarantees auth.uid(); the role-guarded policies
            # in v051/v056 reference it, so it is part of the same contract.
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS auth"))
            conn.execute(
                text("""
                CREATE OR REPLACE FUNCTION auth.uid()
                RETURNS uuid
                LANGUAGE sql
                STABLE
                AS $$
                    SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid
                $$;
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


def _run_alembic(cmd: list[str], database_url: str) -> subprocess.CompletedProcess:
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


def _role_admin_url(migration_url: str) -> str:
    return os.getenv("ROLE_ADMIN_DATABASE_URL", "").strip() or migration_url


def _row_counts(engine: Engine) -> dict[str, int]:
    with engine.connect() as conn:
        return {table: conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() for table in SEEDED_TABLES}


@dataclass
class RehearsalResult:
    engine: Engine
    pre_upgrade_counts: dict[str, int]
    head_upgrade: subprocess.CompletedProcess


@pytest.fixture(scope="module")
def rehearsal() -> Iterator[RehearsalResult]:
    """Upgrade to MID_CHAIN_REVISION, seed, upgrade head — once per module."""
    with rls_postgres_or_skip() as (plain_url, engine):
        provider_url = _role_admin_url(plain_url)
        provider_engine = create_engine(provider_url, future=True)
        with engine.connect() as conn:
            already_migrated = conn.execute(
                text("SELECT to_regclass('public.alembic_version') IS NOT NULL")
            ).scalar_one()
        if already_migrated:
            pytest.fail(
                "seeded mid-chain rehearsal needs an EMPTY database "
                "(it upgrades from zero to v089 before seeding) — "
                "point DATABASE_URL (CI) or REGENGINE_MIGRATION_TEST_DB "
                "(local) at a dedicated database"
            )

        try:
            with engine.connect() as migration_conn, provider_engine.connect() as provider_conn:
                migration_database = migration_conn.execute(text("SELECT current_database()")).scalar_one()
                provider_database = provider_conn.execute(text("SELECT current_database()")).scalar_one()
            if migration_database != provider_database:
                pytest.fail("ROLE_ADMIN_DATABASE_URL must target the same scratch database as the migration credential")

            _provision_cluster(engine, provider_engine)

            mid = _run_alembic(["upgrade", MID_CHAIN_REVISION], plain_url)
            assert mid.returncode == 0, (
                f"alembic upgrade {MID_CHAIN_REVISION} failed on an empty database "
                f"— the mid-chain pin itself is broken:\n{mid.stderr}"
            )

            # Seed through the provider-only fixture seam. At v089 several
            # tables already use FORCE RLS, so the intentionally NOBYPASSRLS
            # migration owner cannot manufacture representative legacy rows.
            # The head upgrade itself still runs only as the migration role.
            import psycopg2

            seed_conn = psycopg2.connect(
                provider_url.replace("postgresql+psycopg://", "postgresql://", 1).replace(
                    "postgresql+psycopg2://", "postgresql://", 1
                )
            )
            try:
                seed_conn.autocommit = True
                with seed_conn.cursor() as cur:
                    cur.execute(_seed_sql())
            finally:
                seed_conn.close()

            pre_counts = _row_counts(provider_engine)
            assert all(count > 0 for count in pre_counts.values()), (
                f"seed_mid_chain.sql left a seeded table empty: {pre_counts} "
                "— the rehearsal would silently degrade to an empty-DB upgrade"
            )

            head = _run_alembic(["upgrade", "head"], plain_url)
            yield RehearsalResult(
                engine=provider_engine,
                pre_upgrade_counts=pre_counts,
                head_upgrade=head,
            )
        finally:
            provider_engine.dispose()


def test_upgrade_head_over_seeded_database(rehearsal: RehearsalResult) -> None:
    """THE gate: the chain from v089 to head must survive populated tables."""
    result = rehearsal.head_upgrade
    assert result.returncode == 0, (
        "alembic upgrade head failed on a seeded database (empty-DB gates "
        "stayed green — this is the production deploy failure mode of "
        f"#2588):\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


def test_seeded_rows_survive_upgrade(rehearsal: RehearsalResult) -> None:
    """No migration may silently drop seeded rows on its way to head."""
    assert _row_counts(rehearsal.engine) == rehearsal.pre_upgrade_counts


def test_audit_sequence_backfill_contiguous_per_tenant(rehearsal: RehearsalResult) -> None:
    """v090's backfill must number pre-existing audit rows 1..n per tenant."""
    with rehearsal.engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT tenant_id::text, array_agg(sequence_num ORDER BY id)
                FROM public.audit_logs
                GROUP BY tenant_id
                ORDER BY tenant_id
            """)
        ).all()
    assert rows, "seeded audit_logs rows disappeared"
    for tenant_id, seqs in rows:
        assert seqs == list(range(1, len(seqs) + 1)), (
            f"tenant {tenant_id} audit chain not contiguously backfilled: {seqs}"
        )


def test_audit_append_only_still_enforced_at_head(rehearsal: RehearsalResult) -> None:
    """A backfill fix must not leave the append-only trigger disabled."""
    with rehearsal.engine.connect() as conn:
        enabled = conn.execute(
            text("""
                SELECT tgenabled FROM pg_trigger
                WHERE tgname = 'audit_append_only'
                  AND tgrelid = 'public.audit_logs'::regclass
            """)
        ).scalar_one()
        assert enabled == "O", f"audit_append_only trigger not enabled at head: {enabled!r}"

    with pytest.raises(Exception, match="append-only"), rehearsal.engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE public.audit_logs SET severity = 'warn'
                WHERE id = (SELECT min(id) FROM public.audit_logs)
            """)
        )


def test_v079_identity_backfill_preserves_existing_users(rehearsal: RehearsalResult) -> None:
    if MID_CHAIN_REVISION != "267d8053ced5":
        return  # v089 fixture users are created after the v084 backfill.
    with rehearsal.engine.connect() as conn:
        missing = conn.execute(
            text("""SELECT count(*) FROM public.users u
            LEFT JOIN public.user_emails e ON e.user_id = u.id AND e.email = u.email
            WHERE e.id IS NULL OR e.email_fingerprint IS NULL""")
        ).scalar_one()
        assert missing == 0
        assert conn.execute(
            text("SELECT relforcerowsecurity FROM pg_class WHERE oid='public.users'::regclass")
        ).scalar_one()


def test_rule_backfills_leave_forced_rls(rehearsal: RehearsalResult) -> None:
    with rehearsal.engine.connect() as conn:
        assert conn.execute(
            text("""SELECT bool_and(relrowsecurity AND relforcerowsecurity)
            FROM pg_class WHERE oid IN ('fsma.rule_definitions'::regclass,
                                        'fsma.rule_audit_log'::regclass)""")
        ).scalar_one()
