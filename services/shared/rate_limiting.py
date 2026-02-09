"""
Shared rate limiting middleware for vertical services.

Uses slowapi for per-IP rate limiting with configurable limits.
Adds X-RateLimit-* headers to responses.
"""

import os
from functools import lru_cache

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request
from starlette.responses import JSONResponse


@lru_cache()
def get_default_limit() -> str:
    """Get the default rate limit from environment or use default."""
    return os.getenv("RATE_LIMIT_DEFAULT", "100/minute")


def create_limiter() -> Limiter:
    """Create a configured rate limiter instance."""
    return Limiter(
        key_func=get_remote_address,
        default_limits=[get_default_limit()],
        storage_uri=os.getenv("RATE_LIMIT_STORAGE_URI", "memory://"),
    )


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Custom handler for rate limit exceeded errors."""
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "detail": f"Rate limit exceeded: {exc.detail}",
            "retry_after": str(getattr(exc, "retry_after", 60)),
        },
        headers={
            "Retry-After": str(getattr(exc, "retry_after", 60)),
            "X-RateLimit-Limit": str(get_default_limit()),
        },
    )


def setup_rate_limiting(app, limiter: Limiter = None):
    """
    Configure rate limiting on a FastAPI app.

    Usage:
        from shared.rate_limiting import create_limiter, setup_rate_limiting

        limiter = create_limiter()
        setup_rate_limiting(app, limiter)
    """
    if limiter is None:
        limiter = create_limiter()

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    return limiter
