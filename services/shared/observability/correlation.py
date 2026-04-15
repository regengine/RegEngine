from __future__ import annotations

import contextvars
import uuid
from typing import Optional

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

# Context variable for correlation ID
correlation_id_ctx = contextvars.ContextVar("correlation_id", default=None)

def get_correlation_id() -> Optional[str]:
    """Retrieve the current correlation ID from context."""
    return correlation_id_ctx.get()

class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware to handle Correlation IDs for distributed tracing.

    Checks for 'X-Correlation-ID' header, generates one if missing,
    sets it in context, binds to structlog, and returns it in the
    response header.
    """

    def __init__(self, app: ASGIApp, header_name: str = "X-Correlation-ID"):
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get(self.header_name)

        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        token = correlation_id_ctx.set(correlation_id)
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        try:
            response = await call_next(request)
            response.headers[self.header_name] = correlation_id
            return response
        finally:
            correlation_id_ctx.reset(token)
            structlog.contextvars.unbind_contextvars("correlation_id")
