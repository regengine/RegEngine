from __future__ import annotations

from typing import List, Optional
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
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

from shared.rate_limit import limiter

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
@limiter.limit("10/minute")
async def create_recall_drill(
    request: Request,
    payload: CreateDrillRequest,
    api_key=Depends(require_api_key),
):
    """Initiate a new mock recall drill."""
    engine = get_recall_engine()
    tenant_id = api_key.get("tenant_id", "default")

    try:
        drill_type = RecallType(payload.type)
        severity = RecallSeverity(payload.severity)

        drill = engine.create_drill(
            tenant_id=tenant_id,
            drill_type=drill_type,
            severity=severity,
            target_lot=payload.target_tlc,
            target_gtin=payload.target_gtin,
            reason=payload.reason,
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
async def get_recall_readiness(
    api_key=Depends(require_api_key),
):
    """
    Get FSMA 204 Recall Readiness Score.

    Calculates operational readiness based on CTE record quality over the
    last 90 days.  A CTE is considered *complete* when all three required
    KDEs are present: quantity, unit_of_measure, and product_description.

    Score = complete_ctes / total_ctes * 100  (0 when no CTEs exist).
    """
    engine = get_recall_engine()
    tenant_id = api_key.get("tenant_id", "default")

    # Query CTE quality from Neo4j for this tenant over the last 90 days.
    cte_count = 0
    complete_cte_count = 0
    incomplete_kde_count = 0
    neo4j_error: Optional[str] = None
    try:
        db_name = Neo4jClient.get_global_database_name()
        try:
            tid = uuid.UUID(str(tenant_id))
            db_name = Neo4jClient.get_tenant_database_name(tid)
        except (ValueError, TypeError):
            pass

        client = Neo4jClient(database=db_name)
        try:
            async with client.session() as session:
                result = await session.run(
                    """
                    MATCH (e:TraceEvent)
                    WHERE e.tenant_id = $tenant_id
                      AND e.timestamp >= datetime() - duration('P90D')
                    RETURN
                        count(e) AS total,
                        sum(CASE
                            WHEN e.quantity IS NOT NULL
                             AND e.unit_of_measure IS NOT NULL
                             AND e.product_description IS NOT NULL
                            THEN 1 ELSE 0
                        END) AS complete,
                        sum(CASE
                            WHEN e.quantity IS NULL
                              OR e.unit_of_measure IS NULL
                              OR e.product_description IS NULL
                            THEN 1 ELSE 0
                        END) AS incomplete
                    """,
                    tenant_id=str(tenant_id),
                )
                record = await result.single()
                if record:
                    cte_count = int(record["total"] or 0)
                    complete_cte_count = int(record["complete"] or 0)
                    incomplete_kde_count = int(record["incomplete"] or 0)
        finally:
            await client.close()
    except Exception as exc:
        logger.warning("recall_readiness_cte_query_failed", error=str(exc))
        neo4j_error = str(exc)

    # Derive score from CTE completeness; fall back to drill-based heuristic
    # when Neo4j is unavailable (so the endpoint always returns a useful value).
    if neo4j_error is None:
        score = int(complete_cte_count / cte_count * 100) if cte_count > 0 else 0
    else:
        sla_metrics = engine.get_sla_metrics(tenant_id)
        score = 100
        if not sla_metrics.get("last_drill_at"):
            score -= 50
        compliance_rate = sla_metrics.get("sla_compliance_rate", 100)
        if compliance_rate < 90:
            score -= int((90 - compliance_rate) * 2)
        score = max(0, min(100, score))

    response: dict = {
        "readiness_score": score,
        "status": "READY" if score > 80 else "AT_RISK",
        "cte_count": cte_count,
        "complete_cte_count": complete_cte_count,
        "incomplete_kde_count": incomplete_kde_count,
    }
    if neo4j_error:
        response["warning"] = f"CTE quality data unavailable ({neo4j_error}); score derived from drill history"
    return response


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
