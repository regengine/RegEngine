"""
Dunning Router — Payment recovery and collections API.

Endpoints for managing dunning cases, retrying payments,
escalating cases, and viewing recovery metrics.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from pydantic import BaseModel, Field
from typing import Optional

from dunning_engine import DunningEngine, DunningStatus, DunningStage
from dependencies import get_dunning_engine
from utils import paginate

router = APIRouter(prefix="/v1/billing/dunning", tags=["Dunning"])


# ── Request Models ─────────────────────────────────────────────────

class OpenCaseRequest(BaseModel):
    tenant_id: str
    tenant_name: str
    invoice_id: str
    invoice_number: str = ""
    amount_due_cents: int = Field(..., gt=0)


# ── Endpoints ──────────────────────────────────────────────────────

@router.post("")
async def open_case(
    request: OpenCaseRequest,
    engine: DunningEngine = Depends(get_dunning_engine),
):
    """Open a new dunning case for a failed payment."""
    case = engine.open_case(
        tenant_id=request.tenant_id,
        tenant_name=request.tenant_name,
        invoice_id=request.invoice_id,
        invoice_number=request.invoice_number,
        amount_due_cents=request.amount_due_cents,
    )
    return {"case": case.model_dump(), "message": f"Dunning case opened for {request.tenant_name}"}


@router.get("")
async def list_cases(
    status: Optional[DunningStatus] = Query(None),
    stage: Optional[DunningStage] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    engine: DunningEngine = Depends(get_dunning_engine),
):
    """List dunning cases with filters and pagination."""
    cases = engine.list_cases(status=status, stage=stage)
    result = paginate([c.model_dump() for c in cases], page=page, page_size=page_size)
    return {
        "cases": result["items"],
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
        "total_pages": result["total_pages"],
        "has_next": result["has_next"],
        "has_prev": result["has_prev"],
    }


@router.get("/summary")
async def dunning_summary(engine: DunningEngine = Depends(get_dunning_engine)):
    """Collections program overview."""
    return engine.get_summary()


@router.get("/{case_id}")
async def get_case(
    case_id: str = Path(...),
    engine: DunningEngine = Depends(get_dunning_engine),
):
    """Get dunning case details."""
    case = engine.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return {"case": case.model_dump()}


@router.post("/{case_id}/retry")
async def retry_payment(
    case_id: str = Path(...),
    engine: DunningEngine = Depends(get_dunning_engine),
):
    """Retry payment collection."""
    try:
        attempt = engine.retry_payment(case_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    case = engine.get_case(case_id)
    return {
        "attempt": attempt.model_dump(),
        "case_status": case.status.value if case else "unknown",
        "case_stage": case.stage.value if case else "unknown",
    }


@router.post("/{case_id}/escalate")
async def escalate_case(
    case_id: str = Path(...),
    engine: DunningEngine = Depends(get_dunning_engine),
):
    """Manually escalate a dunning case."""
    try:
        case = engine.escalate_case(case_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"case": case.model_dump(), "message": f"Escalated to {case.stage.value}"}


@router.post("/{case_id}/write-off")
async def write_off(
    case_id: str = Path(...),
    engine: DunningEngine = Depends(get_dunning_engine),
):
    """Write off a case as uncollectible."""
    try:
        case = engine.write_off(case_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"case": case.model_dump(), "message": "Case written off"}
