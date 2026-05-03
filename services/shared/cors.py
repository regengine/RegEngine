"""Shared CORS configuration for all RegEngine services.

This module provides centralized CORS configuration to prevent security issues
like wildcard origins with credentials enabled.
"""
import os
from typing import List

DEFAULT_ALLOWED_HEADERS = [
    "Authorization",
    "Content-Type",
    "Idempotency-Key",
    "X-Admin-Key",
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


def get_allowed_origins() -> List[str]:
    """Get CORS allowed origins from environment or sensible defaults.
    
    Returns:
        List of allowed origin URLs. Never includes wildcards in production.
    
    Example:
        # In .env:
        # CORS_ALLOWED_ORIGINS=http://localhost:3000,https://app.regengine.co
    """
    env = os.getenv("REGENGINE_ENV", "development")

    # Production: only allow regengine.co origins by default
    if env == "production":
        default_origins = "https://regengine.co,https://www.regengine.co,https://app.regengine.co"
    else:
        default_origins = (
            "http://localhost:3000,http://localhost:8000,http://localhost:8002,"
            "http://localhost:8400,http://127.0.0.1:3000,"
            "https://regengine.co,https://www.regengine.co,https://app.regengine.co"
        )

    origins_str = os.getenv("CORS_ALLOWED_ORIGINS", default_origins)
    origins = [origin.strip() for origin in origins_str.split(",") if origin.strip()]

    # Never allow wildcard in production
    if env == "production" and "*" in origins:
        raise ValueError("CORS wildcard (*) not allowed in production")

    return origins


def get_allowed_headers() -> List[str]:
    """Get explicit CORS allowed headers.

    Wildcard headers are not compatible with credentialed browser requests and
    are rejected in production.
    """
    env = os.getenv("REGENGINE_ENV", "development")
    headers_str = os.getenv("CORS_ALLOWED_HEADERS", ",".join(DEFAULT_ALLOWED_HEADERS))
    headers = [header.strip() for header in headers_str.split(",") if header.strip()]

    if env == "production" and "*" in headers:
        raise ValueError("CORS wildcard (*) headers not allowed in production")

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
