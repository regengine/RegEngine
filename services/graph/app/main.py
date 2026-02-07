"""
FastAPI Application Entry Point for Graph Service
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog
import sys
from pathlib import Path

# Add shared utilities
_SERVICES_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_SERVICES_DIR))
from shared.middleware import TenantContextMiddleware

from .routes import router, v1_router
from .fsma_routes import fsma_router
from .routers.arbitrage import arbitrage_router

logger = structlog.get_logger("graph-api")

app = FastAPI(
    title="Graph Service",
    description="Neo4j-backed regulatory knowledge graph",
    version="1.0.0",
)


# CORS Helpers
def get_allowed_origins():
    import os
    origins = os.getenv("CORS_ORIGINS", "*")
    return origins.split(",") if "," in origins else [origins]

def should_allow_credentials():
    return True

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=should_allow_credentials(),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(TenantContextMiddleware)

# Mount routers
app.include_router(router, tags=["health"])  # Health/metrics at root
app.include_router(v1_router, tags=["v1"])  # General v1 endpoints
app.include_router(fsma_router, prefix="/fsma", tags=["fsma"])  # FSMA-specific
app.include_router(arbitrage_router, tags=["arbitrage"])  # Arbitrage detection


@app.on_event("startup")
async def startup_event():
    """Application startup tasks"""
    logger.info("graph_service_starting", version="1.0.0")


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown tasks"""
    logger.info("graph_service_shutting_down")


# Root endpoint
@app.get("/")
async def root():
    """Service information"""
    return {
        "service": "RegEngine Graph Service",
        "version": "1.0.0",
        "status": "operational",
        "endpoints": {
            "health": "/health",
            "metrics": "/metrics",
            "docs": "/docs",
            "arbitrage": "/graph/arbitrage?framework_from=X&framework_to=Y",
            "gaps": "/graph/gaps?current_framework=X&target_framework=Y",
            "relationships": "/graph/frameworks/{id}/relationships",
            "frameworks": "/graph/frameworks",
            "fsma": "/fsma/*",
        },
    }
