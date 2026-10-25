"""Supplier Compliance sub-router — Compliance score, gaps, FDA export preview, FDA records download.

Split from supplier_onboarding_routes.py for maintainability.
All shared models, helpers, and constants are imported from the original module.
"""

from __future__ import annotations

import io
import uuid as uuid_module
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from shared.data_gap_tracking import INTERNAL_TARGET, fetch_supplier_summaries
from shared.supplier_data_quality import (
    DEFAULT_WINDOW_DAYS,
    LATE_CTE_LABEL,
    MAX_WINDOW_DAYS,
    METRIC_EPCIS_FAILED,
    METRIC_LATE_CTE,
    METRIC_MISSING_KDE,
    METRIC_UNLINKED_LOT,
    MIN_RECORDS,
    fetch_lot_rows,
    fetch_record_rows,
    fetch_sending_hours,
    fetch_supplier_quality,
    flag_records,
    late_records,
    unlinked_lots,
    window_start as quality_window_start,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_session
from .dependencies import get_current_user
from .models import TenantContext
from .sqlalchemy_models import SupplierFacilityModel, UserModel
from .tenant_settings_routes import _ADMIN_ROLE_NAMES, _get_user_role_name
from .supplier_onboarding_routes import (
    SupplierComplianceGap,
    SupplierComplianceGapsResponse,
    SupplierComplianceScoreResponse,
    SupplierFDAExportPreviewResponse,
    SupplierFDAExportRow,
    _build_fda_export_rows,
    _compute_supplier_compliance,
    _get_supplier_facility_or_404,
    _render_fda_export_csv,
    _render_fda_export_xlsx,
)

router = APIRouter(prefix="/supplier", tags=["supplier-onboarding"])

QUALITY_METRIC_ORDER = (METRIC_MISSING_KDE, METRIC_UNLINKED_LOT, METRIC_LATE_CTE, METRIC_EPCIS_FAILED)
# supplier_facilities.agreed_sending_hours is a Postgres integer.
MAX_AGREED_SENDING_HOURS = 2**31 - 1


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


class SupplierGapTimeToFix(BaseModel):
    supplier_key: str
    open_gap_count: int
    median_time_to_fix_seconds: float | None
    oldest_open_gap_opened_at: str | None
    at_risk: bool
    at_risk_gap_count: int
    past_internal_target: bool
    has_data: bool


class SupplierGapTimeToFixResponse(BaseModel):
    suppliers: list[SupplierGapTimeToFix]
    internal_target_seconds: int
    evaluated_at: str


@router.get("/gap-time-to-fix", response_model=SupplierGapTimeToFixResponse)
async def get_gap_time_to_fix(
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> SupplierGapTimeToFixResponse:
    """Per facility data gap time to fix for the current supplier's facilities.

    Scoped to the tenant and to facilities owned by the calling user; RLS on
    ``public.data_gap_events`` enforces the tenant boundary as well.
    """
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    facility_ids = [
        str(facility_id)
        for facility_id in db.scalars(
            select(SupplierFacilityModel.id).where(
                SupplierFacilityModel.tenant_id == tenant_id,
                SupplierFacilityModel.supplier_user_id == current_user.id,
            )
        ).all()
    ]
    now = datetime.now(timezone.utc)
    summaries = fetch_supplier_summaries(db, str(tenant_id), facility_ids, now)
    return SupplierGapTimeToFixResponse(
        suppliers=[SupplierGapTimeToFix(supplier_key=key, **summary) for key, summary in summaries.items()],
        internal_target_seconds=int(INTERNAL_TARGET.total_seconds()),
        evaluated_at=now.isoformat(),
    )


class SupplierQualityMetric(BaseModel):
    key: str
    status: Literal["ok", "not_enough_data", "unavailable"]
    numerator: int | None
    denominator: int | None
    share: float | None
    reason: str | None


class SupplierDataQuality(BaseModel):
    supplier_key: str
    agreed_sending_hours: int | None = None
    metrics: list[SupplierQualityMetric]


class AgreedSendingHoursRequest(BaseModel):
    # Required key; null clears it. Strict: no strings, floats or booleans.
    agreed_sending_hours: int | None = Field(..., strict=True, gt=0, le=MAX_AGREED_SENDING_HOURS)


class AgreedSendingHoursResponse(BaseModel):
    facility_id: str
    agreed_sending_hours: int | None


class SupplierDataQualityResponse(BaseModel):
    suppliers: list[SupplierDataQuality]
    window_days: int
    min_records: int
    late_cte_label: str
    evaluated_at: str


class SupplierQualityRecordItem(BaseModel):
    record_id: str | None = None
    lot_id: str | None = None
    lot_code: str
    cte_type: str | None = None
    event_time: str | None = None
    received_at: str | None = None
    missing_kdes: list[str] = []


class SupplierQualityRecordsResponse(BaseModel):
    supplier_key: str
    metric: str
    window_days: int
    total: int
    limit: int
    offset: int
    items: list[SupplierQualityRecordItem]


def _owned_facility_ids(db: Session, tenant_id: uuid_module.UUID, user_id: Any) -> list[str]:
    return [
        str(facility_id)
        for facility_id in db.scalars(
            select(SupplierFacilityModel.id).where(
                SupplierFacilityModel.tenant_id == tenant_id,
                SupplierFacilityModel.supplier_user_id == user_id,
            )
        ).all()
    ]


def _iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


@router.get("/data-quality", response_model=SupplierDataQualityResponse)
async def get_supplier_data_quality(
    window_days: int = Query(default=DEFAULT_WINDOW_DAYS, ge=1, le=MAX_WINDOW_DAYS),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> SupplierDataQualityResponse:
    """Four separate data quality measures per facility over a rolling window.

    Scoped to the tenant and to facilities owned by the calling user, except
    epcis_failed: EPCIS receipts carry no facility, so that share is tenant
    wide and repeated on every facility.
    """
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    facility_ids = _owned_facility_ids(db, tenant_id, current_user.id)
    now = datetime.now(timezone.utc)
    hours = fetch_sending_hours(db, str(tenant_id), str(current_user.id), facility_ids)
    quality = fetch_supplier_quality(
        db, str(tenant_id), str(current_user.id), facility_ids, quality_window_start(now, window_days), hours
    )
    return SupplierDataQualityResponse(
        suppliers=[
            SupplierDataQuality(
                supplier_key=key,
                agreed_sending_hours=hours.get(key),
                metrics=[SupplierQualityMetric(**metrics[name]) for name in QUALITY_METRIC_ORDER],
            )
            for key, metrics in quality.items()
        ],
        window_days=window_days,
        min_records=MIN_RECORDS,
        late_cte_label=LATE_CTE_LABEL,
        evaluated_at=now.isoformat(),
    )


@router.get("/data-quality/{facility_id}/records", response_model=SupplierQualityRecordsResponse)
async def get_supplier_data_quality_records(
    facility_id: str,
    metric: Literal["missing_kde", "unlinked_lot", "late_cte"],
    window_days: int = Query(default=DEFAULT_WINDOW_DAYS, ge=1, le=MAX_WINDOW_DAYS),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> SupplierQualityRecordsResponse:
    """The exact records behind one facility's metric numerator, paginated."""
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")
    try:
        scoped_facility_id = uuid_module.UUID(facility_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid facility id") from exc
    facility = _get_supplier_facility_or_404(
        db,
        tenant_id=tenant_id,
        supplier_user_id=current_user.id,
        facility_id=scoped_facility_id,
    )
    if metric == METRIC_LATE_CTE and facility.agreed_sending_hours is None:
        raise HTTPException(status_code=409, detail="No agreed sending time is set for this facility")

    key = str(scoped_facility_id)
    since = quality_window_start(datetime.now(timezone.utc), window_days)
    if metric in (METRIC_MISSING_KDE, METRIC_LATE_CTE):
        rows = fetch_record_rows(db, str(tenant_id), str(current_user.id), [key], since)
        flagged = (
            flag_records(rows) if metric == METRIC_MISSING_KDE else late_records(rows, facility.agreed_sending_hours)
        )
        items = [
            SupplierQualityRecordItem(
                record_id=str(row["record_id"]),
                lot_code=row["lot_code"],
                cte_type=row["cte_type"],
                event_time=_iso_or_none(row["event_time"]),
                received_at=_iso_or_none(row["created_at"]),
                missing_kdes=row.get("missing_kdes", []),
            )
            for row in flagged
        ]
    else:
        items = [
            SupplierQualityRecordItem(lot_id=lot["lot_id"], lot_code=lot["lot_code"])
            for lot in unlinked_lots(fetch_lot_rows(db, str(tenant_id), str(current_user.id), [key], since))
        ]
    return SupplierQualityRecordsResponse(
        supplier_key=key,
        metric=metric,
        window_days=window_days,
        total=len(items),
        limit=limit,
        offset=offset,
        items=items[offset : offset + limit],
    )


class TenantAdminChecker:
    """Allow only an Owner or Admin membership in the bound tenant.

    Reuses the tenant settings role gate (#1386). ``required_permission``
    is read by the route security manifest.
    """

    required_permission = "tenant.admin"

    def __call__(self, user: UserModel = Depends(get_current_user), db: Session = Depends(get_session)) -> UserModel:
        tenant_id = TenantContext.get_tenant_context(db)
        if not tenant_id:
            raise HTTPException(status_code=403, detail="E_NO_TENANT_CONTEXT: tenant-scoped endpoint requires X-Tenant-ID")
        if _get_user_role_name(tenant_id, user, db) not in _ADMIN_ROLE_NAMES:
            raise HTTPException(status_code=403, detail="Only tenant Owner or Admin roles may set agreed sending hours")
        return user


require_tenant_admin = TenantAdminChecker()


@router.put("/admin/facilities/{facility_id}/agreed-sending-hours", response_model=AgreedSendingHoursResponse)
async def set_agreed_sending_hours(
    facility_id: str,
    request: AgreedSendingHoursRequest,
    _admin: UserModel = Depends(require_tenant_admin),
    db: Session = Depends(get_session),
) -> AgreedSendingHoursResponse:
    """Tenant admin sets or clears (null) the agreed sending time for a facility in the tenant.

    Suppliers can read it in their data quality summary but cannot change it.
    """
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")
    try:
        scoped_facility_id = uuid_module.UUID(facility_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid facility id") from exc
    # Tenant scoping lives in the query: a facility in another tenant is never loaded.
    facility = db.execute(
        select(SupplierFacilityModel).where(
            SupplierFacilityModel.id == scoped_facility_id,
            SupplierFacilityModel.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if facility is None:
        raise HTTPException(status_code=404, detail="Facility not found")

    facility.agreed_sending_hours = request.agreed_sending_hours
    db.commit()
    return AgreedSendingHoursResponse(
        facility_id=str(scoped_facility_id), agreed_sending_hours=request.agreed_sending_hours
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

    normalized_tlc_code = tlc_code.strip() if tlc_code else None
    trace_scope_supplier_id = None if normalized_tlc_code and scoped_facility_id is None else current_user.id

    rows = _build_fda_export_rows(
        db,
        tenant_id=tenant_id,
        supplier_user_id=trace_scope_supplier_id,
        facility_id=scoped_facility_id,
        tlc_code=normalized_tlc_code,
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

    normalized_tlc_code = tlc_code.strip() if tlc_code else None
    trace_scope_supplier_id = None if normalized_tlc_code and scoped_facility_id is None else current_user.id

    rows = _build_fda_export_rows(
        db,
        tenant_id=tenant_id,
        supplier_user_id=trace_scope_supplier_id,
        facility_id=scoped_facility_id,
        tlc_code=normalized_tlc_code,
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
