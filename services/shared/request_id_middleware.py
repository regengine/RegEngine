"""Request ID middleware for distributed tracing.

Generates or propagates X-Request-ID headers across all services.
Injects the request ID into structlog context for correlated logging.
"""

import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import structlog


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware that ensures every request has a unique correlation ID.

    If the incoming request has an X-Request-ID header, it is preserved.
    Otherwise, a new UUID is generated. The ID is:
    - Added to the response headers
    - Bound to the structlog context for the duration of the request
    """

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Bind to structlog context
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        # Make available to route handlers via request.state
        request.state.request_id = request_id

        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        return response
