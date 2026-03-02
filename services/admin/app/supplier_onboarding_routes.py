from __future__ import annotations

import uuid as uuid_module
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.database import get_session
from app.dependencies import get_current_user
from app.models import TenantContext
from app.sqlalchemy_models import (
    SupplierCTEEventModel,
    SupplierFacilityFTLCategoryModel,
    SupplierFacilityModel,
    SupplierTraceabilityLotModel,
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


SUPPORTED_CTE_TYPES = {
    "shipping",
    "receiving",
    "transforming",
    "harvesting",
    "cooling",
    "initial_packing",
    "first_receiver",
}


class SupplierCTEEventCreateRequest(BaseModel):
    cte_type: str = Field(min_length=2)
    tlc_code: str = Field(min_length=3)
    event_time: datetime | None = None
    kde_data: dict[str, Any] = Field(default_factory=dict)
    obligation_ids: list[str] = Field(default_factory=list)


class SupplierCTEEventResponse(BaseModel):
    event_id: str
    facility_id: str
    tlc_code: str
    cte_type: str
    payload_sha256: str
    merkle_hash: str
    merkle_prev_hash: str | None
    merkle_sequence: int


class SupplierTLCUpsertRequest(BaseModel):
    facility_id: str
    tlc_code: str = Field(min_length=3)
    product_description: str | None = None
    status: str | None = "active"


class SupplierTLCResponse(BaseModel):
    id: str
    facility_id: str
    tlc_code: str
    product_description: str | None
    status: str
    event_count: int
    created_at: str


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


def _sha256_json(payload: dict[str, Any]) -> str:
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _next_merkle_hash(prev_hash: str | None, payload_sha256: str) -> str:
    if prev_hash is None:
        seed = f"GENESIS:{payload_sha256}"
    else:
        seed = f"{prev_hash}:{payload_sha256}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).isoformat()
    return value.astimezone(timezone.utc).isoformat()


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


@router.post("/facilities/{facility_id}/cte-events", response_model=SupplierCTEEventResponse)
async def submit_cte_event(
    facility_id: str,
    request: SupplierCTEEventCreateRequest,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> SupplierCTEEventResponse:
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

    cte_type = request.cte_type.strip().lower()
    if cte_type not in SUPPORTED_CTE_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported cte_type: {request.cte_type}")

    tlc_code = request.tlc_code.strip()
    if not tlc_code:
        raise HTTPException(status_code=400, detail="tlc_code is required")

    event_time = request.event_time or datetime.now(timezone.utc)
    payload = {
        "facility_id": str(facility.id),
        "cte_type": cte_type,
        "tlc_code": tlc_code,
        "event_time": _iso_utc(event_time),
        "kde_data": request.kde_data,
    }
    payload_sha256 = _sha256_json(payload)

    lot = db.execute(
        select(SupplierTraceabilityLotModel).where(
            SupplierTraceabilityLotModel.tenant_id == tenant_id,
            SupplierTraceabilityLotModel.supplier_user_id == current_user.id,
            SupplierTraceabilityLotModel.tlc_code == tlc_code,
        )
    ).scalar_one_or_none()

    if lot is None:
        lot = SupplierTraceabilityLotModel(
            tenant_id=tenant_id,
            supplier_user_id=current_user.id,
            facility_id=facility.id,
            tlc_code=tlc_code,
            product_description=(request.kde_data.get("product_description") if isinstance(request.kde_data, dict) else None),
            status="active",
        )
        db.add(lot)
        db.flush()

    previous_event = db.execute(
        select(SupplierCTEEventModel)
        .where(SupplierCTEEventModel.tenant_id == tenant_id)
        .order_by(SupplierCTEEventModel.sequence_number.desc())
        .limit(1)
    ).scalar_one_or_none()

    merkle_prev_hash = previous_event.merkle_hash if previous_event else None
    sequence_number = int(previous_event.sequence_number + 1) if previous_event else 1
    merkle_hash = _next_merkle_hash(merkle_prev_hash, payload_sha256)

    event = SupplierCTEEventModel(
        tenant_id=tenant_id,
        supplier_user_id=current_user.id,
        facility_id=facility.id,
        lot_id=lot.id,
        cte_type=cte_type,
        event_time=event_time,
        kde_data=request.kde_data,
        payload_sha256=payload_sha256,
        merkle_prev_hash=merkle_prev_hash,
        merkle_hash=merkle_hash,
        sequence_number=sequence_number,
        obligation_ids=request.obligation_ids,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    supplier_graph_sync.record_cte_event(
        tenant_id=str(tenant_id),
        facility_id=str(facility.id),
        facility_name=facility.name,
        cte_event_id=str(event.id),
        cte_type=cte_type,
        event_time=_iso_utc(event.event_time),
        tlc_code=lot.tlc_code,
        product_description=lot.product_description,
        lot_status=lot.status,
        kde_data=event.kde_data or {},
        payload_sha256=event.payload_sha256,
        merkle_prev_hash=event.merkle_prev_hash,
        merkle_hash=event.merkle_hash,
        sequence_number=int(event.sequence_number),
        obligation_ids=event.obligation_ids or [],
    )

    return SupplierCTEEventResponse(
        event_id=str(event.id),
        facility_id=str(facility.id),
        tlc_code=lot.tlc_code,
        cte_type=event.cte_type,
        payload_sha256=event.payload_sha256,
        merkle_hash=event.merkle_hash,
        merkle_prev_hash=event.merkle_prev_hash,
        merkle_sequence=int(event.sequence_number),
    )


@router.post("/tlcs", response_model=SupplierTLCResponse)
async def create_tlc(
    request: SupplierTLCUpsertRequest,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> SupplierTLCResponse:
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    try:
        facility_uuid = uuid_module.UUID(request.facility_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid facility id") from exc

    _get_supplier_facility_or_404(
        db,
        tenant_id=tenant_id,
        supplier_user_id=current_user.id,
        facility_id=facility_uuid,
    )

    existing = db.execute(
        select(SupplierTraceabilityLotModel).where(
            SupplierTraceabilityLotModel.tenant_id == tenant_id,
            SupplierTraceabilityLotModel.supplier_user_id == current_user.id,
            SupplierTraceabilityLotModel.tlc_code == request.tlc_code.strip(),
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="TLC already exists")

    lot = SupplierTraceabilityLotModel(
        tenant_id=tenant_id,
        supplier_user_id=current_user.id,
        facility_id=facility_uuid,
        tlc_code=request.tlc_code.strip(),
        product_description=request.product_description.strip() if request.product_description else None,
        status=(request.status or "active").strip().lower(),
    )
    db.add(lot)
    db.commit()
    db.refresh(lot)

    return SupplierTLCResponse(
        id=str(lot.id),
        facility_id=str(lot.facility_id),
        tlc_code=lot.tlc_code,
        product_description=lot.product_description,
        status=lot.status,
        event_count=0,
        created_at=_iso_utc(lot.created_at),
    )


@router.get("/tlcs", response_model=list[SupplierTLCResponse])
async def list_tlcs(
    facility_id: str | None = None,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> list[SupplierTLCResponse]:
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    lot_query = select(SupplierTraceabilityLotModel).where(
        SupplierTraceabilityLotModel.tenant_id == tenant_id,
        SupplierTraceabilityLotModel.supplier_user_id == current_user.id,
    )

    if facility_id:
        try:
            facility_uuid = uuid_module.UUID(facility_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid facility id") from exc
        _get_supplier_facility_or_404(
            db,
            tenant_id=tenant_id,
            supplier_user_id=current_user.id,
            facility_id=facility_uuid,
        )
        lot_query = lot_query.where(SupplierTraceabilityLotModel.facility_id == facility_uuid)

    lots = db.execute(lot_query.order_by(SupplierTraceabilityLotModel.created_at.desc())).scalars().all()
    if not lots:
        return []

    lot_ids = [lot.id for lot in lots]
    counts = db.execute(
        select(
            SupplierCTEEventModel.lot_id,
            func.count(SupplierCTEEventModel.id),
        )
        .where(
            SupplierCTEEventModel.tenant_id == tenant_id,
            SupplierCTEEventModel.lot_id.in_(lot_ids),
        )
        .group_by(SupplierCTEEventModel.lot_id)
    ).all()
    count_map = {lot_id: int(count) for lot_id, count in counts}

    return [
        SupplierTLCResponse(
            id=str(lot.id),
            facility_id=str(lot.facility_id),
            tlc_code=lot.tlc_code,
            product_description=lot.product_description,
            status=lot.status,
            event_count=count_map.get(lot.id, 0),
            created_at=_iso_utc(lot.created_at),
        )
        for lot in lots
    ]
