"""
Tenant Context Middleware

Extracts tenant_id from authentication context (JWT token or API key) and
makes it available to request handlers via dependency injection.

This middleware ensures every request has a validated tenant_id before
reaching the application logic.

Usage:
    from shared.middleware.tenant_context import (
        TenantContextMiddleware,
        get_current_tenant_id
    )
    
    # Add to FastAPI app
    app.add_middleware(TenantContextMiddleware)
    
    # Use in route handlers
    @app.get("/items")
    async def get_items(tenant_id: UUID = Depends(get_current_tenant_id)):
        return await db.query(Item).filter(Item.tenant_id == tenant_id).all()
"""

import hmac
import os
import uuid
import logging
from typing import Optional, Callable

from fastapi import Request, HTTPException, Depends
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class TenantContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware to extract and validate tenant_id from request context.
    
    Extracts tenant_id from:
    1. JWT token claims (preferred for user requests)
    2. X-RegEngine-Tenant-ID header (for service-to-service calls)
    3. X-API-Key lookup (for API key authentication)
    """
    
    async def dispatch(self, request: Request, call_next: Callable):
        """Process request and extract tenant context."""
        try:
            tenant_id = await self._extract_tenant_id(request)
            
            # Store in request state for easy access
            request.state.tenant_id = tenant_id
            
            # Log tenant context
            logger.debug(
                f"Request {request.method} {request.url.path} "
                f"for tenant {tenant_id}"
            )
            
        except HTTPException:
            # Let the exception handler deal with it
            raise
        except (ValueError, TypeError, AttributeError, KeyError) as e:
            # ValueError: UUID parsing or header validation failures
            # TypeError: unexpected type conversions during extraction
            # AttributeError: missing request attributes
            # KeyError: missing JWT claims
            logger.error(f"Error extracting tenant context: {e}")
            # Continue without tenant_id - let route handlers decide if required
            request.state.tenant_id = None
        
        response = await call_next(request)
        return response
    
    async def _extract_tenant_id(self, request: Request) -> Optional[uuid.UUID]:
        """
        Extract tenant_id from various sources.
        
        Priority order:
        1. JWT token claims (if user is authenticated)
        2. X-RegEngine-Tenant-ID header
        3. API key lookup
        """
        # Method 1: From JWT token
        if hasattr(request.state, "user") and request.state.user:
            tenant_id_str = request.state.user.get("tenant_id")
            if tenant_id_str:
                try:
                    return uuid.UUID(tenant_id_str)
                except ValueError:
                    logger.warning(f"Invalid tenant_id in JWT: {tenant_id_str}")
        
        # Method 2: From custom header (Internal/Service-to-service ONLY)
        # WARNING: This is a potential spoofing vector if not stripped at the gateway.
        # We only trust this header if we are in a 'trusted' internal context.
        tenant_header = request.headers.get("X-RegEngine-Tenant-ID")
        if tenant_header:
            # Validate against the configured internal service secret (env var only —
            # never compare to a hardcoded string in source code).
            internal_secret = request.headers.get("X-RegEngine-Internal-Secret")
            configured_secret = os.getenv("REGENGINE_INTERNAL_SECRET")
            is_internal = bool(
                configured_secret
                and internal_secret
                and hmac.compare_digest(internal_secret, configured_secret)
            )
            
            if is_internal:
                try:
                    return uuid.UUID(tenant_header)
                except ValueError:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid tenant ID format in header: {tenant_header}"
                    )
            else:
                client_host = request.client.host if request.client else "unknown"
                logger.warning(
                    "Rejected unauthenticated X-RegEngine-Tenant-ID header",
                    extra={"client_host": client_host},
                )
        
        # Method 3: From API key
        # API keys must be validated against the database (api_key_store).
        # A single configurable key is supported for service accounts via env vars;
        # a hardcoded key in source code is never acceptable.
        api_key = request.headers.get("X-RegEngine-API-Key")
        if api_key:
            configured_key = os.getenv("REGENGINE_API_KEY")
            configured_tenant = os.getenv("REGENGINE_API_KEY_TENANT_ID")
            if configured_key and configured_tenant and api_key == configured_key:
                try:
                    return uuid.UUID(configured_tenant)
                except ValueError:
                    logger.error(
                        "REGENGINE_API_KEY_TENANT_ID is not a valid UUID — "
                        "API key auth disabled until corrected"
                    )

        return None


async def get_current_tenant_id(request: Request) -> uuid.UUID:
    """
    FastAPI dependency to get the current request's tenant_id.
    
    Raises HTTPException(401) if no tenant_id is available.
    
    Usage:
        @app.get("/reports")
        async def get_reports(
            tenant_id: UUID = Depends(get_current_tenant_id)
        ):
            return await fetch_reports(tenant_id)
    """
    if not hasattr(request.state, "tenant_id") or request.state.tenant_id is None:
        raise HTTPException(
            status_code=401,
            detail="Tenant ID not found in authentication context"
        )
    
    return request.state.tenant_id


async def get_optional_tenant_id(request: Request) -> Optional[uuid.UUID]:
    """
    FastAPI dependency to get tenant_id, but don't require it.
    
    Returns None if no tenant_id is available (doesn't raise exception).
    
    Usage:
        @app.get("/public-data")
        async def get_data(
            tenant_id: Optional[UUID] = Depends(get_optional_tenant_id)
        ):
            if tenant_id:
                return await fetch_tenant_data(tenant_id)
            else:
                return await fetch_public_data()
    """
    return getattr(request.state, "tenant_id", None)


async def validate_tenant_access(
    request: Request,
    tenant_id: uuid.UUID
) -> uuid.UUID:
    """
    Validate that the current user has access to the specified tenant.
    
    This is useful when tenant_id is provided as a path/query parameter
    and you need to verify the user is allowed to access that tenant.
    
    Usage:
        @app.get("/tenants/{tenant_id}/data")
        async def get_tenant_data(
            tenant_id: UUID,
            validated_tenant_id: UUID = Depends(validate_tenant_access)
        ):
            # validated_tenant_id is guaranteed to match user's tenant
            return await fetch_data(validated_tenant_id)
    """
    current_tenant_id = await get_current_tenant_id(request)
    
    if current_tenant_id != tenant_id:
        logger.warning(
            f"Tenant access denied: user in tenant {current_tenant_id} "
            f"attempted to access tenant {tenant_id}"
        )
        raise HTTPException(
            status_code=403,
            detail=f"Access denied to tenant {tenant_id}"
        )
    
    return tenant_id
