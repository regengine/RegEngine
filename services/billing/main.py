"""
RegEngine Billing Service

Enterprise payment orchestration with Stripe integration,
credit programs, and subscription management.

Port: 8800
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure billing module is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from routers import subscriptions, credits, checkout, webhooks, analytics, usage, contracts, invoices, partners, dunning, tax, lifecycle, alerts, forecasting, optimization

logger = structlog.get_logger(__name__)

SERVICE_NAME = "billing-service"
SERVICE_VERSION = "1.0.0"
SERVICE_PORT = int(os.getenv("BILLING_PORT", "8800"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    from stripe_client import is_sandbox
    mode = "SANDBOX" if is_sandbox() else "PRODUCTION"
    logger.info(
        "billing_service_started",
        service=SERVICE_NAME,
        version=SERVICE_VERSION,
        port=SERVICE_PORT,
        mode=mode,
    )
    yield
    logger.info("billing_service_stopped", service=SERVICE_NAME)


app = FastAPI(
    title="RegEngine Billing Service",
    description="Enterprise payment orchestration — subscriptions, credits, and checkout",
    version=SERVICE_VERSION,
    lifespan=lifespan,
)

# ── CORS ───────────────────────────────────────────────────────────
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8080,https://regengine.co,https://regengine.vercel.app",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mount Routers ──────────────────────────────────────────────────
app.include_router(subscriptions.router)
app.include_router(credits.router)
app.include_router(checkout.router)
app.include_router(webhooks.router)
app.include_router(analytics.router)
app.include_router(usage.router)
app.include_router(contracts.router)
app.include_router(invoices.router)
app.include_router(partners.router)
app.include_router(dunning.router)
app.include_router(tax.router)
app.include_router(lifecycle.router)
app.include_router(alerts.router)
app.include_router(forecasting.router)
app.include_router(optimization.router)


# ── Health & Info ──────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check endpoint."""
    from stripe_client import is_sandbox
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "billing_mode": "sandbox" if is_sandbox() else "production",
    }


@app.get("/")
async def root():
    """Service info."""
    return {
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "description": "RegEngine Billing & Payment Orchestration",
        "endpoints": {
            "subscriptions": "/v1/billing/subscriptions",
            "credits": "/v1/billing/credits",
            "checkout": "/v1/billing/checkout",
            "webhooks": "/v1/billing/webhooks",
            "health": "/health",
            "docs": "/docs",
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=SERVICE_PORT, reload=True)
