"""
API-01 / API-02: Request body size limiting and global request timeout.

Middleware that protects services from oversized payloads and runaway
requests.  Wire these into each service's ``main.py`` via
``app.add_middleware(...)``.

Usage::

    from shared.request_safety import RequestSizeLimitMiddleware, RequestTimeoutMiddleware

    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=10 * 1024 * 1024)
    app.add_middleware(RequestTimeoutMiddleware, timeout_seconds=120)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

_EXEMPT_PATHS = {"/health", "/ready", "/readiness", "/metrics", "/"}


# ---------------------------------------------------------------------------
# API-01: Request body size limiter
# ---------------------------------------------------------------------------

class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose Content-Length exceeds *max_bytes*.

    For chunked/streaming uploads where Content-Length is absent the
    middleware allows the request through (Starlette's own body reader
    will enforce memory limits downstream).
    """

    def __init__(self, app, max_bytes: int = 10 * 1024 * 1024):
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                length = int(content_length)
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"error": "invalid_content_length", "detail": "Content-Length header is not a valid integer."},
                )
            if length > self.max_bytes:
                mb = self.max_bytes / (1024 * 1024)
                logger.warning(
                    "request_too_large",
                    content_length=length,
                    max_bytes=self.max_bytes,
                    path=request.url.path,
                )
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": "payload_too_large",
                        "detail": f"Request body exceeds the {mb:.0f} MB limit.",
                    },
                )
        return await call_next(request)


# ---------------------------------------------------------------------------
# API-02: Global request timeout
# ---------------------------------------------------------------------------

class RequestTimeoutMiddleware(BaseHTTPMiddleware):
    """Cancel request processing after *timeout_seconds*.

    Returns 504 Gateway Timeout if the handler doesn't complete in time.
    Health/metrics endpoints are exempt.
    """

    def __init__(self, app, timeout_seconds: float = 120.0):
        super().__init__(app)
        self.timeout_seconds = timeout_seconds

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        try:
            return await asyncio.wait_for(
                call_next(request),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.error(
                "request_timeout",
                path=request.url.path,
                method=request.method,
                timeout_seconds=self.timeout_seconds,
            )
            return JSONResponse(
                status_code=504,
                content={
                    "error": "request_timeout",
                    "detail": f"Request timed out after {self.timeout_seconds:.0f} seconds.",
                },
            )
