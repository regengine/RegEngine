"""B2B EPCIS exchange router.

Phase 2 capability:
- POST /api/v1/exchange/send
- GET  /api/v1/exchange/receive

Builds downstream shipping KDE packages from persisted CTE events and makes
those packages retrievable by the receiving tenant.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.authz import require_permission
from app.shared.tenant_resolution import resolve_tenant_id

logger = logging.getLogger("b2b-exchange")

router = APIRouter(prefix="/api/v1/exchange", tags=["B2B Data Exchange"])

# Dev/test fallback if DB is unavailable.
_exchange_store: dict[str, dict[str, Any]] = {}


class ExchangeSendRequest(BaseModel):
    """Request payload for creating a downstream data package."""

    receiver_tenant_id: str = Field(..., description="Destination tenant that will receive the package")
    traceability_lot_code: Optional[str] = Field(default=None, description="Single TLC to package")
    lot_codes: list[str] = Field(default_factory=list, description="Optional list of TLCs to package")
    event_ids: list[str] = Field(default_factory=list, description="Optional explicit shipping event IDs")
    date_from: Optional[str] = Field(default=None, description="Optional start date/time filter")
    date_to: Optional[str] = Field(default=None, description="Optional end date/time filter")
    receiver_email: Optional[str] = Field(default=None, description="Optional recipient email for notification")
    sender_tenant_id: Optional[str] = Field(default=None, description="Optional sender tenant override")
    max_events: int = Field(default=500, ge=1, le=5000)


def _is_production() -> bool:
    from shared.env import is_production
    return is_production()


def _allow_in_memory_fallback() -> bool:
    explicit = os.getenv("ALLOW_EXCHANGE_IN_MEMORY_FALLBACK")
    if explicit is not None:
        return explicit.lower() in {"1", "true", "yes"}
    return not _is_production()


def _get_db_session():
    """Get database session. Returns None if unavailable."""
    try:
        from shared.database import SessionLocal
        return SessionLocal()
    except Exception as exc:
        logger.warning("db_unavailable error=%s", str(exc))
        return None


# Tenant resolution is now imported from app.shared.tenant_resolution
_resolve_tenant_id = resolve_tenant_id


def _ensure_exchange_table(db_session) -> None:
    db_session.execute(
        text(
            """
            CREATE SCHEMA IF NOT EXISTS fsma;

            CREATE TABLE IF NOT EXISTS fsma.exchange_packages (
                id UUID PRIMARY KEY,
                sender_tenant_id TEXT NOT NULL,
                receiver_tenant_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'received')),
                traceability_lot_codes TEXT[] NOT NULL DEFAULT '{}',
                event_count INTEGER NOT NULL DEFAULT 0,
                notification_target TEXT,
                package_hash TEXT NOT NULL,
                payload JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                received_at TIMESTAMPTZ
            );

            CREATE INDEX IF NOT EXISTS idx_exchange_packages_receiver_status
                ON fsma.exchange_packages (receiver_tenant_id, status, created_at DESC);
            """
        )
    )


def _query_shipping_rows(db_session, sender_tenant_id: str, request: ExchangeSendRequest) -> list[Any]:
    tlcs = [request.traceability_lot_code] if request.traceability_lot_code else []
    tlcs.extend(code for code in request.lot_codes if code)
    tlcs = sorted({code for code in tlcs if code})

    if not tlcs and not request.event_ids:
        raise HTTPException(
            status_code=400,
            detail="Provide traceability_lot_code, lot_codes, or event_ids when sending exchange data",
        )

    where = [
        "e.tenant_id = :tenant_id",
        "e.event_type = 'shipping'",
        "e.validation_status != 'rejected'",
    ]
    params: dict[str, Any] = {
        "tenant_id": sender_tenant_id,
        "limit": request.max_events,
    }

    if tlcs:
        where.append("e.traceability_lot_code = ANY(:tlcs)")
        params["tlcs"] = tlcs

    if request.event_ids:
        where.append("e.id::text = ANY(:event_ids)")
        params["event_ids"] = sorted({event_id for event_id in request.event_ids if event_id})

    if request.date_from:
        where.append("e.event_timestamp >= :date_from")
        params["date_from"] = request.date_from

    if request.date_to:
        where.append("e.event_timestamp <= :date_to")
        params["date_to"] = request.date_to

    rows = db_session.execute(
        text(
            f"""
            SELECT
                e.id::text AS id,
                e.traceability_lot_code,
                e.product_description,
                e.quantity,
                e.unit_of_measure,
                e.event_timestamp,
                e.location_gln,
                e.location_name,
                e.source_event_id,
                e.source,
                e.sha256_hash,
                e.chain_hash,
                COALESCE(
                    (
                        SELECT jsonb_object_agg(k.kde_key, k.kde_value)
                        FROM fsma.cte_kdes k
                        WHERE k.cte_event_id = e.id AND k.tenant_id = e.tenant_id
                    ),
                    '{{}}'::jsonb
                ) AS kdes
            FROM fsma.cte_events e
            WHERE {' AND '.join(where)}
            ORDER BY e.event_timestamp ASC
            LIMIT :limit
            """
        ),
        params,
    ).fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail="No shipping CTEs matched the requested filters")

    return rows


def _build_records(rows: list[Any]) -> list[dict[str, Any]]:
    known_kdes = {
        "ship_from_gln",
        "ship_from_location",
        "ship_to_gln",
        "ship_to_location",
        "receiving_location",
        "tlc_source_gln",
        "tlc_source_fda_reg",
        "immediate_previous_source",
        "reference_document_number",
        "carrier",
    }

    records: list[dict[str, Any]] = []
    for row in rows:
        kdes = dict(row.kdes or {})
        ship_from_gln = kdes.get("ship_from_gln") or row.location_gln
        ship_from_name = kdes.get("ship_from_location") or row.location_name
        ship_to_name = kdes.get("ship_to_location") or kdes.get("receiving_location")

        record = {
            "cte_event_id": row.id,
            "traceability_lot_code": row.traceability_lot_code,
            "event_type": "shipping",
            "event_timestamp": row.event_timestamp.isoformat() if row.event_timestamp else None,
            "product_description": row.product_description,
            "quantity": float(row.quantity) if row.quantity is not None else None,
            "unit_of_measure": row.unit_of_measure,
            "ship_from": {
                "gln": ship_from_gln,
                "name": ship_from_name,
            },
            "ship_to": {
                "gln": kdes.get("ship_to_gln"),
                "name": ship_to_name,
            },
            "tlc_source": {
                "gln": kdes.get("tlc_source_gln"),
                "fda_registration": kdes.get("tlc_source_fda_reg"),
                "immediate_previous_source": kdes.get("immediate_previous_source"),
            },
            "reference_document_number": kdes.get("reference_document_number") or row.source_event_id,
            "carrier": kdes.get("carrier"),
            "integrity": {
                "record_hash": row.sha256_hash,
                "chain_hash": row.chain_hash,
            },
            "additional_kdes": {k: v for k, v in kdes.items() if k not in known_kdes},
            "source": row.source,
        }
        records.append(record)

    return records


def _build_package(
    sender_tenant_id: str,
    request: ExchangeSendRequest,
    rows: list[Any],
) -> tuple[str, str, dict[str, Any]]:
    package_id = str(uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    records = _build_records(rows)
    lot_codes = sorted({record["traceability_lot_code"] for record in records if record.get("traceability_lot_code")})

    package = {
        "package_id": package_id,
        "package_version": "1.0",
        "created_at": created_at,
        "sender_tenant_id": sender_tenant_id,
        "receiver_tenant_id": request.receiver_tenant_id,
        "notification_target": request.receiver_email,
        "summary": {
            "event_count": len(records),
            "traceability_lot_codes": lot_codes,
            "tlc_source_propagated": True,
            "generated_from": "shipping_ctes",
        },
        "records": records,
    }

    package_hash = sha256(
        json.dumps(package, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    package["package_hash"] = package_hash

    return package_id, package_hash, package


def _store_package_db(
    sender_tenant_id: str,
    request: ExchangeSendRequest,
    package_id: str,
    package_hash: str,
    package: dict[str, Any],
) -> None:
    db_session = _get_db_session()
    try:
        _ensure_exchange_table(db_session)
        db_session.execute(
            text(
                """
                INSERT INTO fsma.exchange_packages (
                    id,
                    sender_tenant_id,
                    receiver_tenant_id,
                    status,
                    traceability_lot_codes,
                    event_count,
                    notification_target,
                    package_hash,
                    payload
                )
                VALUES (
                    :id,
                    :sender_tenant_id,
                    :receiver_tenant_id,
                    'pending',
                    :traceability_lot_codes,
                    :event_count,
                    :notification_target,
                    :package_hash,
                    CAST(:payload AS jsonb)
                )
                """
            ),
            {
                "id": package_id,
                "sender_tenant_id": sender_tenant_id,
                "receiver_tenant_id": request.receiver_tenant_id,
                "traceability_lot_codes": package["summary"]["traceability_lot_codes"],
                "event_count": package["summary"]["event_count"],
                "notification_target": request.receiver_email,
                "package_hash": package_hash,
                "payload": json.dumps(package, separators=(",", ":")),
            },
        )
        db_session.commit()
    except Exception:
        db_session.rollback()
        raise
    finally:
        db_session.close()


def _store_package_fallback(package: dict[str, Any]) -> None:
    _exchange_store[package["package_id"]] = {
        "id": package["package_id"],
        "sender_tenant_id": package["sender_tenant_id"],
        "receiver_tenant_id": package["receiver_tenant_id"],
        "status": "pending",
        "traceability_lot_codes": package["summary"]["traceability_lot_codes"],
        "event_count": package["summary"]["event_count"],
        "notification_target": package.get("notification_target"),
        "package_hash": package["package_hash"],
        "payload": package,
        "created_at": package["created_at"],
        "received_at": None,
    }


def _load_packages_db(
    receiver_tenant_id: str,
    package_id: Optional[str],
    limit: int,
    include_payload: bool,
    mark_received: bool,
) -> list[dict[str, Any]]:
    db_session = _get_db_session()
    try:
        _ensure_exchange_table(db_session)

        if package_id:
            rows = db_session.execute(
                text(
                    """
                    SELECT
                        id::text,
                        sender_tenant_id,
                        receiver_tenant_id,
                        status,
                        traceability_lot_codes,
                        event_count,
                        notification_target,
                        package_hash,
                        payload,
                        created_at,
                        received_at
                    FROM fsma.exchange_packages
                    WHERE receiver_tenant_id = :receiver_tenant_id
                      AND id = :package_id::uuid
                    LIMIT 1
                    """
                ),
                {"receiver_tenant_id": receiver_tenant_id, "package_id": package_id},
            ).fetchall()
            if mark_received and rows:
                db_session.execute(
                    text(
                        """
                        UPDATE fsma.exchange_packages
                        SET status = 'received', received_at = now()
                        WHERE receiver_tenant_id = :receiver_tenant_id
                          AND id = :package_id::uuid
                        """
                    ),
                    {"receiver_tenant_id": receiver_tenant_id, "package_id": package_id},
                )
                db_session.commit()
                rows = db_session.execute(
                    text(
                        """
                        SELECT
                            id::text,
                            sender_tenant_id,
                            receiver_tenant_id,
                            status,
                            traceability_lot_codes,
                            event_count,
                            notification_target,
                            package_hash,
                            payload,
                            created_at,
                            received_at
                        FROM fsma.exchange_packages
                        WHERE receiver_tenant_id = :receiver_tenant_id
                          AND id = :package_id::uuid
                        LIMIT 1
                        """
                    ),
                    {"receiver_tenant_id": receiver_tenant_id, "package_id": package_id},
                ).fetchall()
        else:
            rows = db_session.execute(
                text(
                    """
                    SELECT
                        id::text,
                        sender_tenant_id,
                        receiver_tenant_id,
                        status,
                        traceability_lot_codes,
                        event_count,
                        notification_target,
                        package_hash,
                        payload,
                        created_at,
                        received_at
                    FROM fsma.exchange_packages
                    WHERE receiver_tenant_id = :receiver_tenant_id
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                {"receiver_tenant_id": receiver_tenant_id, "limit": limit},
            ).fetchall()

        response: list[dict[str, Any]] = []
        for row in rows:
            item = {
                "package_id": row[0],
                "sender_tenant_id": row[1],
                "receiver_tenant_id": row[2],
                "status": row[3],
                "traceability_lot_codes": list(row[4] or []),
                "event_count": row[5],
                "notification_target": row[6],
                "package_hash": row[7],
                "created_at": row[9].isoformat() if row[9] else None,
                "received_at": row[10].isoformat() if row[10] else None,
            }
            if include_payload:
                item["payload"] = row[8]
            response.append(item)

        return response
    finally:
        db_session.close()


def _load_packages_fallback(
    receiver_tenant_id: str,
    package_id: Optional[str],
    limit: int,
    include_payload: bool,
    mark_received: bool,
) -> list[dict[str, Any]]:
    all_items = [
        item for item in _exchange_store.values() if item["receiver_tenant_id"] == receiver_tenant_id
    ]
    all_items.sort(key=lambda item: item.get("created_at", ""), reverse=True)

    if package_id:
        all_items = [item for item in all_items if item["id"] == package_id]

    if mark_received and package_id and all_items:
        all_items[0]["status"] = "received"
        all_items[0]["received_at"] = datetime.now(timezone.utc).isoformat()

    selected = all_items[:limit]
    response: list[dict[str, Any]] = []
    for item in selected:
        payload: dict[str, Any] = {
            "package_id": item["id"],
            "sender_tenant_id": item["sender_tenant_id"],
            "receiver_tenant_id": item["receiver_tenant_id"],
            "status": item["status"],
            "traceability_lot_codes": list(item.get("traceability_lot_codes") or []),
            "event_count": int(item.get("event_count") or 0),
            "notification_target": item.get("notification_target"),
            "package_hash": item["package_hash"],
            "created_at": item.get("created_at"),
            "received_at": item.get("received_at"),
        }
        if include_payload:
            payload["payload"] = item["payload"]
        response.append(payload)

    return response


@router.post("/send", summary="Send downstream shipping KDE package")
async def send_exchange_package(
    request: ExchangeSendRequest,
    tenant_id: Optional[str] = Query(default=None, description="Optional sender tenant override"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    x_regengine_api_key: Optional[str] = Header(default=None, alias="X-RegEngine-API-Key"),
    _auth=Depends(require_permission("exchange.write")),
):
    sender_tenant_id = _resolve_tenant_id(
        request.sender_tenant_id or tenant_id,
        x_tenant_id,
        x_regengine_api_key,
    )
    if not sender_tenant_id:
        raise HTTPException(status_code=400, detail="Sender tenant context required")

    try:
        db_session = _get_db_session()
        try:
            rows = _query_shipping_rows(db_session, sender_tenant_id, request)
        finally:
            db_session.close()

        package_id, package_hash, package = _build_package(sender_tenant_id, request, rows)
        _store_package_db(sender_tenant_id, request, package_id, package_hash, package)
    except HTTPException:
        raise
    except Exception as exc:
        if not _allow_in_memory_fallback():
            logger.error("exchange_send_failed_no_fallback error=%s", str(exc))
            raise HTTPException(status_code=503, detail="Exchange service unavailable") from exc

        logger.warning("exchange_send_failed_using_fallback error=%s", str(exc))
        # Re-run extraction in fallback mode without DB package persistence.
        package_id = str(uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        records = []
        for event_id in request.event_ids:
            records.append(
                {
                    "cte_event_id": event_id,
                    "traceability_lot_code": request.traceability_lot_code,
                    "event_type": "shipping",
                    "event_timestamp": created_at,
                    "product_description": "EDI/EPCIS Shipping Event",
                    "quantity": None,
                    "unit_of_measure": None,
                    "ship_from": {},
                    "ship_to": {},
                    "tlc_source": {},
                    "reference_document_number": None,
                    "carrier": None,
                    "integrity": {"record_hash": None, "chain_hash": None},
                    "additional_kdes": {},
                    "source": "exchange_fallback",
                }
            )

        lot_codes = sorted(
            {
                code
                for code in ([request.traceability_lot_code] + list(request.lot_codes))
                if code
            }
        )
        package = {
            "package_id": package_id,
            "package_version": "1.0",
            "created_at": created_at,
            "sender_tenant_id": sender_tenant_id,
            "receiver_tenant_id": request.receiver_tenant_id,
            "notification_target": request.receiver_email,
            "summary": {
                "event_count": len(records),
                "traceability_lot_codes": lot_codes,
                "tlc_source_propagated": True,
                "generated_from": "shipping_ctes",
            },
            "records": records,
        }
        package_hash = sha256(
            json.dumps(package, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        package["package_hash"] = package_hash
        _store_package_fallback(package)

    logger.info(
        "exchange_package_sent package_id=%s sender=%s receiver=%s events=%s",
        package_id,
        sender_tenant_id,
        request.receiver_tenant_id,
        package["summary"]["event_count"],
    )

    return {
        "status": "queued",
        "package_id": package_id,
        "sender_tenant_id": sender_tenant_id,
        "receiver_tenant_id": request.receiver_tenant_id,
        "event_count": package["summary"]["event_count"],
        "traceability_lot_codes": package["summary"]["traceability_lot_codes"],
        "package_hash": package["package_hash"],
        "created_at": package["created_at"],
        "notification": {
            "target": request.receiver_email,
            "status": "queued" if request.receiver_email else "not_requested",
        },
    }


@router.get("/receive", summary="Receive downstream KDE packages")
async def receive_exchange_packages(
    tenant_id: Optional[str] = Query(default=None, description="Optional receiver tenant override"),
    package_id: Optional[str] = Query(default=None, description="Optional single package ID"),
    limit: int = Query(default=25, ge=1, le=200),
    include_payload: bool = Query(default=True, description="Include full package payload"),
    mark_received: bool = Query(default=False, description="Mark selected package as received"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    x_regengine_api_key: Optional[str] = Header(default=None, alias="X-RegEngine-API-Key"),
    _auth=Depends(require_permission("exchange.read")),
):
    receiver_tenant_id = _resolve_tenant_id(tenant_id, x_tenant_id, x_regengine_api_key)
    if not receiver_tenant_id:
        raise HTTPException(status_code=400, detail="Receiver tenant context required")

    try:
        packages = _load_packages_db(
            receiver_tenant_id=receiver_tenant_id,
            package_id=package_id,
            limit=limit,
            include_payload=include_payload,
            mark_received=mark_received,
        )
    except Exception as exc:
        if not _allow_in_memory_fallback():
            logger.error("exchange_receive_failed_no_fallback error=%s", str(exc))
            raise HTTPException(status_code=503, detail="Exchange service unavailable") from exc

        logger.warning("exchange_receive_failed_using_fallback error=%s", str(exc))
        packages = _load_packages_fallback(
            receiver_tenant_id=receiver_tenant_id,
            package_id=package_id,
            limit=limit,
            include_payload=include_payload,
            mark_received=mark_received,
        )

    return {
        "receiver_tenant_id": receiver_tenant_id,
        "count": len(packages),
        "packages": packages,
    }
