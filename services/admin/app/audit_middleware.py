"""
Audit Middleware — Automatic Request Context Capture
ISO 27001: 12.4.1

Wraps every request with actor/IP/UA context for audit logging.
Route handlers access via: request.state.audit_context
"""

import ipaddress
import os
import re
import uuid

import structlog
from shared.proxy_ip_attestation import verified_proxy_client_ip as _verified_proxy_client_ip
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = structlog.get_logger("audit_middleware")

# #1414: paths that MUST NOT run through the audit context middleware.
# These are unauthenticated / metadata endpoints — running them through
# audit builds pressure on the audit chain with no forensic value and
# exposes actor_ip spoofing via XFF on paths that don't require auth.
_AUDIT_SKIP_PATHS: frozenset[str] = frozenset(
    {
        "/health",
        "/healthz",
        "/ready",
        "/readyz",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/metrics",
        "/favicon.ico",
    }
)

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


# Same shape the signed proxy attestation accepts. Anything else is not
# used as audit evidence, because the request id is caller-controlled.
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _audit_request_id(request: Request) -> str:
    """Return a bounded request id, or a fresh id when the candidate is hostile."""
    candidate = str(getattr(request.state, "request_id", "") or "").strip()
    if _REQUEST_ID_RE.fullmatch(candidate):
        return candidate
    return str(uuid.uuid4())


def _audit_user_agent(request: Request) -> str:
    """Drop control characters and cap the user agent stored in audit context."""
    raw = request.headers.get("user-agent") or ""
    cleaned = "".join(ch for ch in raw if ch.isprintable())
    return cleaned[:512]


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
    """Parse legacy trusted-proxy CIDRs for configuration compatibility.

    AuditContextMiddleware no longer uses peer CIDRs to authorize forwarding
    headers: a public backend cannot tell a legitimate BFF call from a direct
    caller that happens to traverse the same edge. Raw forwarding headers are
    always ignored; only the signed proxy-IP attestation is authoritative.

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
    """Legacy helper retained for compatibility tests; not an audit trust gate."""
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

        # RequestIDMiddleware owns the canonical per-hop request ID in the
        # consolidated app and runs before this middleware. The standalone
        # admin service has no request-ID middleware, so retain a local UUID
        # fallback there.
        request.state.audit_context = {
            "request_id": _audit_request_id(request),
            "actor_ip": self._get_client_ip(request),
            "actor_ua": _audit_user_agent(request),
            "endpoint": f"{request.method} {request.url.path}",
        }

        response = await call_next(request)
        return response

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """Resolve an authenticated BFF client IP or use the socket peer.

        Raw ``Forwarded``, ``X-Forwarded-For``, and ``X-Real-IP`` values are
        never authority, including when Railway is the immediate peer. The
        public backend can also be called directly, so peer-CIDR trust alone
        cannot distinguish a Vercel BFF request from attacker-supplied headers.
        """
        client_host = request.client.host if request.client else None
        verified_client_ip = _verified_proxy_client_ip(request)
        if verified_client_ip:
            return verified_client_ip
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
