"""
Audit Middleware — Automatic Request Context Capture
ISO 27001: 12.4.1

Wraps every request with actor/IP/UA context for audit logging.
Route handlers access via: request.state.audit_context
"""

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = structlog.get_logger("audit_middleware")


class AuditContextMiddleware(BaseHTTPMiddleware):
    """
    Injects audit context into request state so route handlers
    don't need boilerplate for extracting IP, UA, etc.

    Usage in route handlers:
        ctx = request.state.audit_context
        AuditLogger.log_event(
            db=db,
            ...,
            actor_ip=ctx["actor_ip"],
            actor_ua=ctx["actor_ua"],
            endpoint=ctx["endpoint"],
            request_id=ctx["request_id"],
        )
    """

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.audit_context = {
            "request_id": request_id,
            "actor_ip": self._get_client_ip(request),
            "actor_ua": (request.headers.get("user-agent") or "")[:512],
            "endpoint": f"{request.method} {request.url.path}",
        }

        response = await call_next(request)
        return response

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """Extract real IP, respecting proxy headers."""
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        return request.client.host if request.client else "unknown"
