from fastapi import FastAPI
from shared.cors import (
    get_allowed_headers,
    get_allowed_origins,
    should_allow_credentials,
)
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

# Paths exempt from TrustedHost validation (infra probes, metrics).
# Railway's internal health-checker may send a Host header that doesn't
# match any configured domain (e.g. container IP or private hostname).
_TRUSTED_HOST_EXEMPT_PATHS = {"/health", "/ready", "/readiness", "/metrics", "/"}

# Single source of truth for the Host-header allowlist. Mirrors the hosts
# each service is legitimately reached on (public domain, Railway internal
# + public, local dev, inter-service names). Validating Host here is the
# mitigation for PYSEC-2026-161 (starlette BadHost path poisoning) — it
# rejects forged Host headers before any path-based logic runs.
TRUSTED_HOST_ALLOWLIST = [
    "*.regengine.co",
    "*.up.railway.app",
    "*.railway.internal",
    "localhost",
    # Loopback IPs: local dev self-calls (e.g. system-metrics → ingestion
    # with *_SERVICE_URL=http://127.0.0.1:8000) 400'd with "Invalid host
    # header" because only the "localhost" spelling was allowed.
    "127.0.0.1",
    "::1",
    "testserver",
    "ingestion-service",
    "admin-api",
    "billing-service",
    "compliance-api",
    "compliance-api-worker",
    "nlp-service",
    "graph-service",
    "scheduler",
    "otel-collector",
    "gateway",
]


class _HealthBypassTrustedHostMiddleware:
    """ASGI middleware: skip TrustedHost for health/readiness probes.

    Delegates all other requests to Starlette's TrustedHostMiddleware unchanged.
    """

    def __init__(self, app, allowed_hosts=None):
        self.app = app
        self.trusted_host_app = TrustedHostMiddleware(app, allowed_hosts=allowed_hosts or [])

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path", "") in _TRUSTED_HOST_EXEMPT_PATHS:
            await self.app(scope, receive, send)
        else:
            await self.trusted_host_app(scope, receive, send)


def add_trusted_host(app: FastAPI):
    """Add Host-header validation (TrustedHost) to the FastAPI app.

    Split out from add_security so services that register their own CORS
    (e.g. admin) can still get Host validation without double-registering
    CORS. Uses the shared TRUSTED_HOST_ALLOWLIST as the single source.
    """
    app.add_middleware(_HealthBypassTrustedHostMiddleware, allowed_hosts=TRUSTED_HOST_ALLOWLIST)


def add_security(app: FastAPI):
    """Add CORS and TrustedHost security middleware to the FastAPI app."""
    origins = get_allowed_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=should_allow_credentials(),
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=get_allowed_headers(),
    )
    add_trusted_host(app)
