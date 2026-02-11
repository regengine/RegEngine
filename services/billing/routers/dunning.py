"""
Dunning Router — Payment recovery and collections API.

Endpoints for managing dunning cases, retrying payments,
escalating cases, and viewing recovery metrics.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel
from typing import Optional

from dunning_engine import dunning_engine, DunningStatus, DunningStage

router = APIRouter(prefix="/v1/billing/dunning", tags=["Dunning"])


# ── Request Models ─────────────────────────────────────────────────

class OpenCaseRequest(BaseModel):
    tenant_id: str
    tenant_name: str
    invoice_id: str
    invoice_number: str = ""
    amount_due_cents: int


# ── Endpoints ──────────────────────────────────────────────────────

@router.post("")
async def open_case(request: OpenCaseRequest):
    """Open a new dunning case for a failed payment."""
    case = dunning_engine.open_case(
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
):
    """List dunning cases with filters."""
    cases = dunning_engine.list_cases(status=status, stage=stage)
    return {"cases": [c.model_dump() for c in cases], "total": len(cases)}


@router.get("/summary")
async def dunning_summary():
    """Collections program overview."""
    return dunning_engine.get_summary()


@router.get("/{case_id}")
async def get_case(case_id: str = Path(...)):
    """Get dunning case details."""
    case = dunning_engine.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return {"case": case.model_dump()}


@router.post("/{case_id}/retry")
async def retry_payment(case_id: str = Path(...)):
    """Retry payment collection."""
    try:
        attempt = dunning_engine.retry_payment(case_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    case = dunning_engine.get_case(case_id)
    return {
        "attempt": attempt.model_dump(),
        "case_status": case.status.value if case else "unknown",
        "case_stage": case.stage.value if case else "unknown",
    }


@router.post("/{case_id}/escalate")
async def escalate_case(case_id: str = Path(...)):
    """Manually escalate a dunning case."""
    try:
        case = dunning_engine.escalate_case(case_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"case": case.model_dump(), "message": f"Escalated to {case.stage.value}"}


@router.post("/{case_id}/write-off")
async def write_off(case_id: str = Path(...)):
    """Write off a case as uncollectible."""
    try:
        case = dunning_engine.write_off(case_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"case": case.model_dump(), "message": "Case written off"}
