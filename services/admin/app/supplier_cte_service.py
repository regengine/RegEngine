from __future__ import annotations

import hashlib
import json
import uuid as uuid_module
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.sqlalchemy_models import (
    SupplierCTEEventModel,
    SupplierFacilityModel,
    SupplierTraceabilityLotModel,
    TenantModel,
    UserModel,
)


SUPPORTED_CTE_TYPES = {
    "shipping",
    "receiving",
    "transforming",
    "harvesting",
    "cooling",
    "initial_packing",
    "first_receiver",
}


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


def _sha256_json(payload: dict[str, Any]) -> str:
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _next_merkle_hash(prev_hash: str | None, payload_sha256: str) -> str:
    if prev_hash is None:
        seed = f"GENESIS:{payload_sha256}"
    else:
        seed = f"{prev_hash}:{payload_sha256}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _acquire_tenant_merkle_lock(db: Session, tenant_id: uuid_module.UUID) -> None:
    tenant_row = db.execute(
        select(TenantModel.id)
        .where(TenantModel.id == tenant_id)
        .with_for_update()
    ).scalar_one_or_none()
    if tenant_row is None:
        raise HTTPException(status_code=400, detail="Tenant not found")


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
            product_description=(
                normalized_kde_data.get("product_description")
                if isinstance(normalized_kde_data, dict)
                else None
            ),
            status="active",
        )
        db.add(lot)
        db.flush()

    _acquire_tenant_merkle_lock(db, tenant_id)

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
