"""Centralized test environment defaults.

Single source of truth for all test-specific environment variables.
Import this module early (before any service imports) to ensure
consistent defaults across all test suites.

Usage in conftest.py:
    from tests.env_defaults import apply_defaults
    apply_defaults()
"""

import os
import secrets


def _random_secret(nbytes: int = 32) -> str:
    """Return a fresh random secret for test defaults.

    Generated per pytest process at import time so test runs never share
    a hard-coded credential that production validation would accept.
    """
    return secrets.token_urlsafe(nbytes)


_DEFAULTS = {
    "REGENGINE_ENV": "test",
    "ENVIRONMENT": "test",
    "LOG_LEVEL": "WARNING",
    # No DATABASE_URL / ADMIN_DATABASE_URL defaults on purpose: they used to
    # point at the LIVE local dev database (regengine_admin), which armed
    # every skipif-DATABASE_URL gate in the suite and let migration/e2e/live
    # tests silently migrate, seed, and delete rows in the developer's dev DB
    # (2026-07-25 incident). CI exports real service-container URLs; local
    # runs designate a disposable database via REGENGINE_MIGRATION_TEST_DB
    # (see tests/migrations/rls_db.py) or skip.
    # Lets services/admin/app/database.py build its import-time engine without
    # ADMIN_DATABASE_URL (honored only with REGENGINE_ENV=test/development).
    "ADMIN_FALLBACK_SQLITE": "sqlite:///:memory:",
    # Auth: random per-run secrets (no hard-coded values). A fixed test
    # credential that passes validation hides gaps production would catch,
    # so every pytest process mints its own.
    "AUTH_SECRET_KEY": _random_secret(48),
    "AUTH_TEST_BYPASS_TOKEN": _random_secret(),
    "INTERNAL_SERVICE_SECRET": _random_secret(),
}


def apply_defaults(overrides: dict[str, str] | None = None) -> None:
    """Set test defaults that are not already present in the environment.

    Parameters
    ----------
    overrides : dict, optional
        Extra key-value pairs to apply *after* the base defaults, allowing
        per-suite customisation (e.g. security tests can force LOG_LEVEL).
    """
    for key, value in _DEFAULTS.items():
        os.environ.setdefault(key, value)
    if overrides:
        for key, value in overrides.items():
            os.environ[key] = value
