import uuid
from contextvars import ContextVar

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ContextVar to store request ID for access outside of request context (e.g. deep in service logic)
request_id_ctx: ContextVar[str] = ContextVar("request_id", default=" unknown")


class RequestIDMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Make the canonical per-hop ID available to downstream middleware and
        # handlers. AuditContextMiddleware reuses this exact value so response
        # headers, logs, and privileged audit evidence remain correlatable.
        request.state.request_id = request_id

        # Set in context var
        token = request_id_ctx.set(request_id)

        # Add to structlog context
        structlog.contextvars.bind_contextvars(request_id=request_id)

        try:
            # Process request
            response = await call_next(request)

            # Add header to response
            response.headers["X-Request-ID"] = request_id

            return response
        finally:
            # Always reset context, even on exceptions
            request_id_ctx.reset(token)
            structlog.contextvars.unbind_contextvars("request_id")


def get_current_request_id() -> str:
    """Get the current request ID from context."""
    return request_id_ctx.get()
