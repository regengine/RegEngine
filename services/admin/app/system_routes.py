from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List
import httpx
import structlog
import asyncio
from shared.auth import require_api_key

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

SERVICE_URLS = {
    "ingestion": "http://ingestion-api:8002/health",
    # compliance:8500 inside docker network
    "compliance": "http://compliance-api:8500/health",
    "graph": "http://graph-api:8200/v1/labels/health",
}

@router.get("/status", response_model=SystemStatusResponse)
async def get_system_status(api_key=Depends(require_api_key)):
    # Enforce Super Admin check - require 'admin' scope
    if not hasattr(api_key, 'scopes') or 'admin' not in (api_key.scopes or []):
        raise HTTPException(
            status_code=403,
            detail="Super Admin access required for system endpoints"
        )
    
    async with httpx.AsyncClient(timeout=3.0) as client:
        tasks = []
        for name, url in SERVICE_URLS.items():
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
async def get_system_metrics(api_key=Depends(require_api_key)):
    # Mock data for now until we have direct DB access or calls
    return SystemMetricsResponse(
        total_tenants=5, # Real impl would query KeyStore
        total_documents=128, # Real impl query Graph
        active_jobs=3 
    )
