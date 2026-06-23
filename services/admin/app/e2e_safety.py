"""Safety locks for local-only E2E test affordances."""

from __future__ import annotations

import os

from shared.env import is_production

REGENGINE_E2E_MODE_ENV = "REGENGINE_E2E_MODE"
_E2E_TRUE_VALUES = {"1", "true", "yes", "on"}


class CriticalSecurityError(RuntimeError):
    """Raised when test-only behavior is enabled in a production environment."""


def _raw_e2e_mode_enabled() -> bool:
    return os.getenv(REGENGINE_E2E_MODE_ENV, "").strip().lower() in _E2E_TRUE_VALUES


def assert_e2e_mode_allowed() -> None:
    """Fail closed if E2E mode is enabled in production."""
    if _raw_e2e_mode_enabled() and is_production():
        raise CriticalSecurityError("E2E mode is strictly forbidden in production")


def e2e_mode_enabled() -> bool:
    """Return whether local E2E mode is enabled after enforcing production lockout."""
    assert_e2e_mode_allowed()
    return _raw_e2e_mode_enabled()
