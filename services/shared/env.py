"""Centralized environment detection for all RegEngine services."""
import os
import logging

_logger = logging.getLogger("regengine.env")


def is_production() -> bool:
    """Check if running in production.

    Checks REGENGINE_ENV first (set by docker-compose and Railway),
    then falls back to ENV, then DATABASE_URL heuristic.
    """
    regengine_env = os.getenv("REGENGINE_ENV", "").lower()
    if regengine_env:
        return regengine_env == "production"
    env = os.getenv("ENV", "").lower()
    if env:
        return env == "production"
    # Last resort: detect Supabase pooler in DATABASE_URL
    return "pooler.supabase.com" in os.getenv("DATABASE_URL", "")


def get_environment() -> str:
    """Get the current environment name."""
    return (
        os.getenv("REGENGINE_ENV", "").lower()
        or os.getenv("ENV", "").lower()
        or "development"
    )


def validate_cloud_environment() -> None:
    """Ensure REGENGINE_ENV is set correctly when running in cloud.

    If cloud platform env vars (RAILWAY_ENVIRONMENT, VERCEL_ENV, etc.)
    are detected but REGENGINE_ENV is not explicitly set, force it to
    'production' to prevent auth bypass tokens from being active.
    """
    cloud_indicators = [
        "RAILWAY_ENVIRONMENT",
        "RAILWAY_SERVICE_NAME",
        "VERCEL_ENV",
        "VERCEL_URL",
    ]
    is_cloud = any(os.getenv(var) for var in cloud_indicators)
    if not is_cloud:
        return

    regengine_env = os.getenv("REGENGINE_ENV", "").lower()
    if regengine_env == "production":
        return

    if not regengine_env:
        _logger.critical(
            "Cloud deployment detected but REGENGINE_ENV is not set. "
            "Forcing REGENGINE_ENV=production to prevent auth bypass. "
            "Set REGENGINE_ENV explicitly in your deployment config."
        )
        os.environ["REGENGINE_ENV"] = "production"
    elif regengine_env in ("development", "test"):
        _logger.critical(
            "Cloud deployment detected with REGENGINE_ENV=%s. "
            "This enables auth test bypass tokens. "
            "Forcing REGENGINE_ENV=production.",
            regengine_env,
        )
        os.environ["REGENGINE_ENV"] = "production"


# Auto-validate on import — all services import shared.env early
validate_cloud_environment()
