"""Shared CORS configuration for all RegEngine services.

This module provides centralized CORS configuration to prevent security issues
like wildcard origins with credentials enabled.
"""

import os
from typing import List
from urllib.parse import parse_qs, urlsplit

DEFAULT_ALLOWED_HEADERS = [
    "Authorization",
    "Content-Type",
    "Idempotency-Key",
    "X-API-Version",
    "X-Correlation-ID",
    "X-Metrics-Key",
    "X-RegEngine-API-Key",
    "X-RegEngine-Partner-Key",
    "X-RegEngine-Tenant-ID",
    "X-Request-ID",
    "X-Requested-With",
    "X-Tenant-ID",
]

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
)


def _split_csv(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _unique(values: List[str]) -> List[str]:
    seen = set()
    unique_values = []
    for value in values:
        if value not in seen:
            seen.add(value)
            unique_values.append(value)
    return unique_values


def _current_environment() -> str:
    return os.getenv("REGENGINE_ENV", "").strip().lower() or os.getenv("ENV", "").strip().lower() or "development"


def _hostname_is_pooler(host: str) -> bool:
    host = host.strip().lower()
    hostname, separator, port = host.rpartition(":")
    if separator and (not port or port.isdecimal()):
        host = hostname
    return host == "pooler.supabase.com" or host.endswith(".pooler.supabase.com")


def _is_supabase_pooler_database() -> bool:
    """Detect a Supabase pooler DATABASE_URL by exact hostname / subdomain.

    Parses the URL and compares the hostname instead of doing a substring
    check, so a value like ``postgres://u:p@host/db?x=pooler.supabase.com``
    cannot spoof the pooler host.

    libpq honours a ``?host=`` query parameter, which overrides the URI
    host (and may be a comma-separated list). SQLAlchemy also accepts
    ``host:port`` query values, with an empty port selecting the default.
    A pooler reached that way is a
    real production connection, so we fail closed and treat it as the pooler
    too, rather than trusting only the URI authority.
    """
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        return False
    try:
        parts = urlsplit(db_url)
    except ValueError:
        return False
    if _hostname_is_pooler(parts.hostname or ""):
        return True
    try:
        query = parse_qs(parts.query)
    except ValueError:
        return False
    for raw_value in query.get("host", []):
        for candidate in raw_value.split(","):
            if _hostname_is_pooler(candidate):
                return True
    return False


def _is_restricted_cors_environment() -> bool:
    """Return true outside explicit local/test environments or in cloud."""
    env = _current_environment()
    if env not in {"development", "test"}:
        return True
    if any(os.getenv(var) for var in CLOUD_ENV_VARS):
        return True
    return _is_supabase_pooler_database()


def _validate_exact_preview_origins(origins: List[str]) -> None:
    for origin in origins:
        parsed = urlsplit(origin)
        if (
            "*" in origin
            or parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("CORS_ALLOWED_PREVIEW_ORIGINS must contain exact http(s) origins")


def get_allowed_origins() -> List[str]:
    """Get CORS allowed origins from environment or sensible defaults.

    Returns:
        List of allowed origin URLs. Never includes wildcards in production/cloud.

    Example:
        # In .env:
        # CORS_ALLOWED_ORIGINS=http://localhost:3000,https://app.regengine.co
    """
    # Production/cloud-like environments only allow regengine.co origins by default.
    if _is_restricted_cors_environment():
        default_origins = "https://regengine.co,https://www.regengine.co,https://app.regengine.co"
    else:
        default_origins = (
            "http://localhost:3000,http://localhost:8000,http://localhost:8002,"
            "http://localhost:8400,http://127.0.0.1:3000,"
            "https://regengine.co,https://www.regengine.co,https://app.regengine.co"
        )

    origins_str = os.getenv("CORS_ALLOWED_ORIGINS", default_origins)
    origins = _split_csv(origins_str)

    preview_origins = _split_csv(os.getenv("CORS_ALLOWED_PREVIEW_ORIGINS", ""))
    _validate_exact_preview_origins(preview_origins)
    origins = _unique(origins + preview_origins)

    # Never allow wildcard in production or cloud-like environments.
    if _is_restricted_cors_environment() and "*" in origins:
        raise ValueError("CORS wildcard (*) not allowed in production or cloud environments")

    return origins


def get_allowed_headers() -> List[str]:
    """Get explicit CORS allowed headers.

    Wildcard headers are not compatible with credentialed browser requests and
    are rejected in production/cloud environments.
    """
    headers_str = os.getenv("CORS_ALLOWED_HEADERS", ",".join(DEFAULT_ALLOWED_HEADERS))
    headers = _split_csv(headers_str)

    if _is_restricted_cors_environment() and "*" in headers:
        raise ValueError("CORS wildcard (*) headers not allowed in production or cloud environments")

    return headers


def should_allow_credentials() -> bool:
    """Check if credentials should be allowed.

    Only allows credentials if:
    1. Not using wildcard origins (CSRF protection)
    2. Explicitly enabled via CORS_ALLOW_CREDENTIALS env var

    Returns:
        True if safe to allow credentials, False otherwise.
    """
    origins = get_allowed_origins()

    # Never allow credentials with wildcard origins (CSRF risk)
    if "*" in origins:
        return False

    # Require explicit opt-in for credentials
    # Default to false - only enable if you need session cookies/auth headers
    return os.getenv("CORS_ALLOW_CREDENTIALS", "false").lower() == "true"
