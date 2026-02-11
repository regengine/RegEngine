"""
Contracts Router — Enterprise deal management API.

Endpoints for contract lifecycle, quote generation, pipeline views,
SLA monitoring, and renewal tracking.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel
from typing import Optional

from contract_engine import contract_engine, DealStage, ContractType
from utils import format_cents, paginate

router = APIRouter(prefix="/v1/billing/contracts", tags=["Contracts"])


# ── Request Models ─────────────────────────────────────────────────

class CreateContractRequest(BaseModel):
    tenant_id: str
    tenant_name: str
    tier_id: str = "enterprise"
    contract_type: ContractType = ContractType.ENTERPRISE
    term_years: int = 1
    owner: str = "sales@regengine.co"
    notes: str = ""


class AdvanceStageRequest(BaseModel):
    new_stage: DealStage


class GenerateQuoteRequest(BaseModel):
    discount_codes: list[str] = []
    custom_discount_pct: float = 0
    notes: str = ""


# ── Endpoints ──────────────────────────────────────────────────────

@router.post("")
async def create_contract(request: CreateContractRequest):
    """Create a new enterprise deal/contract."""
    contract = contract_engine.create_contract(
        tenant_id=request.tenant_id,
        tenant_name=request.tenant_name,
        tier_id=request.tier_id,
        contract_type=request.contract_type,
        term_years=request.term_years,
        owner=request.owner,
        notes=request.notes,
    )
    return {
        "contract": contract.model_dump(),
        "message": f"Contract created for {request.tenant_name}",
    }


@router.get("")
async def list_contracts(
    stage: Optional[DealStage] = Query(None),
    owner: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """List all contracts with optional filters and pagination."""
    contracts = contract_engine.list_contracts(stage=stage, owner=owner)
    result = paginate([c.model_dump() for c in contracts], page=page, page_size=page_size)
    return {
        "contracts": result["items"],
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
        "total_pages": result["total_pages"],
        "has_next": result["has_next"],
        "has_prev": result["has_prev"],
    }


@router.get("/pipeline")
async def deal_pipeline():
    """Visual deal pipeline summary by stage."""
    return contract_engine.get_pipeline()


@router.get("/sla-status")
async def sla_status():
    """SLA compliance for all active contracts."""
    statuses = contract_engine.get_sla_status()
    passing = sum(1 for s in statuses if s["compliance"] == "passing")
    breached = sum(1 for s in statuses if s["compliance"] == "breached")
    return {
        "statuses": statuses,
        "summary": {
            "total": len(statuses),
            "passing": passing,
            "breached": breached,
            "compliance_rate": round(passing / max(len(statuses), 1) * 100, 1),
        },
    }


@router.get("/renewals")
async def upcoming_renewals(days: int = Query(90, ge=7, le=365)):
    """Contracts approaching renewal."""
    renewals = contract_engine.get_upcoming_renewals(days_ahead=days)
    return {
        "renewals": renewals,
        "total": len(renewals),
        "total_acv_at_risk_cents": sum(r["acv_cents"] for r in renewals),
        "total_acv_at_risk_display": format_cents(sum(r['acv_cents'] for r in renewals)),
    }


@router.get("/{contract_id}")
async def get_contract(contract_id: str = Path(...)):
    """Get contract details."""
    contract = contract_engine.get_contract(contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail=f"Contract {contract_id} not found")
    return {"contract": contract.model_dump()}


@router.patch("/{contract_id}/stage")
async def advance_stage(
    request: AdvanceStageRequest,
    contract_id: str = Path(...),
):
    """Advance a deal through the pipeline."""
    try:
        contract = contract_engine.advance_stage(contract_id, request.new_stage)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "contract": contract.model_dump(),
        "message": f"Deal advanced to {request.new_stage.value}",
    }


@router.post("/{contract_id}/quote")
async def generate_quote(
    request: GenerateQuoteRequest,
    contract_id: str = Path(...),
):
    """Generate a quote with discount modeling."""
    try:
        quote = contract_engine.generate_quote(
            contract_id=contract_id,
            discount_codes=request.discount_codes,
            custom_discount_pct=request.custom_discount_pct,
            notes=request.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "quote": quote.model_dump(),
        "message": f"Quote generated: {format_cents(quote.total_contract_value_cents)} TCV",
    }
