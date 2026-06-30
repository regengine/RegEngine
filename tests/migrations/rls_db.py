"""Shared Postgres acquisition for the behavioral RLS test gates (#2530).

The RLS behavioral tests (``test_rls_hardening.py``, ``test_rls_coverage.py``)
need a real PostgreSQL. Historically they only knew how to spin one up via
``testcontainers`` (Docker-in-Docker), and skipped silently whenever Docker
was unavailable — which is every blocking CI job, so the RLS gate was
decorative (#2530).

This helper makes acquisition order explicit and CI-gateable:

  1. If ``DATABASE_URL`` is set, reuse it. CI provisions a ``postgres:16``
     service container and exports ``DATABASE_URL``; reusing it means the RLS
     gate runs without Docker-in-Docker.
  2. Otherwise fall back to a disposable ``testcontainers`` Postgres (local
     dev convenience).
  3. If neither is available:
       * ``REGENGINE_REQUIRE_DB=1`` (or ``true``) → ``pytest.fail`` — a CI job
         that sets this can never turn the RLS gate green by skipping.
       * unset → ``pytest.skip`` — local runs without Docker stay friendly,
         where the static guards (check_rls_fallback.py) remain the safety net.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


def _require_db() -> bool:
    return os.getenv("REGENGINE_REQUIRE_DB", "").strip().lower() in {"1", "true", "yes"}


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
    """Return DATABASE_URL if it points at a reachable Postgres, else None.

    Only postgres URLs are considered (the sqlite default used elsewhere can't
    host RLS). The connection is probed so a placeholder localhost default that
    isn't actually running falls through to testcontainers/skip rather than
    raising a raw connection error from inside the fixture.
    """
    url = os.getenv("DATABASE_URL")
    if not url or not url.startswith(("postgresql://", "postgresql+psycopg://", "postgresql+psycopg2://")):
        return None
    normalized = _normalize_psycopg(url)
    engine = create_engine(normalized, future=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return normalized
    except Exception:
        return None
    finally:
        engine.dispose()


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

    # DATABASE_URL absent or unreachable — fall back to testcontainers (local dev).
    try:
        import testcontainers.postgres  # noqa: F401
        from testcontainers.postgres import PostgresContainer
    except ImportError as exc:  # pragma: no cover - depends on local env
        skip_or_fail_db(f"DATABASE_URL unset and testcontainers unavailable: {exc}")
        return

    try:
        container = PostgresContainer("postgres:16", driver="psycopg")
        container.start()
    except Exception as exc:  # Docker missing, image pull fails, etc.
        skip_or_fail_db(f"DATABASE_URL unset and PostgresContainer unavailable: {exc}")
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
