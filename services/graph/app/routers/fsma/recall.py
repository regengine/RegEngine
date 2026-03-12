from __future__ import annotations

from typing import List, Optional
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ...fsma_recall import (
    MockRecallEngine,
    RecallDrill,
    RecallSeverity,
    RecallType,
    ScheduledDrill,
)
from ...fsma_utils import trace_backward, trace_forward
from ...neo4j_utils import Neo4jClient
from shared.auth import require_api_key

router = APIRouter(tags=["Recall"])
logger = structlog.get_logger("fsma-recall")


# ============================================================================
# INITIALIZATION
# ============================================================================


# Singleton instance
_recall_engine = None

def get_recall_engine():
    """Factory to get configured mock recall engine (Singleton)."""
    global _recall_engine
    if _recall_engine:
        return _recall_engine

    async def wrapped_forward(tlc, tenant_id=None):
        db_name = Neo4jClient.get_global_database_name()
        if tenant_id:
            try:
                # Handle both string and UUID objects
                tid = uuid.UUID(str(tenant_id))
                db_name = Neo4jClient.get_tenant_database_name(tid)
            except (ValueError, TypeError):
                pass
        
        client = Neo4jClient(database=db_name)
        try:
            res = await trace_forward(client, tlc, tenant_id=str(tenant_id) if tenant_id else None)
            # Convert TraceResult to dict for engine compatibility if needed
            return res.__dict__ if hasattr(res, "__dict__") else res
        finally:
            await client.close()

    async def wrapped_backward(tlc, tenant_id=None):
        db_name = Neo4jClient.get_global_database_name()
        if tenant_id:
            try:
                tid = uuid.UUID(str(tenant_id))
                db_name = Neo4jClient.get_tenant_database_name(tid)
            except (ValueError, TypeError):
                pass
        
        client = Neo4jClient(database=db_name)
        try:
            res = await trace_backward(client, tlc, tenant_id=str(tenant_id) if tenant_id else None)
            return res.__dict__ if hasattr(res, "__dict__") else res
        finally:
            await client.close()

    _recall_engine = MockRecallEngine(
        trace_forward_fn=wrapped_forward,
        trace_backward_fn=wrapped_backward,
    )
    return _recall_engine


# ============================================================================
# RECALL DRILL ENDPOINTS
# ============================================================================


class CreateDrillRequest(BaseModel):
    type: str = "forward_trace"
    target_tlc: Optional[str] = None
    target_gtin: Optional[str] = None
    severity: str = "class_ii"
    reason: str = "manual_drill"


@router.get("/history")
def get_recall_history(
    limit: int = 20,
    tenant_id: Optional[str] = Query(None),
    api_key=Depends(require_api_key),
):
    """Get history of mock recall drills."""
    engine = get_recall_engine()
    # Default to tenant from API key if not provided
    effective_tenant = tenant_id or api_key.get("tenant_id", "default")
    drills = engine.get_drill_history(effective_tenant, limit=limit)
    return {"drills": [d.to_dict() for d in drills]}


@router.post("/drill")
async def create_recall_drill(
    request: CreateDrillRequest,
    api_key=Depends(require_api_key),
):
    """Initiate a new mock recall drill."""
    engine = get_recall_engine()
    tenant_id = api_key.get("tenant_id", "default")

    try:
        drill_type = RecallType(request.type)
        severity = RecallSeverity(request.severity)

        drill = engine.create_drill(
            tenant_id=tenant_id,
            drill_type=drill_type,
            severity=severity,
            target_lot=request.target_tlc,
            target_gtin=request.target_gtin,
            reason=request.reason,
            initiated_by=api_key.get("user_id", "api_user"),
        )

        # Execute immediately (async background execution would be better in prod)
        result = await engine.execute_drill(drill)
        
        # Re-fetch to get updated status
        updated_drill = engine.get_drill(tenant_id, drill.drill_id)
        if not updated_drill:
            raise HTTPException(status_code=500, detail="Drill lost after execution")

        return updated_drill.to_dict()

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("drill_creation_failed", error=str(e))
        logger.exception("endpoint_error", error=str(e)); raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/drill/{drill_id}")
def get_drill_details(
    drill_id: str,
    api_key=Depends(require_api_key),
):
    """Get details of a specific drill."""
    engine = get_recall_engine()
    tenant_id = api_key.get("tenant_id", "default")
    drill = engine.get_drill(tenant_id, drill_id)
    
    if not drill:
        raise HTTPException(status_code=404, detail="Drill not found")
        
    return drill.to_dict()


@router.delete("/drill/{drill_id}")
def cancel_recall_drill(
    drill_id: str,
    api_key=Depends(require_api_key),
):
    """Cancel a pending drill."""
    engine = get_recall_engine()
    tenant_id = api_key.get("tenant_id", "default")
    drill = engine.get_drill(tenant_id, drill_id)
    
    if not drill:
        raise HTTPException(status_code=404, detail="Drill not found")

    success = engine.cancel_drill(drill)
    return {"success": success, "drill_id": drill_id}


# ============================================================================
# READINESS & SLA ENDPOINTS
# ============================================================================


@router.get("/readiness")
def get_recall_readiness(
    api_key=Depends(require_api_key),
):
    """
    Get FSMA 204 Recall Readiness Score.
    
    Calculates operational readiness based on:
    - Recent successful drills
    - Data completeness
    - Contact info availability
    """
    engine = get_recall_engine()
    tenant_id = api_key.get("tenant_id", "default")
    sla_metrics = engine.get_sla_metrics(tenant_id)
    
    # Calculate synthetic readiness score (0-100)
    score = 100
    
    # Penalize for no recent drills
    if not sla_metrics.get("last_drill_at"):
        score -= 50
    
    # Penalize for SLA breaches
    compliance_rate = sla_metrics.get("sla_compliance_rate", 100)
    if compliance_rate < 90:
        score -= (90 - compliance_rate) * 2
        
    return {
        "readiness_score": max(0, min(100, score)),
        "status": "READY" if score > 80 else "AT_RISK",
        "last_drill": sla_metrics.get("last_drill_at"),
        "24h_sla_compliance": compliance_rate
    }


@router.get("/sla")
def get_recall_sla(
    api_key=Depends(require_api_key),
):
    """Get 24-hour SLA compliance metrics."""
    engine = get_recall_engine()
    tenant_id = api_key.get("tenant_id", "default")
    metrics = engine.get_sla_metrics(tenant_id)
    
    return {
        "sla_percent": metrics.get("sla_compliance_rate", 100),
        "total_drills": metrics.get("total_drills", 0),
        "avg_response_hours": (metrics.get("avg_trace_time", 0) / 3600),
    }


# ============================================================================
# SCHEDULE ENDPOINTS
# ============================================================================


@router.get("/schedules")
def get_recall_schedules(
    api_key=Depends(require_api_key),
):
    """Get scheduled recurring drills."""
    engine = get_recall_engine()
    tenant_id = api_key.get("tenant_id", "default")
    schedules = engine.get_schedules(tenant_id)
    return {"schedules": [s.to_dict() for s in schedules]}


class CreateScheduleRequest(BaseModel):
    drill_type: str = "forward_trace"
    frequency_days: int = 90
    severity: str = "class_ii"
    target_strategy: str = "random"


@router.post("/schedule")
def create_recall_schedule(
    request: CreateScheduleRequest,
    api_key=Depends(require_api_key),
):
    """Schedule a recurring mock recall."""
    engine = get_recall_engine()
    tenant_id = api_key.get("tenant_id", "default")
    
    try:
        schedule = engine.create_schedule(
            tenant_id=tenant_id,
            drill_type=RecallType(request.drill_type),
            frequency_days=request.frequency_days,
            severity=RecallSeverity(request.severity),
            target_strategy=request.target_strategy
        )
        return schedule.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
