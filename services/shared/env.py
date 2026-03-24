"""Centralized environment detection for all RegEngine services."""
import os


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
