"""End-to-end fresh-DB migration test (#1187 regression guard).

Spins up a disposable PostgreSQL container, runs ``alembic upgrade
head`` from the absolute starting state (no stamped revision, no
existing tables), and asserts:

  1. The upgrade succeeds.
  2. The core schemas and tables declared by the consolidated
     baseline + v043-v058 chain exist after the upgrade.
  3. The v061 task_queue policy is in place (no OR-empty-string
     bypass).
  4. ``fsma.fsma_audit_trail.tenant_id`` and ``fsma.task_queue.tenant_id``
     are NOT NULL (#1287).
  5. ``fsma.task_queue`` has FORCE ROW LEVEL SECURITY enabled (#1281).
  6. Baseline ``downgrade`` refuses to run in the default env
     (#1264 guard).

Requires Docker for testcontainers. If Docker is unavailable the
module skips cleanly — the static CI guards
(``scripts/check_rls_fallback.py``, linting) remain the safety net.

Manual verification if Docker is unavailable:

    docker run --rm -e POSTGRES_PASSWORD=test -p 55432:5432 -d postgres:16
    DATABASE_URL=postgresql://postgres:test@localhost:55432/postgres \\
        alembic upgrade head
    # Then re-run with REGENGINE_ENV=development and
    # REGENGINE_ALLOW_BASELINE_DOWNGRADE=1 to exercise the guard.

Run via:
    pytest tests/migrations/test_migration_fresh_db.py -v
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Iterator

import pytest

# Skip the whole module if Docker / testcontainers unavailable.
testcontainers = pytest.importorskip("testcontainers")  # noqa: F841
pytest.importorskip("testcontainers.postgres")

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402
from testcontainers.postgres import PostgresContainer  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_alembic(cmd: list[str], database_url: str, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    """Invoke alembic as a subprocess with DATABASE_URL set.

    A subprocess keeps the test isolated from any alembic state the
    parent pytest process might hold (env.py caching, etc.).
    """
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-m", "alembic", *cmd],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.fixture(scope="module")
def pg_container() -> Iterator[PostgresContainer]:
    """Module-scoped Postgres container shared by all tests.

    The module's tests each mutate the DB state, so the fixture is a
    container — individual tests create their own engines or invoke
    ``alembic upgrade`` in a subprocess against the same DB.
    """
    try:
        container = PostgresContainer("postgres:16", driver="psycopg")
        container.start()
    except Exception as exc:  # Docker missing, image pull fails, etc.
        pytest.skip(f"PostgresContainer unavailable: {exc}")

    try:
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="module")
def database_url(pg_container: PostgresContainer) -> str:
    """The fixture's Postgres DSN, normalized for alembic's psycopg driver."""
    return pg_container.get_connection_url().replace(
        "postgresql+psycopg2://", "postgresql://"
    )


@pytest.fixture(scope="module")
def pg_engine(database_url: str) -> Iterator[Engine]:
    """Engine connected to the module's Postgres container.

    Yielded after ``alembic upgrade head`` has already run, so tests
    using this fixture observe the post-upgrade state.
    """
    # Convert the plain postgres:// DSN to one psycopg accepts from
    # SQLAlchemy. create_engine wants postgresql+psycopg:// for
    # psycopg 3.
    sa_url = database_url.replace(
        "postgresql://", "postgresql+psycopg://"
    )
    engine = create_engine(sa_url, future=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="module", autouse=True)
def applied_head(pg_container: PostgresContainer, database_url: str) -> None:
    """Auto-apply `alembic upgrade head` against the empty container once.

    If the upgrade fails, every test in the module fails — which is
    exactly what we want for a fresh-DB regression guard. The
    assertion lives in ``test_alembic_upgrade_head_succeeds``; this
    fixture just ensures the other tests observe the post-upgrade
    state.
    """
    result = _run_alembic(["upgrade", "head"], database_url)
    if result.returncode != 0:
        # Stash the output on the fixture's module so the dedicated
        # assertion test can surface it.
        pytest.fail(
            "alembic upgrade head failed on a fresh DB "
            "(regression of #1187).\n"
            f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
        )


def test_alembic_upgrade_head_succeeds(database_url: str) -> None:
    """After upgrade, alembic current should resolve cleanly.

    NOTE: during the v059 collision window (5+ PRs sharing revision
    ``f5a6b7c8d9e0``), ``alembic history`` and ``upgrade head`` will
    raise ``RevisionError: Requested revision ... overlaps`` until the
    collision is resolved by the merge chain. This test will fail in
    that window by design — it's the acceptance criterion for the
    rebase. Once the first v059 lands and the others get re-revved to
    v060a/v060b/..., both this test and ``alembic current`` should
    succeed.

    The earlier autouse fixture ``applied_head`` already validates
    that ``alembic upgrade head`` itself succeeds; this test checks
    the post-upgrade head state.
    """
    result = _run_alembic(["current"], database_url)
    assert result.returncode == 0, (
        f"alembic current failed:\n{result.stdout}\n\n{result.stderr}"
    )
    # Exactly one head revision should be stamped.
    # Output format: "<rev> (head)\n" or similar.
    non_blank = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(non_blank) == 1, (
        "Expected exactly one head revision after upgrade; "
        f"alembic current reported:\n{result.stdout}"
    )


def test_core_tables_exist(pg_engine: Engine) -> None:
    """The baseline + compliance-control-plane + task-queue migrations
    should have created the canonical table set. This is the #1187
    regression guard — before the fix, these CREATE statements never
    ran because the baseline migration crashed with FileNotFoundError.
    """
    expected_tables = {
        # V002 — FSMA CTE persistence
        ("fsma", "cte_events"),
        ("fsma", "cte_kdes"),
        ("fsma", "hash_chain"),
        # V043 — Canonical traceability events
        ("fsma", "traceability_events"),
        # V044 — Versioned rules engine
        ("fsma", "rule_definitions"),
        # V047 — Identity resolution
        ("fsma", "canonical_entities"),
        ("fsma", "entity_aliases"),
        # v048 — Operational hardening
        ("fsma", "fda_sla_requests"),
        ("fsma", "chain_verification_log"),
        # v049 — Audit trail
        ("fsma", "fsma_audit_trail"),
        # v050 — Task queue
        ("fsma", "task_queue"),
    }
    with pg_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT schemaname, tablename FROM pg_tables "
                "WHERE schemaname IN ('fsma', 'public')"
            )
        ).fetchall()
    present = {(r.schemaname, r.tablename) for r in rows}
    missing = expected_tables - present
    assert not missing, (
        f"Expected tables missing after fresh-DB upgrade: {sorted(missing)}. "
        f"Present fsma/public tables: {sorted(present)}"
    )


def test_task_queue_policy_fail_closed(pg_engine: Engine) -> None:
    """v061 replaced the v050 fail-open policy. Assert the replacement
    policy uses ``get_tenant_context()`` and does NOT contain the
    original OR-empty-string bypass."""
    with pg_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT policyname, qual FROM pg_policies "
                "WHERE schemaname = 'fsma' AND tablename = 'task_queue'"
            )
        ).fetchall()
    assert rows, "task_queue has no RLS policies after v061"
    for row in rows:
        qual = row.qual or ""
        assert "current_setting('app.tenant_id', true) = ''" not in qual, (
            f"v050 fail-open bypass still present in policy {row.policyname}: {qual}"
        )
        # Either get_tenant_context() (preferred) or a direct GUC
        # comparison without the empty-string escape hatch.
        assert (
            "get_tenant_context" in qual
            or "nullif" in qual.lower()
        ), (
            f"Policy {row.policyname} doesn't use a fail-hard resolver: {qual}"
        )


def test_task_queue_has_force_rls(pg_engine: Engine) -> None:
    """#1281 guard — FORCE RLS on task_queue."""
    with pg_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT relrowsecurity, relforcerowsecurity "
                "FROM pg_class c "
                "JOIN pg_namespace n ON c.relnamespace = n.oid "
                "WHERE n.nspname = 'fsma' AND c.relname = 'task_queue'"
            )
        ).fetchone()
    assert row is not None, "fsma.task_queue not found"
    assert row.relrowsecurity, "ENABLE ROW LEVEL SECURITY missing"
    assert row.relforcerowsecurity, (
        "FORCE ROW LEVEL SECURITY missing (#1281 regression)"
    )


def test_tenant_id_not_null_on_audit_and_tasks(pg_engine: Engine) -> None:
    """#1287 guard — tenant_id NOT NULL on fsma_audit_trail + task_queue."""
    for table in ("fsma_audit_trail", "task_queue"):
        with pg_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_schema = 'fsma' "
                    "AND table_name = :t AND column_name = 'tenant_id'"
                ),
                {"t": table},
            ).fetchone()
        assert row is not None, f"tenant_id column missing on fsma.{table}"
        assert row.is_nullable == "NO", (
            f"fsma.{table}.tenant_id is nullable (#1287 regression)"
        )


def test_baseline_downgrade_is_blocked(database_url: str) -> None:
    """#1264 guard — ``alembic downgrade base`` refuses unless both env
    vars are set. A fresh container defaults to REGENGINE_ENV unset,
    so the first attempt must fail."""
    result = _run_alembic(
        ["downgrade", "base"],
        database_url,
        extra_env={"REGENGINE_ENV": ""},
    )
    assert result.returncode != 0, (
        "Baseline downgrade was NOT blocked — #1264 guard regressed.\n"
        f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
    )
    # The guard's message should appear in the error output.
    combined = result.stdout + result.stderr
    assert "Baseline downgrade blocked" in combined, (
        "Downgrade failed but not via the #1264 guard. "
        f"Output:\n{combined}"
    )
