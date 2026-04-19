"""
Audit Middleware — Automatic Request Context Capture
ISO 27001: 12.4.1

Wraps every request with actor/IP/UA context for audit logging.
Route handlers access via: request.state.audit_context
"""

import ipaddress
import os
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = structlog.get_logger("audit_middleware")


# #1414: paths that MUST NOT run through the audit context middleware.
# These are unauthenticated / metadata endpoints — running them through
# audit builds pressure on the audit chain with no forensic value and
# exposes actor_ip spoofing via XFF on paths that don't require auth.
_AUDIT_SKIP_PATHS: frozenset[str] = frozenset({
    "/health",
    "/healthz",
    "/ready",
    "/readyz",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/metrics",
    "/favicon.ico",
})


def _should_skip(path: str) -> bool:
    """Check if this request path is in the audit-middleware skip list."""
    if path in _AUDIT_SKIP_PATHS:
        return True
    # /docs/*, /redoc/* — FastAPI mounts sub-paths for Swagger assets.
    if path.startswith(("/docs/", "/redoc/")):
        return True
    return False


def _trusted_proxy_cidrs() -> list[ipaddress._BaseNetwork]:
    """Parse AUDIT_TRUSTED_PROXY_CIDRS env into a list of IP networks.

    #1414: ``X-Forwarded-For`` is trusted ONLY when the immediate
    connection originates from a trusted proxy. In production this is
    typically the Railway edge CIDR range; in dev it can include
    127.0.0.0/8. Unset = no proxies trusted; XFF is ignored.
    """
    raw = os.getenv("AUDIT_TRUSTED_PROXY_CIDRS", "").strip()
    if not raw:
        return []
    cidrs: list[ipaddress._BaseNetwork] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            cidrs.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            logger.warning("audit_trusted_proxy_cidr_invalid", value=item)
    return cidrs


def _is_trusted_proxy(client_host: str | None) -> bool:
    if not client_host:
        return False
    try:
        client_ip = ipaddress.ip_address(client_host)
    except ValueError:
        return False
    for cidr in _trusted_proxy_cidrs():
        if client_ip in cidr:
            return True
    return False


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
        # #1414: skip health / docs / metrics — audit pressure without value.
        if _should_skip(request.url.path):
            return await call_next(request)

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
        """Extract real IP. #1414: ``X-Forwarded-For`` and
        ``X-Real-IP`` are honored ONLY when the immediate peer is a
        trusted proxy (AUDIT_TRUSTED_PROXY_CIDRS). Otherwise we use the
        raw socket address so attackers can't spoof ``actor_ip`` on
        unauthenticated routes to evade per-IP rate limits or blame
        another IP in audit.
        """
        client_host = request.client.host if request.client else None

        if _is_trusted_proxy(client_host):
            forwarded = request.headers.get("x-forwarded-for")
            if forwarded:
                # Left-most hop is the originator when the chain is trusted.
                return forwarded.split(",")[0].strip()
            real_ip = request.headers.get("x-real-ip")
            if real_ip:
                return real_ip.strip()

        return client_host or "unknown"
