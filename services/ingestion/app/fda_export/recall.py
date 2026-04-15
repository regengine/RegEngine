"""
Recall-filtered exports with dynamic WHERE clause construction.

Extracted from fda_export_router.py — pure structural refactor.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from app.fda_export_service import (
    _build_chain_verification_payload,
    _build_completeness_summary,
    _build_fda_package,
    _generate_csv,
)

from .queries import (
    build_recall_where_clause,
    fetch_recall_events,
    log_recall_export,
    rows_to_event_dicts,
)
from .formatters import (
    build_csv_response,
    build_package_response,
    generate_csv_and_hash,
    make_timestamp,
)

logger = logging.getLogger("fda-export")


async def export_recall_filtered_handler(
    tenant_id: str,
    product: Optional[str],
    location: Optional[str],
    tlc: Optional[str],
    event_type: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
    format: str,
):
    """Generate recall-filtered FDA export with flexible search criteria.

    This is the core logic for the /export/recall endpoint.
    """
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

        db_session = SessionLocal()
        persistence = CTEPersistence(db_session)

        # Build dynamic query with parameterized filters
        where_clause, params = build_recall_where_clause(
            tenant_id=tenant_id,
            product=product,
            location=location,
            tlc=tlc,
            event_type=event_type,
            start_date=start_date,
            end_date=end_date,
        )

        rows = fetch_recall_events(db_session, where_clause, params)

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
        events = rows_to_event_dicts(rows)

        csv_content, export_hash = generate_csv_and_hash(events)
        chain_verification = persistence.verify_chain(tenant_id=tenant_id)
        completeness_summary = _build_completeness_summary(events)

        # Log the recall export
        log_recall_export(
            db_session=db_session,
            tenant_id=tenant_id,
            events=events,
            export_hash=export_hash,
            format=format,
            tlc=tlc,
            start_date=start_date,
            end_date=end_date,
        )

        timestamp = make_timestamp()
        if format == "package":
            filename = f"fda_recall_package_{timestamp}.zip"
            return build_package_response(
                events=events,
                csv_content=csv_content,
                export_hash=export_hash,
                chain_verification=chain_verification,
                completeness_summary=completeness_summary,
                tenant_id=tenant_id,
                tlc=tlc,
                start_date=start_date,
                end_date=end_date,
                filename=filename,
                extra_headers={
                    "X-Export-Type": "recall_package",
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

        return build_csv_response(
            csv_content=csv_content,
            filename=filename,
            export_hash=export_hash,
            record_count=len(events),
            chain_valid=chain_verification.valid,
            extra_headers={
                "X-Export-Type": "recall",
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
