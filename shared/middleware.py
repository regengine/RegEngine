from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.requests import Request
import contextvars
import uuid

# Context variable to hold tenant ID
tenant_id_context = contextvars.ContextVar("tenant_id", default=None)

class TenantContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        tenant_id = request.headers.get("X-Tenant-ID")
        if tenant_id:
            token = tenant_id_context.set(tenant_id)
            # Also store on request.state for dependency functions
            request.state.tenant_id = uuid.UUID(tenant_id) if tenant_id else None
            try:
                response = await call_next(request)
                return response
            finally:
                tenant_id_context.reset(token)
        else:
            request.state.tenant_id = None
            return await call_next(request)

from .correlation import CorrelationIdMiddleware, correlation_id_ctx

from typing import Optional
from fastapi import HTTPException


async def get_current_tenant_id(request: Request = None) -> Optional[str]:
    """Get the current tenant ID from request state or context variable.
    
    When used as a FastAPI dependency (with request), reads from request.state.
    When called directly (no request), reads from context variable.
    """
    if request is not None:
        tenant_id = getattr(getattr(request, 'state', None), 'tenant_id', None)
        if tenant_id is None:
            raise HTTPException(status_code=401, detail="Tenant ID not found in request")
        return tenant_id
    return tenant_id_context.get()


async def get_optional_tenant_id(request: Request = None) -> Optional[str]:
    """Get the current tenant ID if available, or None.
    
    Unlike get_current_tenant_id, this does not raise on missing tenant.
    """
    if request is not None:
        return getattr(getattr(request, 'state', None), 'tenant_id', None)
    return tenant_id_context.get()


async def validate_tenant_access(request: Request, expected_tenant_id: uuid.UUID) -> uuid.UUID:
    """Validate that the request's tenant ID matches the expected tenant ID.
    
    Raises HTTPException(403) if there's a mismatch.
    """
    current_tenant_id = getattr(getattr(request, 'state', None), 'tenant_id', None)
    if current_tenant_id is None:
        raise HTTPException(status_code=401, detail="Tenant ID not found in request")
    if current_tenant_id != expected_tenant_id:
        raise HTTPException(status_code=403, detail="Access denied: tenant ID mismatch")
    return current_tenant_id
