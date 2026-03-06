from fastapi import FastAPI
from services.shared.api_key_store import get_api_key_store
from services.shared.logging import get_logger

logger = get_logger("billing-api")

app = FastAPI(
    title="Billing Service",
    version="1.0.0",
    description="Billing and payment services",
)

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "billing-api"}

@app.get("/")
async def root():
    """Root endpoint."""
    return {"service": "billing-api", "version": "1.0.0"}

@app.on_event("startup")
async def startup_event():
    """Startup event."""
    logger.info("Billing service starting up")

@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event."""
    logger.info("Billing service shutting down")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8800)