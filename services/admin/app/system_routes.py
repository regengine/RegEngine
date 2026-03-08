from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List
import httpx
import structlog
import asyncio
import os
from app.dependencies import get_current_user
from app.sqlalchemy_models import UserModel

router = APIRouter(prefix="/system", tags=["system"])
logger = structlog.get_logger("admin.system")

class ServiceHealth(BaseModel):
    name: str
    status: str
    details: Dict[str, Any]

class SystemStatusResponse(BaseModel):
    overall_status: str
    services: List[ServiceHealth]

class SystemMetricsResponse(BaseModel):
    total_tenants: int
    total_documents: int
    active_jobs: int

def _get_service_urls() -> Dict[str, str]:
    """Build service health-check URLs from env vars or fallback to Docker names."""
    ingestion = os.getenv("INGESTION_SERVICE_URL", "http://ingestion-api:8002")
    compliance = os.getenv("COMPLIANCE_SERVICE_URL", "http://compliance-api:8500")
    graph = os.getenv("GRAPH_SERVICE_URL", "http://graph-api:8200")
    return {
        "ingestion": f"{ingestion.rstrip('/')}/health",
        "compliance": f"{compliance.rstrip('/')}/health",
        "graph": f"{graph.rstrip('/')}/v1/labels/health",
    }

@router.get("/status", response_model=SystemStatusResponse)
async def get_system_status(current_user: UserModel = Depends(get_current_user)):
    service_urls = _get_service_urls()

    async with httpx.AsyncClient(timeout=5.0) as client:
        tasks = []
        for name, url in service_urls.items():
            tasks.append(check_service_health(client, name, url))

        results = await asyncio.gather(*tasks)

    overall = "healthy"
    for r in results:
        if r.status != "healthy":
            overall = "degraded"

    return SystemStatusResponse(overall_status=overall, services=results)

async def check_service_health(client, name: str, url: str) -> ServiceHealth:
    try:
        response = await client.get(url)
        if response.status_code == 200:
            return ServiceHealth(name=name, status="healthy", details=response.json())
        return ServiceHealth(name=name, status="unhealthy", details={"error": f"Status {response.status_code}"})
    except Exception as e:
        return ServiceHealth(name=name, status="unhealthy", details={"error": str(e)})

@router.get("/metrics", response_model=SystemMetricsResponse)
async def get_system_metrics(current_user: UserModel = Depends(get_current_user)):
    # Mock data for now until we have direct DB access or calls
    return SystemMetricsResponse(
        total_tenants=5,
        total_documents=128,
        active_jobs=3
    )
