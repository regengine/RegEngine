"""
Construction Compliance Service - Main application.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sys

from pathlib import Path
_SERVICES_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_SERVICES_DIR))
from shared.middleware import TenantContextMiddleware
from shared.cors import get_allowed_origins, should_allow_credentials

from .config import settings
from .bim_tracking import router as bim_router

app = FastAPI(title="Construction API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=should_allow_credentials(),
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TenantContextMiddleware)
app.include_router(bim_router)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": settings.SERVICE_NAME}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=True)
