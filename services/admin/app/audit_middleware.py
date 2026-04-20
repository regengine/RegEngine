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

# Prefix matches — any subpath under these is also skipped. Covers FastAPI's
# Swagger static assets (/docs/oauth2-redirect, etc.) and future health
# subpaths like /health/db without a code change.
_AUDIT_SKIP_PREFIXES: tuple[str, ...] = (
    "/health/",
    "/healthz/",
    "/ready/",
    "/readyz/",
    "/docs/",
    "/redoc/",
    "/metrics/",
)


def _should_skip(path: str) -> bool:
    """Check if this request path is in the audit-middleware skip list."""
    if path in _AUDIT_SKIP_PATHS:
        return True
    if path.startswith(_AUDIT_SKIP_PREFIXES):
        return True
    return False


def _should_skip_request(method: str, path: str) -> bool:
    """Return True when the request should bypass audit context.

    Beyond the path skip list we also skip CORS preflight (``OPTIONS``) on
    any route: preflights carry no authenticated actor and must return
    204/200 before auth runs, so attaching audit context is pointless and
    opens an XFF-spoofing surface on every route in the service.
    """
    if method == "OPTIONS":
        return True
    return _should_skip(path)


def _trusted_proxy_cidrs() -> list[ipaddress._BaseNetwork]:
    """Parse trusted-proxy CIDRs from env into a list of IP networks.

    #1414: ``X-Forwarded-For`` is trusted ONLY when the immediate
    connection originates from a trusted proxy. In production this is
    typically the Railway edge CIDR range; in dev it can include
    127.0.0.0/8. Unset = no proxies trusted; XFF is ignored.

    Two env vars are accepted, checked in order:

    1. ``AUDIT_TRUSTED_PROXY_CIDRS`` — original name, preserved for
       back-compat with existing deploy configs.
    2. ``TRUSTED_PROXY_CIDRS`` — shorter alias; may be shared with other
       services in future.

    If both are set, ``AUDIT_TRUSTED_PROXY_CIDRS`` wins (explicit beats
    generic) and we log a warning so ops notices the redundancy.
    """
    raw_audit = os.getenv("AUDIT_TRUSTED_PROXY_CIDRS", "").strip()
    raw_shared = os.getenv("TRUSTED_PROXY_CIDRS", "").strip()
    if raw_audit and raw_shared and raw_audit != raw_shared:
        logger.warning(
            "trusted_proxy_env_conflict",
            reason="AUDIT_TRUSTED_PROXY_CIDRS and TRUSTED_PROXY_CIDRS disagree; using AUDIT_TRUSTED_PROXY_CIDRS",
        )
    raw = raw_audit or raw_shared
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
        # #1414: skip CORS preflight + health / docs / metrics — audit
        # pressure without value, and an XFF-spoofing surface on
        # unauthenticated routes.
        if _should_skip_request(request.method, request.url.path):
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
        trusted proxy (AUDIT_TRUSTED_PROXY_CIDRS / TRUSTED_PROXY_CIDRS).
        Otherwise we use the raw socket address so attackers can't spoof
        ``actor_ip`` on unauthenticated routes to evade per-IP rate
        limits or blame another IP in audit.

        Malformed XFF (first hop not a valid IP) falls back to the socket
        address rather than returning garbage. IPv6 hops are accepted
        natively by ``ipaddress.ip_address``.
        """
        client_host = request.client.host if request.client else None

        if _is_trusted_proxy(client_host):
            forwarded = request.headers.get("x-forwarded-for")
            if forwarded:
                # Left-most hop is the originator when the chain is trusted.
                first_hop = forwarded.split(",")[0].strip()
                if first_hop and _looks_like_ip(first_hop):
                    return first_hop
            real_ip = request.headers.get("x-real-ip")
            if real_ip:
                candidate = real_ip.strip()
                if candidate and _looks_like_ip(candidate):
                    return candidate

        return client_host or "unknown"


def _looks_like_ip(value: str) -> bool:
    """Lightweight IPv4/IPv6 validity check. Prevents a malformed XFF
    hop (e.g. a hostname, an empty string, ``'unknown'``) from landing
    in ``actor_ip`` where downstream audit + rate-limit code assumes an
    IP. IPv6 addresses with zone ids (``fe80::1%eth0``) are rejected —
    they would never appear in a legitimate XFF hop.
    """
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True
