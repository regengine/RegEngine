"""
Ingestion Service - FastAPI Application Entry Point

This module creates the FastAPI application and configures:
- CORS for frontend access
- Health check endpoint
- API routes from routes.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Centralised path resolution
_srv = str(Path(__file__).resolve().parent.parent)
if _srv not in sys.path:
    sys.path.insert(0, _srv)
from shared.paths import ensure_shared_importable
ensure_shared_importable()

from shared.middleware import TenantContextMiddleware, RequestIDMiddleware
from shared.observability import setup_telemetry
from shared.tenant_rate_limiting import TenantRateLimitMiddleware

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from app.routes import router

logger = structlog.get_logger("ingestion")

# Create FastAPI app
app = FastAPI(
    title="RegEngine Ingestion Service",
    description="Document ingestion and normalization service for RegEngine",
    version="1.0.0",
)

# Setup OpenTelemetry
setup_telemetry("ingestion-service", app)

# Add tenant isolation middleware
app.add_middleware(RequestIDMiddleware)
app.add_middleware(TenantContextMiddleware)
app.add_middleware(TenantRateLimitMiddleware, default_rpm=100)

# Configure CORS for frontend access
# In development, allow localhost:3000
# In production, this should be restricted to your domain
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

# Global exception handlers (Sprint 18)
from shared.error_handling import install_exception_handlers
install_exception_handlers(app)

# Include the API routes
app.include_router(router)

# Health check
@app.get("/health")
async def health():
    return {"status": "healthy", "service": "ingestion-service", "version": "1.0.0"}

@app.get("/ready")
async def readiness():
    return {"status": "ready", "service": "ingestion-service"}

# Startup event
@app.on_event("startup")
async def startup():
    logger.info("ingestion_service_starting", cors_origins=cors_origins)

# Shutdown event
@app.on_event("shutdown") 
async def shutdown():
    logger.info("ingestion_service_shutting_down")
