from __future__ import annotations

import contextvars
import uuid
from typing import Optional

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

# Context variable for correlation ID — shared across sync/async boundaries so
# structlog processors, Sentry scope hooks, and Kafka producers can read the
# trace ID of the originating HTTP request.
correlation_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "correlation_id", default=None
)

# Header name used end-to-end. External callers that already carry a trace ID
# (gateway, upstream service) should send this header; otherwise one is minted.
CORRELATION_ID_HEADER = "X-Correlation-ID"


def get_correlation_id() -> Optional[str]:
    """Retrieve the current correlation ID from context.

    Returns None when called outside of an HTTP request / background task that
    hasn't had the ID seeded. Callers should treat a None return as "no trace
    context" rather than assume one.
    """
    return correlation_id_ctx.get()


def set_correlation_id(correlation_id: str) -> contextvars.Token:
    """Explicitly seed the correlation ID contextvar.

    Intended for use by Kafka consumers / APScheduler jobs that receive the
    correlation ID out-of-band and need to re-hydrate the context before
    invoking handlers. Returns the contextvars.Token so the caller can reset
    the var on exit.
    """
    return correlation_id_ctx.set(correlation_id)


def generate_correlation_id() -> str:
    """Return a fresh UUIDv4 string for a new trace."""
    return str(uuid.uuid4())


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Middleware that binds a correlation ID to every HTTP request.

    Behaviour:
    * Reads ``X-Correlation-ID`` from the incoming request, or mints a
      UUIDv4 if absent.
    * Stores the value on ``correlation_id_ctx`` and binds it to the
      structlog contextvars so every log line within the request carries it
      (alongside request_id / tenant_id which other middleware set).
    * Exposes the value on ``request.state.correlation_id`` for route
      handlers that want to read it without importing the contextvar.
    * Echoes the header back on the response so clients / downstream
      services can log the same trace ID.

    This middleware is intentionally lightweight and should be mounted
    *before* TenantContextMiddleware / AuditContextMiddleware so downstream
    middleware can call ``get_correlation_id()``.
    """

    def __init__(self, app: ASGIApp, header_name: str = CORRELATION_ID_HEADER) -> None:
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get(self.header_name)
        if not correlation_id:
            correlation_id = generate_correlation_id()

        # Basic guard: cap correlation-id length to avoid abuse via header stuffing.
        # 128 chars is more than enough for a UUID / W3C trace-id.
        correlation_id = str(correlation_id)[:128]

        token = correlation_id_ctx.set(correlation_id)
        # Also bind to structlog contextvars so emitted logs pick it up without
        # any processor touching the ContextVar directly.
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        # Route handlers can read this without importing the contextvar module.
        request.state.correlation_id = correlation_id

        try:
            response = await call_next(request)
            response.headers[self.header_name] = correlation_id
            return response
        finally:
            correlation_id_ctx.reset(token)
            structlog.contextvars.unbind_contextvars("correlation_id")
