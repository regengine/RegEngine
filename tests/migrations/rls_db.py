"""Shared Postgres acquisition for the behavioral RLS test gates (#2530).

The RLS behavioral tests (``test_rls_hardening.py``, ``test_rls_coverage.py``)
need a real PostgreSQL. Historically they only knew how to spin one up via
``testcontainers`` (Docker-in-Docker), and skipped silently whenever Docker
was unavailable — which is every blocking CI job, so the RLS gate was
decorative (#2530).

This helper makes acquisition order explicit and CI-gateable:

  1. If ``REGENGINE_MIGRATION_TEST_DB`` is set, use it — the explicit local
     opt-in. It must point at a disposable scratch database; a dev-stack URL
     or an unreachable one FAILS instead of silently degrading.
  2. If ``DATABASE_URL`` is set AND we are in CI (``CI=true``), reuse it. CI
     provisions a ``postgres:16`` service container and exports
     ``DATABASE_URL``; reusing it means the RLS gate runs without
     Docker-in-Docker. Outside CI ``DATABASE_URL`` is IGNORED: the service
     conftests (services/admin, services/scheduler) ``setdefault`` it to the
     local dev stack, and these gates run ``alembic upgrade head`` + seed data
     into whatever they reach — a 2026-07-25 local run migrated and seeded a
     developer's live dev database that way. Dev-stack URLs (database
     ``regengine``/``regengine_admin`` on a local host) are refused even in CI.
  3. Otherwise fall back to a disposable ``testcontainers`` Postgres (local
     dev convenience).
  4. If none is available:
       * ``REGENGINE_REQUIRE_DB=1`` (or ``true``) → ``pytest.fail`` — a CI job
         that sets this can never turn the RLS gate green by skipping.
       * unset → ``pytest.skip`` — local runs without Docker stay friendly,
         where the static guards (check_rls_fallback.py) remain the safety net.
"""

from __future__ import annotations

import os
import warnings
from contextlib import contextmanager
from typing import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url

_PG_PREFIXES = ("postgresql://", "postgresql+psycopg://", "postgresql+psycopg2://")

# The dev-stack databases the service conftests point DATABASE_URL at by
# default (services/admin/conftest.py → regengine_admin,
# services/scheduler/conftest.py → regengine). The gates must never target
# them under any configuration — they upgrade-head and seed their target.
_DEV_STACK_DB_NAMES = frozenset({"regengine", "regengine_admin"})
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _require_db() -> bool:
    return os.getenv("REGENGINE_REQUIRE_DB", "").strip().lower() in {"1", "true", "yes"}


def _is_ci() -> bool:
    """GitHub Actions exports ``CI=true``; service-container reuse is scoped to it."""
    return os.getenv("CI", "").strip().lower() in {"1", "true", "yes"}


def _is_dev_stack_url(url: str) -> bool:
    try:
        parsed = make_url(_normalize_psycopg(url))
    except Exception:
        return False
    host = (parsed.host or "").lower()
    return host in _LOCAL_HOSTS and (parsed.database or "") in _DEV_STACK_DB_NAMES


def _probe_reachable(url: str) -> bool:
    """True if the URL answers ``SELECT 1`` (placeholder defaults often don't)."""
    engine = create_engine(url, future=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        engine.dispose()


def _normalize_psycopg(url: str) -> str:
    """Force the psycopg (v3) driver, which the test deps pin."""
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def skip_or_fail_db(reason: str) -> None:
    if _require_db():
        pytest.fail(f"{reason} (REGENGINE_REQUIRE_DB=1 — RLS gate must run a real Postgres, not skip)")
    pytest.skip(reason)


def _usable_database_url() -> str | None:
    """Return the Postgres URL the gates may reuse, or None (→ testcontainers/skip).

    Reuse must be deliberate, never inherited (see module docstring):

      * ``REGENGINE_MIGRATION_TEST_DB`` — explicit local opt-in; must be a
        reachable, non-dev-stack ``postgresql://`` URL, anything else FAILS
        loudly (you asked for reuse, so misconfiguration must not silently
        degrade to testcontainers).
      * ``DATABASE_URL`` — honored only under ``CI=true``, and never for a
        dev-stack URL. Outside CI it is almost always a leaked conftest
        default or a direnv export, so it is ignored with a RuntimeWarning
        (UserWarning is filtered out by pyproject's filterwarnings).

    Only postgres URLs are considered (the sqlite default used elsewhere can't
    host RLS). The connection is probed so a placeholder default that isn't
    actually running falls through to testcontainers/skip rather than raising
    a raw connection error from inside the fixture.
    """
    explicit = os.getenv("REGENGINE_MIGRATION_TEST_DB", "").strip()
    if explicit:
        if not explicit.startswith(_PG_PREFIXES):
            pytest.fail(f"REGENGINE_MIGRATION_TEST_DB must be a postgresql:// URL, got: {explicit!r}")
        if _is_dev_stack_url(explicit):
            pytest.fail(
                f"REGENGINE_MIGRATION_TEST_DB points at the local dev stack ({explicit!r}) — "
                "the migration gates run `alembic upgrade head` + seeds into their target; "
                "use a disposable scratch database"
            )
        normalized = _normalize_psycopg(explicit)
        if not _probe_reachable(normalized):
            pytest.fail(f"REGENGINE_MIGRATION_TEST_DB is set but not reachable: {explicit!r}")
        return normalized

    url = os.getenv("DATABASE_URL")
    if not url or not url.startswith(_PG_PREFIXES):
        return None
    if _is_dev_stack_url(url):
        warnings.warn(
            f"refusing to run migration gates against DATABASE_URL={url!r}: it matches the local "
            "dev stack defaults set by services/*/conftest.py, and these gates run "
            "`alembic upgrade head` + seeds into their target; falling back to testcontainers/skip "
            "(set REGENGINE_MIGRATION_TEST_DB to a disposable scratch database to opt in)",
            RuntimeWarning,
            stacklevel=2,
        )
        return None
    if not _is_ci():
        warnings.warn(
            f"ignoring DATABASE_URL={url!r} for the migration gates: outside CI these suites only "
            "reuse a database explicitly designated via REGENGINE_MIGRATION_TEST_DB; falling back "
            "to testcontainers/skip",
            RuntimeWarning,
            stacklevel=2,
        )
        return None
    normalized = _normalize_psycopg(url)
    if not _probe_reachable(normalized):
        return None
    return normalized


def _plain_url(driver_url: str) -> str:
    """Strip the SQLAlchemy driver suffix so alembic/psql get a libpq URL."""
    return driver_url.replace("postgresql+psycopg://", "postgresql://", 1).replace(
        "postgresql+psycopg2://", "postgresql://", 1
    )


@contextmanager
def rls_postgres_or_skip() -> Iterator[tuple[str, Engine]]:
    """Yield ``(plain_database_url, engine)`` for a real Postgres, or skip/fail.

    Reuses ``DATABASE_URL`` when it points at a reachable Postgres (CI service
    container); otherwise spins up a disposable testcontainers Postgres. When no
    Postgres can be obtained, the behaviour depends on ``REGENGINE_REQUIRE_DB``
    (see module docstring). ``plain_database_url`` carries no driver suffix so it
    can be handed to alembic / libpq directly.
    """
    reachable_url = _usable_database_url()
    if reachable_url:
        engine = create_engine(reachable_url, future=True)
        try:
            yield _plain_url(reachable_url), engine
        finally:
            engine.dispose()
        return

    # No reusable URL (unset, refused by the guard, or unreachable) — fall
    # back to testcontainers (local dev).
    try:
        import testcontainers.postgres  # noqa: F401
        from testcontainers.postgres import PostgresContainer
    except ImportError as exc:  # pragma: no cover - depends on local env
        skip_or_fail_db(f"no reusable migration-test DATABASE_URL and testcontainers unavailable: {exc}")
        return

    try:
        container = PostgresContainer("postgres:16", driver="psycopg")
        container.start()
    except Exception as exc:  # Docker missing, image pull fails, etc.
        skip_or_fail_db(f"no reusable migration-test DATABASE_URL and PostgresContainer unavailable: {exc}")
        return

    try:
        url = _normalize_psycopg(container.get_connection_url())
        engine = create_engine(url, future=True)
        try:
            yield _plain_url(url), engine
        finally:
            engine.dispose()
    finally:
        container.stop()


@contextmanager
def rls_engine_or_skip() -> Iterator[Engine]:
    """Yield just the Engine — convenience wrapper over rls_postgres_or_skip."""
    with rls_postgres_or_skip() as (_, engine):
        yield engine
