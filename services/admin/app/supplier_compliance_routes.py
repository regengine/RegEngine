"""Supplier Compliance sub-router — Compliance score, gaps, FDA export preview, FDA records download.

Split from supplier_onboarding_routes.py for maintainability.
All shared models, helpers, and constants are imported from the original module.
"""
from __future__ import annotations

import io
import uuid as uuid_module
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_session
from app.dependencies import get_current_user
from app.models import TenantContext
from app.sqlalchemy_models import UserModel
from app.supplier_onboarding_routes import (
    SupplierComplianceScoreResponse,
    SupplierComplianceGap,
    SupplierComplianceGapsResponse,
    SupplierFDAExportRow,
    SupplierFDAExportPreviewResponse,
    _get_supplier_facility_or_404,
    _compute_supplier_compliance,
    _build_fda_export_rows,
    _render_fda_export_csv,
    _render_fda_export_xlsx,
)

router = APIRouter(prefix="/supplier", tags=["supplier-onboarding"])


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
