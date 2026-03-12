import sys
from pathlib import Path

from fastapi import FastAPI

_SERVICE_DIR = Path(__file__).resolve().parent
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))

from app.routes import router as fsma_router


app = FastAPI(
    title="RegEngine FSMA 204 Compliance Service",
    version="1.0.0",
    description=(
        "FSMA 204 compliance API providing checklists, industry categories, "
        "and configuration validation for food traceability requirements."
    ),
)


@app.get("/health")
async def health_check() -> dict:
    return {"status": "healthy", "service": "compliance-api"}


@app.get("/")
async def root() -> dict:
    return {
        "service": "compliance-api",
        "product": "RegEngine FSMA 204 Compliance Service",
        "version": app.version,
        "docs": "/docs",
        "key_endpoints": {
            "industries": "/industries",
            "checklists": "/checklists",
            "validate": "/validate",
        },
    }


app.include_router(fsma_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8500)
