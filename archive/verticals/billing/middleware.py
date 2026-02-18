"""
Billing Service — Security & Observability Middleware

Three middleware layers applied to every request:

1. **SecurityHeadersMiddleware** — browser hardening headers
2. **RequestIdMiddleware** — UUID per request for log correlation
3. **RateLimitMiddleware** — token-bucket rate limiting
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from typing import Callable, Dict, Tuple

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = structlog.get_logger(__name__)


# ── Security Headers ──────────────────────────────────────────────

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cache-Control": "no-store",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach hardening headers to every response."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value
        return response


# ── Request-ID Tracing ────────────────────────────────────────────

class RequestIdMiddleware(BaseHTTPMiddleware):
    """Generate a unique request ID and attach it to the request + response.

    The ID is available at ``request.state.request_id`` and is echoed
    back to the client via the ``X-Request-ID`` response header.
    Also binds to the structlog context for automatic inclusion in
    every log line during the request lifecycle.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


# ── Rate Limiting ─────────────────────────────────────────────────

# Routes with stricter limits (requests per minute)
_SENSITIVE_PREFIXES = {
    "/v1/billing/credits/redeem": 20,
    "/v1/billing/invoices": 60,        # POST creates
    "/v1/billing/subscriptions/create": 20,
    "/v1/billing/checkout": 30,
}

# Default limit for all other routes
_DEFAULT_RPM = 120


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory token-bucket rate limiter.

    Keyed by client IP. Separate buckets for sensitive endpoints.
    Not suitable for multi-process deployments — use Redis-backed
    rate limiter for production clusters.
    """

    def __init__(self, app):
        super().__init__(app)
        # ip → (tokens_remaining, last_refill_time)
        self._buckets: Dict[str, Dict[str, Tuple[float, float]]] = defaultdict(dict)

    def _get_limit(self, path: str) -> int:
        for prefix, limit in _SENSITIVE_PREFIXES.items():
            if path.startswith(prefix):
                return limit
        return _DEFAULT_RPM

    def _get_bucket_key(self, path: str) -> str:
        for prefix in _SENSITIVE_PREFIXES:
            if path.startswith(prefix):
                return prefix
        return "__default__"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip rate limiting for health checks and docs
        if request.url.path in ("/health", "/docs", "/openapi.json", "/"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        bucket_key = self._get_bucket_key(request.url.path)
        limit = self._get_limit(request.url.path)

        now = time.time()
        ip_buckets = self._buckets[client_ip]

        if bucket_key not in ip_buckets:
            ip_buckets[bucket_key] = (float(limit), now)

        tokens, last_refill = ip_buckets[bucket_key]

        # Refill tokens based on elapsed time
        elapsed = now - last_refill
        tokens = min(float(limit), tokens + elapsed * (limit / 60.0))

        if tokens < 1.0:
            logger.warning(
                "rate_limit_exceeded",
                client_ip=client_ip,
                path=request.url.path,
                bucket=bucket_key,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Please slow down.",
                    "retry_after_seconds": int(60 / limit),
                },
                headers={"Retry-After": str(int(60 / limit))},
            )

        tokens -= 1.0
        ip_buckets[bucket_key] = (tokens, now)

        return await call_next(request)
