
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import structlog
from contextvars import ContextVar

# ContextVar to store request ID for access outside of request context (e.g. deep in service logic)
request_id_ctx: ContextVar[str] = ContextVar("request_id", default=" unknown")

class RequestIDMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        
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
