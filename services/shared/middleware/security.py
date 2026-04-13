from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from shared.cors import get_allowed_origins

# Paths exempt from TrustedHost validation (infra probes, metrics).
# Railway's internal health-checker may send a Host header that doesn't
# match any configured domain (e.g. container IP or private hostname).
_TRUSTED_HOST_EXEMPT_PATHS = {"/health", "/ready", "/metrics", "/"}


class _HealthBypassTrustedHostMiddleware:
    """ASGI middleware: skip TrustedHost for health/readiness probes.

    Delegates all other requests to Starlette's TrustedHostMiddleware unchanged.
    """

    def __init__(self, app, allowed_hosts=None):
        self.app = app
        self.trusted_host_app = TrustedHostMiddleware(
            app, allowed_hosts=allowed_hosts or []
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path", "") in _TRUSTED_HOST_EXEMPT_PATHS:
            await self.app(scope, receive, send)
        else:
            await self.trusted_host_app(scope, receive, send)


def add_security(app: FastAPI):
    """Add CORS and TrustedHost security middleware to the FastAPI app."""
    origins = get_allowed_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_origin_regex=r"https://regengine[a-z0-9-]*\.(up\.railway\.app|vercel\.app)",
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-RegEngine-API-Key",
            "X-Admin-Key",
            "X-Tenant-ID",
            "X-Request-ID",
            "X-Requested-With",
            "X-Metrics-Key",
        ],
    )
    app.add_middleware(_HealthBypassTrustedHostMiddleware, allowed_hosts=[
        "*.regengine.co",
        "*.up.railway.app",
        "*.railway.internal",
        "localhost",
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
    ])
