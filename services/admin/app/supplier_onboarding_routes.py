from __future__ import annotations

import uuid as uuid_module
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database import get_session
from app.dependencies import get_current_user
from app.models import TenantContext
from app.sqlalchemy_models import (
    SupplierFacilityFTLCategoryModel,
    SupplierFacilityModel,
    UserModel,
)
from app.supplier_graph_sync import supplier_graph_sync


router = APIRouter(prefix="/supplier", tags=["supplier-onboarding"])


FTL_CATEGORY_CATALOG = [
    {"id": "1", "name": "Fruits (fresh-cut)", "ctes": ["receiving", "transforming", "shipping"]},
    {
        "id": "2",
        "name": "Vegetables (leafy greens)",
        "ctes": ["harvesting", "cooling", "initial_packing", "receiving", "transforming", "shipping"],
    },
    {"id": "3", "name": "Shell eggs", "ctes": ["initial_packing", "receiving", "shipping"]},
    {"id": "4", "name": "Nut butter", "ctes": ["receiving", "transforming", "shipping"]},
    {"id": "5", "name": "Fresh herbs", "ctes": ["harvesting", "cooling", "initial_packing", "receiving", "shipping"]},
    {"id": "6", "name": "Finfish (fresh/frozen)", "ctes": ["first_receiver", "receiving", "transforming", "shipping"]},
    {"id": "7", "name": "Crustaceans (fresh/frozen)", "ctes": ["first_receiver", "receiving", "transforming", "shipping"]},
    {"id": "8", "name": "Molluscan shellfish", "ctes": ["harvesting", "first_receiver", "receiving", "shipping"]},
    {"id": "9", "name": "Ready-to-eat deli salads", "ctes": ["receiving", "transforming", "shipping"]},
    {"id": "10", "name": "Soft & semi-soft cheeses", "ctes": ["receiving", "transforming", "shipping"]},
]

FTL_CATEGORY_LOOKUP = {item["id"]: item for item in FTL_CATEGORY_CATALOG}


class SupplierFacilityCreateRequest(BaseModel):
    name: str = Field(min_length=2)
    street: str = Field(min_length=2)
    city: str = Field(min_length=2)
    state: str = Field(min_length=2)
    postal_code: str = Field(min_length=3)
    fda_registration_number: str | None = None
    roles: list[str] = Field(default_factory=list)


class SupplierFacilityResponse(BaseModel):
    id: str
    name: str
    street: str
    city: str
    state: str
    postal_code: str
    fda_registration_number: str | None
    roles: list[str]


class FacilityFTLScopingRequest(BaseModel):
    category_ids: list[str] = Field(default_factory=list)


class FacilityFTLScopingResponse(BaseModel):
    facility_id: str
    categories: list[dict[str, Any]]
    required_ctes: list[str]
    source: str


def _get_supplier_facility_or_404(
    db: Session,
    *,
    tenant_id: uuid_module.UUID,
    supplier_user_id: uuid_module.UUID,
    facility_id: uuid_module.UUID,
) -> SupplierFacilityModel:
    facility = db.get(SupplierFacilityModel, facility_id)
    if (
        facility is None
        or facility.tenant_id != tenant_id
        or facility.supplier_user_id != supplier_user_id
    ):
        raise HTTPException(status_code=404, detail="Facility not found")
    return facility


def _derive_required_ctes(categories: list[dict[str, Any]]) -> list[str]:
    required_ctes: list[str] = []
    seen: set[str] = set()
    for category in categories:
        for cte in category.get("ctes", []):
            if cte in seen:
                continue
            seen.add(cte)
            required_ctes.append(cte)
    return required_ctes


@router.get("/ftl-categories")
async def get_ftl_categories() -> dict[str, list[dict[str, Any]]]:
    return {"categories": FTL_CATEGORY_CATALOG}


@router.post("/facilities", response_model=SupplierFacilityResponse)
async def create_supplier_facility(
    request: SupplierFacilityCreateRequest,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> SupplierFacilityResponse:
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    facility = SupplierFacilityModel(
        tenant_id=tenant_id,
        supplier_user_id=current_user.id,
        name=request.name.strip(),
        street=request.street.strip(),
        city=request.city.strip(),
        state=request.state.strip(),
        postal_code=request.postal_code.strip(),
        fda_registration_number=(request.fda_registration_number.strip() if request.fda_registration_number else None),
        roles=[role.strip() for role in request.roles if role.strip()],
    )
    db.add(facility)
    db.commit()
    db.refresh(facility)

    return SupplierFacilityResponse(
        id=str(facility.id),
        name=facility.name,
        street=facility.street,
        city=facility.city,
        state=facility.state,
        postal_code=facility.postal_code,
        fda_registration_number=facility.fda_registration_number,
        roles=facility.roles or [],
    )


@router.put("/facilities/{facility_id}/ftl-categories", response_model=FacilityFTLScopingResponse)
async def set_facility_ftl_categories(
    facility_id: str,
    request: FacilityFTLScopingRequest,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> FacilityFTLScopingResponse:
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    try:
        facility_uuid = uuid_module.UUID(facility_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid facility id") from exc

    facility = _get_supplier_facility_or_404(
        db,
        tenant_id=tenant_id,
        supplier_user_id=current_user.id,
        facility_id=facility_uuid,
    )

    categories: list[dict[str, Any]] = []
    for category_id in request.category_ids:
        normalized_id = str(category_id)
        category = FTL_CATEGORY_LOOKUP.get(normalized_id)
        if category is None:
            raise HTTPException(status_code=400, detail=f"Unknown FTL category id: {normalized_id}")
        categories.append(category)

    db.execute(
        delete(SupplierFacilityFTLCategoryModel).where(
            SupplierFacilityFTLCategoryModel.facility_id == facility_uuid,
            SupplierFacilityFTLCategoryModel.tenant_id == tenant_id,
        )
    )

    for category in categories:
        db.add(
            SupplierFacilityFTLCategoryModel(
                tenant_id=tenant_id,
                facility_id=facility_uuid,
                category_id=category["id"],
                category_name=category["name"],
                required_ctes=category["ctes"],
            )
        )

    db.commit()

    supplier_graph_sync.record_facility_ftl_scoping(
        tenant_id=str(tenant_id),
        facility_id=str(facility.id),
        facility_name=facility.name,
        supplier_user_id=str(current_user.id),
        supplier_email=current_user.email,
        street=facility.street,
        city=facility.city,
        state=facility.state,
        postal_code=facility.postal_code,
        fda_registration_number=facility.fda_registration_number,
        roles=facility.roles or [],
        categories=categories,
    )

    return FacilityFTLScopingResponse(
        facility_id=str(facility.id),
        categories=categories,
        required_ctes=_derive_required_ctes(categories),
        source="postgres",
    )


@router.get("/facilities/{facility_id}/required-ctes", response_model=FacilityFTLScopingResponse)
async def get_required_ctes(
    facility_id: str,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> FacilityFTLScopingResponse:
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    try:
        facility_uuid = uuid_module.UUID(facility_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid facility id") from exc

    facility = _get_supplier_facility_or_404(
        db,
        tenant_id=tenant_id,
        supplier_user_id=current_user.id,
        facility_id=facility_uuid,
    )

    graph_payload = supplier_graph_sync.get_required_ctes_for_facility(str(facility.id))
    if graph_payload is not None:
        return FacilityFTLScopingResponse(
            facility_id=str(facility.id),
            categories=graph_payload.get("categories", []),
            required_ctes=graph_payload.get("required_ctes", []),
            source=graph_payload.get("source", "neo4j"),
        )

    category_rows = db.execute(
        select(SupplierFacilityFTLCategoryModel).where(
            SupplierFacilityFTLCategoryModel.tenant_id == tenant_id,
            SupplierFacilityFTLCategoryModel.facility_id == facility_uuid,
        )
    ).scalars().all()

    categories = [
        {
            "id": row.category_id,
            "name": row.category_name,
            "ctes": row.required_ctes or [],
        }
        for row in category_rows
    ]

    return FacilityFTLScopingResponse(
        facility_id=str(facility.id),
        categories=categories,
        required_ctes=_derive_required_ctes(categories),
        source="postgres",
    )
