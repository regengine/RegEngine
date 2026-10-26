"""Supplier Facilities sub-router — Facilities CRUD, FTL categories, required CTEs, CTE events, TLCs.

Split from supplier_onboarding_routes.py for maintainability.
All shared models, helpers, and constants are imported from the original module.
"""

from __future__ import annotations

import uuid as uuid_module
from typing import Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query
from shared.pagination import PaginationParams
from sqlalchemy import delete, exists, func, select
from sqlalchemy.orm import Session

from .database import get_session
from .dependencies import PermissionChecker, get_current_user, require_owner
from .models import TenantContext
from .sqlalchemy_models import (
    SupplierCTEEventModel,
    SupplierFacilityFTLCategoryModel,
    SupplierFacilityModel,
    SupplierFunnelEventModel,
    SupplierTraceabilityLotModel,
    UserModel,
)
from .supplier_cte_service import _persist_supplier_cte_event
from .supplier_graph_sync import supplier_graph_sync
from .supplier_onboarding_routes import (
    FTL_CATEGORY_CATALOG,
    FTL_CATEGORY_LOOKUP,
    FacilityFTLScopingRequest,
    FacilityFTLScopingResponse,
    FacilityRemovalCheckResponse,
    SupplierCTEEventCreateRequest,
    SupplierCTEEventResponse,
    SupplierFacilityCreateRequest,
    SupplierFacilityResponse,
    SupplierTLCResponse,
    SupplierTLCUpsertRequest,
    _derive_required_ctes,
    _get_supplier_facility_or_404,
    _iso_utc,
)

router = APIRouter(prefix="/supplier", tags=["supplier-onboarding"])


@router.get("/ftl-categories", response_model=dict[str, list[dict[str, Any]]])
async def get_ftl_categories(
    current_user: UserModel = Depends(get_current_user),
) -> dict[str, list[dict[str, Any]]]:
    """Return the FTL category catalog. Requires authentication."""
    return {"categories": FTL_CATEGORY_CATALOG}


@router.get("/facilities", response_model=dict[str, Any])
async def list_supplier_facilities(
    pagination: PaginationParams = Depends(),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """List all facilities belonging to the current supplier user."""
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    base_filter = [
        SupplierFacilityModel.tenant_id == tenant_id,
        SupplierFacilityModel.supplier_user_id == current_user.id,
    ]

    total = db.execute(select(func.count()).select_from(SupplierFacilityModel).where(*base_filter)).scalar()

    rows = db.scalars(
        select(SupplierFacilityModel)
        .where(*base_filter)
        .order_by(SupplierFacilityModel.created_at.desc())
        .offset(pagination.skip)
        .limit(pagination.limit)
    ).all()

    items = [
        SupplierFacilityResponse(
            id=str(f.id),
            name=f.name,
            street=f.street,
            city=f.city,
            state=f.state,
            postal_code=f.postal_code,
            fda_registration_number=f.fda_registration_number,
            roles=f.roles or [],
        )
        for f in rows
    ]
    return {"items": items, "total": total, "skip": pagination.skip, "limit": pagination.limit}


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


_LINKED_RECORD_MODELS = (
    SupplierTraceabilityLotModel,
    SupplierCTEEventModel,
    SupplierFunnelEventModel,
)


def _linked_record_counts(
    db: Session,
    tenant_id: uuid_module.UUID,
    facility_id: uuid_module.UUID,
) -> tuple[int, int, int]:
    counts: list[int] = []
    for model in _LINKED_RECORD_MODELS:
        counts.append(
            db.execute(
                select(func.count())
                .select_from(model)
                .where(model.tenant_id == tenant_id, model.facility_id == facility_id)
            ).scalar()
            or 0
        )
    return counts[0], counts[1], counts[2]


def _no_linked_records(tenant_id: uuid_module.UUID, facility_id: uuid_module.UUID) -> tuple[Any, ...]:
    """WHERE clauses that match only a facility with no linked rows."""
    return tuple(
        ~exists(
            select(model.id).where(model.tenant_id == tenant_id, model.facility_id == facility_id)
        )
        for model in _LINKED_RECORD_MODELS
    )


def _load_facility_for_removal(
    db: Session,
    facility_id: uuid_module.UUID,
    tenant_id: uuid_module.UUID,
) -> SupplierFacilityModel | None:
    stmt = select(SupplierFacilityModel).where(
        SupplierFacilityModel.id == facility_id,
        SupplierFacilityModel.tenant_id == tenant_id,
    )
    bind = db.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update()
    return db.execute(stmt).scalar_one_or_none()


def _reject_linked_facility(
    facility_name: str,
    lots_count: int,
    cte_events_count: int,
    funnel_events_count: int,
) -> NoReturn:
    raise HTTPException(
        status_code=409,
        detail=(
            f"Cannot remove facility '{facility_name}' with linked records: "
            f"{lots_count} lots/TLCs, {cte_events_count} CTE events, "
            f"{funnel_events_count} other records. "
            f"Delete only when zero linked rows."
        ),
    )


@router.get("/facilities/{facility_id}/removal-check", response_model=FacilityRemovalCheckResponse)
async def check_supplier_facility_removal(
    facility_id: str,
    current_user: UserModel = Depends(get_current_user),
    _perm: bool = Depends(require_owner),
    db: Session = Depends(get_session),
) -> FacilityRemovalCheckResponse:
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    try:
        facility_uuid = uuid_module.UUID(facility_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid facility id") from exc

    facility = db.get(SupplierFacilityModel, facility_uuid)
    if facility is None or facility.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Facility not found")

    lots_count, cte_events_count, funnel_events_count = _linked_record_counts(
        db, tenant_id, facility_uuid
    )

    scoping_config_count = db.execute(
        select(func.count()).select_from(SupplierFacilityFTLCategoryModel).where(
            SupplierFacilityFTLCategoryModel.tenant_id == tenant_id,
            SupplierFacilityFTLCategoryModel.facility_id == facility_uuid,
        )
    ).scalar() or 0

    allowed = (lots_count == 0 and cte_events_count == 0 and funnel_events_count == 0)

    return FacilityRemovalCheckResponse(
        facility_id=str(facility.id),
        facility_name=facility.name,
        allowed=allowed,
        linked_counts={
            "lots": lots_count,
            "events": cte_events_count,
            "cte_events": cte_events_count,
            "records": funnel_events_count,
            "funnel_events": funnel_events_count,
            "scoping_config": scoping_config_count,
        },
        lots_count=lots_count,
        cte_events_count=cte_events_count,
        funnel_events_count=funnel_events_count,
        scoping_config_count=scoping_config_count,
        address={
            "street": facility.street,
            "city": facility.city,
            "state": facility.state,
            "postal_code": facility.postal_code,
        },
    )


@router.delete("/facilities/{facility_id}")
async def delete_supplier_facility(
    facility_id: str,
    current_user: UserModel = Depends(get_current_user),
    _perm: bool = Depends(require_owner),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    try:
        facility_uuid = uuid_module.UUID(facility_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid facility id") from exc

    # Lock the facility on PostgreSQL before counting. A lot or CTE insert
    # takes a key share lock on this row, so it cannot commit until this
    # transaction ends. Lots and CTE events are ON DELETE CASCADE: a count
    # in an earlier statement would miss a row that commits before the
    # DELETE, and the cascade would destroy it.
    facility = _load_facility_for_removal(db, facility_uuid, tenant_id)
    if facility is None:
        raise HTTPException(status_code=404, detail="Facility not found")

    lots_count, cte_events_count, funnel_events_count = _linked_record_counts(
        db, tenant_id, facility_uuid
    )
    if lots_count or cte_events_count or funnel_events_count:
        _reject_linked_facility(facility.name, lots_count, cte_events_count, funnel_events_count)

    facility_name = facility.name
    # The DELETE re-checks linked rows in the same statement. A row that
    # arrived after the count above makes this match nothing, so the
    # cascade never runs.
    result = db.execute(
        delete(SupplierFacilityModel).where(
            SupplierFacilityModel.id == facility_uuid,
            SupplierFacilityModel.tenant_id == tenant_id,
            *_no_linked_records(tenant_id, facility_uuid),
        ),
        execution_options={"synchronize_session": "fetch"},
    )
    if result.rowcount != 1:
        db.rollback()
        if _load_facility_for_removal(db, facility_uuid, tenant_id) is None:
            raise HTTPException(status_code=404, detail="Facility not found")
        lots_count, cte_events_count, funnel_events_count = _linked_record_counts(
            db, tenant_id, facility_uuid
        )
        _reject_linked_facility(facility_name, lots_count, cte_events_count, funnel_events_count)

    # FTL scoping is configuration, not traceability evidence. Postgres
    # already cascades it with the facility; this covers databases that
    # are not enforcing that foreign key.
    db.execute(
        delete(SupplierFacilityFTLCategoryModel).where(
            SupplierFacilityFTLCategoryModel.tenant_id == tenant_id,
            SupplierFacilityFTLCategoryModel.facility_id == facility_uuid,
        )
    )
    db.commit()

    return {
        "status": "deleted",
        "id": str(facility_uuid),
        "facility_name": facility_name,
    }


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

    graph_payload = supplier_graph_sync.get_required_ctes_for_facility(str(facility.id), tenant_id=str(tenant_id))
    # An empty graph payload (no record in Neo4j, or Neo4j down) is not
    # an answer: fall through to the Postgres scoping rows below instead
    # of reporting zero coverage and hiding real FTL scoping.
    if graph_payload is not None and (graph_payload.get("categories") or graph_payload.get("required_ctes")):
        return FacilityFTLScopingResponse(
            facility_id=str(facility.id),
            categories=graph_payload.get("categories", []),
            required_ctes=graph_payload.get("required_ctes", []),
            source=graph_payload.get("source", "neo4j"),
        )

    category_rows = (
        db.execute(
            select(SupplierFacilityFTLCategoryModel).where(
                SupplierFacilityFTLCategoryModel.tenant_id == tenant_id,
                SupplierFacilityFTLCategoryModel.facility_id == facility_uuid,
            )
        )
        .scalars()
        .all()
    )

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

    event, lot = _persist_supplier_cte_event(
        db,
        tenant_id=tenant_id,
        current_user=current_user,
        facility=facility,
        cte_type=request.cte_type,
        tlc_code=request.tlc_code,
        event_time=request.event_time,
        kde_data=request.kde_data,
        obligation_ids=request.obligation_ids,
    )
    db.commit()
    db.refresh(event)

    supplier_graph_sync.record_cte_event(
        tenant_id=str(tenant_id),
        facility_id=str(facility.id),
        facility_name=facility.name,
        cte_event_id=str(event.id),
        cte_type=event.cte_type,
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


@router.get("/tlcs", response_model=dict[str, Any])
async def list_tlcs(
    facility_id: str | None = None,
    pagination: PaginationParams = Depends(),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    base_filters = [
        SupplierTraceabilityLotModel.tenant_id == tenant_id,
        SupplierTraceabilityLotModel.supplier_user_id == current_user.id,
    ]

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
        base_filters.append(SupplierTraceabilityLotModel.facility_id == facility_uuid)

    total = db.execute(select(func.count()).select_from(SupplierTraceabilityLotModel).where(*base_filters)).scalar()

    lot_query = (
        select(SupplierTraceabilityLotModel)
        .where(*base_filters)
        .order_by(SupplierTraceabilityLotModel.created_at.desc())
        .offset(pagination.skip)
        .limit(pagination.limit)
    )
    lots = db.execute(lot_query).scalars().all()
    if not lots:
        return {"items": [], "total": total, "skip": pagination.skip, "limit": pagination.limit}

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

    items = [
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
    return {"items": items, "total": total, "skip": pagination.skip, "limit": pagination.limit}
