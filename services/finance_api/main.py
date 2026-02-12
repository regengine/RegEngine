
from fastapi import FastAPI
from services.finance_api.routes import router
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Finance API",
    description="Finance Vertical Decision Service",
    version="1.0.0"
)

app.include_router(router)

@app.on_event("startup")
async def startup_event():
    logger.info("Finance API starting up...")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Finance API shutting down...")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "finance-api"}
