"""Regression tests for the ``rls_db`` DATABASE_URL reuse guard.

On 2026-07-25 a local ``pytest tests/migrations/test_seeded_mid_chain_upgrade.py``
run silently ran ``alembic upgrade head`` + the mid-chain seed into the
developer's live dev database: ``services/admin/conftest.py`` and
``services/scheduler/conftest.py`` ``setdefault`` ``DATABASE_URL`` to the dev
stack, and ``rls_db._usable_database_url`` reused any reachable Postgres URL
(with ``REGENGINE_SEED_CLIENT_ROLES=1`` it also created cluster-wide
anon/authenticated roles).

These tests pin the guard that prevents that:

  * the dev-stack URLs (``regengine``/``regengine_admin`` on a local host) are
    refused unconditionally — without even probing them;
  * outside CI, ``DATABASE_URL`` is never reused; only
    ``REGENGINE_MIGRATION_TEST_DB`` designates a reusable database;
  * in CI (``CI=true``), non-dev-stack ``DATABASE_URL`` reuse keeps working
    (the service-container path);
  * a misconfigured ``REGENGINE_MIGRATION_TEST_DB`` FAILS instead of silently
    degrading to testcontainers.

No test here touches a real database — the reachability probe is stubbed, and
for refused URLs it must never be called at all.
"""

from __future__ import annotations

import pytest

from tests.migrations import rls_db

ADMIN_CONFTEST_DEFAULT = "postgresql://regengine:regengine@localhost:5432/regengine_admin"  # pragma: allowlist secret
SCHEDULER_CONFTEST_DEFAULT = "postgresql://regengine:regengine@localhost:5432/regengine"  # pragma: allowlist secret
SCRATCH_URL = "postgresql://postgres:postgres@localhost:5432/rls_scratch"  # pragma: allowlist secret
SCRATCH_URL_PSYCOPG = "postgresql+psycopg://postgres:postgres@localhost:5432/rls_scratch"  # pragma: allowlist secret


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip ambient env and forbid probing — a probe means the guard leaked."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ADMIN_DATABASE_URL", raising=False)
    monkeypatch.delenv("REGENGINE_MIGRATION_TEST_DB", raising=False)
    monkeypatch.delenv("CI", raising=False)

    def _forbid_probe(url: str) -> bool:
        raise AssertionError(f"guard leaked: reachability probe attempted against {url!r}")

    monkeypatch.setattr(rls_db, "_probe_reachable", _forbid_probe)


@pytest.mark.parametrize("dev_url", [ADMIN_CONFTEST_DEFAULT, SCHEDULER_CONFTEST_DEFAULT])
def test_conftest_dev_defaults_refused_without_probe(monkeypatch: pytest.MonkeyPatch, dev_url: str) -> None:
    """The exact URLs the service conftests setdefault must never be reused."""
    monkeypatch.setenv("DATABASE_URL", dev_url)
    with pytest.warns(RuntimeWarning, match="dev stack"):
        assert rls_db._usable_database_url() is None


def test_dev_default_refused_even_in_ci(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("DATABASE_URL", SCHEDULER_CONFTEST_DEFAULT)
    with pytest.warns(RuntimeWarning, match="dev stack"):
        assert rls_db._usable_database_url() is None


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1"])
def test_dev_stack_names_refused_on_any_local_host_port_or_user(monkeypatch: pytest.MonkeyPatch, host: str) -> None:
    """Matching is by database name + local host, not the literal conftest URL."""
    url = f"postgresql://postgres:postgres@{host}:5433/regengine"  # pragma: allowlist secret
    monkeypatch.setenv("DATABASE_URL", url)
    with pytest.warns(RuntimeWarning, match="dev stack"):
        assert rls_db._usable_database_url() is None


def test_local_database_url_requires_explicit_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    """Outside CI, even a non-dev-stack DATABASE_URL is not reused."""
    monkeypatch.setenv("DATABASE_URL", SCRATCH_URL)
    with pytest.warns(RuntimeWarning, match="REGENGINE_MIGRATION_TEST_DB"):
        assert rls_db._usable_database_url() is None


def test_ci_reuses_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CI service-container path (#2530) must keep working unchanged."""
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("DATABASE_URL", SCRATCH_URL)
    monkeypatch.setattr(rls_db, "_probe_reachable", lambda url: True)
    assert rls_db._usable_database_url() == SCRATCH_URL_PSYCOPG


def test_ci_unreachable_database_url_falls_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("DATABASE_URL", SCRATCH_URL)
    monkeypatch.setattr(rls_db, "_probe_reachable", lambda url: False)
    assert rls_db._usable_database_url() is None


def test_explicit_opt_in_wins_over_leaked_conftest_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """REGENGINE_MIGRATION_TEST_DB works locally even with a conftest default present."""
    monkeypatch.setenv("DATABASE_URL", ADMIN_CONFTEST_DEFAULT)
    monkeypatch.setenv("REGENGINE_MIGRATION_TEST_DB", SCRATCH_URL)
    monkeypatch.setattr(rls_db, "_probe_reachable", lambda url: True)
    assert rls_db._usable_database_url() == SCRATCH_URL_PSYCOPG


def test_explicit_opt_in_refuses_dev_stack_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGENGINE_MIGRATION_TEST_DB", ADMIN_CONFTEST_DEFAULT)
    with pytest.raises(pytest.fail.Exception, match="dev stack"):
        rls_db._usable_database_url()


def test_explicit_opt_in_unreachable_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGENGINE_MIGRATION_TEST_DB", SCRATCH_URL)
    monkeypatch.setattr(rls_db, "_probe_reachable", lambda url: False)
    with pytest.raises(pytest.fail.Exception, match="not reachable"):
        rls_db._usable_database_url()


def test_explicit_opt_in_rejects_non_postgres_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGENGINE_MIGRATION_TEST_DB", "sqlite:///:memory:")
    with pytest.raises(pytest.fail.Exception, match="postgresql"):
        rls_db._usable_database_url()


def test_non_postgres_database_url_still_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    assert rls_db._usable_database_url() is None


# --- guarded_live_database_url: the import-safe policy the live/e2e suites use ---


def test_live_dev_default_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", ADMIN_CONFTEST_DEFAULT)
    with pytest.warns(RuntimeWarning, match="dev stack"):
        assert rls_db.guarded_live_database_url() is None


def test_live_admin_fallback_dev_default_refused_even_in_ci(monkeypatch: pytest.MonkeyPatch) -> None:
    """The legacy ADMIN_DATABASE_URL fallback must not reintroduce the dev DB."""
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("ADMIN_DATABASE_URL", ADMIN_CONFTEST_DEFAULT)
    with pytest.warns(RuntimeWarning, match="dev stack"):
        assert rls_db.guarded_live_database_url() is None


def test_live_local_url_requires_explicit_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", SCRATCH_URL)
    with pytest.warns(RuntimeWarning, match="REGENGINE_MIGRATION_TEST_DB"):
        assert rls_db.guarded_live_database_url() is None


def test_live_ci_reuses_database_url_verbatim(monkeypatch: pytest.MonkeyPatch) -> None:
    """No driver normalization — CI engines must keep their current behavior."""
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("DATABASE_URL", SCRATCH_URL)
    assert rls_db.guarded_live_database_url() == SCRATCH_URL


def test_live_ci_admin_fallback_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("ADMIN_DATABASE_URL", SCRATCH_URL)
    assert rls_db.guarded_live_database_url() == SCRATCH_URL


def test_live_sqlite_conftest_default_skips_to_admin_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """The sqlite defaults the service conftests now set are non-postgres → skipped over."""
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ADMIN_DATABASE_URL", SCRATCH_URL)
    assert rls_db.guarded_live_database_url() == SCRATCH_URL


def test_live_explicit_opt_in_works_locally(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", ADMIN_CONFTEST_DEFAULT)
    monkeypatch.setenv("REGENGINE_MIGRATION_TEST_DB", SCRATCH_URL)
    assert rls_db.guarded_live_database_url() == SCRATCH_URL


def test_live_explicit_opt_in_refuses_dev_stack_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGENGINE_MIGRATION_TEST_DB", SCHEDULER_CONFTEST_DEFAULT)
    with pytest.raises(pytest.fail.Exception, match="dev stack"):
        rls_db.guarded_live_database_url()


def test_live_nothing_set_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    assert rls_db.guarded_live_database_url() is None
