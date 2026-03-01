from fastapi import FastAPI
from services.shared.api_key_store import get_api_key_store
from services.shared.logger import get_logger

logger = get_logger("compliance-api")

app = FastAPI(
    title="Compliance Service",
    version="1.0.0",
    description="Compliance and regulatory services",
)

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "compliance-api"}

@app.get("/")
async def root():
    """Root endpoint."""
    return {"service": "compliance-api", "version": "1.0.0"}

@app.on_event("startup")
async def startup_event():
    """Startup event."""
    logger.info("Compliance service starting up")

@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event."""
    logger.info("Compliance service shutting down")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8500)