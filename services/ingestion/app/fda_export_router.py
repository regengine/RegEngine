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

import csv
import hashlib
import io
import json
import logging
from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import uuid4
import zipfile

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.authz import require_permission
from app.webhook_models import REQUIRED_KDES_BY_CTE, WebhookCTEType

logger = logging.getLogger("fda-export")

router = APIRouter(prefix="/api/v1/fda", tags=["FDA Export"])


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
    # KDE columns — FSMA 204 requires all KDEs in export
    "Reference Document Number",
    "Receive Date",
    "Ship Date",
    "Harvest Date",
    "Cooling Date",
    "Packing Date",
    "Transformation Date",
    "Landing Date",
    "Receiving Location",
    "Temperature (°F)",
    "Carrier",
    "Additional KDEs (JSON)",
]


# KDE keys that get their own named columns in the FDA export
_NAMED_KDE_COLUMNS = {
    "reference_document_number": "Reference Document Number",
    "receive_date": "Receive Date",
    "ship_date": "Ship Date",
    "harvest_date": "Harvest Date",
    "cooling_date": "Cooling Date",
    "packing_date": "Packing Date",
    "transformation_date": "Transformation Date",
    "landing_date": "Landing Date",
    "receiving_location": "Receiving Location",
    "temperature": "Temperature (°F)",
    "carrier": "Carrier",
}


def _event_to_fda_row(event: dict) -> dict:
    """Convert a persisted CTE event to an FDA spreadsheet row."""
    kdes = event.get("kdes", {})
    timestamp = event.get("event_timestamp", "")

    # Split timestamp into date and time
    event_date = ""
    event_time = ""
    if timestamp:
        try:
            ts = str(timestamp)
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            event_date = dt.strftime("%Y-%m-%d")
            event_time = dt.strftime("%H:%M:%S %Z")
        except (ValueError, AttributeError):
            event_date = str(timestamp)[:10]

    row = {
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

    # Map named KDE columns
    for kde_key, col_name in _NAMED_KDE_COLUMNS.items():
        row[col_name] = str(kdes.get(kde_key, "")) if kdes.get(kde_key) else ""

    # Remaining KDEs not in named columns → JSON blob
    extra_kdes = {k: v for k, v in kdes.items() if k not in _NAMED_KDE_COLUMNS}
    row["Additional KDEs (JSON)"] = json.dumps(extra_kdes) if extra_kdes else ""

    return row


def _generate_csv(events: list[dict]) -> str:
    """Generate FDA-compliant CSV from a list of CTE events."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=FDA_COLUMNS)
    writer.writeheader()

    for event in events:
        writer.writerow(_event_to_fda_row(event))

    return output.getvalue()


def _safe_filename_token(raw: str) -> str:
    """Normalize user-provided identifiers for filenames."""
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in raw)[:64] or "all"


def _event_value_for_required_field(event: dict, required_field: str) -> Any:
    """Resolve required field values from direct event fields or KDE map."""
    kdes = event.get("kdes", {})
    if required_field in {"traceability_lot_code", "product_description", "quantity", "unit_of_measure"}:
        return event.get(required_field)
    if required_field == "location_name":
        return event.get("location_name") or kdes.get("location_name")
    return kdes.get(required_field)


def _build_completeness_summary(events: list[dict]) -> dict:
    """
    Assess required KDE coverage across exported events.

    Completeness is computed against REQUIRED_KDES_BY_CTE.
    """
    missing_by_field: dict[str, int] = {}
    missing_by_event: list[dict[str, Any]] = []
    checks_total = 0
    checks_missing = 0

    for event in events:
        raw_event_type = str(event.get("event_type", "")).upper()
        required_fields = []
        if raw_event_type in WebhookCTEType.__members__:
            required_fields = REQUIRED_KDES_BY_CTE[WebhookCTEType[raw_event_type]]

        missing_fields = []
        for required_field in required_fields:
            checks_total += 1
            value = _event_value_for_required_field(event, required_field)
            missing = value is None or str(value).strip() == ""
            if missing:
                checks_missing += 1
                missing_fields.append(required_field)
                missing_by_field[required_field] = missing_by_field.get(required_field, 0) + 1

        if missing_fields:
            missing_by_event.append(
                {
                    "event_id": event.get("id"),
                    "event_type": event.get("event_type"),
                    "traceability_lot_code": event.get("traceability_lot_code"),
                    "missing_fields": missing_fields,
                }
            )

    checks_passed = checks_total - checks_missing
    coverage_ratio = 1.0 if checks_total == 0 else round(checks_passed / checks_total, 4)

    return {
        "required_checks_total": checks_total,
        "required_checks_passed": checks_passed,
        "required_checks_missing": checks_missing,
        "required_kde_coverage_ratio": coverage_ratio,
        "events_with_missing_required_fields": len(missing_by_event),
        "missing_required_by_field": missing_by_field,
        "missing_required_events": missing_by_event[:250],
    }


def _build_chain_verification_payload(
    *,
    tenant_id: str,
    tlc: Optional[str],
    events: list[dict],
    csv_hash: str,
    chain_verification: Any,
    completeness_summary: dict,
) -> dict:
    """Build JSON payload used for independent package verification."""
    missing_record_hashes = sum(1 for event in events if not event.get("sha256_hash"))
    missing_chain_hashes = sum(1 for event in events if not event.get("chain_hash"))

    verification_status = "VERIFIED" if chain_verification.valid else "UNVERIFIED"
    if missing_record_hashes or missing_chain_hashes:
        verification_status = "PARTIAL"

    return {
        "version": "1.0",
        "snapshot_id": str(uuid4()),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "hash_algorithm": "SHA-256",
        "content_hash": csv_hash,
        "verification_status": verification_status,
        "tenant_id": tenant_id,
        "traceability_lot_code": tlc,
        "record_count": len(events),
        "chain_verification": {
            "valid": bool(chain_verification.valid),
            "chain_length": int(chain_verification.chain_length),
            "errors": list(chain_verification.errors),
            "checked_at": chain_verification.checked_at,
        },
        "row_hash_coverage": {
            "records_with_hash": len(events) - missing_record_hashes,
            "records_with_chain_hash": len(events) - missing_chain_hashes,
            "missing_record_hashes": missing_record_hashes,
            "missing_chain_hashes": missing_chain_hashes,
        },
        "completeness": {
            "required_kde_coverage_ratio": completeness_summary["required_kde_coverage_ratio"],
            "events_with_missing_required_fields": completeness_summary["events_with_missing_required_fields"],
        },
        "attestation": {
            "attested_by": "regengine-fda-export-router",
            "assertion": "Package generated from persisted fsma.cte_events with chain verification.",
        },
    }


def _build_fda_package(
    *,
    events: list[dict],
    csv_content: str,
    csv_hash: str,
    chain_payload: dict,
    completeness_summary: dict,
    tenant_id: str,
    tlc: Optional[str],
    query_start_date: Optional[str],
    query_end_date: Optional[str],
) -> tuple[bytes, dict]:
    """Build zip package bytes and return package metadata."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    scope = _safe_filename_token(tlc or "all")
    csv_name = f"fda_spreadsheet_{scope}_{timestamp}.csv"
    chain_name = f"chain_verification_{scope}_{timestamp}.json"
    manifest_name = "manifest.json"
    readme_name = "README.txt"

    csv_bytes = csv_content.encode("utf-8")
    chain_bytes = json.dumps(chain_payload, indent=2, sort_keys=True).encode("utf-8")
    readme_bytes = (
        "RegEngine FDA Traceability Package\n"
        "=================================\n"
        "Contents:\n"
        "1) fda_spreadsheet_*.csv - FDA-sortable traceability rows\n"
        "2) chain_verification_*.json - chain integrity and hash coverage metadata\n"
        "3) manifest.json - package metadata and file checksums\n"
        "\n"
        "Verification:\n"
        "- Compare manifest file hashes with local SHA-256 calculations.\n"
        "- Validate chain_verification.verification_status == VERIFIED or PARTIAL.\n"
    ).encode("utf-8")

    file_hashes = {
        csv_name: hashlib.sha256(csv_bytes).hexdigest(),
        chain_name: hashlib.sha256(chain_bytes).hexdigest(),
        readme_name: hashlib.sha256(readme_bytes).hexdigest(),
    }

    event_types: dict[str, int] = {}
    tlc_counts: dict[str, int] = {}
    for event in events:
        event_type = str(event.get("event_type") or "")
        if event_type:
            event_types[event_type] = event_types.get(event_type, 0) + 1
        event_tlc = str(event.get("traceability_lot_code") or "")
        if event_tlc:
            tlc_counts[event_tlc] = tlc_counts.get(event_tlc, 0) + 1

    manifest = {
        "version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "export_type": "fda_traceability_package",
        "tenant_id": tenant_id,
        "query": {
            "tlc": tlc,
            "start_date": query_start_date,
            "end_date": query_end_date,
        },
        "summary": {
            "record_count": len(events),
            "event_type_breakdown": event_types,
            "traceability_lot_codes": sorted(tlc_counts.keys()),
            "traceability_lot_code_counts": tlc_counts,
            "csv_content_hash": csv_hash,
        },
        "completeness": completeness_summary,
        "verification": {
            "status": chain_payload.get("verification_status"),
            "chain_valid": chain_payload.get("chain_verification", {}).get("valid"),
            "chain_length": chain_payload.get("chain_verification", {}).get("chain_length"),
        },
        "files": [
            {"name": name, "sha256": digest}
            for name, digest in file_hashes.items()
        ],
    }
    # Do not include a manifest self-hash entry: self-referential hashes cannot be
    # recomputed from final bytes without special canonicalization rules.
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")

    payload = io.BytesIO()
    with zipfile.ZipFile(payload, mode="w", compression=zipfile.ZIP_DEFLATED) as zipf:
        zipf.writestr(csv_name, csv_bytes)
        zipf.writestr(chain_name, chain_bytes)
        zipf.writestr(manifest_name, manifest_bytes)
        zipf.writestr(readme_name, readme_bytes)

    package_bytes = payload.getvalue()
    package_hash = hashlib.sha256(package_bytes).hexdigest()

    return package_bytes, {
        "csv_name": csv_name,
        "chain_name": chain_name,
        "manifest_name": manifest_name,
        "readme_name": readme_name,
        "package_hash": package_hash,
        "manifest": manifest,
    }


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
    format: Literal["package", "csv"] = Query(
        default="package",
        description="Export format: package (zip bundle) or csv",
    ),
    tenant_id: str = Query(..., description="Tenant identifier"),
    _auth=Depends(require_permission("fda.export")),
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
                    "X-KDE-Coverage": str(completeness_summary["required_kde_coverage_ratio"]),
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
                "X-KDE-Coverage": str(completeness_summary["required_kde_coverage_ratio"]),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("fda_export_failed", extra={"error": str(e), "tlc": tlc})
        raise HTTPException(status_code=500, detail="Export failed. Check server logs for details.")
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
    format: Literal["package", "csv"] = Query(
        default="csv",
        description="Export format: package (zip bundle) or csv",
    ),
    tenant_id: str = Query(..., description="Tenant identifier"),
    _auth=Depends(require_permission("fda.export")),
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
                    "X-KDE-Coverage": str(completeness_summary["required_kde_coverage_ratio"]),
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
                "X-KDE-Coverage": str(completeness_summary["required_kde_coverage_ratio"]),
            },
        )

    except Exception as e:
        logger.error("fda_export_all_failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Export failed. Check server logs for details.")
    finally:
        if db_session:
            db_session.close()


@router.get(
    "/export/history",
    summary="View FDA export audit log",
    description="Returns the history of all FDA exports generated for this tenant.",
)
async def export_history(
    tenant_id: str = Query(..., description="Tenant identifier"),
    limit: int = Query(50, ge=1, le=200),
    _auth=Depends(require_permission("fda.read")),
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
            # SQLAlchemy Row objects — use tuple() for safe index access
            r = tuple(row)
            kdes = r[12] if r[12] else {}
            ts = r[6]
            if hasattr(ts, "isoformat"):
                ts = ts.isoformat()
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
        except Exception:
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
    except Exception as e:
        logger.error("fda_recall_export_failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Recall export failed. Check server logs for details.")
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
    tenant_id: str = Query(..., description="Tenant identifier"),
    _auth=Depends(require_permission("fda.verify")),
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
    except Exception as e:
        logger.error("export_verify_failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Verification failed. Check server logs for details.")
    finally:
        if db_session:
            db_session.close()
