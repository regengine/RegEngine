"""Supplier Funnel sub-router — Funnel events, social proof, funnel summary, demo reset.

Split from supplier_onboarding_routes.py for maintainability.
All shared models, helpers, and constants are imported from the original module.
"""
from __future__ import annotations

import uuid as uuid_module
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database import get_session
from app.dependencies import get_current_user
from app.models import TenantContext
from app.sqlalchemy_models import (
    SupplierCTEEventModel,
    SupplierFacilityFTLCategoryModel,
    SupplierFacilityModel,
    SupplierFunnelEventModel,
    SupplierTraceabilityLotModel,
    UserModel,
)
from app.supplier_graph_sync import supplier_graph_sync
from app.supplier_cte_service import _persist_supplier_cte_event
from app.supplier_onboarding_routes import (
    FTL_CATEGORY_LOOKUP,
    SupplierDemoResetResponse,
    SupplierFunnelEventRequest,
    SupplierFunnelEventResponse,
    SupplierSocialProofResponse,
    SupplierFunnelSummaryResponse,
    _get_supplier_facility_or_404,
    _derive_required_ctes,
    _iso_utc,
    _compute_supplier_compliance,
    _compute_social_proof,
    _compute_funnel_summary,
)

router = APIRouter(prefix="/supplier", tags=["supplier-onboarding"])


@router.post("/demo/reset", response_model=SupplierDemoResetResponse)
async def reset_supplier_demo(
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> SupplierDemoResetResponse:
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    db.execute(
        delete(SupplierCTEEventModel).where(
            SupplierCTEEventModel.tenant_id == tenant_id,
            SupplierCTEEventModel.supplier_user_id == current_user.id,
        )
    )
    db.execute(
        delete(SupplierTraceabilityLotModel).where(
            SupplierTraceabilityLotModel.tenant_id == tenant_id,
            SupplierTraceabilityLotModel.supplier_user_id == current_user.id,
        )
    )
    db.execute(
        delete(SupplierFacilityFTLCategoryModel).where(
            SupplierFacilityFTLCategoryModel.tenant_id == tenant_id,
            SupplierFacilityFTLCategoryModel.facility_id.in_(
                select(SupplierFacilityModel.id).where(
                    SupplierFacilityModel.tenant_id == tenant_id,
                    SupplierFacilityModel.supplier_user_id == current_user.id,
                )
            ),
        )
    )
    db.execute(
        delete(SupplierFunnelEventModel).where(
            SupplierFunnelEventModel.tenant_id == tenant_id,
            SupplierFunnelEventModel.supplier_user_id == current_user.id,
        )
    )
    db.execute(
        delete(SupplierFacilityModel).where(
            SupplierFacilityModel.tenant_id == tenant_id,
            SupplierFacilityModel.supplier_user_id == current_user.id,
        )
    )
    db.commit()

    facility_blueprints = [
        {
            "key": "grower",
            "name": "Salinas Valley Grower",
            "street": "710 Fieldline Rd",
            "city": "Salinas",
            "state": "CA",
            "postal_code": "93908",
            "fda_registration_number": "10000000001",
            "roles": ["Grower"],
            "category_ids": ["2"],
        },
        {
            "key": "cooler",
            "name": "Monterey Cooling Hub",
            "street": "420 Chiller Ave",
            "city": "Monterey",
            "state": "CA",
            "postal_code": "93940",
            "fda_registration_number": "10000000002",
            "roles": ["Processor"],
            "category_ids": ["1"],
        },
        {
            "key": "packer",
            "name": "Salinas Packhouse",
            "street": "1200 Abbott St",
            "city": "Salinas",
            "state": "CA",
            "postal_code": "93901",
            "fda_registration_number": "10000000003",
            "roles": ["Packer"],
            "category_ids": ["1"],
        },
        {
            "key": "distributor",
            "name": "East Bay Distribution Center",
            "street": "55 Logistics Pkwy",
            "city": "Oakland",
            "state": "CA",
            "postal_code": "94621",
            "fda_registration_number": "10000000004",
            "roles": ["Distributor"],
            "category_ids": ["1"],
        },
    ]

    facilities_by_key: dict[str, SupplierFacilityModel] = {}
    categories_by_facility_id: dict[uuid_module.UUID, list[dict[str, Any]]] = {}

    for blueprint in facility_blueprints:
        facility = SupplierFacilityModel(
            tenant_id=tenant_id,
            supplier_user_id=current_user.id,
            name=blueprint["name"],
            street=blueprint["street"],
            city=blueprint["city"],
            state=blueprint["state"],
            postal_code=blueprint["postal_code"],
            fda_registration_number=blueprint["fda_registration_number"],
            roles=blueprint["roles"],
        )
        db.add(facility)
        db.flush()

        selected_categories: list[dict[str, Any]] = []
        for category_id in blueprint["category_ids"]:
            category = FTL_CATEGORY_LOOKUP.get(category_id)
            if category is None:
                raise HTTPException(status_code=500, detail=f"Missing seed FTL category id: {category_id}")
            selected_categories.append(category)
            db.add(
                SupplierFacilityFTLCategoryModel(
                    tenant_id=tenant_id,
                    facility_id=facility.id,
                    category_id=category["id"],
                    category_name=category["name"],
                    required_ctes=category["ctes"],
                )
            )

        facilities_by_key[blueprint["key"]] = facility
        categories_by_facility_id[facility.id] = selected_categories

    seed_now = datetime.now(timezone.utc)
    event_blueprints = [
        {"facility_key": "grower", "cte_type": "harvesting", "tlc_code": "TLC-2026-SAL-1001", "hours_ago": 120, "kde_data": {"quantity": 520, "unit_of_measure": "cases", "product_description": "Baby Spinach", "reference_document": "HRV-1001"}},
        {"facility_key": "grower", "cte_type": "cooling", "tlc_code": "TLC-2026-SAL-1001", "hours_ago": 116, "kde_data": {"quantity": 520, "unit_of_measure": "cases", "product_description": "Baby Spinach", "reference_document": "CL-1001"}},
        {"facility_key": "grower", "cte_type": "initial_packing", "tlc_code": "TLC-2026-SAL-1001", "hours_ago": 112, "kde_data": {"quantity": 500, "unit_of_measure": "cases", "product_description": "Baby Spinach", "reference_document": "IP-1001"}},
        {"facility_key": "grower", "cte_type": "receiving", "tlc_code": "TLC-2026-SAL-1002", "hours_ago": 108, "kde_data": {"quantity": 340, "unit_of_measure": "cases", "product_description": "Spring Mix", "reference_document": "RCV-1002"}},
        {"facility_key": "grower", "cte_type": "transforming", "tlc_code": "TLC-2026-SAL-1002", "hours_ago": 104, "kde_data": {"quantity": 320, "unit_of_measure": "cases", "product_description": "Spring Mix", "reference_document": "XFM-1002"}},
        {"facility_key": "grower", "cte_type": "shipping", "tlc_code": "TLC-2026-SAL-1002", "hours_ago": 100, "kde_data": {"quantity": 320, "unit_of_measure": "cases", "product_description": "Spring Mix", "reference_document": "BOL-1002"}},
        {"facility_key": "cooler", "cte_type": "receiving", "tlc_code": "TLC-2026-SAL-1001", "hours_ago": 96, "kde_data": {"quantity": 500, "unit_of_measure": "cases", "product_description": "Baby Spinach", "reference_document": "RCV-2001"}},
        {"facility_key": "cooler", "cte_type": "transforming", "tlc_code": "TLC-2026-SAL-1001", "hours_ago": 92, "kde_data": {"quantity": 490, "unit_of_measure": "cases", "product_description": "Baby Spinach", "reference_document": "XFM-2001"}},
        {"facility_key": "cooler", "cte_type": "shipping", "tlc_code": "TLC-2026-SAL-1001", "hours_ago": 88, "kde_data": {"quantity": 490, "unit_of_measure": "cases", "product_description": "Baby Spinach", "reference_document": "BOL-2001"}},
        {"facility_key": "packer", "cte_type": "receiving", "tlc_code": "TLC-2026-SAL-1001", "hours_ago": 84, "kde_data": {"quantity": 480, "unit_of_measure": "cases", "product_description": "Baby Spinach", "reference_document": "RCV-3001"}},
        {"facility_key": "packer", "cte_type": "shipping", "tlc_code": "TLC-2026-SAL-1001", "hours_ago": 80, "kde_data": {"quantity": 470, "unit_of_measure": "cases", "product_description": "Baby Spinach", "reference_document": "BOL-3001"}},
        {"facility_key": "packer", "cte_type": "receiving", "tlc_code": "TLC-2026-SAL-1003", "hours_ago": 76, "kde_data": {"quantity": 260, "unit_of_measure": "cases", "product_description": "Romaine Hearts", "reference_document": "RCV-3003"}},
        {"facility_key": "packer", "cte_type": "shipping", "tlc_code": "TLC-2026-SAL-1003", "hours_ago": 72, "kde_data": {"quantity": 250, "unit_of_measure": "cases", "product_description": "Romaine Hearts", "reference_document": "BOL-3003"}},
        {"facility_key": "distributor", "cte_type": "receiving", "tlc_code": "TLC-2026-SAL-1001", "hours_ago": 64, "kde_data": {"quantity": 460, "unit_of_measure": "cases", "product_description": "Baby Spinach", "reference_document": "RCV-4001"}},
        {"facility_key": "distributor", "cte_type": "transforming", "tlc_code": "TLC-2026-SAL-1001", "hours_ago": 60, "kde_data": {"quantity": 450, "unit_of_measure": "cases", "product_description": "Baby Spinach", "reference_document": "XFM-4001"}},
        {"facility_key": "distributor", "cte_type": "shipping", "tlc_code": "TLC-2026-SAL-1001", "hours_ago": 56, "kde_data": {"quantity": 450, "unit_of_measure": "cases", "product_description": "Baby Spinach", "reference_document": "BOL-4001"}},
    ]

    seeded_records: list[tuple[SupplierCTEEventModel, SupplierTraceabilityLotModel, SupplierFacilityModel]] = []
    for item in event_blueprints:
        facility = facilities_by_key[item["facility_key"]]
        event, lot = _persist_supplier_cte_event(
            db,
            tenant_id=tenant_id,
            current_user=current_user,
            facility=facility,
            cte_type=item["cte_type"],
            tlc_code=item["tlc_code"],
            event_time=seed_now - timedelta(hours=int(item["hours_ago"])),
            kde_data=item["kde_data"],
            obligation_ids=[],
        )
        seeded_records.append((event, lot, facility))

    db.commit()

    for facility in facilities_by_key.values():
        selected_categories = categories_by_facility_id.get(facility.id, [])
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
            categories=selected_categories,
        )

    for event, lot, facility in seeded_records:
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

    focus_facility = facilities_by_key["packer"]
    focus_categories = categories_by_facility_id.get(focus_facility.id, [])
    focus_required_ctes = _derive_required_ctes(focus_categories)
    score_payload, gap_payloads = _compute_supplier_compliance(
        db,
        tenant_id=tenant_id,
        supplier_user_id=current_user.id,
        facility_id=focus_facility.id,
        lookback_days=30,
    )

    seeded_tlc_codes = list(dict.fromkeys(lot.tlc_code for _, lot, _facility in seeded_records if lot.tlc_code))
    seeded_cte_types = list(dict.fromkeys(event.cte_type for event, _lot, _facility in seeded_records if event.cte_type))
    focus_gap = next(
        (
            gap
            for gap in gap_payloads
            if gap.get("facility_id") == str(focus_facility.id)
        ),
        gap_payloads[0] if gap_payloads else None,
    )
    return SupplierDemoResetResponse(
        focus_facility_id=str(focus_facility.id),
        focus_facility_name=focus_facility.name,
        focus_required_ctes=focus_required_ctes,
        focus_gap_cte=(focus_gap.get("cte_type") if focus_gap else None),
        focus_gap_issue=(focus_gap.get("issue") if focus_gap else None),
        focus_gap_reason=(focus_gap.get("reason") if focus_gap else None),
        seeded_facilities=len(facilities_by_key),
        seeded_tlcs=len(seeded_tlc_codes),
        seeded_tlc_codes=seeded_tlc_codes,
        seeded_events=len(seeded_records),
        seeded_cte_types=seeded_cte_types,
        dashboard_score=int(score_payload["score"]),
        open_gap_count=len(gap_payloads),
    )


@router.post("/funnel-events", response_model=SupplierFunnelEventResponse)
async def create_supplier_funnel_event(
    request: SupplierFunnelEventRequest,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> SupplierFunnelEventResponse:
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    scoped_facility_id: uuid_module.UUID | None = None
    if request.facility_id:
        try:
            scoped_facility_id = uuid_module.UUID(request.facility_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid facility id") from exc
        _get_supplier_facility_or_404(
            db,
            tenant_id=tenant_id,
            supplier_user_id=current_user.id,
            facility_id=scoped_facility_id,
        )

    event = SupplierFunnelEventModel(
        tenant_id=tenant_id,
        supplier_user_id=current_user.id,
        facility_id=scoped_facility_id,
        event_name=request.event_name.strip().lower(),
        step=(request.step.strip().lower() if request.step else None),
        status=(request.status.strip().lower() if request.status else None),
        metadata_=request.metadata,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    return SupplierFunnelEventResponse(
        event_id=str(event.id),
        event_name=event.event_name,
        created_at=_iso_utc(event.created_at),
    )


@router.get("/social-proof", response_model=SupplierSocialProofResponse)
async def get_supplier_social_proof(
    _current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> SupplierSocialProofResponse:
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    payload = _compute_social_proof(db, tenant_id=tenant_id)
    return SupplierSocialProofResponse(**payload)


@router.get("/funnel-summary", response_model=SupplierFunnelSummaryResponse)
async def get_supplier_funnel_summary(
    _current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> SupplierFunnelSummaryResponse:
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    payload = _compute_funnel_summary(db, tenant_id=tenant_id)
    return SupplierFunnelSummaryResponse(**payload)
