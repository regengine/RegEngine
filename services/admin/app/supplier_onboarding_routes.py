from __future__ import annotations

import csv
import io
import uuid as uuid_module
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any
import zipfile

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
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
    SupplierFunnelEventModel,
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


class SupplierComplianceScoreResponse(BaseModel):
    score: int
    coverage_ratio: float
    freshness_ratio: float
    integrity_ratio: float
    required_ctes: int
    covered_ctes: int
    stale_ctes: int
    missing_ctes: int
    total_events: int
    evaluated_at: str


class SupplierComplianceGap(BaseModel):
    facility_id: str
    facility_name: str
    cte_type: str | None
    severity: str
    issue: str
    reason: str
    last_seen: str | None = None


class SupplierComplianceGapsResponse(BaseModel):
    gaps: list[SupplierComplianceGap]
    total: int
    high: int
    medium: int
    low: int
    evaluated_at: str


class SupplierDemoResetResponse(BaseModel):
    focus_facility_id: str
    focus_facility_name: str
    focus_required_ctes: list[str]
    focus_gap_cte: str | None = None
    focus_gap_issue: str | None = None
    focus_gap_reason: str | None = None
    seeded_facilities: int
    seeded_tlcs: int
    seeded_tlc_codes: list[str]
    seeded_events: int
    seeded_cte_types: list[str]
    dashboard_score: int
    open_gap_count: int


class SupplierFunnelEventRequest(BaseModel):
    event_name: str = Field(min_length=3, max_length=80)
    step: str | None = None
    status: str | None = None
    facility_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SupplierFunnelEventResponse(BaseModel):
    event_id: str
    event_name: str
    created_at: str


class SupplierSocialProofResponse(BaseModel):
    suppliers_onboarded: int
    facilities_registered: int
    tlcs_tracked: int
    cte_events_verified: int
    fda_exports_generated: int
    updated_at: str


class SupplierFunnelStepSummary(BaseModel):
    step: str
    viewed: int
    completed: int
    completion_rate_pct: float


class SupplierFunnelSummaryResponse(BaseModel):
    steps: list[SupplierFunnelStepSummary]
    total_step_views: int
    total_step_completions: int
    fda_exports_generated: int
    demo_resets_completed: int
    updated_at: str


class SupplierFDAExportRow(BaseModel):
    event_id: str
    tlc_code: str
    product_description: str | None = None
    cte_type: str
    facility_name: str
    event_time: str
    quantity: str
    unit_of_measure: str
    reference_document: str
    payload_sha256: str
    merkle_hash: str
    merkle_sequence: int


class SupplierFDAExportPreviewResponse(BaseModel):
    rows: list[SupplierFDAExportRow]
    total_count: int


FDA_EXPORT_COLUMN_ORDER = [
    "event_id",
    "tlc_code",
    "product_description",
    "cte_type",
    "facility_name",
    "event_time",
    "quantity",
    "unit_of_measure",
    "reference_document",
    "payload_sha256",
    "merkle_hash",
    "merkle_sequence",
]


FDA_EXPORT_HEADERS = {
    "event_id": "Event ID",
    "tlc_code": "Traceability Lot Code",
    "product_description": "Product Description",
    "cte_type": "Critical Tracking Event",
    "facility_name": "Facility",
    "event_time": "Event Time (UTC)",
    "quantity": "Quantity",
    "unit_of_measure": "Unit of Measure",
    "reference_document": "Reference Document",
    "payload_sha256": "SHA-256",
    "merkle_hash": "Merkle Hash",
    "merkle_sequence": "Merkle Sequence",
}


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


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _persist_supplier_cte_event(
    db: Session,
    *,
    tenant_id: uuid_module.UUID,
    current_user: UserModel,
    facility: SupplierFacilityModel,
    cte_type: str,
    tlc_code: str,
    event_time: datetime | None,
    kde_data: dict[str, Any],
    obligation_ids: list[str],
) -> tuple[SupplierCTEEventModel, SupplierTraceabilityLotModel]:
    normalized_cte_type = cte_type.strip().lower()
    if normalized_cte_type not in SUPPORTED_CTE_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported cte_type: {cte_type}")

    normalized_tlc_code = tlc_code.strip()
    if not normalized_tlc_code:
        raise HTTPException(status_code=400, detail="tlc_code is required")

    normalized_kde_data = kde_data if isinstance(kde_data, dict) else {}
    normalized_event_time = _as_utc(event_time) or datetime.now(timezone.utc)

    payload = {
        "facility_id": str(facility.id),
        "cte_type": normalized_cte_type,
        "tlc_code": normalized_tlc_code,
        "event_time": _iso_utc(normalized_event_time),
        "kde_data": normalized_kde_data,
    }
    payload_sha256 = _sha256_json(payload)

    lot = db.execute(
        select(SupplierTraceabilityLotModel).where(
            SupplierTraceabilityLotModel.tenant_id == tenant_id,
            SupplierTraceabilityLotModel.supplier_user_id == current_user.id,
            SupplierTraceabilityLotModel.tlc_code == normalized_tlc_code,
        )
    ).scalar_one_or_none()

    if lot is None:
        lot = SupplierTraceabilityLotModel(
            tenant_id=tenant_id,
            supplier_user_id=current_user.id,
            facility_id=facility.id,
            tlc_code=normalized_tlc_code,
            product_description=(normalized_kde_data.get("product_description") if isinstance(normalized_kde_data, dict) else None),
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
        cte_type=normalized_cte_type,
        event_time=normalized_event_time,
        kde_data=normalized_kde_data,
        payload_sha256=payload_sha256,
        merkle_prev_hash=merkle_prev_hash,
        merkle_hash=merkle_hash,
        sequence_number=sequence_number,
        obligation_ids=obligation_ids,
    )
    db.add(event)
    db.flush()
    return event, lot


def _merkle_integrity_ratio(events: list[SupplierCTEEventModel]) -> float:
    if not events:
        return 1.0

    checks = 0
    valid = 0
    previous: SupplierCTEEventModel | None = None

    for event in events:
        checks += 1
        if previous is None:
            if int(event.sequence_number) == 1 and event.merkle_prev_hash is None:
                valid += 1
        else:
            expected_sequence = int(previous.sequence_number) + 1
            if int(event.sequence_number) == expected_sequence and event.merkle_prev_hash == previous.merkle_hash:
                valid += 1
        previous = event

    return valid / checks if checks else 1.0


def _compute_supplier_compliance(
    db: Session,
    *,
    tenant_id: uuid_module.UUID,
    supplier_user_id: uuid_module.UUID,
    facility_id: uuid_module.UUID | None,
    lookback_days: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    facilities_query = select(SupplierFacilityModel).where(
        SupplierFacilityModel.tenant_id == tenant_id,
        SupplierFacilityModel.supplier_user_id == supplier_user_id,
    )
    if facility_id is not None:
        facilities_query = facilities_query.where(SupplierFacilityModel.id == facility_id)

    facilities = db.execute(facilities_query).scalars().all()
    evaluated_at = datetime.now(timezone.utc)
    evaluated_at_iso = _iso_utc(evaluated_at)
    if not facilities:
        return (
            {
                "score": 0,
                "coverage_ratio": 0.0,
                "freshness_ratio": 0.0,
                "integrity_ratio": 1.0,
                "required_ctes": 0,
                "covered_ctes": 0,
                "stale_ctes": 0,
                "missing_ctes": 0,
                "total_events": 0,
                "evaluated_at": evaluated_at_iso,
            },
            [],
        )

    facility_ids = [facility.id for facility in facilities]

    category_rows = db.execute(
        select(SupplierFacilityFTLCategoryModel).where(
            SupplierFacilityFTLCategoryModel.tenant_id == tenant_id,
            SupplierFacilityFTLCategoryModel.facility_id.in_(facility_ids),
        )
    ).scalars().all()

    scoped_events = db.execute(
        select(SupplierCTEEventModel)
        .where(
            SupplierCTEEventModel.tenant_id == tenant_id,
            SupplierCTEEventModel.supplier_user_id == supplier_user_id,
            SupplierCTEEventModel.facility_id.in_(facility_ids),
        )
        .order_by(SupplierCTEEventModel.sequence_number.asc())
    ).scalars().all()

    all_supplier_events = db.execute(
        select(SupplierCTEEventModel)
        .where(
            SupplierCTEEventModel.tenant_id == tenant_id,
            SupplierCTEEventModel.supplier_user_id == supplier_user_id,
        )
        .order_by(SupplierCTEEventModel.sequence_number.asc())
    ).scalars().all()

    required_by_facility: dict[uuid_module.UUID, list[str]] = {facility.id: [] for facility in facilities}
    required_seen_by_facility: dict[uuid_module.UUID, set[str]] = {facility.id: set() for facility in facilities}

    for row in category_rows:
        for cte in row.required_ctes or []:
            normalized_cte = str(cte).strip().lower()
            if not normalized_cte:
                continue
            if normalized_cte in required_seen_by_facility[row.facility_id]:
                continue
            required_seen_by_facility[row.facility_id].add(normalized_cte)
            required_by_facility[row.facility_id].append(normalized_cte)

    events_by_facility: dict[uuid_module.UUID, list[SupplierCTEEventModel]] = {facility.id: [] for facility in facilities}
    for event in scoped_events:
        events_by_facility[event.facility_id].append(event)

    threshold = evaluated_at - timedelta(days=lookback_days)
    required_total = 0
    covered_total = 0
    fresh_total = 0
    gap_payloads: list[dict[str, Any]] = []

    for facility in facilities:
        required_ctes = required_by_facility.get(facility.id, [])
        if not required_ctes:
            gap_payloads.append(
                {
                    "facility_id": str(facility.id),
                    "facility_name": facility.name,
                    "cte_type": None,
                    "severity": "high",
                    "issue": "No FTL categories scoped for this facility",
                    "reason": "ftl_not_scoped",
                    "last_seen": None,
                }
            )
            continue

        required_total += len(required_ctes)
        latest_by_cte: dict[str, datetime | None] = {}
        for event in events_by_facility.get(facility.id, []):
            normalized_cte = (event.cte_type or "").strip().lower()
            if not normalized_cte:
                continue
            event_time = _as_utc(event.event_time)
            existing = latest_by_cte.get(normalized_cte)
            if existing is None:
                latest_by_cte[normalized_cte] = event_time
                continue
            if event_time is not None and event_time > existing:
                latest_by_cte[normalized_cte] = event_time

        for cte in required_ctes:
            latest = latest_by_cte.get(cte)
            if latest is None:
                gap_payloads.append(
                    {
                        "facility_id": str(facility.id),
                        "facility_name": facility.name,
                        "cte_type": cte,
                        "severity": "high",
                        "issue": f"Missing required {cte} event",
                        "reason": "required_cte_missing",
                        "last_seen": None,
                    }
                )
                continue

            covered_total += 1
            if latest >= threshold:
                fresh_total += 1
            else:
                gap_payloads.append(
                    {
                        "facility_id": str(facility.id),
                        "facility_name": facility.name,
                        "cte_type": cte,
                        "severity": "medium",
                        "issue": f"{cte} event is older than {lookback_days} days",
                        "reason": "required_cte_stale",
                        "last_seen": _iso_utc(latest),
                    }
                )

    integrity_ratio = _merkle_integrity_ratio(all_supplier_events)

    if required_total == 0:
        coverage_ratio = 0.0
        freshness_ratio = 0.0
        score = 0
    else:
        coverage_ratio = covered_total / required_total
        freshness_ratio = fresh_total / required_total
        score = int(round(100 * ((coverage_ratio * 0.75) + (freshness_ratio * 0.15) + (integrity_ratio * 0.10))))
        score = max(0, min(100, score))

    score_payload = {
        "score": score,
        "coverage_ratio": round(coverage_ratio, 4),
        "freshness_ratio": round(freshness_ratio, 4),
        "integrity_ratio": round(integrity_ratio, 4),
        "required_ctes": required_total,
        "covered_ctes": covered_total,
        "stale_ctes": max(covered_total - fresh_total, 0),
        "missing_ctes": max(required_total - covered_total, 0),
        "total_events": len(scoped_events),
        "evaluated_at": evaluated_at_iso,
    }
    return score_payload, gap_payloads


def _compute_social_proof(db: Session, *, tenant_id: uuid_module.UUID) -> dict[str, Any]:
    suppliers_onboarded = int(
        db.execute(
            select(func.count(func.distinct(SupplierFacilityModel.supplier_user_id))).where(
                SupplierFacilityModel.tenant_id == tenant_id,
            )
        ).scalar_one()
        or 0
    )

    facilities_registered = int(
        db.execute(
            select(func.count(SupplierFacilityModel.id)).where(
                SupplierFacilityModel.tenant_id == tenant_id,
            )
        ).scalar_one()
        or 0
    )

    tlcs_tracked = int(
        db.execute(
            select(func.count(SupplierTraceabilityLotModel.id)).where(
                SupplierTraceabilityLotModel.tenant_id == tenant_id,
            )
        ).scalar_one()
        or 0
    )

    cte_events_verified = int(
        db.execute(
            select(func.count(SupplierCTEEventModel.id)).where(
                SupplierCTEEventModel.tenant_id == tenant_id,
            )
        ).scalar_one()
        or 0
    )

    fda_exports_generated = int(
        db.execute(
            select(func.count(SupplierFunnelEventModel.id)).where(
                SupplierFunnelEventModel.tenant_id == tenant_id,
                SupplierFunnelEventModel.event_name == "fda_export_downloaded",
            )
        ).scalar_one()
        or 0
    )

    return {
        "suppliers_onboarded": suppliers_onboarded,
        "facilities_registered": facilities_registered,
        "tlcs_tracked": tlcs_tracked,
        "cte_events_verified": cte_events_verified,
        "fda_exports_generated": fda_exports_generated,
        "updated_at": _iso_utc(datetime.now(timezone.utc)),
    }


SUPPLIER_FUNNEL_STEP_ORDER = [
    "buyer_invite",
    "supplier_signup",
    "facility_setup",
    "ftl_scoping",
    "cte_capture",
    "tlc_mgmt",
    "dashboard",
    "fda_export",
]


def _compute_funnel_summary(db: Session, *, tenant_id: uuid_module.UUID) -> dict[str, Any]:
    grouped_rows = db.execute(
        select(
            SupplierFunnelEventModel.step,
            SupplierFunnelEventModel.event_name,
            func.count(SupplierFunnelEventModel.id),
        )
        .where(SupplierFunnelEventModel.tenant_id == tenant_id)
        .group_by(SupplierFunnelEventModel.step, SupplierFunnelEventModel.event_name)
    ).all()

    viewed_by_step: dict[str, int] = {}
    completed_by_step: dict[str, int] = {}
    for step, event_name, count_value in grouped_rows:
        normalized_step = (step or "").strip().lower()
        if not normalized_step:
            continue
        normalized_event = (event_name or "").strip().lower()
        count_int = int(count_value or 0)
        if normalized_event == "step_viewed":
            viewed_by_step[normalized_step] = viewed_by_step.get(normalized_step, 0) + count_int
        elif normalized_event == "step_completed":
            completed_by_step[normalized_step] = completed_by_step.get(normalized_step, 0) + count_int

    ordered_steps = list(SUPPLIER_FUNNEL_STEP_ORDER)
    discovered_steps = sorted({*viewed_by_step.keys(), *completed_by_step.keys()} - set(ordered_steps))
    all_steps = ordered_steps + discovered_steps

    step_summaries: list[dict[str, Any]] = []
    total_views = 0
    total_completions = 0
    for step in all_steps:
        viewed = viewed_by_step.get(step, 0)
        completed = completed_by_step.get(step, 0)
        total_views += viewed
        total_completions += completed
        completion_rate_pct = round((completed / viewed) * 100, 1) if viewed > 0 else 0.0
        step_summaries.append(
            {
                "step": step,
                "viewed": viewed,
                "completed": completed,
                "completion_rate_pct": completion_rate_pct,
            }
        )

    fda_exports_generated = int(
        db.execute(
            select(func.count(SupplierFunnelEventModel.id)).where(
                SupplierFunnelEventModel.tenant_id == tenant_id,
                SupplierFunnelEventModel.event_name == "fda_export_downloaded",
            )
        ).scalar_one()
        or 0
    )
    demo_resets_completed = int(
        db.execute(
            select(func.count(SupplierFunnelEventModel.id)).where(
                SupplierFunnelEventModel.tenant_id == tenant_id,
                SupplierFunnelEventModel.event_name == "demo_reset_completed",
            )
        ).scalar_one()
        or 0
    )

    return {
        "steps": step_summaries,
        "total_step_views": total_views,
        "total_step_completions": total_completions,
        "fda_exports_generated": fda_exports_generated,
        "demo_resets_completed": demo_resets_completed,
        "updated_at": _iso_utc(datetime.now(timezone.utc)),
    }


def _string_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _build_fda_export_rows(
    db: Session,
    *,
    tenant_id: uuid_module.UUID,
    supplier_user_id: uuid_module.UUID,
    facility_id: uuid_module.UUID | None,
    tlc_code: str | None,
    start_time: datetime | None,
    end_time: datetime | None,
) -> list[dict[str, Any]]:
    event_query = (
        select(
            SupplierCTEEventModel,
            SupplierTraceabilityLotModel,
            SupplierFacilityModel,
        )
        .join(SupplierTraceabilityLotModel, SupplierTraceabilityLotModel.id == SupplierCTEEventModel.lot_id)
        .join(SupplierFacilityModel, SupplierFacilityModel.id == SupplierCTEEventModel.facility_id)
        .where(
            SupplierCTEEventModel.tenant_id == tenant_id,
            SupplierCTEEventModel.supplier_user_id == supplier_user_id,
            SupplierTraceabilityLotModel.tenant_id == tenant_id,
            SupplierTraceabilityLotModel.supplier_user_id == supplier_user_id,
            SupplierFacilityModel.tenant_id == tenant_id,
            SupplierFacilityModel.supplier_user_id == supplier_user_id,
        )
    )

    if facility_id is not None:
        event_query = event_query.where(SupplierCTEEventModel.facility_id == facility_id)
    if tlc_code:
        event_query = event_query.where(SupplierTraceabilityLotModel.tlc_code == tlc_code)

    normalized_start_time = _as_utc(start_time)
    normalized_end_time = _as_utc(end_time)
    if normalized_start_time is not None:
        event_query = event_query.where(SupplierCTEEventModel.event_time >= normalized_start_time)
    if normalized_end_time is not None:
        event_query = event_query.where(SupplierCTEEventModel.event_time <= normalized_end_time)

    event_rows = db.execute(
        event_query.order_by(SupplierCTEEventModel.event_time.desc(), SupplierCTEEventModel.sequence_number.desc())
    ).all()

    output_rows: list[dict[str, Any]] = []
    for event, lot, facility in event_rows:
        kde_data = event.kde_data if isinstance(event.kde_data, dict) else {}
        quantity_value = kde_data.get("quantity", kde_data.get("qty", ""))
        unit_value = kde_data.get("unit_of_measure", kde_data.get("uom", ""))
        reference_document = (
            kde_data.get("reference_document")
            or kde_data.get("reference_document_id")
            or kde_data.get("bill_of_lading")
            or kde_data.get("reference_doc")
            or ""
        )

        output_rows.append(
            {
                "event_id": str(event.id),
                "tlc_code": lot.tlc_code,
                "product_description": lot.product_description or kde_data.get("product_description"),
                "cte_type": event.cte_type,
                "facility_name": facility.name,
                "event_time": _iso_utc(_as_utc(event.event_time) or datetime.now(timezone.utc)),
                "quantity": _string_value(quantity_value),
                "unit_of_measure": _string_value(unit_value),
                "reference_document": _string_value(reference_document),
                "payload_sha256": event.payload_sha256,
                "merkle_hash": event.merkle_hash,
                "merkle_sequence": int(event.sequence_number),
            }
        )

    return output_rows


def _render_fda_export_csv(rows: list[dict[str, Any]]) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[FDA_EXPORT_HEADERS[column] for column in FDA_EXPORT_COLUMN_ORDER])
    writer.writeheader()

    for row in rows:
        writer.writerow(
            {
                FDA_EXPORT_HEADERS[column]: _string_value(row.get(column, ""))
                for column in FDA_EXPORT_COLUMN_ORDER
            }
        )

    return output.getvalue().encode("utf-8")


def _xlsx_column_name(index: int) -> str:
    name = ""
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _render_fda_export_xlsx_fallback(rows: list[dict[str, Any]]) -> bytes:
    header_values = [FDA_EXPORT_HEADERS[column] for column in FDA_EXPORT_COLUMN_ORDER]
    last_column = _xlsx_column_name(len(FDA_EXPORT_COLUMN_ORDER))

    sheet_rows: list[str] = []

    header_cells = []
    for col_idx, header in enumerate(header_values, start=1):
        cell_ref = f"{_xlsx_column_name(col_idx)}1"
        header_cells.append(
            f"<c r=\"{cell_ref}\" t=\"inlineStr\"><is><t>{_xml_escape(header)}</t></is></c>"
        )
    sheet_rows.append(f"<row r=\"1\">{''.join(header_cells)}</row>")

    for row_idx, row in enumerate(rows, start=2):
        data_cells: list[str] = []
        for col_idx, column in enumerate(FDA_EXPORT_COLUMN_ORDER, start=1):
            cell_ref = f"{_xlsx_column_name(col_idx)}{row_idx}"
            value = _xml_escape(_string_value(row.get(column, "")))
            data_cells.append(
                f"<c r=\"{cell_ref}\" t=\"inlineStr\"><is><t>{value}</t></is></c>"
            )
        sheet_rows.append(f"<row r=\"{row_idx}\">{''.join(data_cells)}</row>")

    cols_xml_parts: list[str] = []
    for idx, column in enumerate(FDA_EXPORT_COLUMN_ORDER, start=1):
        display_name = FDA_EXPORT_HEADERS[column]
        width = min(max(len(display_name) + 2, 14), 42)
        cols_xml_parts.append(f"<col min=\"{idx}\" max=\"{idx}\" width=\"{width}\" customWidth=\"1\"/>")

    worksheet_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">"
        "<sheetViews><sheetView workbookViewId=\"0\"><pane ySplit=\"1\" topLeftCell=\"A2\" activePane=\"bottomLeft\" state=\"frozen\"/>"
        "</sheetView></sheetViews>"
        "<sheetFormatPr defaultRowHeight=\"15\"/>"
        f"<cols>{''.join(cols_xml_parts)}</cols>"
        f"<sheetData>{''.join(sheet_rows)}</sheetData>"
        f"<autoFilter ref=\"A1:{last_column}1\"/>"
        "</worksheet>"
    )

    workbook_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" "
        "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\">"
        "<sheets><sheet name=\"FDA Traceability\" sheetId=\"1\" r:id=\"rId1\"/></sheets>"
        "</workbook>"
    )

    root_rels_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
        "<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"xl/workbook.xml\"/>"
        "</Relationships>"
    )

    workbook_rels_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
        "<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" Target=\"worksheets/sheet1.xml\"/>"
        "</Relationships>"
    )

    content_types_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
        "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>"
        "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
        "<Override PartName=\"/xl/workbook.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/>"
        "<Override PartName=\"/xl/worksheets/sheet1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/>"
        "</Types>"
    )

    payload = io.BytesIO()
    with zipfile.ZipFile(payload, mode="w", compression=zipfile.ZIP_DEFLATED) as workbook_zip:
        workbook_zip.writestr("[Content_Types].xml", content_types_xml)
        workbook_zip.writestr("_rels/.rels", root_rels_xml)
        workbook_zip.writestr("xl/workbook.xml", workbook_xml)
        workbook_zip.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        workbook_zip.writestr("xl/worksheets/sheet1.xml", worksheet_xml)
    return payload.getvalue()


def _render_fda_export_xlsx(rows: list[dict[str, Any]]) -> bytes:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
        from openpyxl.utils import get_column_letter
    except ModuleNotFoundError:
        return _render_fda_export_xlsx_fallback(rows)

    workbook = Workbook()
    worksheet: Any = workbook.active
    worksheet.title = "FDA Traceability"
    worksheet.append([FDA_EXPORT_HEADERS[column] for column in FDA_EXPORT_COLUMN_ORDER])

    for row in rows:
        worksheet.append([_string_value(row.get(column, "")) for column in FDA_EXPORT_COLUMN_ORDER])

    for cell in worksheet[1]:
        cell.font = Font(bold=True)

    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions

    for index, column_name in enumerate(FDA_EXPORT_COLUMN_ORDER, start=1):
        display_name = FDA_EXPORT_HEADERS[column_name]
        width = max(len(display_name) + 2, 14)
        worksheet.column_dimensions[get_column_letter(index)].width = min(width, 42)

    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


@router.get("/ftl-categories")
async def get_ftl_categories() -> dict[str, list[dict[str, Any]]]:
    return {"categories": FTL_CATEGORY_CATALOG}


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


@router.get("/compliance-score", response_model=SupplierComplianceScoreResponse)
async def get_compliance_score(
    facility_id: str | None = None,
    lookback_days: int = Query(default=30, ge=1, le=365),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> SupplierComplianceScoreResponse:
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    scoped_facility_id: uuid_module.UUID | None = None
    if facility_id:
        try:
            scoped_facility_id = uuid_module.UUID(facility_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid facility id") from exc
        _get_supplier_facility_or_404(
            db,
            tenant_id=tenant_id,
            supplier_user_id=current_user.id,
            facility_id=scoped_facility_id,
        )

    score_payload, _ = _compute_supplier_compliance(
        db,
        tenant_id=tenant_id,
        supplier_user_id=current_user.id,
        facility_id=scoped_facility_id,
        lookback_days=lookback_days,
    )
    return SupplierComplianceScoreResponse(**score_payload)


@router.get("/gaps", response_model=SupplierComplianceGapsResponse)
async def get_compliance_gaps(
    facility_id: str | None = None,
    lookback_days: int = Query(default=30, ge=1, le=365),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> SupplierComplianceGapsResponse:
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    scoped_facility_id: uuid_module.UUID | None = None
    if facility_id:
        try:
            scoped_facility_id = uuid_module.UUID(facility_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid facility id") from exc
        _get_supplier_facility_or_404(
            db,
            tenant_id=tenant_id,
            supplier_user_id=current_user.id,
            facility_id=scoped_facility_id,
        )

    score_payload, gap_payloads = _compute_supplier_compliance(
        db,
        tenant_id=tenant_id,
        supplier_user_id=current_user.id,
        facility_id=scoped_facility_id,
        lookback_days=lookback_days,
    )
    gaps = [SupplierComplianceGap(**gap_payload) for gap_payload in gap_payloads]

    high = sum(1 for gap in gaps if gap.severity == "high")
    medium = sum(1 for gap in gaps if gap.severity == "medium")
    low = sum(1 for gap in gaps if gap.severity == "low")

    return SupplierComplianceGapsResponse(
        gaps=gaps,
        total=len(gaps),
        high=high,
        medium=medium,
        low=low,
        evaluated_at=score_payload["evaluated_at"],
    )


@router.get("/export/fda-records/preview", response_model=SupplierFDAExportPreviewResponse)
async def preview_fda_records_export(
    facility_id: str | None = None,
    tlc_code: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = Query(default=25, ge=1, le=500),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> SupplierFDAExportPreviewResponse:
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    scoped_facility_id: uuid_module.UUID | None = None
    if facility_id:
        try:
            scoped_facility_id = uuid_module.UUID(facility_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid facility id") from exc
        _get_supplier_facility_or_404(
            db,
            tenant_id=tenant_id,
            supplier_user_id=current_user.id,
            facility_id=scoped_facility_id,
        )

    rows = _build_fda_export_rows(
        db,
        tenant_id=tenant_id,
        supplier_user_id=current_user.id,
        facility_id=scoped_facility_id,
        tlc_code=tlc_code.strip() if tlc_code else None,
        start_time=start_time,
        end_time=end_time,
    )

    preview_rows = [SupplierFDAExportRow(**row) for row in rows[:limit]]
    return SupplierFDAExportPreviewResponse(rows=preview_rows, total_count=len(rows))


@router.get("/export/fda-records")
async def export_fda_records(
    format: str = Query(default="xlsx", pattern="^(csv|xlsx)$"),
    facility_id: str | None = None,
    tlc_code: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> StreamingResponse:
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    scoped_facility_id: uuid_module.UUID | None = None
    if facility_id:
        try:
            scoped_facility_id = uuid_module.UUID(facility_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid facility id") from exc
        _get_supplier_facility_or_404(
            db,
            tenant_id=tenant_id,
            supplier_user_id=current_user.id,
            facility_id=scoped_facility_id,
        )

    rows = _build_fda_export_rows(
        db,
        tenant_id=tenant_id,
        supplier_user_id=current_user.id,
        facility_id=scoped_facility_id,
        tlc_code=tlc_code.strip() if tlc_code else None,
        start_time=start_time,
        end_time=end_time,
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if format == "csv":
        payload = _render_fda_export_csv(rows)
        filename = f"fda_traceability_records_{timestamp}.csv"
        media_type = "text/csv"
    else:
        payload = _render_fda_export_xlsx(rows)
        filename = f"fda_traceability_records_{timestamp}.xlsx"
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    return StreamingResponse(
        io.BytesIO(payload),
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "X-FDA-Record-Count": str(len(rows)),
        },
    )
