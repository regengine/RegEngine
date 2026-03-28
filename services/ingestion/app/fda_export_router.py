"""
FDA 24-Hour Export Router.

Provides the endpoints that fulfill RegEngine's core promise:
"When the FDA calls, produce compliant traceability records within 24 hours."

This module reads from the Postgres persistence layer (fsma.cte_events)
and generates sortable, searchable CSV exports in the FDA's expected format.

Endpoints:
    GET  /api/v1/fda/export            — Generate FDA spreadsheet/package for a TLC
    GET  /api/v1/fda/export/all        — Export all events (date-filtered)
    GET  /api/v1/fda/export/history     — View export audit log
    POST /api/v1/fda/export/verify      — Verify a previous export's integrity
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.authz import require_permission
from app.export_models import ExportHistoryResponse, ExportVerifyResponse
from app.fda_export_service import (
    _build_chain_verification_payload,
    _build_completeness_summary,
    _build_fda_package,
    _generate_csv,
    _generate_csv_v2,
    _safe_filename_token,
)
from app.subscription_gate import require_active_subscription
from app.webhook_models import REQUIRED_KDES_BY_CTE, WebhookCTEType

logger = logging.getLogger("fda-export")

router = APIRouter(prefix="/api/v1/fda", tags=["FDA Export"])


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
    responses={
        200: {
            "content": {
                "text/csv": {},
                "application/zip": {},
            },
            "description": "FDA-compliant CSV or ZIP package",
        },
    },
)
async def export_fda_spreadsheet(
    tlc: str = Query(..., description="Traceability Lot Code to trace"),
    start_date: Optional[str] = Query(None, description="Start date filter (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date filter (YYYY-MM-DD)"),
    format: Literal["package", "csv"] = Query(
        default="package",
        description="Export format: package (zip bundle) or csv",
    ),
    tenant_id: str = Query(..., description="Tenant identifier"),
    _auth=Depends(require_permission("fda.export")),
    _subscription=Depends(require_active_subscription),
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

        # Generate CSV as canonical export evidence.
        csv_content = _generate_csv(events)
        export_hash = hashlib.sha256(csv_content.encode("utf-8")).hexdigest()
        chain_verification = persistence.verify_chain(tenant_id=tenant_id)
        completeness_summary = _build_completeness_summary(events)

        # Log the export
        persistence.log_export(
            tenant_id=tenant_id,
            export_hash=export_hash,
            record_count=len(events),
            query_tlc=tlc,
            query_start_date=start_date,
            query_end_date=end_date,
            generated_by="api_package" if format == "package" else "api",
        )
        db_session.commit()

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_tlc = _safe_filename_token(tlc)

        logger.info(
            "fda_export_generated",
            extra={
                "tlc": tlc,
                "record_count": len(events),
                "export_hash": export_hash[:16],
                "tenant_id": tenant_id,
                "format": format,
            },
        )

        kde_coverage = completeness_summary["required_kde_coverage_ratio"]
        kde_warnings = completeness_summary["events_with_missing_required_fields"]
        compliance_headers: dict[str, str] = {
            "X-KDE-Coverage": str(kde_coverage),
            "X-KDE-Warnings": str(kde_warnings),
        }
        if kde_coverage < 0.80:
            compliance_headers["X-Compliance-Warning"] = "KDE coverage below 80% threshold"

        if format == "package":
            chain_payload = _build_chain_verification_payload(
                tenant_id=tenant_id,
                tlc=tlc,
                events=events,
                csv_hash=export_hash,
                chain_verification=chain_verification,
                completeness_summary=completeness_summary,
            )
            package_bytes, package_meta = _build_fda_package(
                events=events,
                csv_content=csv_content,
                csv_hash=export_hash,
                chain_payload=chain_payload,
                completeness_summary=completeness_summary,
                tenant_id=tenant_id,
                tlc=tlc,
                query_start_date=start_date,
                query_end_date=end_date,
            )
            filename = f"fda_traceability_package_{safe_tlc}_{timestamp}.zip"
            return StreamingResponse(
                io.BytesIO(package_bytes),
                media_type="application/zip",
                headers={
                    "Content-Disposition": f"attachment; filename={filename}",
                    "X-Export-Hash": export_hash,
                    "X-Package-Hash": package_meta["package_hash"],
                    "X-Record-Count": str(len(events)),
                    "X-Chain-Integrity": "VERIFIED" if chain_verification.valid else "UNVERIFIED",
                    **compliance_headers,
                },
            )

        filename = f"fda_export_{safe_tlc}_{timestamp}.csv"
        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "X-Export-Hash": export_hash,
                "X-Record-Count": str(len(events)),
                "X-Chain-Integrity": "VERIFIED" if chain_verification.valid else "UNVERIFIED",
                **compliance_headers,
            },
        )

    except HTTPException:
        raise
    except (ImportError, ValueError, RuntimeError, OSError) as e:
        logger.error("fda_export_failed", extra={"error": str(e), "tlc": tlc})
        raise HTTPException(status_code=500, detail="Export failed. Check server logs for details.")
    finally:
        if db_session:
            db_session.close()


@router.get(
    "/export/all",
    summary="Export all CTE events",
    description="Export all traceability events for a tenant within an optional date range.",
    responses={
        200: {
            "content": {
                "text/csv": {},
                "application/zip": {},
            },
            "description": "FDA-compliant CSV or ZIP package",
        },
    },
)
async def export_all_events(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    event_type: Optional[str] = Query(None, description="Filter by CTE type"),
    format: Literal["package", "csv"] = Query(
        default="csv",
        description="Export format: package (zip bundle) or csv",
    ),
    tenant_id: str = Query(..., description="Tenant identifier"),
    _auth=Depends(require_permission("fda.export")),
    _subscription=Depends(require_active_subscription),
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

        # Batch-fetch by distinct TLCs to avoid O(N×M) query amplification
        tlcs = list({evt["traceability_lot_code"] for evt in events})
        full_events = []
        for tlc_batch_start in range(0, len(tlcs), 50):
            tlc_batch = tlcs[tlc_batch_start:tlc_batch_start + 50]
            for tlc in tlc_batch:
                full = persistence.query_events_by_tlc(
                    tenant_id=tenant_id,
                    tlc=tlc,
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
        chain_verification = persistence.verify_chain(tenant_id=tenant_id)
        completeness_summary = _build_completeness_summary(deduped)

        persistence.log_export(
            tenant_id=tenant_id,
            export_hash=export_hash,
            record_count=len(deduped),
            query_start_date=start_date,
            query_end_date=end_date,
            generated_by="api_package_all" if format == "package" else "api",
        )
        db_session.commit()

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        kde_coverage = completeness_summary["required_kde_coverage_ratio"]
        kde_warnings = completeness_summary["events_with_missing_required_fields"]
        compliance_headers: dict[str, str] = {
            "X-KDE-Coverage": str(kde_coverage),
            "X-KDE-Warnings": str(kde_warnings),
        }
        if kde_coverage < 0.80:
            compliance_headers["X-Compliance-Warning"] = "KDE coverage below 80% threshold"

        if format == "package":
            chain_payload = _build_chain_verification_payload(
                tenant_id=tenant_id,
                tlc=None,
                events=deduped,
                csv_hash=export_hash,
                chain_verification=chain_verification,
                completeness_summary=completeness_summary,
            )
            package_bytes, package_meta = _build_fda_package(
                events=deduped,
                csv_content=csv_content,
                csv_hash=export_hash,
                chain_payload=chain_payload,
                completeness_summary=completeness_summary,
                tenant_id=tenant_id,
                tlc=None,
                query_start_date=start_date,
                query_end_date=end_date,
            )
            filename = f"fda_export_all_{timestamp}.zip"
            return StreamingResponse(
                io.BytesIO(package_bytes),
                media_type="application/zip",
                headers={
                    "Content-Disposition": f"attachment; filename={filename}",
                    "X-Export-Hash": export_hash,
                    "X-Package-Hash": package_meta["package_hash"],
                    "X-Record-Count": str(len(deduped)),
                    "X-Chain-Integrity": "VERIFIED" if chain_verification.valid else "UNVERIFIED",
                    **compliance_headers,
                },
            )

        filename = f"fda_export_all_{timestamp}.csv"

        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "X-Export-Hash": export_hash,
                "X-Record-Count": str(len(deduped)),
                "X-Chain-Integrity": "VERIFIED" if chain_verification.valid else "UNVERIFIED",
                **compliance_headers,
            },
        )

    except (ImportError, ValueError, RuntimeError, OSError) as e:
        logger.error("fda_export_all_failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Export failed. Check server logs for details.")
    finally:
        if db_session:
            db_session.close()


@router.get(
    "/export/history",
    response_model=ExportHistoryResponse,
    summary="View FDA export audit log",
    description="Returns the history of all FDA exports generated for this tenant.",
)
async def export_history(
    tenant_id: str = Query(..., description="Tenant identifier"),
    limit: int = Query(50, ge=1, le=200),
    _auth=Depends(require_permission("fda.read")),
    _subscription=Depends(require_active_subscription),
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

    except (ImportError, ValueError, RuntimeError, OSError) as e:
        logger.error("export_history_failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="History query failed. Check server logs for details.")
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
    responses={
        200: {
            "content": {
                "text/csv": {},
                "application/zip": {},
            },
            "description": "FDA-compliant CSV or ZIP package",
        },
    },
)
async def export_recall_filtered(
    tenant_id: str = Query(..., description="Tenant identifier"),
    product: Optional[str] = Query(None, description="Product description (partial match)"),
    location: Optional[str] = Query(None, description="Location name or GLN (partial match)"),
    tlc: Optional[str] = Query(None, description="Traceability Lot Code (exact or partial)"),
    event_type: Optional[str] = Query(None, description="CTE type filter"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    format: Literal["package", "csv"] = Query(
        default="csv",
        description="Export format: package (zip bundle) or csv",
    ),
    _auth=Depends(require_permission("fda.export")),
    _subscription=Depends(require_active_subscription),
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
        from shared.cte_persistence import CTEPersistence
        from sqlalchemy import text

        db_session = SessionLocal()
        persistence = CTEPersistence(db_session)

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
                     FROM fsma.cte_kdes k WHERE k.cte_event_id = e.id) AS kdes,
                    e.ingested_at
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
            # SQLAlchemy Row objects — use tuple() for safe index access
            r = tuple(row)
            kdes = r[12] if r[12] else {}
            ts = r[6]
            if hasattr(ts, "isoformat"):
                ts = ts.isoformat()
            ingested = r[13]
            events.append({
                "id": str(r[0]),
                "event_type": r[1],
                "traceability_lot_code": r[2],
                "product_description": r[3],
                "quantity": r[4],
                "unit_of_measure": r[5],
                "event_timestamp": str(ts) if ts else "",
                "location_gln": r[7],
                "location_name": r[8],
                "source": r[9],
                "sha256_hash": r[10],
                "chain_hash": r[11] or "",
                "kdes": kdes,
                "ingested_at": ingested.isoformat() if hasattr(ingested, "isoformat") else str(ingested or ""),
            })

        csv_content = _generate_csv(events)
        export_hash = hashlib.sha256(csv_content.encode("utf-8")).hexdigest()
        chain_verification = persistence.verify_chain(tenant_id=tenant_id)
        completeness_summary = _build_completeness_summary(events)

        # Log the recall export
        try:
            db_session.execute(
                text("""
                    INSERT INTO fsma.fda_export_log
                    (tenant_id, export_type, record_count, export_hash, generated_by, query_tlc, query_start_date, query_end_date)
                    VALUES (:tid, :etype, :cnt, :hash, :generated_by, :tlc, :sd, :ed)
                """),
                {
                    "tid": tenant_id, "cnt": len(events), "hash": export_hash,
                    "etype": "recall_package" if format == "package" else "recall",
                    "generated_by": "api_recall_package" if format == "package" else "api_recall",
                    "tlc": tlc, "sd": start_date, "ed": end_date,
                },
            )
            db_session.commit()
        except (ValueError, RuntimeError, OSError):
            pass  # Don't fail the export if audit logging fails

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        if format == "package":
            chain_payload = _build_chain_verification_payload(
                tenant_id=tenant_id,
                tlc=tlc,
                events=events,
                csv_hash=export_hash,
                chain_verification=chain_verification,
                completeness_summary=completeness_summary,
            )
            package_bytes, package_meta = _build_fda_package(
                events=events,
                csv_content=csv_content,
                csv_hash=export_hash,
                chain_payload=chain_payload,
                completeness_summary=completeness_summary,
                tenant_id=tenant_id,
                tlc=tlc,
                query_start_date=start_date,
                query_end_date=end_date,
            )
            filename = f"fda_recall_package_{timestamp}.zip"
            return StreamingResponse(
                io.BytesIO(package_bytes),
                media_type="application/zip",
                headers={
                    "Content-Disposition": f"attachment; filename={filename}",
                    "X-Export-Hash": export_hash,
                    "X-Package-Hash": package_meta["package_hash"],
                    "X-Record-Count": str(len(events)),
                    "X-Export-Type": "recall_package",
                    "X-Chain-Integrity": "VERIFIED" if chain_verification.valid else "UNVERIFIED",
                    "X-KDE-Coverage": str(completeness_summary["required_kde_coverage_ratio"]),
                },
            )

        filename = f"fda_recall_export_{timestamp}.csv"

        logger.info(
            "fda_recall_export_generated",
            extra={
                "record_count": len(events),
                "filters": {"product": product, "location": location, "tlc": tlc},
                "export_hash": export_hash[:16],
                "tenant_id": tenant_id,
                "format": format,
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
                "X-Chain-Integrity": "VERIFIED" if chain_verification.valid else "UNVERIFIED",
                "X-KDE-Coverage": str(completeness_summary["required_kde_coverage_ratio"]),
            },
        )

    except HTTPException:
        raise
    except (ImportError, ValueError, RuntimeError, OSError) as e:
        logger.error("fda_recall_export_failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Recall export failed. Check server logs for details.")
    finally:
        if db_session:
            db_session.close()


@router.post(
    "/export/verify",
    response_model=ExportVerifyResponse,
    summary="Verify a previous export's integrity",
    description=(
        "Re-generate an export with the same parameters and compare its hash "
        "to the original. Proves that the underlying data hasn't been tampered with."
    ),
)
async def verify_export(
    export_id: str = Query(..., description="Export log ID to verify"),
    tenant_id: str = Query(..., description="Tenant identifier"),
    _auth=Depends(require_permission("fda.verify")),
    _subscription=Depends(require_active_subscription),
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
                SELECT export_type, query_tlc, query_start_date, query_end_date,
                       record_count, export_hash, generated_at
                FROM fsma.fda_export_log
                WHERE id = :eid AND tenant_id = :tid
            """),
            {"eid": export_id, "tid": tenant_id},
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"Export '{export_id}' not found")

        export_type, original_tlc, start_date, end_date, original_count, original_hash, generated_at = row

        start = str(start_date) if start_date else None
        end = str(end_date) if end_date else None

        # Re-query and re-generate deterministically based on stored query scope.
        if original_tlc:
            # Single-TLC export path
            events = persistence.query_events_by_tlc(
                tenant_id=tenant_id,
                tlc=original_tlc,
                start_date=start,
                end_date=end,
            )
        elif export_type in {"fda_spreadsheet", "fda_package"}:
            # Full export path (no TLC filter)
            events_page, _ = persistence.query_all_events(
                tenant_id=tenant_id,
                start_date=start,
                end_date=end,
                event_type=None,
                limit=10000,
            )
            expanded: list[dict] = []
            for event in events_page:
                expanded.extend(
                    persistence.query_events_by_tlc(
                        tenant_id=tenant_id,
                        tlc=event["traceability_lot_code"],
                        start_date=start,
                        end_date=end,
                    )
                )
            seen: set[str] = set()
            events = []
            for event in expanded:
                event_id = str(event.get("id"))
                if event_id in seen:
                    continue
                seen.add(event_id)
                events.append(event)
        else:
            # Recall exports can include product/location wildcard filters that are
            # not fully persisted in fda_export_log today.
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Export type '{export_type}' is not fully reproducible from stored "
                    "audit filters. Verify via package manifest and chain artifact."
                ),
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
    except (ImportError, ValueError, RuntimeError, OSError) as e:
        logger.error("export_verify_failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Verification failed. Check server logs for details.")
    finally:
        if db_session:
            db_session.close()


# ---------------------------------------------------------------------------
# V2 Export — Canonical Model (fsma.traceability_events + rule evaluations)
# ---------------------------------------------------------------------------

@router.get(
    "/export/v2",
    summary="Generate FDA export from canonical model (v2)",
    description=(
        "Query traceability events from the canonical fsma.traceability_events table, "
        "join rule evaluation results from fsma.rule_evaluations + fsma.rule_definitions, "
        "and generate an FDA-compliant CSV/package with Compliance Status and Rule Failures "
        "columns appended. Backward-compatible with v1 column layout — new columns are "
        "appended at the end."
    ),
    responses={
        200: {
            "content": {
                "text/csv": {},
                "application/zip": {},
            },
            "description": "FDA-compliant CSV or ZIP package with compliance columns",
        },
    },
)
async def export_fda_spreadsheet_v2(
    tenant_id: str = Query(..., description="Tenant identifier"),
    tlc: Optional[str] = Query(None, description="Traceability Lot Code filter (exact or partial with %%)"),
    start_date: Optional[str] = Query(None, description="Start date filter (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date filter (YYYY-MM-DD)"),
    event_type: Optional[str] = Query(None, description="Filter by CTE type"),
    format: Literal["package", "csv"] = Query(
        default="csv",
        description="Export format: package (zip bundle) or csv",
    ),
    _auth=Depends(require_permission("fda.export")),
    _subscription=Depends(require_active_subscription),
):
    """Generate FDA-compliant traceability export from the canonical model with rule evaluation results."""
    db_session = None
    try:
        from shared.database import SessionLocal
        from shared.cte_persistence import CTEPersistence
        from sqlalchemy import text

        db_session = SessionLocal()
        persistence = CTEPersistence(db_session)

        # ----- Build dynamic WHERE clause -----
        conditions = ["e.tenant_id = :tid"]
        params: dict[str, Any] = {"tid": tenant_id}

        if tlc:
            if "%" in tlc:
                conditions.append("e.traceability_lot_code LIKE :tlc")
            else:
                conditions.append("e.traceability_lot_code = :tlc")
            params["tlc"] = tlc

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

        # ----- Query from canonical model with rule evaluations -----
        rows = db_session.execute(
            text(f"""
                SELECT
                    e.event_id,
                    e.event_type,
                    e.traceability_lot_code,
                    e.product_description,
                    e.quantity,
                    e.unit_of_measure,
                    e.event_timestamp,
                    e.location_gln,
                    e.location_name,
                    e.source,
                    e.sha256_hash,
                    e.chain_hash,
                    e.kdes,
                    e.provenance,
                    -- aggregate rule evaluation results per event
                    COALESCE(
                        jsonb_agg(
                            jsonb_build_object(
                                'rule_name', rd.rule_name,
                                'passed', re.passed,
                                'why_failed', re.why_failed
                            )
                        ) FILTER (WHERE re.rule_id IS NOT NULL),
                        '[]'::jsonb
                    ) AS rule_results,
                    e.ingested_at
                FROM fsma.traceability_events e
                LEFT JOIN fsma.rule_evaluations re ON re.event_id = e.event_id
                LEFT JOIN fsma.rule_definitions rd ON rd.rule_id = re.rule_id
                WHERE {where_clause}
                GROUP BY
                    e.event_id, e.event_type, e.traceability_lot_code,
                    e.product_description, e.quantity, e.unit_of_measure,
                    e.event_timestamp, e.location_gln, e.location_name,
                    e.source, e.sha256_hash, e.chain_hash, e.kdes, e.provenance,
                    e.ingested_at
                ORDER BY e.event_timestamp ASC
                LIMIT 10000
            """),
            params,
        ).fetchall()

        if not rows:
            detail_parts = [f"tenant_id='{tenant_id}'"]
            if tlc:
                detail_parts.append(f"tlc='{tlc}'")
            if event_type:
                detail_parts.append(f"event_type='{event_type}'")
            if start_date:
                detail_parts.append(f"from={start_date}")
            if end_date:
                detail_parts.append(f"to={end_date}")
            raise HTTPException(
                status_code=404,
                detail=f"No traceability records found matching filters: {', '.join(detail_parts)}",
            )

        # ----- Convert rows to event dicts -----
        events: list[dict] = []
        for row in rows:
            r = tuple(row)
            kdes = r[12] if r[12] else {}
            provenance = r[13] if r[13] else {}
            rule_results_raw = r[14] if r[14] else []
            ingested = r[15]
            ts = r[6]
            if hasattr(ts, "isoformat"):
                ts = ts.isoformat()

            # Normalize rule_results: parse from JSON string if needed
            if isinstance(rule_results_raw, str):
                try:
                    rule_results_raw = json.loads(rule_results_raw)
                except (json.JSONDecodeError, TypeError):
                    rule_results_raw = []

            events.append({
                "id": str(r[0]),
                "event_type": r[1],
                "traceability_lot_code": r[2],
                "product_description": r[3],
                "quantity": r[4],
                "unit_of_measure": r[5],
                "event_timestamp": str(ts) if ts else "",
                "location_gln": r[7],
                "location_name": r[8],
                "source": r[9],
                "sha256_hash": r[10],
                "chain_hash": r[11] or "",
                "kdes": kdes,
                "provenance": provenance,
                "rule_results": rule_results_raw,
                "ingested_at": ingested.isoformat() if hasattr(ingested, "isoformat") else str(ingested or ""),
            })

        # ----- Generate CSV with compliance columns -----
        csv_content = _generate_csv_v2(events)
        export_hash = hashlib.sha256(csv_content.encode("utf-8")).hexdigest()
        chain_verification = persistence.verify_chain(tenant_id=tenant_id)
        completeness_summary = _build_completeness_summary(events)

        # ----- Compute compliance summary stats -----
        total_events = len(events)
        events_passing = sum(
            1 for e in events
            if e.get("rule_results") and all(r.get("passed") for r in e["rule_results"])
        )
        events_failing = sum(
            1 for e in events
            if e.get("rule_results") and any(not r.get("passed") for r in e["rule_results"])
        )
        events_no_rules = total_events - events_passing - events_failing

        # ----- Log the export to audit table -----
        try:
            db_session.execute(
                text("""
                    INSERT INTO fsma.fda_export_log
                    (tenant_id, export_type, record_count, export_hash, generated_by,
                     query_tlc, query_start_date, query_end_date)
                    VALUES (:tid, :etype, :cnt, :hash, :generated_by, :tlc, :sd, :ed)
                """),
                {
                    "tid": tenant_id,
                    "cnt": len(events),
                    "hash": export_hash,
                    "etype": "v2_package" if format == "package" else "v2_spreadsheet",
                    "generated_by": "api_v2_package" if format == "package" else "api_v2",
                    "tlc": tlc,
                    "sd": start_date,
                    "ed": end_date,
                },
            )
            db_session.commit()
        except (ValueError, RuntimeError, OSError):
            logger.warning("v2_export_audit_log_failed", exc_info=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        scope = _safe_filename_token(tlc or "all")

        logger.info(
            "fda_export_v2_generated",
            extra={
                "tlc": tlc,
                "record_count": len(events),
                "export_hash": export_hash[:16],
                "tenant_id": tenant_id,
                "format": format,
                "compliance_pass": events_passing,
                "compliance_fail": events_failing,
                "compliance_no_rules": events_no_rules,
            },
        )

        if format == "package":
            # Build chain verification payload with provenance metadata
            chain_payload = _build_chain_verification_payload(
                tenant_id=tenant_id,
                tlc=tlc,
                events=events,
                csv_hash=export_hash,
                chain_verification=chain_verification,
                completeness_summary=completeness_summary,
            )
            # Enrich chain payload with v2 provenance + compliance metadata
            chain_payload["data_source"] = "fsma.traceability_events (canonical model)"
            chain_payload["compliance_summary"] = {
                "total_events": total_events,
                "events_passing": events_passing,
                "events_failing": events_failing,
                "events_no_rules": events_no_rules,
                "compliance_rate": round(events_passing / total_events, 4) if total_events else 0,
            }
            chain_payload["provenance"] = {
                "source_table": "fsma.traceability_events",
                "rule_tables": ["fsma.rule_evaluations", "fsma.rule_definitions"],
                "export_version": "2.0",
            }
            chain_payload["attestation"] = {
                "attested_by": "regengine-fda-export-router-v2",
                "assertion": (
                    "Package generated from canonical fsma.traceability_events "
                    "with rule evaluation results and chain verification."
                ),
            }

            package_bytes, package_meta = _build_fda_package(
                events=events,
                csv_content=csv_content,
                csv_hash=export_hash,
                chain_payload=chain_payload,
                completeness_summary=completeness_summary,
                tenant_id=tenant_id,
                tlc=tlc,
                query_start_date=start_date,
                query_end_date=end_date,
            )
            filename = f"fda_v2_package_{scope}_{timestamp}.zip"
            return StreamingResponse(
                io.BytesIO(package_bytes),
                media_type="application/zip",
                headers={
                    "Content-Disposition": f"attachment; filename={filename}",
                    "X-Export-Hash": export_hash,
                    "X-Package-Hash": package_meta["package_hash"],
                    "X-Record-Count": str(len(events)),
                    "X-Export-Version": "2.0",
                    "X-Chain-Integrity": "VERIFIED" if chain_verification.valid else "UNVERIFIED",
                    "X-KDE-Coverage": str(completeness_summary["required_kde_coverage_ratio"]),
                    "X-Compliance-Rate": str(
                        round(events_passing / total_events, 4) if total_events else 0
                    ),
                },
            )

        # CSV-only response
        filename = f"fda_v2_export_{scope}_{timestamp}.csv"
        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "X-Export-Hash": export_hash,
                "X-Record-Count": str(len(events)),
                "X-Export-Version": "2.0",
                "X-Chain-Integrity": "VERIFIED" if chain_verification.valid else "UNVERIFIED",
                "X-KDE-Coverage": str(completeness_summary["required_kde_coverage_ratio"]),
                "X-Compliance-Rate": str(
                    round(events_passing / total_events, 4) if total_events else 0
                ),
            },
        )

    except HTTPException:
        raise
    except (ImportError, ValueError, RuntimeError, OSError) as e:
        logger.error("fda_export_v2_failed", extra={"error": str(e), "tenant_id": tenant_id})
        raise HTTPException(status_code=500, detail="V2 export failed. Check server logs for details.")
    finally:
        if db_session:
            db_session.close()


# ---------------------------------------------------------------------------
# Merkle Tree Verification Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/export/merkle-root",
    summary="Get Merkle root for a tenant's hash chain",
    description=(
        "Computes a Merkle tree from all hash chain entries for the tenant "
        "and returns the root hash. This enables O(log n) verification of "
        "individual event inclusion without walking the entire chain."
    ),
)
async def get_merkle_root(
    tenant_id: str = Query(..., description="Tenant identifier"),
    _auth=Depends(require_permission("fda.verify")),
):
    """Return the current Merkle root for a tenant's hash chain."""
    db_session = None
    try:
        from shared.database import SessionLocal
        from shared.cte_persistence import CTEPersistence

        db_session = SessionLocal()
        persistence = CTEPersistence(db_session)

        result = persistence.verify_chain_merkle(tenant_id)

        return {
            "tenant_id": tenant_id,
            "valid": result.valid,
            "merkle_root": result.merkle_root,
            "chain_length": result.chain_length,
            "tree_depth": result.tree_depth,
            "errors": result.errors,
            "checked_at": result.checked_at,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "merkle_root_failed",
            extra={"error": str(e), "tenant_id": tenant_id},
        )
        raise HTTPException(
            status_code=500,
            detail="Merkle root computation failed. Check server logs.",
        )
    finally:
        if db_session:
            db_session.close()


@router.get(
    "/export/merkle-proof",
    summary="Get Merkle inclusion proof for a specific event",
    description=(
        "Generates a Merkle inclusion proof that cryptographically demonstrates "
        "a specific event is part of the tenant's hash chain. The proof can be "
        "independently verified with just the event hash, proof steps, and root."
    ),
)
async def get_merkle_proof(
    tenant_id: str = Query(..., description="Tenant identifier"),
    event_id: str = Query(..., description="CTE event ID to prove inclusion for"),
    _auth=Depends(require_permission("fda.verify")),
):
    """Return a Merkle inclusion proof for a specific event."""
    db_session = None
    try:
        from shared.database import SessionLocal
        from shared.cte_persistence import CTEPersistence

        db_session = SessionLocal()
        persistence = CTEPersistence(db_session)

        proof_data = persistence.get_merkle_proof(tenant_id, event_id)

        if proof_data is None:
            raise HTTPException(
                status_code=404,
                detail=f"Event '{event_id}' not found in hash chain for tenant '{tenant_id}'",
            )

        return {
            "tenant_id": tenant_id,
            **proof_data,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "merkle_proof_failed",
            extra={"error": str(e), "tenant_id": tenant_id, "event_id": event_id},
        )
        raise HTTPException(
            status_code=500,
            detail="Merkle proof generation failed. Check server logs.",
        )
    finally:
        if db_session:
            db_session.close()
