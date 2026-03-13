from __future__ import annotations

import os
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from shared.auth import require_api_key
from .fsma_spreadsheet import generate_fda_csv

router = APIRouter(tags=["fsma-compliance"])


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class ComplianceRequirement(BaseModel):
    id: str
    title: str
    description: str
    category: str | None = None
    priority: str | None = None  # LOW | MEDIUM | HIGH | CRITICAL
    status: str | None = None    # NOT_STARTED | IN_PROGRESS | COMPLIANT | NON_COMPLIANT


class ComplianceChecklist(BaseModel):
    id: str
    name: str
    description: str | None = None
    industry: str
    framework: str | None = None
    version: str | None = None
    requirements: list[ComplianceRequirement] = []
    items: list[ComplianceRequirement] = []


class Industry(BaseModel):
    id: str
    name: str
    description: str | None = None
    checklist_count: int = 0


class ValidationRequest(BaseModel):
    config: dict[str, Any]
    framework: str | None = None
    strict: bool = False


class ValidationError(BaseModel):
    path: str
    message: str
    code: str | None = None


class ValidationWarning(BaseModel):
    path: str
    message: str
    suggestion: str | None = None


class ValidationResult(BaseModel):
    valid: bool
    errors: list[ValidationError] = []
    warnings: list[ValidationWarning] = []


# ---------------------------------------------------------------------------
# FSMA 204 seed data
# ---------------------------------------------------------------------------

_FSMA_204 = "FSMA 204"
_CTE_RECEIVING = "Receiving CTE Records"
_CTE_SHIPPING = "Shipping CTE Records"

_INDUSTRIES: list[Industry] = [
    Industry(id="fresh-produce", name="Fresh Produce", description="Leafy greens, herbs, melons, and fresh-cut produce", checklist_count=1),
    Industry(id="seafood", name="Seafood", description="Finfish, shellfish, and aquaculture products", checklist_count=1),
    Industry(id="dairy", name="Dairy", description="Milk, cheese, yogurt, and cultured dairy products", checklist_count=1),
    Industry(id="deli-prepared", name="Deli & Prepared Foods", description="Ready-to-eat and mixed-ingredient products", checklist_count=1),
    Industry(id="shell-eggs", name="Shell Eggs", description="Fresh and processed shell egg products", checklist_count=1),
]

_PRODUCE_REQS = [
    ComplianceRequirement(id="fp-1", title="Traceability Lot Code (TLC)", description="Assign a unique TLC to each lot of fresh produce at the point of receiving or initial packing.", category="KDE", priority="CRITICAL"),
    ComplianceRequirement(id="fp-2", title=_CTE_RECEIVING, description="Capture grower lot ID, harvest date, and cooling location at the RECEIVING CTE.", category="CTE", priority="HIGH"),
    ComplianceRequirement(id="fp-3", title="Transformation CTE Records", description="Link input TLCs to output TLCs when produce is cut, mixed, or repackaged.", category="CTE", priority="HIGH"),
    ComplianceRequirement(id="fp-4", title=_CTE_SHIPPING, description="Record TLC, quantity, destination, and ship date for every outbound lot.", category="CTE", priority="HIGH"),
    ComplianceRequirement(id="fp-5", title="24-Hour Recall Response", description="Demonstrate ability to produce all required KDE records within 24 hours of an FDA request.", category="Readiness", priority="CRITICAL"),
    ComplianceRequirement(id="fp-6", title="Supplier TLC Linkage", description="Maintain upstream TLC references from direct suppliers for at least 2 years.", category="Records", priority="MEDIUM"),
]

_SEAFOOD_REQS = [
    ComplianceRequirement(id="sf-1", title="Source Vessel / Harvest Reference", description="Record source vessel name or aquaculture site ID as a KDE for all finfish and shellfish.", category="KDE", priority="CRITICAL"),
    ComplianceRequirement(id="sf-2", title="Landing Date KDE", description="Capture the date seafood was landed or harvested as part of the HARVESTING CTE.", category="KDE", priority="HIGH"),
    ComplianceRequirement(id="sf-3", title="Temperature Log", description="Maintain cold-chain temperature records throughout the supply chain as a supporting KDE.", category="KDE", priority="HIGH"),
    ComplianceRequirement(id="sf-4", title=_CTE_RECEIVING, description="Document TLC, quantity, supplier reference, and receiving date at each receiving point.", category="CTE", priority="HIGH"),
    ComplianceRequirement(id="sf-5", title="Lot Transformation Linkage", description="Link input lots to output lots when fish is processed, portioned, or repackaged.", category="CTE", priority="HIGH"),
    ComplianceRequirement(id="sf-6", title=_CTE_SHIPPING, description="Record TLC, destination, ship date, and quantity for every outbound seafood lot.", category="CTE", priority="HIGH"),
]

_DAIRY_REQS = [
    ComplianceRequirement(id="da-1", title="Supplier Lot KDE", description="Capture the supplier's lot number for all incoming dairy ingredients as a receiving KDE.", category="KDE", priority="CRITICAL"),
    ComplianceRequirement(id="da-2", title="Co-Mingling Event Records", description="Document all lots that were combined during processing, preserving individual lot references.", category="CTE", priority="HIGH"),
    ComplianceRequirement(id="da-3", title="Production Line KDE", description="Record the production line identifier for each finished product batch.", category="KDE", priority="MEDIUM"),
    ComplianceRequirement(id="da-4", title="Hold & Release Status", description="Track hold and release decisions for every lot and link to the associated TLC.", category="KDE", priority="HIGH"),
    ComplianceRequirement(id="da-5", title="Packing CTE Records", description="Record TLC, pack date, package size, and production line at the PACKING CTE.", category="CTE", priority="HIGH"),
    ComplianceRequirement(id="da-6", title=_CTE_SHIPPING, description="Capture TLC, destination, ship date, and quantity at the SHIPPING CTE.", category="CTE", priority="HIGH"),
]

_DELI_REQS = [
    ComplianceRequirement(id="dl-1", title="Input Lot Map", description="Maintain a complete map of all input lot TLCs that contributed to each finished RTE product lot.", category="KDE", priority="CRITICAL"),
    ComplianceRequirement(id="dl-2", title="Recipe Revision KDE", description="Record the recipe or formulation version used for each production batch.", category="KDE", priority="MEDIUM"),
    ComplianceRequirement(id="dl-3", title="Pack Timestamp KDE", description="Capture the date and time of packing for each RTE product lot.", category="KDE", priority="HIGH"),
    ComplianceRequirement(id="dl-4", title=_CTE_RECEIVING, description="Document TLC, supplier lot, and receiving date for all incoming ingredients.", category="CTE", priority="HIGH"),
    ComplianceRequirement(id="dl-5", title="Transformation CTE Records", description="Link all input TLCs to output TLCs for every transformation step.", category="CTE", priority="HIGH"),
    ComplianceRequirement(id="dl-6", title=_CTE_SHIPPING, description="Record TLC, destination, ship date, and quantity for outbound RTE lots.", category="CTE", priority="HIGH"),
]

_EGGS_REQS = [
    ComplianceRequirement(id="eg-1", title="Pack Date KDE", description="Record the Julian pack date on every carton and in traceability records.", category="KDE", priority="CRITICAL"),
    ComplianceRequirement(id="eg-2", title="Facility Registration Number", description="Capture the FDA facility registration number as a KDE at the packing facility.", category="KDE", priority="HIGH"),
    ComplianceRequirement(id="eg-3", title="Distributor Reference KDE", description="Maintain distributor name and reference number linking packed lots to downstream buyers.", category="KDE", priority="HIGH"),
    ComplianceRequirement(id="eg-4", title=_CTE_RECEIVING, description="Document incoming flock source, lay date range, and quantity at receiving.", category="CTE", priority="HIGH"),
    ComplianceRequirement(id="eg-5", title="Packing CTE Records", description="Record pack date, facility registration, lot size, and carton count at packing.", category="CTE", priority="HIGH"),
    ComplianceRequirement(id="eg-6", title=_CTE_SHIPPING, description="Capture TLC, distributor reference, ship date, and quantity at shipping.", category="CTE", priority="HIGH"),
]

_CHECKLISTS: list[ComplianceChecklist] = [
    ComplianceChecklist(
        id="fsma-204-fresh-produce",
        name="FSMA 204 Fresh Produce Traceability",
        description="CTE and KDE compliance checklist for leafy greens, herbs, melons, and fresh-cut produce under FSMA Section 204.",
        industry="Fresh Produce",
        framework=_FSMA_204,
        version="1.0",
        requirements=_PRODUCE_REQS,
        items=_PRODUCE_REQS,
    ),
    ComplianceChecklist(
        id="fsma-204-seafood",
        name="FSMA 204 Seafood Traceability",
        description="CTE and KDE compliance checklist for finfish and shellfish chain-of-custody under FSMA Section 204.",
        industry="Seafood",
        framework=_FSMA_204,
        version="1.0",
        requirements=_SEAFOOD_REQS,
        items=_SEAFOOD_REQS,
    ),
    ComplianceChecklist(
        id="fsma-204-dairy",
        name="FSMA 204 Dairy Traceability",
        description="CTE and KDE compliance checklist for soft cheeses and fluid dairy products under FSMA Section 204.",
        industry="Dairy",
        framework=_FSMA_204,
        version="1.0",
        requirements=_DAIRY_REQS,
        items=_DAIRY_REQS,
    ),
    ComplianceChecklist(
        id="fsma-204-deli-prepared",
        name="FSMA 204 Deli & Prepared Foods Traceability",
        description="CTE and KDE compliance checklist for ready-to-eat and mixed-ingredient products under FSMA Section 204.",
        industry="Deli & Prepared Foods",
        framework=_FSMA_204,
        version="1.0",
        requirements=_DELI_REQS,
        items=_DELI_REQS,
    ),
    ComplianceChecklist(
        id="fsma-204-shell-eggs",
        name="FSMA 204 Shell Egg Traceability",
        description="CTE and KDE compliance checklist for shell eggs under FSMA Section 204.",
        industry="Shell Eggs",
        framework=_FSMA_204,
        version="1.0",
        requirements=_EGGS_REQS,
        items=_EGGS_REQS,
    ),
]

_CHECKLIST_INDEX: dict[str, ComplianceChecklist] = {c.id: c for c in _CHECKLISTS}

# Required FSMA 204 KDE fields for validation
_REQUIRED_FSMA_FIELDS = {"tlc", "cte_type", "event_date", "location"}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/industries", dependencies=[Depends(require_api_key)])
async def list_industries() -> dict:
    return {"industries": [i.model_dump() for i in _INDUSTRIES], "total": len(_INDUSTRIES)}


@router.get("/checklists", dependencies=[Depends(require_api_key)])
async def list_checklists(industry: str | None = None) -> dict:
    results = _CHECKLISTS
    if industry:
        results = [c for c in results if c.industry.lower() == industry.lower()]
    return {"checklists": [c.model_dump() for c in results], "total": len(results)}


@router.get("/checklists/{checklist_id}", dependencies=[Depends(require_api_key)])
async def get_checklist(checklist_id: str) -> ComplianceChecklist:
    checklist = _CHECKLIST_INDEX.get(checklist_id)
    if not checklist:
        raise HTTPException(status_code=404, detail=f"Checklist '{checklist_id}' not found")
    return checklist


@router.post("/validate", dependencies=[Depends(require_api_key)])
async def validate_config(request: ValidationRequest) -> ValidationResult:
    errors: list[ValidationError] = []
    warnings: list[ValidationWarning] = []

    config = request.config
    strict = request.strict

    # Check for required FSMA 204 top-level fields
    for field in _REQUIRED_FSMA_FIELDS:
        if field not in config:
            errors.append(ValidationError(
                path=field,
                message=f"Required FSMA 204 field '{field}' is missing from configuration.",
                code="MISSING_REQUIRED_FIELD",
            ))

    # Warn on missing optional but recommended fields
    recommended = {"lot_size_unit", "supplier_reference", "product_description"}
    for field in recommended:
        if field not in config:
            warnings.append(ValidationWarning(
                path=field,
                message=f"Recommended field '{field}' is not present.",
                suggestion=f"Add '{field}' to improve traceability record completeness.",
            ))

    if strict and warnings:
        for w in warnings:
            errors.append(ValidationError(
                path=w.path,
                message=w.message,
                code="STRICT_MODE_WARNING",
            ))
        warnings = []

    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)


# ---------------------------------------------------------------------------
# FDA Audit Spreadsheet Export
# ---------------------------------------------------------------------------

_GRAPH_SERVICE_URL = os.getenv("GRAPH_SERVICE_URL", "http://localhost:8003")


@router.get("/v1/fsma/audit/spreadsheet", dependencies=[Depends(require_api_key)])
async def fsma_audit_spreadsheet(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    tlc: str | None = Query(None, description="Filter by Traceability Lot Code"),
    requesting_entity: str | None = Query(None, description="Name of requesting entity"),
) -> StreamingResponse:
    """Generate an FDA 204 Sortable Spreadsheet CSV for the given date range."""

    params: dict[str, str] = {
        "start_date": start_date,
        "end_date": end_date,
    }
    if tlc:
        params["tlc"] = tlc

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{_GRAPH_SERVICE_URL}/v1/fsma/traceability/search/events",
            params=params,
        )
        if resp.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"Graph service returned {resp.status_code}: {resp.text[:200]}",
            )
        data = resp.json()

    events = data.get("events") or data.get("results") or []

    csv_content = generate_fda_csv(
        events,
        start_date=start_date,
        end_date=end_date,
        requesting_entity=requesting_entity or "",
    )

    filename = f"fsma_204_audit_{start_date}_{end_date}.csv"
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
