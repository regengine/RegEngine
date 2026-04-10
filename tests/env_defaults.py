"""Centralized test environment defaults.

Single source of truth for all test-specific environment variables.
Import this module early (before any service imports) to ensure
consistent defaults across all test suites.

Usage in conftest.py:
    from tests.env_defaults import apply_defaults
    apply_defaults()
"""
import os

# Database URLs (local Docker by default; CI overrides via env)
_DEFAULTS = {
    "REGENGINE_ENV": "test",
    "ENVIRONMENT": "test",
    "LOG_LEVEL": "WARNING",
    # Database
    "DATABASE_URL": "postgresql://regengine:regengine@localhost:5432/regengine_admin",
    "ADMIN_DATABASE_URL": "postgresql+psycopg://regengine:regengine@localhost:5432/regengine_admin",
    # Auth
    "AUTH_SECRET_KEY": "dev_secret_key_change_me",
    "ADMIN_MASTER_KEY": "admin-master-key-dev",
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
