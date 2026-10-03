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
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

_EXEMPT_PATHS = {"/health", "/ready", "/readiness", "/metrics", "/"}


# ---------------------------------------------------------------------------
# API-01: Request body size limiter
# ---------------------------------------------------------------------------


class RequestSizeLimitMiddleware:
    """Reject requests whose declared or actual body exceeds *max_bytes*.

    Check each received chunk before retaining it, then replay the bounded
    body downstream. Content-Length is only an early rejection shortcut.
    """

    def __init__(self, app: ASGIApp, max_bytes: int = 10 * 1024 * 1024):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in _EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                length = int(content_length)
            except ValueError:
                response = JSONResponse(
                    status_code=400,
                    content={
                        "error": "invalid_content_length",
                        "detail": "Content-Length header is not a valid integer.",
                    },
                )
                await response(scope, receive, send)
                return
            if length > self.max_bytes:
                await self._too_large(request, length)(scope, receive, send)
                return

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            length = len(body) + len(chunk)
            if length > self.max_bytes:
                await self._too_large(request, length)(scope, receive, send)
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break

        buffered_body: bytes | None = bytes(body)
        del body

        async def replay_body() -> Message:
            nonlocal buffered_body
            if buffered_body is not None:
                message: Message = {"type": "http.request", "body": buffered_body, "more_body": False}
                buffered_body = None
                return message
            return await receive()

        await self.app(scope, replay_body, send)

    def _too_large(self, request: Request, length: int) -> JSONResponse:
        mb = self.max_bytes / (1024 * 1024)
        logger.warning(
            "request_too_large: body_bytes=%s max_bytes=%s path=%s",
            length,
            self.max_bytes,
            request.url.path,
        )
        return JSONResponse(
            status_code=413,
            content={
                "error": "payload_too_large",
                "detail": f"Request body exceeds the {mb:.0f} MB limit.",
            },
        )


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
            # Same stdlib-logger kwargs bug as above: the structlog-style
            # call raised TypeError, turning every timed-out request into
            # a 500 instead of the intended 504 (#2503).
            logger.error(
                "request_timeout: path=%s method=%s timeout_seconds=%s",
                request.url.path,
                request.method,
                self.timeout_seconds,
            )
            return JSONResponse(
                status_code=504,
                content={
                    "error": "request_timeout",
                    "detail": f"Request timed out after {self.timeout_seconds:.0f} seconds.",
                },
            )
