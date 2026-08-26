"""Centralized test environment defaults.

Single source of truth for all test-specific environment variables.
Import this module early (before any service imports) to ensure
consistent defaults across all test suites.

Usage in conftest.py:
    from tests.env_defaults import apply_defaults
    apply_defaults()
"""

import os

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
    # Auth
    "AUTH_SECRET_KEY": "dev_secret_key_change_me",
    "AUTH_TEST_BYPASS_TOKEN": "test-bypass-ci-only-not-for-production",
    "INTERNAL_SERVICE_SECRET": "trusted-internal-v1",
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
