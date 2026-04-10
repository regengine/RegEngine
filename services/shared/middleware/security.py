from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from shared.cors import get_allowed_origins


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
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[
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
        "gateway"
    ])
