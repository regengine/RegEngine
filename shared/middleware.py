from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.requests import Request
import contextvars

# Context variable to hold tenant ID
tenant_id_context = contextvars.ContextVar("tenant_id", default=None)

class TenantContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        tenant_id = request.headers.get("X-Tenant-ID")
        if tenant_id:
            token = tenant_id_context.set(tenant_id)
            try:
                response = await call_next(request)
                return response
            finally:
                tenant_id_context.reset(token)
        else:
            return await call_next(request)

from .correlation import CorrelationIdMiddleware, correlation_id_ctx

def get_current_tenant_id() -> str | None:
    """Helper to get the current tenant ID from context."""
    return tenant_id_context.get()
