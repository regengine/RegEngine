"""
FDA 24-Hour Export Router.

Provides the endpoints that fulfill RegEngine's core promise:
"When the FDA calls, produce compliant traceability records within 24 hours."

This module reads from the Postgres persistence layer (fsma.cte_events)
and generates sortable, searchable CSV exports in the FDA's expected format.

Endpoints:
    GET  /api/v1/fda/export            — Generate FDA spreadsheet for a TLC
    GET  /api/v1/fda/export/all        — Export all events (date-filtered)
    GET  /api/v1/fda/export/history     — View export audit log
    POST /api/v1/fda/export/verify      — Verify a previous export's integrity
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

logger = logging.getLogger("fda-export")

router = APIRouter(prefix="/api/v1/fda", tags=["FDA Export"])


# ---------------------------------------------------------------------------
# Auth (shared with webhook router)
# ---------------------------------------------------------------------------

def _verify_api_key(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    x_regengine_api_key: Optional[str] = Header(default=None, alias="X-RegEngine-API-Key"),
) -> None:
    from app.config import get_settings
    settings = get_settings()
    configured_api_key = getattr(settings, "api_key", None)
    if configured_api_key is not None:
        provided_api_key = x_api_key or x_regengine_api_key
        if not provided_api_key or provided_api_key != configured_api_key:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ---------------------------------------------------------------------------
# FDA Spreadsheet Column Spec
# ---------------------------------------------------------------------------
# These columns align with FDA's expected format for FSMA 204 traceability
# records. The column names match the FDA's IFT spreadsheet specification.

FDA_COLUMNS = [
    "Traceability Lot Code (TLC)",
    "Product Description",
    "Quantity",
    "Unit of Measure",
    "Event Type (CTE)",
    "Event Date",
    "Event Time",
    "Location GLN",
    "Location Name",
    "Ship From GLN",
    "Ship From Name",
    "Ship To GLN",
    "Ship To Name",
    "Immediate Previous Source",
    "TLC Source GLN",
    "TLC Source FDA Registration",
    "Source Document",
    "Record Hash (SHA-256)",
    "Chain Hash",
]


def _event_to_fda_row(event: dict) -> dict:
    """Convert a persisted CTE event to an FDA spreadsheet row."""
    kdes = event.get("kdes", {})
    timestamp = event.get("event_timestamp", "")

    # Split timestamp into date and time
    event_date = ""
    event_time = ""
    if timestamp:
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            event_date = dt.strftime("%Y-%m-%d")
            event_time = dt.strftime("%H:%M:%S %Z")
        except (ValueError, AttributeError):
            event_date = str(timestamp)[:10]

    return {
        "Traceability Lot Code (TLC)": event.get("traceability_lot_code", ""),
        "Product Description": event.get("product_description", ""),
        "Quantity": event.get("quantity", ""),
        "Unit of Measure": event.get("unit_of_measure", ""),
        "Event Type (CTE)": event.get("event_type", ""),
        "Event Date": event_date,
        "Event Time": event_time,
        "Location GLN": event.get("location_gln", "") or "",
        "Location Name": event.get("location_name", "") or "",
        "Ship From GLN": kdes.get("ship_from_gln", ""),
        "Ship From Name": kdes.get("ship_from_location", ""),
        "Ship To GLN": kdes.get("ship_to_gln", ""),
        "Ship To Name": kdes.get("ship_to_location", kdes.get("receiving_location", "")),
        "Immediate Previous Source": kdes.get("immediate_previous_source", ""),
        "TLC Source GLN": kdes.get("tlc_source_gln", ""),
        "TLC Source FDA Registration": kdes.get("tlc_source_fda_reg", ""),
        "Source Document": event.get("source", ""),
        "Record Hash (SHA-256)": event.get("sha256_hash", ""),
        "Chain Hash": event.get("chain_hash", ""),
    }


def _generate_csv(events: list[dict]) -> str:
    """Generate FDA-compliant CSV from a list of CTE events."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=FDA_COLUMNS)
    writer.writeheader()

    for event in events:
        writer.writerow(_event_to_fda_row(event))

    return output.getvalue()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/export",
    summary="Generate FDA export for a traceability lot code",
    description=(
        "Query all CTE events for a specific TLC within an optional date range, "
        "generate the FDA-required CSV spreadsheet, log the export for audit, "
        "and return the file. This is the endpoint that fulfills the 24-hour "
        "FDA response requirement."
    ),
)
async def export_fda_spreadsheet(
    tlc: str = Query(..., description="Traceability Lot Code to trace"),
    start_date: Optional[str] = Query(None, description="Start date filter (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date filter (YYYY-MM-DD)"),
    tenant_id: str = Query("default", description="Tenant identifier"),
    _: None = Depends(_verify_api_key),
):
    """Generate and return an FDA-compliant traceability export."""
    db_session = None
    try:
        from shared.database import SessionLocal
        from shared.cte_persistence import CTEPersistence

        db_session = SessionLocal()
        persistence = CTEPersistence(db_session)

        # Query events
        events = persistence.query_events_by_tlc(
            tenant_id=tenant_id,
            tlc=tlc,
            start_date=start_date,
            end_date=end_date,
        )

        if not events:
            raise HTTPException(
                status_code=404,
                detail=f"No traceability records found for TLC '{tlc}'"
            )

        # Generate CSV
        csv_content = _generate_csv(events)

        # Hash the export for audit integrity
        export_hash = hashlib.sha256(csv_content.encode("utf-8")).hexdigest()

        # Log the export
        persistence.log_export(
            tenant_id=tenant_id,
            export_hash=export_hash,
            record_count=len(events),
            query_tlc=tlc,
            query_start_date=start_date,
            query_end_date=end_date,
            generated_by="api",
        )
        db_session.commit()

        # Generate filename
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_tlc = tlc.replace("/", "_").replace(" ", "_")[:50]
        filename = f"fda_export_{safe_tlc}_{timestamp}.csv"

        logger.info(
            "fda_export_generated",
            extra={
                "tlc": tlc,
                "record_count": len(events),
                "export_hash": export_hash[:16],
                "tenant_id": tenant_id,
            },
        )

        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "X-Export-Hash": export_hash,
                "X-Record-Count": str(len(events)),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("fda_export_failed", extra={"error": str(e), "tlc": tlc})
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")
    finally:
        if db_session:
            db_session.close()


@router.get(
    "/export/all",
    summary="Export all CTE events",
    description="Export all traceability events for a tenant within an optional date range.",
)
async def export_all_events(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    event_type: Optional[str] = Query(None, description="Filter by CTE type"),
    tenant_id: str = Query("default"),
    _: None = Depends(_verify_api_key),
):
    """Export all events as FDA-format CSV."""
    db_session = None
    try:
        from shared.database import SessionLocal
        from shared.cte_persistence import CTEPersistence

        db_session = SessionLocal()
        persistence = CTEPersistence(db_session)

        events, total = persistence.query_all_events(
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
            event_type=event_type,
            limit=10000,
        )

        # For the full export, fetch KDEs for each event
        full_events = []
        for evt in events:
            full = persistence.query_events_by_tlc(
                tenant_id=tenant_id,
                tlc=evt["traceability_lot_code"],
                start_date=start_date,
                end_date=end_date,
            )
            full_events.extend(full)

        # Deduplicate by event ID
        seen = set()
        deduped = []
        for e in full_events:
            if e["id"] not in seen:
                seen.add(e["id"])
                deduped.append(e)

        csv_content = _generate_csv(deduped)
        export_hash = hashlib.sha256(csv_content.encode("utf-8")).hexdigest()

        persistence.log_export(
            tenant_id=tenant_id,
            export_hash=export_hash,
            record_count=len(deduped),
            query_start_date=start_date,
            query_end_date=end_date,
            generated_by="api",
        )
        db_session.commit()

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"fda_export_all_{timestamp}.csv"

        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "X-Export-Hash": export_hash,
                "X-Record-Count": str(len(deduped)),
            },
        )

    except Exception as e:
        logger.error("fda_export_all_failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")
    finally:
        if db_session:
            db_session.close()


@router.get(
    "/export/history",
    summary="View FDA export audit log",
    description="Returns the history of all FDA exports generated for this tenant.",
)
async def export_history(
    tenant_id: str = Query("default"),
    limit: int = Query(50, ge=1, le=200),
    _: None = Depends(_verify_api_key),
):
    """Return export audit log."""
    db_session = None
    try:
        from shared.database import SessionLocal
        db_session = SessionLocal()

        from sqlalchemy import text
        rows = db_session.execute(
            text("""
                SELECT id, export_type, query_tlc, query_start_date, query_end_date,
                       record_count, export_hash, generated_by, generated_at
                FROM fsma.fda_export_log
                WHERE tenant_id = :tid
                ORDER BY generated_at DESC
                LIMIT :lim
            """),
            {"tid": tenant_id, "lim": limit},
        ).fetchall()

        return {
            "tenant_id": tenant_id,
            "exports": [
                {
                    "id": str(r[0]),
                    "export_type": r[1],
                    "query_tlc": r[2],
                    "query_start_date": str(r[3]) if r[3] else None,
                    "query_end_date": str(r[4]) if r[4] else None,
                    "record_count": r[5],
                    "export_hash": r[6],
                    "generated_by": r[7],
                    "generated_at": r[8].isoformat() if r[8] else None,
                }
                for r in rows
            ],
            "total": len(rows),
        }

    except Exception as e:
        logger.error("export_history_failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"History query failed: {str(e)}")
    finally:
        if db_session:
            db_session.close()


@router.get(
    "/export/recall",
    summary="Recall-filtered FDA export",
    description=(
        "Generate an FDA-compliant export filtered by product, location, and/or date range. "
        "This is the endpoint used during actual FDA recall investigations: "
        "'Show me everything from [location] on [date] for [product].' "
        "Supports any combination of filters."
    ),
)
async def export_recall_filtered(
    tenant_id: str = Query("default", description="Tenant identifier"),
    product: Optional[str] = Query(None, description="Product description (partial match)"),
    location: Optional[str] = Query(None, description="Location name or GLN (partial match)"),
    tlc: Optional[str] = Query(None, description="Traceability Lot Code (exact or partial)"),
    event_type: Optional[str] = Query(None, description="CTE type filter"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    _: None = Depends(_verify_api_key),
):
    """Generate recall-filtered FDA export with flexible search criteria."""
    # Require at least one filter to prevent full-table dumps
    if not any([product, location, tlc, event_type, start_date]):
        raise HTTPException(
            status_code=400,
            detail="At least one filter is required (product, location, tlc, event_type, or start_date)",
        )

    db_session = None
    try:
        from shared.database import SessionLocal
        from sqlalchemy import text

        db_session = SessionLocal()

        # Build dynamic query with parameterized filters
        conditions = ["e.tenant_id = :tid"]
        params: dict = {"tid": tenant_id}

        if product:
            conditions.append("LOWER(e.product_description) LIKE LOWER(:product)")
            params["product"] = f"%{product}%"

        if location:
            conditions.append(
                "(LOWER(e.location_name) LIKE LOWER(:loc) OR e.location_gln LIKE :loc_exact)"
            )
            params["loc"] = f"%{location}%"
            params["loc_exact"] = f"%{location}%"

        if tlc:
            conditions.append("e.traceability_lot_code LIKE :tlc")
            params["tlc"] = f"%{tlc}%" if "%" not in tlc else tlc

        if event_type:
            conditions.append("e.event_type = :etype")
            params["etype"] = event_type

        if start_date:
            conditions.append("e.event_timestamp >= :start")
            params["start"] = start_date

        if end_date:
            conditions.append("e.event_timestamp <= :end")
            params["end"] = end_date + "T23:59:59"

        where_clause = " AND ".join(conditions)

        # Query events with KDEs
        rows = db_session.execute(
            text(f"""
                SELECT
                    e.id, e.event_type, e.traceability_lot_code, e.product_description,
                    e.quantity, e.unit_of_measure, e.event_timestamp,
                    e.location_gln, e.location_name, e.source, e.sha256_hash,
                    h.chain_hash,
                    (SELECT jsonb_object_agg(k.kde_key, k.kde_value)
                     FROM fsma.cte_kdes k WHERE k.cte_event_id = e.id) AS kdes
                FROM fsma.cte_events e
                LEFT JOIN fsma.hash_chain h ON h.event_hash = e.sha256_hash AND h.tenant_id = e.tenant_id
                WHERE {where_clause}
                ORDER BY e.event_timestamp ASC
                LIMIT 10000
            """),
            params,
        ).fetchall()

        if not rows:
            filters_used = []
            if product: filters_used.append(f"product='{product}'")
            if location: filters_used.append(f"location='{location}'")
            if tlc: filters_used.append(f"tlc='{tlc}'")
            if event_type: filters_used.append(f"event_type='{event_type}'")
            if start_date: filters_used.append(f"from={start_date}")
            if end_date: filters_used.append(f"to={end_date}")
            raise HTTPException(
                status_code=404,
                detail=f"No records found matching recall filters: {', '.join(filters_used)}",
            )

        # Convert to FDA export format
        events = []
        for row in rows:
            kdes = row[12] if row[12] else {}
            events.append({
                "id": str(row[0]),
                "event_type": row[1],
                "traceability_lot_code": row[2],
                "product_description": row[3],
                "quantity": row[4],
                "unit_of_measure": row[5],
                "event_timestamp": row[6],
                "location_gln": row[7],
                "location_name": row[8],
                "source": row[9],
                "sha256_hash": row[10],
                "chain_hash": row[11] or "",
                "kdes": kdes,
            })

        csv_content = _generate_csv(events)
        export_hash = hashlib.sha256(csv_content.encode("utf-8")).hexdigest()

        # Log the recall export
        try:
            db_session.execute(
                text("""
                    INSERT INTO fsma.fda_export_log
                    (tenant_id, export_type, record_count, export_hash, generated_by, query_tlc, query_start_date, query_end_date)
                    VALUES (:tid, 'recall', :cnt, :hash, 'api_recall', :tlc, :sd, :ed)
                """),
                {
                    "tid": tenant_id, "cnt": len(events), "hash": export_hash,
                    "tlc": tlc, "sd": start_date, "ed": end_date,
                },
            )
            db_session.commit()
        except Exception:
            pass  # Don't fail the export if audit logging fails

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"fda_recall_export_{timestamp}.csv"

        logger.info(
            "fda_recall_export_generated",
            extra={
                "record_count": len(events),
                "filters": {"product": product, "location": location, "tlc": tlc},
                "export_hash": export_hash[:16],
                "tenant_id": tenant_id,
            },
        )

        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "X-Export-Hash": export_hash,
                "X-Record-Count": str(len(events)),
                "X-Export-Type": "recall",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("fda_recall_export_failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Recall export failed: {str(e)}")
    finally:
        if db_session:
            db_session.close()


@router.post(
    "/export/verify",
    summary="Verify a previous export's integrity",
    description=(
        "Re-generate an export with the same parameters and compare its hash "
        "to the original. Proves that the underlying data hasn't been tampered with."
    ),
)
async def verify_export(
    export_id: str = Query(..., description="Export log ID to verify"),
    tenant_id: str = Query("default"),
    _: None = Depends(_verify_api_key),
):
    """Verify that an export can be reproduced with the same hash."""
    db_session = None
    try:
        from shared.database import SessionLocal
        from shared.cte_persistence import CTEPersistence
        from sqlalchemy import text as sql_text

        db_session = SessionLocal()
        persistence = CTEPersistence(db_session)

        # Look up the original export
        row = db_session.execute(
            sql_text("""
                SELECT query_tlc, query_start_date, query_end_date,
                       record_count, export_hash, generated_at
                FROM fsma.fda_export_log
                WHERE id = :eid AND tenant_id = :tid
            """),
            {"eid": export_id, "tid": tenant_id},
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"Export '{export_id}' not found")

        original_tlc, start_date, end_date, original_count, original_hash, generated_at = row

        # Re-query and re-generate
        events = persistence.query_events_by_tlc(
            tenant_id=tenant_id,
            tlc=original_tlc,
            start_date=str(start_date) if start_date else None,
            end_date=str(end_date) if end_date else None,
        )

        csv_content = _generate_csv(events)
        regenerated_hash = hashlib.sha256(csv_content.encode("utf-8")).hexdigest()

        match = regenerated_hash == original_hash

        return {
            "export_id": export_id,
            "original_hash": original_hash,
            "regenerated_hash": regenerated_hash,
            "hashes_match": match,
            "original_record_count": original_count,
            "current_record_count": len(events),
            "data_integrity": "VERIFIED" if match else "MISMATCH_DETECTED",
            "original_generated_at": generated_at.isoformat() if generated_at else None,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("export_verify_failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")
    finally:
        if db_session:
            db_session.close()
