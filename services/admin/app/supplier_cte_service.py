from __future__ import annotations

import hashlib
import json
import uuid as uuid_module
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .sqlalchemy_models import (
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

CTE_TYPE_ALIASES = {
    "transformation": "transforming",
    "first_land_based_receiving": "first_receiver",
}


def _normalize_supplier_cte_type(cte_type: str) -> str:
    normalized = cte_type.strip().lower()
    return CTE_TYPE_ALIASES.get(normalized, normalized)


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


def _bridge_to_canonical(
    db: Session,
    *,
    tenant_id: uuid_module.UUID,
    event: SupplierCTEEventModel,
    facility: SupplierFacilityModel,
    tlc_code: str,
    kde_data: dict[str, Any],
) -> None:
    """
    Bridge a supplier CTE event into the canonical TraceabilityEvent pipeline.

    This ensures supplier-contributed data is visible to FDA export,
    compliance scoring, and the canonical records API.
    Non-blocking: failures are logged but do not abort the supplier write.
    """
    import logging
    _logger = logging.getLogger("supplier-canonical-bridge")

    try:
        from shared.canonical_event import (
            TraceabilityEvent,
            CTEType,
            IngestionSource,
            ProvenanceMetadata,
        )
        from shared.canonical_persistence import CanonicalEventStore

        # Map supplier CTE type to canonical CTEType
        _cte_map = {
            "shipping": "shipping",
            "receiving": "receiving",
            "transforming": "transformation",
            "harvesting": "harvesting",
            "cooling": "cooling",
            "initial_packing": "initial_packing",
            "first_receiver": "first_land_based_receiving",
        }
        canonical_cte = _cte_map.get(event.cte_type, "receiving")

        provenance = ProvenanceMetadata(
            mapper_name="supplier_cte_bridge",
            mapper_version="1.0.0",
            original_format="json",
            normalization_rules_applied=["supplier_portal_normalization"],
        )

        facility_gln = getattr(facility, "gln", None) or str(facility.id)

        canonical_event = TraceabilityEvent(
            tenant_id=tenant_id,
            source_system=IngestionSource.SUPPLIER_PORTAL,
            source_record_id=str(event.id),
            event_type=CTEType(canonical_cte),
            event_timestamp=event.event_time,
            traceability_lot_code=tlc_code,
            product_reference=kde_data.get("product_description", ""),
            lot_reference=tlc_code,
            quantity=float(kde_data.get("quantity", 1.0)),
            unit_of_measure=str(kde_data.get("unit_of_measure", "each")),
            from_facility_reference=facility_gln,
            kdes=kde_data,
            raw_payload={
                "supplier_cte_event_id": str(event.id),
                "facility_id": str(facility.id),
                "cte_type": event.cte_type,
                "event_time": event.event_time.isoformat() if event.event_time else None,
                "kde_data": kde_data,
            },
            provenance_metadata=provenance,
        ).prepare_for_persistence()

        store = CanonicalEventStore(db, dual_write=True)
        store.persist_event(canonical_event)

        _logger.info(
            "supplier_cte_canonical_bridged",
            extra={
                "supplier_event_id": str(event.id),
                "canonical_event_id": str(canonical_event.event_id),
                "tenant_id": str(tenant_id),
            },
        )
    except Exception as exc:
        _logger.warning(
            "supplier_canonical_bridge_failed",
            extra={"supplier_event_id": str(event.id), "error": str(exc)},
        )


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
    normalized_cte_type = _normalize_supplier_cte_type(cte_type)
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

    # Bridge to canonical pipeline for FDA export and compliance scoring
    _bridge_to_canonical(
        db,
        tenant_id=tenant_id,
        event=event,
        facility=facility,
        tlc_code=normalized_tlc_code,
        kde_data=normalized_kde_data,
    )

    return event, lot
