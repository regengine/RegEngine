from fastapi import FastAPI
from services.shared.api_key_store import get_api_key_store
from services.shared.logger import get_logger

logger = get_logger("energy-api")

app = FastAPI(
    title="Energy Service",
    version="1.0.0",
    description="Energy and ML services",
)

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "energy-api"}

@app.get("/")
async def root():
    """Root endpoint."""
    return {"service": "energy-api", "version": "1.0.0"}

@app.on_event("startup")
async def startup_event():
    """Startup event."""
    logger.info("Energy service starting up")

@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event."""
    logger.info("Energy service shutting down")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8700)