from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import httpx
import structlog
import asyncio
import os
from sqlalchemy import text
from app.dependencies import get_current_user, get_session
from app.sqlalchemy_models import UserModel
from sqlalchemy.orm import Session

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
    # FSMA-specific live metrics
    compliance_score: Optional[int] = None
    compliance_grade: Optional[str] = None
    events_ingested: Optional[int] = None
    chain_length: Optional[int] = None
    chain_valid: Optional[bool] = None
    open_alerts: Optional[int] = None

def _get_service_urls() -> Dict[str, str]:
    """Build service health-check URLs from env vars or fallback to Docker names."""
    ingestion = os.getenv("INGESTION_SERVICE_URL", "http://ingestion-api:8002")
    compliance = os.getenv("COMPLIANCE_SERVICE_URL", "http://compliance-api:8500")
    urls = {
        "ingestion": f"{ingestion.rstrip('/')}/health",
        "compliance": f"{compliance.rstrip('/')}/health",
    }
    # Graph service is optional — only check if explicitly configured
    graph = os.getenv("GRAPH_SERVICE_URL")
    if graph:
        urls["graph"] = f"{graph.rstrip('/')}/v1/labels/health"
    return urls

def _get_ingestion_base() -> str:
    return os.getenv("INGESTION_SERVICE_URL", "http://ingestion-api:8002").rstrip("/")

@router.get("/status", response_model=SystemStatusResponse)
async def get_system_status(current_user: UserModel = Depends(get_current_user)):
    service_urls = _get_service_urls()

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
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
    """Check service health with one retry on failure."""
    for attempt in range(2):
        try:
            response = await client.get(url)
            if response.status_code == 200:
                return ServiceHealth(name=name, status="healthy", details=response.json())
            if attempt == 0:
                await asyncio.sleep(1)
                continue
            return ServiceHealth(name=name, status="unhealthy", details={"error": f"Status {response.status_code}"})
        except Exception as e:
            if attempt == 0:
                await asyncio.sleep(1)
                continue
            error_msg = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
            logger.warning("health_check_failed", service=name, url=url, error=error_msg)
            return ServiceHealth(name=name, status="unhealthy", details={"error": error_msg})
    # Should not reach here, but just in case
    return ServiceHealth(name=name, status="unhealthy", details={"error": "max retries"})


def _resolve_tenant(db: Session) -> str:
    """Resolve tenant UUID from the RLS context set by get_current_user."""
    try:
        row = db.execute(text("SELECT current_setting('app.tenant_id', true)")).fetchone()
        tid = row[0] if row else None
        if tid:
            return tid
    except Exception:
        pass
    return "5946c58f-ddf9-4db0-9baa-acb11c6fce91"  # fallback: demo tenant


@router.get("/metrics", response_model=SystemMetricsResponse)
async def get_system_metrics(
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """Fetch live metrics from the ingestion service.

    Calls the scoring and chain-verify endpoints on the ingestion service
    to return real compliance data instead of hardcoded mocks.
    """
    base = _get_ingestion_base()
    tenant = _resolve_tenant(db)

    score_data: Dict[str, Any] = {}
    chain_data: Dict[str, Any] = {}

    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
        score_task = client.get(f"{base}/api/v1/compliance/score/{tenant}")
        chain_task = client.get(
            f"{base}/api/v1/webhooks/chain/verify",
            params={"tenant_id": tenant},
        )
        score_resp, chain_resp = await asyncio.gather(
            score_task, chain_task, return_exceptions=True,
        )

        if isinstance(score_resp, Exception):
            logger.warning("metrics_score_fetch_failed", error=str(score_resp))
        elif score_resp.status_code == 200:
            score_data = score_resp.json()

        if isinstance(chain_resp, Exception):
            logger.warning("metrics_chain_fetch_failed", error=str(chain_resp))
        elif chain_resp.status_code == 200:
            chain_data = chain_resp.json()

    events = score_data.get("events_analyzed", 0)
    return SystemMetricsResponse(
        total_tenants=1,
        total_documents=events,
        active_jobs=0,
        compliance_score=score_data.get("overall_score"),
        compliance_grade=score_data.get("grade"),
        events_ingested=events,
        chain_length=chain_data.get("chain_length"),
        chain_valid=chain_data.get("chain_valid"),
        open_alerts=0,  # TODO: query alerts table
    )
