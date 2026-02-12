"""
RegEngine Finance API Server
============================
FastAPI server for Finance vertical compliance API.

Includes:
- Finance decision endpoints
- ROE endpoints
- Evidence endpoints
- Health checks
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging

# Import routers
from services.finance_api.routes import router as finance_router
from services.regulatory_engine.routes import router as roe_router
from services.evidence.routes import router as evidence_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="RegEngine Finance API",
    description="AI Governance compliance API for Finance vertical",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(finance_router, tags=["Finance"])
app.include_router(roe_router, tags=["Regulatory Obligations"])
app.include_router(evidence_router, tags=["Evidence"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "RegEngine Finance API",
        "version": "1.0.0",
        "status": "operational",
        "endpoints": {
            "finance": "/v1/finance",
            "obligations": "/v1/obligations",
            "evidence": "/v1/evidence",
            "docs": "/docs"
        }
    }


@app.get("/health")
async def health_check():
    """Global health check."""
    return {
        "status": "healthy",
        "services": {
            "finance_api": "operational",
            "regulatory_engine": "operational",
            "evidence_service": "operational"
        }
    }


if __name__ == "__main__":
    logger.info("Starting RegEngine Finance API server...")
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
