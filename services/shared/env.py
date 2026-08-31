"""Centralized environment detection for all RegEngine services."""

import logging
import os

_logger = logging.getLogger("regengine.env")

# #2512: single source of truth for the cloud-deployment marker set.
# This tuple is the central security gate — when ANY of these are present
# and REGENGINE_ENV is not explicitly set, validate_cloud_environment()
# forces production, which is the only thing preventing dev auth fallbacks
# (ephemeral JWT keys, in-memory sessions, permissive Supabase branch) from
# running in a deployed environment. Keep it broader than just Railway/Vercel
# so non-Railway hosts (Render, Fly, Kubernetes, self-hosted Docker) do not
# silently resolve to development. services/admin/app/database.py and
# services/admin/app/invite_routes.py import this so the marker set cannot
# drift again.
CLOUD_ENV_VARS = (
    "RAILWAY_ENVIRONMENT",
    "RAILWAY_ENVIRONMENT_NAME",
    "RAILWAY_ENVIRONMENT_ID",
    "RAILWAY_PROJECT_NAME",
    "RAILWAY_PROJECT_ID",
    "RAILWAY_SERVICE_NAME",
    "RAILWAY_SERVICE_ID",
    "VERCEL_ENV",
    "VERCEL_URL",
    "RENDER",
    "FLY_APP_NAME",
    "KUBERNETES_SERVICE_HOST",
)

# Backwards-compatible private alias (kept for any internal references).
_CLOUD_ENV_VARS = CLOUD_ENV_VARS

_PRODUCTION_ENVIRONMENT_NAMES = {"production"}
_LOCAL_AUTH_ENVIRONMENT_NAMES = {"development", "dev", "local", "test", "testing"}
_TRUE_VALUES = {"1", "true", "yes", "on"}


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
    return os.getenv("REGENGINE_ENV", "").lower() or os.getenv("ENV", "").lower() or "development"


def is_cloud_deployment() -> bool:
    """Return whether a supported deployment-platform marker is present."""

    return any(os.getenv(var) for var in CLOUD_ENV_VARS)


def requires_strict_auth_runtime() -> bool:
    """Return whether authentication must use shared, durable backends.

    Production is always strict.  Deployed staging/preview environments are
    strict too, even though they deliberately retain their non-production
    environment name.  ``REGENGINE_AUTH_STRICT=1`` makes the same posture
    explicit for self-hosted staging where no recognized cloud marker exists.

    There is intentionally no environment-variable escape hatch that can
    disable strict behavior in production or a deployed non-local runtime.
    """

    if is_production():
        return True
    if os.getenv("REGENGINE_AUTH_STRICT", "").strip().lower() in _TRUE_VALUES:
        return True
    return is_cloud_deployment() and get_environment() not in _LOCAL_AUTH_ENVIRONMENT_NAMES


def validate_cloud_environment() -> None:
    """Ensure REGENGINE_ENV is set correctly when running in cloud.

    If cloud platform env vars (RAILWAY_ENVIRONMENT, VERCEL_ENV, etc.)
    are detected but REGENGINE_ENV is not explicitly set, force it to
    'production' to prevent auth bypass tokens from being active.
    """
    is_cloud = is_cloud_deployment()
    if not is_cloud:
        return

    regengine_env = os.getenv("REGENGINE_ENV", "").lower()
    if regengine_env == "production":
        return

    railway_environment_name = (
        (os.getenv("RAILWAY_ENVIRONMENT_NAME") or os.getenv("RAILWAY_ENVIRONMENT") or "").strip().lower()
    )
    if railway_environment_name in _PRODUCTION_ENVIRONMENT_NAMES:
        _logger.critical(
            "Railway production environment detected with REGENGINE_ENV=%s. Forcing REGENGINE_ENV=production.",
            regengine_env or "<unset>",
        )
        os.environ["REGENGINE_ENV"] = "production"
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
