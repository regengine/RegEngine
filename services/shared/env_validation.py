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
    """Warn loudly if required environment variables are missing.

    Logs at CRITICAL level but does not exit — Railway and other PaaS
    platforms may inject env vars after the module is first imported.
    """
    missing = [v for v in var_names if not os.getenv(v)]
    if missing:
        logger.critical(
            "Missing required environment variables: %s — service may fail at runtime",
            ", ".join(missing),
        )


def warn_env(*var_names: str) -> None:
    """Log a warning for each unset optional environment variable."""
    for v in var_names:
        if not os.getenv(v):
            logger.warning("Optional env var %s not set — using default", v)


def assert_legacy_entrypoint_not_in_production(service_name: str) -> None:
    """Fail loudly if a per-service legacy main.py is launched in production.

    Production runs ``server.main:app`` (the consolidated monolith) per the
    repo-root ``Dockerfile`` — see ``docs/architecture/CONSOLIDATION.md``.
    The per-service ``services/<svc>/main.py`` files are retained for local
    debugging and to keep each subtree importable in isolation; they are
    NOT the production entrypoint.

    Call this at the top of each legacy main.py so a stray Railway deploy
    pointed at the wrong start command (or a future docker-compose copy
    that drifted into prod) fails fast instead of silently serving from
    a partial router surface.

    The guard reads ``RAILWAY_ENVIRONMENT_NAME`` / ``RAILWAY_ENVIRONMENT`` /
    ``REGENGINE_ENV`` directly to avoid importing ``shared.env`` (which
    pulls heavier dependencies that some legacy mains may not even have
    available at this point in startup). Opt-out via
    ``ALLOW_LEGACY_ENTRYPOINT_IN_PROD=1`` for the explicit "I really do
    want to run this in prod, I'm doing surgery" case.
    """
    if os.getenv("ALLOW_LEGACY_ENTRYPOINT_IN_PROD", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return

    is_prod = (
        os.getenv("RAILWAY_ENVIRONMENT_NAME", "").strip().lower() == "production"
        or os.getenv("RAILWAY_ENVIRONMENT", "").strip().lower() == "production"
        or os.getenv("REGENGINE_ENV", "").strip().lower() == "production"
    )
    if not is_prod:
        return

    message = (
        f"Refusing to start legacy entrypoint services/{service_name}/main.py "
        "in production. The consolidated monolith server.main:app is the "
        "production entrypoint (see docs/architecture/CONSOLIDATION.md). "
        "If this is intentional surgery, set ALLOW_LEGACY_ENTRYPOINT_IN_PROD=1."
    )
    logger.critical(message)
    raise RuntimeError(message)
