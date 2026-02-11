"""
Opportunity Service - FastAPI Application Entry Point
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog
from shared.middleware import TenantContextMiddleware

from app.routes import router

logger = structlog.get_logger("opportunity-api")

app = FastAPI(
    title="Opportunity Service",
    description="Regulatory opportunity & arbitrage detection API",
    version="1.0.0",
)

# Standard CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(TenantContextMiddleware)

# Mount routes
app.include_router(router)

@app.on_event("startup")
async def startup_event():
    logger.info("opportunity_service_starting", version="1.0.0")



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8300)
