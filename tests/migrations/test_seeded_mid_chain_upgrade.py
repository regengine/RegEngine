"""Seeded mid-chain migration rehearsal — #2588 follow-up.

Every other migration gate (`test_rls_coverage.py`, `test_migration_fresh_db.py`)
runs ``alembic upgrade head`` against an EMPTY database, so migrations whose
behaviour depends on existing rows never fail in CI. That is exactly how v090
``44225a26ed58`` shipped: its ``sequence_num`` backfill UPDATE on
``audit_logs`` is rejected by the v066 ``audit_append_only`` trigger on any
populated database — both production deploy attempts on 2026-07-15 failed at
that migration while every CI gate stayed green.

This gate rehearses what production actually experiences:

  1. ``alembic upgrade`` to ``MID_CHAIN_REVISION`` (v089 — the revision
     production sat at when the v090 deploys failed),
  2. seed a small representative dataset (``seed_mid_chain.sql``: two
     tenants, users, audit_logs rows that arm the append-only trigger,
     fsma.cte_events, fsma.request_cases/request_signoffs),
  3. ``alembic upgrade head`` over the populated tables.

Any migration after v089 that UPDATEs/DELETEs guarded rows, adds a
constraint existing rows violate, or otherwise assumes empty tables fails
here pre-merge. New migrations are appended after head, so they are always
covered without moving the pin; the seed is executed at exactly
``MID_CHAIN_REVISION`` forever, so later schema changes cannot invalidate it.

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
from sqlalchemy import text
from sqlalchemy.engine import Engine

from tests.migrations.rls_db import rls_postgres_or_skip

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_SQL = Path(__file__).resolve().parent / "seed_mid_chain.sql"

# v089 — last revision before the v090 branch point whose audit_logs
# backfill produced the 2026-07-15 production deploy failures. The seed SQL
# is written against this revision's schema; move the pin only together
# with seed_mid_chain.sql.
MID_CHAIN_REVISION = "38e02636e340"

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


def _provision_cluster(engine: Engine) -> None:
    """Pre-create what the migration chain expects from the cluster.

    The app roles + get_tenant_context() bootstrap mirrors
    test_rls_coverage._provision_app_roles (production clusters have these
    before migrations ever run). The optional anon/authenticated pair
    reproduces a Supabase-style cluster so role-guarded migration branches
    (e.g. v092's REVOKE ... FROM authenticated) execute rather than no-op.
    """
    with engine.begin() as conn:
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
    env["DATABASE_URL"] = database_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", *cmd],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


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
        with engine.connect() as conn:
            already_migrated = conn.execute(
                text("SELECT to_regclass('public.alembic_version') IS NOT NULL")
            ).scalar_one()
        if already_migrated:
            pytest.fail(
                "seeded mid-chain rehearsal needs an EMPTY database "
                "(it upgrades from zero to v089 before seeding) — "
                "point DATABASE_URL at a dedicated database"
            )

        _provision_cluster(engine)

        mid = _run_alembic(["upgrade", MID_CHAIN_REVISION], plain_url)
        assert mid.returncode == 0, (
            f"alembic upgrade {MID_CHAIN_REVISION} failed on an empty database "
            f"— the mid-chain pin itself is broken:\n{mid.stderr}"
        )

        # psycopg2 (already required by alembic/env.py) executes the whole
        # multi-statement seed script in one call; the psycopg3 driver the
        # test engines use only accepts one statement per execute.
        import psycopg2

        seed_conn = psycopg2.connect(plain_url)
        try:
            seed_conn.autocommit = True
            with seed_conn.cursor() as cur:
                cur.execute(SEED_SQL.read_text())
        finally:
            seed_conn.close()

        pre_counts = _row_counts(engine)
        assert all(count > 0 for count in pre_counts.values()), (
            f"seed_mid_chain.sql left a seeded table empty: {pre_counts} "
            "— the rehearsal would silently degrade to an empty-DB upgrade"
        )

        head = _run_alembic(["upgrade", "head"], plain_url)
        yield RehearsalResult(engine=engine, pre_upgrade_counts=pre_counts, head_upgrade=head)


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
