"""Environment variable validation for RegEngine services.

Usage:
    from shared.env_validation import require_env, warn_env

    # At service startup — fail fast if critical vars are missing
    require_env("DATABASE_URL", "JWT_SECRET")

    # Warn about optional vars that may cause degraded behavior
    warn_env("SENTRY_DSN", "REDIS_URL")
"""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("regengine.config")


def require_env(*var_names: str) -> None:
    """Exit immediately if any required environment variables are missing."""
    missing = [v for v in var_names if not os.getenv(v)]
    if missing:
        logger.critical(
            "Missing required environment variables: %s — exiting",
            ", ".join(missing),
        )
        sys.exit(1)


def warn_env(*var_names: str) -> None:
    """Log a warning for each unset optional environment variable."""
    for v in var_names:
        if not os.getenv(v):
            logger.warning("Optional env var %s not set — using default", v)
