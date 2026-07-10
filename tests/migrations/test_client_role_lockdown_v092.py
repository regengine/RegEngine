"""v092 client-role lockdown — structural and behavioral assertions.

Companion to ``test_rls_coverage.py``. That suite proves every
tenant-scoped ``fsma.*`` table is RLS-hardened at alembic head; the
tables it exempts as "global by design" (``rule_definitions``,
``rule_audit_log``) plus the ``public.*`` service/credential tables were
still RLS-DISABLED, which Supabase's advisor correctly flags: its
``anon``/``authenticated`` client roles could read and write them —
including the compliance-rules catalog, MFA recovery codes, and funnel
telemetry. v092 (``b3c8e1f4a627``) closes that with an app-role-only
policy per table.

Structural test: at alembic head every v092 table that exists has RLS
enabled, forced where required, and exactly the ``app_only_*`` policy.

Behavioral test: a transient role shaped like Supabase's
``authenticated`` (LOGIN-less, no bypassrls, explicitly GRANTed table
privileges to simulate the pre-v092 grant surface) sees zero rows and
cannot insert, while ``regengine`` retains full access. This is the
actual exposure the advisory describes, exercised end to end.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from tests.migrations.rls_db import rls_postgres_or_skip, skip_or_fail_db
from tests.migrations.test_rls_coverage import _provision_app_roles

REPO_ROOT = Path(__file__).resolve().parents[2]

# (schema, table, force_expected) — mirrors _TABLES in the v092 migration.
# alembic_version/schema_migrations are ENABLE-only so the migration
# owner can never lock itself out.
V092_TABLES = [
    ("fsma", "rule_definitions", True),
    ("fsma", "rule_audit_log", True),
    ("fsma", "incidents", True),
    ("public", "funnel_events", True),
    ("public", "audit_log_buffer", True),
    ("public", "admin_mfa_recovery_codes", True),
    ("public", "password_reset_tokens", True),
    ("public", "tool_leads", True),
    ("public", "sandbox_shares", True),
    ("public", "alembic_version", False),
    ("public", "schema_migrations", False),
]


@pytest.fixture(scope="module")
def upgraded_engine() -> Iterator[Engine]:
    """Real Postgres at alembic head (same contract as test_rls_coverage)."""
    with rls_postgres_or_skip() as (plain_url, engine):
        driver_url = engine.url.render_as_string(hide_password=False)
        env = {
            "DATABASE_URL": plain_url,
            "PATH": subprocess.os.environ["PATH"],
        }
        for k in ("REGENGINE_ENV", "REGENGINE_ALLOW_BASELINE_DOWNGRADE"):
            v = subprocess.os.environ.get(k)
            if v is not None:
                env[k] = v

        _provision_app_roles(driver_url)
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            skip_or_fail_db(
                f"alembic upgrade head failed (returncode={result.returncode}):"
                f"\nstdout: {result.stdout}\nstderr: {result.stderr}"
            )
        yield engine


def _existing(engine: Engine) -> list[tuple[str, str, bool]]:
    with engine.connect() as conn:
        present = []
        for schema, table, force in V092_TABLES:
            if conn.execute(
                text("SELECT to_regclass(:fq)"), {"fq": f"{schema}.{table}"}
            ).scalar():
                present.append((schema, table, force))
        return present


def test_v092_tables_have_rls_and_app_only_policy(upgraded_engine: Engine) -> None:
    problems: list[str] = []
    with upgraded_engine.connect() as conn:
        for schema, table, force in _existing(upgraded_engine):
            row = conn.execute(
                text(
                    """
                    SELECT c.relrowsecurity, c.relforcerowsecurity
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = :s AND c.relname = :t
                    """
                ),
                {"s": schema, "t": table},
            ).one()
            if not row.relrowsecurity:
                problems.append(f"{schema}.{table}: RLS not enabled")
            if force and not row.relforcerowsecurity:
                problems.append(f"{schema}.{table}: RLS not forced")

            policy = conn.execute(
                text(
                    """
                    SELECT count(*) FROM pg_policies
                    WHERE schemaname = :s AND tablename = :t
                      AND policyname = :p
                    """
                ),
                {"s": schema, "t": table, "p": f"app_only_{table}"},
            ).scalar()
            if policy != 1:
                problems.append(f"{schema}.{table}: app_only policy missing")
    assert not problems, "v092 lockdown drifted:\n" + "\n".join(problems)


def test_client_shaped_role_sees_nothing_app_role_unaffected(
    upgraded_engine: Engine,
) -> None:
    """Simulate Supabase's ``authenticated``: no bypassrls, explicit
    GRANTs (the pre-v092 exposure surface). RLS must yield zero rows and
    reject writes; ``regengine`` must keep full access."""
    role = "v092_client_probe"
    url = upgraded_engine.url.render_as_string(hide_password=False)
    engine = create_engine(url, future=True)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"""
                    DO $$ BEGIN
                        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                            CREATE ROLE {role} NOLOGIN;
                        END IF;
                    END $$;
                    """
                )
            )
            conn.execute(text(f"GRANT USAGE ON SCHEMA public, fsma TO {role}"))
            conn.execute(
                text(
                    f"GRANT SELECT, INSERT ON fsma.rule_definitions, public.funnel_events TO {role}"
                )
            )

        with engine.connect() as conn:
            conn.execute(text(f"SET ROLE {role}"))
            visible = conn.execute(
                text("SELECT count(*) FROM fsma.rule_definitions")
            ).scalar()
            assert visible == 0, (
                f"client-shaped role can read {visible} rule_definitions rows — "
                "the rules catalog is still exposed"
            )
            with pytest.raises(Exception, match="policy|denied|violates"):
                conn.execute(
                    text(
                        """
                        INSERT INTO public.funnel_events (tenant_id, event_name, metadata)
                        VALUES (gen_random_uuid(), 'first_ingest', '{}'::jsonb)
                        """
                    )
                )
            conn.rollback()

        # App role keeps read access through the app_only policy.
        with engine.connect() as conn:
            conn.execute(text("SET ROLE regengine"))
            conn.execute(text("SELECT count(*) FROM fsma.rule_definitions")).scalar()
    finally:
        with engine.begin() as conn:
            conn.execute(text("RESET ROLE"))
            conn.execute(text(f"DROP OWNED BY {role} CASCADE"))
            conn.execute(text(f"DROP ROLE IF EXISTS {role}"))
        engine.dispose()
