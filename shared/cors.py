"""Shared CORS configuration for all RegEngine services.

This module provides centralized CORS configuration to prevent security issues
like wildcard origins with credentials enabled.
"""
import os
from typing import List


def get_allowed_origins() -> List[str]:
    """Get CORS allowed origins from environment or sensible defaults.
    
    Returns:
        List of allowed origin URLs. Never includes wildcards in production.
    
    Example:
        # In .env:
        # CORS_ALLOWED_ORIGINS=http://localhost:3000,https://app.regengine.co
    """
    origins_str = os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://localhost:8000"  # Dev defaults
    )
    origins = [origin.strip() for origin in origins_str.split(",") if origin.strip()]
    
    # Never allow wildcard in production
    if os.getenv("REGENGINE_ENV") == "production" and "*" in origins:
        raise ValueError("CORS wildcard (*) not allowed in production")
    
    return origins


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
