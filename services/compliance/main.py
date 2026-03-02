import sys
from pathlib import Path

from fastapi import FastAPI

_SERVICE_DIR = Path(__file__).resolve().parent
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))

from app.routes import router as fair_lending_router


app = FastAPI(
    title="RegEngine Fair Lending Compliance OS",
    version="0.1.0",
    description=(
        "API-first Fair Lending Compliance OS focused on ECOA/FHA obligations, "
        "bias monitoring, model governance, immutable audit artifacts, and executive risk scoring."
    ),
)


@app.get("/health")
async def health_check() -> dict:
    return {"status": "healthy", "service": "compliance-api"}


@app.get("/")
async def root() -> dict:
    return {
        "service": "compliance-api",
        "product": "RegEngine Fair Lending Compliance OS",
        "version": app.version,
        "docs": "/docs",
        "key_endpoints": {
            "regulatory_mapping": "/v1/regulatory/map",
            "fair_lending_analysis": "/v1/fair-lending/analyze",
            "audit_export": "/v1/audit/export",
            "risk_summary": "/v1/risk/summary",
            "model_registry": "/v1/models",
        },
    }


app.include_router(fair_lending_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8500)
