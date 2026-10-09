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
enabled and forced where required. Most retain the client-lockdown
``app_only_*`` policy; v111 replaces tenant-bearing surfaces with tenant
policies and leaves release-disabled incidents/exchange surfaces deny-all.

Behavioral test: a transient role shaped like Supabase's
``authenticated`` (LOGIN-less, no bypassrls, explicitly GRANTed table
privileges to simulate the pre-v092 grant surface) sees zero rows and
cannot insert, while ``regengine`` retains only its explicit v111 access. This is the
actual exposure the advisory describes, exercised end to end.
"""

from __future__ import annotations

import re
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

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

# Tables adopted from runtime DDL by v098 with the same lockdown treatment
# (fsma.incidents is already in V092_TABLES). Without these entries the
# v098 lockdown would have no structural regression gate at all —
# test_rls_coverage.py exempts exchange_packages and only scans fsma.*.
V098_TABLES = [
    ("fsma", "exchange_packages", True),
    ("public", "scheduler_seen_items", True),
    ("public", "scheduler_job_runs", True),
]

LOCKDOWN_TABLES = V092_TABLES + V098_TABLES

# Postgres reports an RLS insert/update denial as SQLSTATE 42501
# ("new row violates row-level security policy ..."), which SQLAlchemy
# surfaces as a DBAPIError. Only that error proves policy denial: any
# other failure (a NOT NULL or FK "violates ..." IntegrityError, a
# connection fault, or a plain setup bug) must fail the test instead of
# satisfying it, so the type is narrowed to DBAPIError and the message
# must name the row-level security policy itself.
_POLICY_DENIAL_MATCH = "row-level security policy"


@contextmanager
def _expect_policy_denial(conn, statement):
    """Run ``conn.execute(statement)``; pass only on a DB policy denial.

    A database error that does not name the row-level security policy is
    re-raised unchanged so it fails the test instead of satisfying it,
    and non-database faults propagate untouched.
    """
    try:
        conn.execute(statement)
    except DBAPIError as exc:
        if not re.search(_POLICY_DENIAL_MATCH, str(exc)):
            raise
        yield
    else:
        pytest.fail("write succeeded for the client-shaped role; RLS did not deny it")


@pytest.fixture(scope="module")
def upgraded_engine() -> Iterator[Engine]:
    """Real Postgres at alembic head (same contract as test_rls_coverage)."""
    with rls_postgres_or_skip() as (plain_url, engine):
        driver_url = engine.url.render_as_string(hide_password=False)
        env = {
            "MIGRATIONS_DATABASE_URL": plain_url,
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
        for schema, table, force in LOCKDOWN_TABLES:
            if conn.execute(text("SELECT to_regclass(:fq)"), {"fq": f"{schema}.{table}"}).scalar():
                present.append((schema, table, force))
        return present


def test_v092_tables_have_approved_head_policy(upgraded_engine: Engine) -> None:
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

            policies = set(
                conn.execute(
                    text(
                        """
                        SELECT policyname FROM pg_policies
                        WHERE schemaname = :s AND tablename = :t
                        """
                    ),
                    {"s": schema, "t": table},
                ).scalars()
            )
            if (schema, table) in {
                ("fsma", "incidents"),
                ("fsma", "exchange_packages"),
            }:
                if policies:
                    problems.append(f"{schema}.{table}: disabled surface has policies {sorted(policies)}")
            elif (schema, table) == ("public", "funnel_events"):
                if "tenant_isolation_funnel_events" not in policies:
                    problems.append(f"{schema}.{table}: tenant policy missing")
            elif (schema, table) == ("public", "audit_log_buffer"):
                required = {
                    "audit_log_buffer_sysadmin_reconcile",
                    "audit_log_buffer_sysadmin_update",
                }
                if not required <= policies:
                    problems.append(f"{schema}.{table}: admin replay policies missing")
                if "audit_log_buffer_runtime_insert" in policies:
                    problems.append(f"{schema}.{table}: disabled producer still admitted")
            elif (schema, table) == ("public", "admin_mfa_recovery_codes"):
                replacement = "admin_mfa_recovery_codes_self_or_admin"
                if policies != {replacement}:
                    problems.append(f"{schema}.{table}: expected only {replacement}, found {sorted(policies)}")
                else:
                    policy = conn.execute(
                        text(
                            """
                            SELECT permissive, roles, cmd, qual, with_check
                            FROM pg_policies
                            WHERE schemaname = :s
                              AND tablename = :t
                              AND policyname = :policy
                            """
                        ),
                        {"s": schema, "t": table, "policy": replacement},
                    ).one()
                    expected_guard = (
                        "((CURRENT_USER = 'regengine_sysadmin'::name) AND "
                        "((user_id = (NULLIF(current_setting("
                        "'regengine.user_id'::text, true), ''::text))::uuid) OR "
                        "(current_setting('regengine.is_sysadmin'::text, true) "
                        "= 'true'::text)))"
                    )
                    observed = (
                        policy.permissive,
                        tuple(policy.roles),
                        policy.cmd,
                        policy.qual,
                        policy.with_check,
                    )
                    expected = (
                        "PERMISSIVE",
                        ("regengine_sysadmin",),
                        "ALL",
                        expected_guard,
                        expected_guard,
                    )
                    if observed != expected:
                        problems.append(f"{schema}.{table}: v111 self-or-admin policy drifted")
            elif f"app_only_{table}" not in policies:
                problems.append(f"{schema}.{table}: app_only policy missing")
    assert not problems, "v092/v098 lockdown drifted:\n" + "\n".join(problems)


def test_client_shaped_role_sees_nothing_app_role_unaffected(
    upgraded_engine: Engine,
) -> None:
    """Simulate Supabase's ``authenticated``: no bypassrls, explicit
    GRANTs (the pre-v092 exposure surface). RLS must yield zero rows and
    reject writes; ``regengine`` keeps only its explicit catalog read."""
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
            conn.execute(text(f"GRANT SELECT, INSERT ON fsma.rule_definitions, public.funnel_events TO {role}"))

        with engine.connect() as conn:
            conn.execute(text(f"SET ROLE {role}"))
            visible = conn.execute(text("SELECT count(*) FROM fsma.rule_definitions")).scalar()
            assert visible == 0, (
                f"client-shaped role can read {visible} rule_definitions rows — the rules catalog is still exposed"
            )
            with _expect_policy_denial(
                conn,
                text(
                    """
                    INSERT INTO public.funnel_events (tenant_id, event_name, metadata)
                    VALUES (gen_random_uuid(), 'first_ingest', '{}'::jsonb)
                    """
                ),
            ):
                pass
            conn.rollback()

        # App role keeps its explicitly granted read-only rules-catalog access.
        with engine.connect() as conn:
            conn.execute(text("SET ROLE regengine"))
            conn.execute(text("SELECT count(*) FROM fsma.rule_definitions")).scalar()
    finally:
        with engine.begin() as conn:
            conn.execute(text("RESET ROLE"))
            conn.execute(text(f"DROP OWNED BY {role} CASCADE"))
            conn.execute(text(f"DROP ROLE IF EXISTS {role}"))
        engine.dispose()


class _RaisingConn:
    """Minimal stub exposing ``execute`` for the policy-denial gate."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    def execute(self, _statement):
        raise self._error


def _db_error(exc_type, message: str):
    return exc_type("INSERT INTO public.funnel_events ...", {}, Exception(message))


def test_policy_denial_gate_accepts_rls_violation() -> None:
    """A genuine RLS denial satisfies the gate."""
    error = _db_error(
        DBAPIError,
        'new row violates row-level security policy for table "funnel_events"',
    )
    with _expect_policy_denial(_RaisingConn(error), text("INSERT")):
        pass


def test_policy_denial_gate_rejects_constraint_violation() -> None:
    """A NOT NULL "violates ..." IntegrityError must not satisfy the gate.

    The old ``pytest.raises(Exception, match="policy|denied|violates")``
    clause swallowed this error, so a broken insert that never reached a
    policy check still passed as policy denial.
    """
    from sqlalchemy.exc import IntegrityError

    error = _db_error(
        IntegrityError,
        'null value in column "tenant_id" violates not-null constraint',
    )
    with pytest.raises(IntegrityError):
        with _expect_policy_denial(_RaisingConn(error), text("INSERT")):
            pass


def test_policy_denial_gate_rejects_setup_fault() -> None:
    """A non-database setup fault must not satisfy the gate.

    The old base-``Exception`` clause swallowed any error whose message
    happened to contain "denied", so fixture or role-setup faults passed
    as policy denial.
    """
    with pytest.raises(RuntimeError, match="setup denied"):
        with _expect_policy_denial(
            _RaisingConn(RuntimeError("setup denied: fixture misconfigured")),
            text("INSERT"),
        ):
            pass


def test_policy_denial_gate_rejects_successful_write() -> None:
    """A write that succeeds must fail the gate instead of passing."""
    from _pytest.outcomes import Failed

    class _OkConn:
        def execute(self, _statement):
            return None

    with pytest.raises(Failed, match="RLS did not deny"):
        with _expect_policy_denial(_OkConn(), text("INSERT")):
            pass
