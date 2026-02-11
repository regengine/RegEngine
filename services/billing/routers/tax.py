"""
Tax Router — Tax calculation and management API.

Endpoints for calculating tax, managing jurisdictions,
exemptions, and generating tax reports.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel
from typing import Optional

from tax_engine import tax_engine, ExemptionReason

router = APIRouter(prefix="/v1/billing/tax", tags=["Tax"])


# ── Request Models ─────────────────────────────────────────────────

class CalculateTaxRequest(BaseModel):
    tenant_id: str
    jurisdiction_id: str
    subtotal_cents: int
    is_digital: bool = True


class AddExemptionRequest(BaseModel):
    tenant_id: str
    tenant_name: str
    jurisdiction_id: str
    reason: ExemptionReason
    certificate_number: str = ""


# ── Endpoints ──────────────────────────────────────────────────────

@router.post("/calculate")
async def calculate_tax(request: CalculateTaxRequest):
    """Calculate tax for a transaction."""
    try:
        result = tax_engine.calculate_tax(
            tenant_id=request.tenant_id,
            jurisdiction_id=request.jurisdiction_id,
            subtotal_cents=request.subtotal_cents,
            is_digital=request.is_digital,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"calculation": result.model_dump()}


@router.get("/jurisdictions")
async def list_jurisdictions(country: Optional[str] = Query(None)):
    """List available tax jurisdictions."""
    jurs = tax_engine.list_jurisdictions(country=country)
    return {"jurisdictions": [j.model_dump() for j in jurs], "total": len(jurs)}


@router.get("/exemptions")
async def list_exemptions(tenant_id: Optional[str] = Query(None)):
    """List tax exemptions."""
    exemptions = tax_engine.list_exemptions(tenant_id=tenant_id)
    return {"exemptions": [e.model_dump() for e in exemptions], "total": len(exemptions)}


@router.post("/exemptions")
async def add_exemption(request: AddExemptionRequest):
    """Register a new tax exemption."""
    try:
        exemption = tax_engine.add_exemption(
            tenant_id=request.tenant_id,
            tenant_name=request.tenant_name,
            jurisdiction_id=request.jurisdiction_id,
            reason=request.reason,
            certificate_number=request.certificate_number,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"exemption": exemption.model_dump(), "message": "Exemption registered (pending verification)"}


@router.post("/exemptions/{exemption_id}/verify")
async def verify_exemption(exemption_id: str = Path(...)):
    """Verify a tax exemption certificate."""
    try:
        exemption = tax_engine.verify_exemption(exemption_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"exemption": exemption.model_dump(), "message": "Exemption verified"}


@router.get("/report")
async def tax_report(period: Optional[str] = Query(None)):
    """Tax liability report by jurisdiction."""
    return tax_engine.get_tax_report(period=period)
