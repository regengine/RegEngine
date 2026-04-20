from __future__ import annotations

import uuid as uuid_module
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..graph_outbox import enqueue_graph_write
from ..supplier_cte_service import _persist_supplier_cte_event
from ..supplier_graph_sync import CTE_EVENT_QUERY, supplier_graph_sync
from ..supplier_onboarding_routes import FTL_CATEGORY_LOOKUP
from ..sqlalchemy_models import (
    SupplierCTEEventModel,
    SupplierFacilityFTLCategoryModel,
    SupplierFacilityModel,
    SupplierTraceabilityLotModel,
    UserModel,
)


logger = structlog.get_logger("bulk_upload.transaction_manager")


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _facility_identity_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        _normalize_text(row.get("name")).lower(),
        _normalize_text(row.get("street")).lower(),
        _normalize_text(row.get("city")).lower(),
        _normalize_text(row.get("state")).lower(),
        _normalize_text(row.get("postal_code")).lower(),
    )


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).isoformat()
    return value.astimezone(timezone.utc).isoformat()


def _parse_optional_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def build_validation_preview(
    db: Session,
    *,
    tenant_id: uuid_module.UUID,
    supplier_user_id: uuid_module.UUID,
    normalized_payload: dict[str, list[dict[str, Any]]],
    validation_errors: list[dict[str, Any]],
) -> dict[str, Any]:
    facilities = normalized_payload.get("facilities") or []
    ftl_scopes = normalized_payload.get("ftl_scopes") or []
    tlcs = normalized_payload.get("tlcs") or []
    events = normalized_payload.get("events") or []

    existing_facilities = db.execute(
        select(SupplierFacilityModel).where(
            SupplierFacilityModel.tenant_id == tenant_id,
            SupplierFacilityModel.supplier_user_id == supplier_user_id,
        )
    ).scalars().all()
    existing_keys = {_facility_identity_key(row.__dict__) for row in existing_facilities}
    known_facility_names = {
        _normalize_text(facility.name).lower()
        for facility in existing_facilities
        if _normalize_text(facility.name)
    }
    for row in facilities:
        name = _normalize_text(row.get("name")).lower()
        if name:
            known_facility_names.add(name)

    facilities_to_create = 0
    facilities_to_update = 0
    for row in facilities:
        if _facility_identity_key(row) in existing_keys:
            facilities_to_update += 1
        else:
            facilities_to_create += 1

    preview_errors = list(validation_errors)
    for section_name, rows in [
        ("ftl_scope", ftl_scopes),
        ("tlc", tlcs),
        ("event", events),
    ]:
        for row_number, row in enumerate(rows, start=1):
            facility_name = _normalize_text(row.get("facility_name")).lower()
            if not facility_name:
                continue
            if facility_name in known_facility_names:
                continue
            preview_errors.append(
                {
                    "section": section_name,
                    "row": row_number,
                    "message": f"Unknown facility_name reference: {row.get('facility_name')}",
                }
            )

    tlc_codes = {_normalize_text(row.get("tlc_code")) for row in tlcs if _normalize_text(row.get("tlc_code"))}
    if tlc_codes:
        existing_tlc_codes = set(
            db.execute(
                select(SupplierTraceabilityLotModel.tlc_code).where(
                    SupplierTraceabilityLotModel.tenant_id == tenant_id,
                    SupplierTraceabilityLotModel.supplier_user_id == supplier_user_id,
                    SupplierTraceabilityLotModel.tlc_code.in_(tlc_codes),
                )
            ).scalars().all()
        )
    else:
        existing_tlc_codes = set()

    tlcs_to_create = 0
    tlcs_to_update = 0
    for row in tlcs:
        if _normalize_text(row.get("tlc_code")) in existing_tlc_codes:
            tlcs_to_update += 1
        else:
            tlcs_to_create += 1

    unique_scopes = {
        (
            _normalize_text(row.get("facility_name")).lower(),
            _normalize_text(row.get("category_id")),
        )
        for row in ftl_scopes
    }

    return {
        "facilities_to_create": facilities_to_create,
        "facilities_to_update": facilities_to_update,
        "ftl_scopes_to_upsert": len(unique_scopes),
        "tlcs_to_create": tlcs_to_create,
        "tlcs_to_update": tlcs_to_update,
        "events_to_chain": len(events),
        "errors": preview_errors,
        # Allow commit when only warnings remain — hard errors still block
        "can_commit": all(
            e.get("severity") == "warning"
            for e in preview_errors
        ) if preview_errors else True,
    }


def execute_bulk_commit(
    db: Session,
    *,
    tenant_id: uuid_module.UUID,
    current_user: UserModel,
    normalized_payload: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    facilities_payload = normalized_payload.get("facilities") or []
    ftl_scopes_payload = normalized_payload.get("ftl_scopes") or []
    tlcs_payload = normalized_payload.get("tlcs") or []
    events_payload = normalized_payload.get("events") or []

    facilities_created = 0
    facilities_updated = 0
    ftl_scopes_upserted = 0
    tlcs_created = 0
    tlcs_updated = 0

    categories_by_facility: dict[uuid_module.UUID, list[dict[str, Any]]] = defaultdict(list)
    emitted_event_rows: list[tuple[SupplierCTEEventModel, SupplierTraceabilityLotModel, SupplierFacilityModel]] = []

    existing_facilities = db.execute(
        select(SupplierFacilityModel).where(
            SupplierFacilityModel.tenant_id == tenant_id,
            SupplierFacilityModel.supplier_user_id == current_user.id,
        )
    ).scalars().all()

    facilities_by_key = {
        _facility_identity_key(
            {
                "name": facility.name,
                "street": facility.street,
                "city": facility.city,
                "state": facility.state,
                "postal_code": facility.postal_code,
            }
        ): facility
        for facility in existing_facilities
    }
    facilities_by_name = {facility.name.strip().lower(): facility for facility in existing_facilities if facility.name}

    def resolve_facility_by_name(name: str) -> SupplierFacilityModel:
        normalized = _normalize_text(name).lower()
        facility = facilities_by_name.get(normalized)
        if facility is not None:
            return facility

        facility = db.execute(
            select(SupplierFacilityModel).where(
                SupplierFacilityModel.tenant_id == tenant_id,
                SupplierFacilityModel.supplier_user_id == current_user.id,
                func.lower(SupplierFacilityModel.name) == normalized,
            )
        ).scalar_one_or_none()
        if facility is None:
            raise ValueError(f"Unknown facility_name reference: {name}")
        facilities_by_name[normalized] = facility
        return facility

    try:
        for row in facilities_payload:
            key = _facility_identity_key(row)
            existing = facilities_by_key.get(key)
            if existing is None:
                facility = SupplierFacilityModel(
                    tenant_id=tenant_id,
                    supplier_user_id=current_user.id,
                    name=_normalize_text(row.get("name")),
                    street=_normalize_text(row.get("street")),
                    city=_normalize_text(row.get("city")),
                    state=_normalize_text(row.get("state")),
                    postal_code=_normalize_text(row.get("postal_code")),
                    fda_registration_number=(
                        _normalize_text(row.get("fda_registration_number")) or None
                    ),
                    roles=row.get("roles") or [],
                )
                db.add(facility)
                db.flush()
                facilities_by_key[key] = facility
                facilities_by_name[facility.name.strip().lower()] = facility
                facilities_created += 1
            else:
                existing.fda_registration_number = (
                    _normalize_text(row.get("fda_registration_number")) or existing.fda_registration_number
                )
                incoming_roles = row.get("roles") or []
                if incoming_roles:
                    existing.roles = incoming_roles
                facilities_by_name[existing.name.strip().lower()] = existing
                facilities_updated += 1

        for row in ftl_scopes_payload:
            facility = resolve_facility_by_name(str(row.get("facility_name") or ""))
            category_id = _normalize_text(row.get("category_id"))
            category = FTL_CATEGORY_LOOKUP.get(category_id)
            if category is None:
                raise ValueError(f"Unknown FTL category_id: {category_id}")

            scoped = db.execute(
                select(SupplierFacilityFTLCategoryModel).where(
                    SupplierFacilityFTLCategoryModel.facility_id == facility.id,
                    SupplierFacilityFTLCategoryModel.category_id == category_id,
                )
            ).scalar_one_or_none()
            if scoped is None:
                scoped = SupplierFacilityFTLCategoryModel(
                    tenant_id=tenant_id,
                    facility_id=facility.id,
                    category_id=category_id,
                    category_name=category["name"],
                    required_ctes=category["ctes"],
                )
                db.add(scoped)
            else:
                scoped.category_name = category["name"]
                scoped.required_ctes = category["ctes"]

            ftl_scopes_upserted += 1
            categories_by_facility[facility.id].append(
                {
                    "id": category_id,
                    "name": category["name"],
                    "ctes": category["ctes"],
                }
            )

        for row in tlcs_payload:
            facility = resolve_facility_by_name(str(row.get("facility_name") or ""))
            tlc_code = _normalize_text(row.get("tlc_code"))
            if not tlc_code:
                raise ValueError("tlc_code is required for TLC rows")

            existing_lot = db.execute(
                select(SupplierTraceabilityLotModel).where(
                    SupplierTraceabilityLotModel.tenant_id == tenant_id,
                    SupplierTraceabilityLotModel.supplier_user_id == current_user.id,
                    SupplierTraceabilityLotModel.tlc_code == tlc_code,
                )
            ).scalar_one_or_none()
            if existing_lot is None:
                lot = SupplierTraceabilityLotModel(
                    tenant_id=tenant_id,
                    supplier_user_id=current_user.id,
                    facility_id=facility.id,
                    tlc_code=tlc_code,
                    product_description=(
                        _normalize_text(row.get("product_description")) or None
                    ),
                    status=_normalize_text(row.get("status")) or "active",
                )
                db.add(lot)
                tlcs_created += 1
            else:
                existing_lot.facility_id = facility.id
                incoming_description = _normalize_text(row.get("product_description"))
                if incoming_description:
                    existing_lot.product_description = incoming_description
                incoming_status = _normalize_text(row.get("status"))
                if incoming_status:
                    existing_lot.status = incoming_status
                tlcs_updated += 1

        # Session autoflush is disabled in production settings/tests, so flush TLC
        # upserts before event queries to avoid duplicate same-TLC inserts.
        db.flush()

        sorted_events = sorted(
            events_payload,
            key=lambda item: (
                _normalize_text(item.get("tlc_code")),
                _normalize_text(item.get("event_time")),
            ),
        )

        # Process events in batches to avoid OOM and timeout on large uploads.
        # Each batch is flushed to the DB but the full commit happens at the end.
        BATCH_SIZE = 500
        for batch_start in range(0, len(sorted_events), BATCH_SIZE):
            batch = sorted_events[batch_start:batch_start + BATCH_SIZE]
            for row in batch:
                facility = resolve_facility_by_name(str(row.get("facility_name") or ""))
                event, lot = _persist_supplier_cte_event(
                    db,
                    tenant_id=tenant_id,
                    current_user=current_user,
                    facility=facility,
                    cte_type=str(row.get("cte_type") or ""),
                    tlc_code=str(row.get("tlc_code") or ""),
                    event_time=_parse_optional_datetime(row.get("event_time")),
                    kde_data=row.get("kde_data") or {},
                    obligation_ids=row.get("obligation_ids") or [],
                )
                emitted_event_rows.append((event, lot, facility))
            # Flush batch to DB (writes to Postgres, keeps transaction open)
            db.flush()

        db.commit()

    except SQLAlchemyError:
        db.rollback()
        raise

    sync_warnings: list[str] = []

    for facility_id, categories in categories_by_facility.items():
        facility = next((f for f in facilities_by_name.values() if f.id == facility_id), None)
        if facility is None:
            continue
        try:
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
        except Exception as exc:  # pragma: no cover - external dependency failure
            logger.warning(
                "bulk_upload_facility_graph_sync_failed",
                tenant_id=str(tenant_id),
                facility_id=str(facility.id),
                error=str(exc),
            )
            sync_warnings.append(f"facility_scoping:{facility.id}")

    # Graph sync for events.
    #
    # Fast path (first ``MAX_SYNC_EVENTS``): write to Neo4j synchronously via
    # :func:`supplier_graph_sync.record_cte_event`. Keeps the happy path for
    # small imports simple and responsive.
    #
    # Durable path (remaining events): enqueue to the ``graph_outbox`` table
    # via :func:`enqueue_graph_write`. A background drainer (see
    # ``services/admin/app/graph_outbox.py::GraphOutboxDrainer``) replays each
    # row into Neo4j with retry + backoff. Prior to #1411 this code branch
    # appended a misleading ``graph_sync_deferred`` warning claiming a
    # background worker would pick the events up, but no such wiring existed
    # — a 500-event bulk import silently dropped 400 Neo4j nodes. The
    # outbox is the existing durable primitive for exactly this case
    # (docstring of ``graph_outbox.py`` explicitly calls out the adoption
    # pattern).
    MAX_SYNC_EVENTS = 100
    events_to_sync = emitted_event_rows[:MAX_SYNC_EVENTS]
    events_to_enqueue = emitted_event_rows[MAX_SYNC_EVENTS:]

    for event, lot, facility in events_to_sync:
        try:
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
        except Exception as exc:  # pragma: no cover - external dependency failure
            logger.warning(
                "bulk_upload_event_graph_sync_failed",
                tenant_id=str(tenant_id),
                cte_event_id=str(event.id),
                error=str(exc),
            )
            sync_warnings.append(f"cte_event:{event.id}")

    # Enqueue the overflow to graph_outbox. We do this in its own short
    # transaction so an outbox failure never rolls back the canonical
    # Postgres write that has already been committed. If the enqueue
    # itself fails (bad DB state, missing table on a misconfigured env,
    # etc.) we surface a warning and keep going — the bulk import still
    # succeeds because the canonical FSMA data is already durable in
    # Postgres; the graph mirror is eventually-consistent best-effort.
    enqueued_count = 0
    for event, lot, facility in events_to_enqueue:
        try:
            enqueue_graph_write(
                db,
                tenant_id=str(tenant_id),
                operation="cte_event_recorded",
                cypher=CTE_EVENT_QUERY,
                params={
                    "operation": "cte_event_recorded",
                    "tenant_id": str(tenant_id),
                    "facility_id": str(facility.id),
                    "facility_name": facility.name,
                    "cte_event_id": str(event.id),
                    "cte_type": event.cte_type,
                    "event_time": _iso_utc(event.event_time),
                    "tlc_code": lot.tlc_code,
                    "product_description": lot.product_description,
                    "lot_status": lot.status,
                    "kde_data": event.kde_data or {},
                    "payload_sha256": event.payload_sha256,
                    "merkle_prev_hash": event.merkle_prev_hash,
                    "merkle_hash": event.merkle_hash,
                    "sequence_number": int(event.sequence_number),
                    "obligation_ids": event.obligation_ids or [],
                },
                # Stable dedupe so a bulk-commit retry doesn't double-enqueue.
                dedupe_key=f"bulk_upload:{event.id}",
            )
            enqueued_count += 1
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "bulk_upload_event_graph_outbox_enqueue_failed",
                tenant_id=str(tenant_id),
                cte_event_id=str(event.id),
                error=str(exc),
            )
            sync_warnings.append(f"graph_outbox_enqueue_failed:{event.id}")

    # Commit the outbox inserts so the drainer can pick them up. Safe to
    # run even when no rows were enqueued — commit on an empty unit of
    # work is a no-op.
    if events_to_enqueue:
        try:
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            logger.warning(
                "bulk_upload_event_graph_outbox_commit_failed",
                tenant_id=str(tenant_id),
                error=str(exc),
            )
            # The enqueue attempts we counted above did not actually land.
            sync_warnings.append(
                f"graph_outbox_commit_failed:{len(events_to_enqueue)}"
            )
            enqueued_count = 0

    if enqueued_count > 0:
        sync_warnings.append(
            f"graph_sync_deferred:{enqueued_count} events enqueued to graph_outbox for async replay"
        )

    summary = {
        "facilities_created": facilities_created,
        "facilities_updated": facilities_updated,
        "ftl_scopes_upserted": ftl_scopes_upserted,
        "tlcs_created": tlcs_created,
        "tlcs_updated": tlcs_updated,
        "events_chained": len(emitted_event_rows),
        "last_merkle_hash": emitted_event_rows[-1][0].merkle_hash if emitted_event_rows else None,
    }
    if sync_warnings:
        summary["sync_warning_count"] = len(sync_warnings)
        summary["sync_warnings"] = sync_warnings
    return summary
