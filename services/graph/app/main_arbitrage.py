"""
Standalone FastAPI Application for Arbitrage Testing
Use this to test the new arbitrage endpoints without FSMA dependencies
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from .routes import router  # Just health/metrics
from .routers.arbitrage import arbitrage_router

logger = structlog.get_logger("graph-api")

app = FastAPI(title="Graph Arbitrage API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=should_allow_credentials(),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(router, tags=["health"])  # Health/metrics
app.include_router(arbitrage_router, tags=["arbitrage"])  # Arbitrage endpoints


@app.on_event("startup")
async def startup_event():
    """Application startup tasks"""
    logger.info("graph_arbitrage_service_starting", version="1.0.0")


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown tasks"""
    logger.info("graph_arbitrage_service_shutting_down")


# Root endpoint
@app.get("/")
async def root():
    """Service information"""
    return {
        "service": "RegEngine Graph Service - Arbitrage Demo",
        "version": "1.0.0",
        "status": "operational",
        "note": "Standalone arbitrage testing (FSMA routes disabled)",
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
            "arbitrage": "/graph/arbitrage?framework_from=SOC2&framework_to=ISO27001",
            "gaps": "/graph/gaps?current_framework=SOC2&target_framework=HIPAA",
            "relationships": "/graph/frameworks/SOC2/relationships",
            "frameworks": "/graph/frameworks",
        },
    }
