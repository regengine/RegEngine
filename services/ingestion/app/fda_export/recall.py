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

from ..fda_export_service import (
    _build_chain_verification_payload,
    _build_completeness_summary,
    _build_fda_package,
    _generate_csv,
)

from .queries import (
    AuditLogWriteError,
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
    *,
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
    request_id: Optional[str] = None,
    user_agent: Optional[str] = None,
    source_ip: Optional[str] = None,
    include_pii: bool = False,
):
    """Generate recall-filtered FDA export with flexible search criteria.

    This is the core logic for the /export/recall endpoint. Identity
    fields are passed through to :func:`log_recall_export` so each
    audit-log row records WHO produced the export and WHEN, satisfying
    FSMA 204 §1.1455(c) chain-of-custody requirements (issues #1205,
    #1209, #1215).

    ``include_pii=False`` (default) redacts facility names and shipping
    location strings in the generated CSV/package; the router gates the
    flag on ``fda.export.pii`` permission and logs every true value to
    the audit trail (issue #1219).
    """
    # Full-tenant recall dumps are regulatorily invalid and a
    # competitive-intelligence leak vector. A real recall is scoped to
    # an affected product/lot/location. See issue #1209.
    #
    # Rule 1: at least one *identifier* filter must be present. A date
    # range alone is not sufficient — ``end_date`` alone previously
    # satisfied the check, which let any authorized user dump the
    # entire supply chain as a "recall" export.
    has_identifier = any([product, location, tlc, event_type])
    if not has_identifier:
        raise HTTPException(
            status_code=400,
            detail=(
                "Recall exports require at least one identifier filter "
                "(product, location, tlc, or event_type). A date-range-only "
                "query would return the entire tenant dataset, which is not "
                "a valid recall scope."
            ),
        )

    # Rule 2: if any date bound is supplied, both must be supplied and
    # ``end_date >= start_date``. An open-ended ``end_date`` forces a
    # time-bounded query that cannot silently include data older than
    # the FSMA 204 two-year retention window.
    if (start_date and not end_date) or (end_date and not start_date):
        raise HTTPException(
            status_code=400,
            detail=(
                "Both start_date and end_date are required when either is "
                "provided. Supply both bounds or omit both."
            ),
        )
    if start_date and end_date and end_date < start_date:
        raise HTTPException(
            status_code=400,
            detail="end_date must be on or after start_date.",
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

        csv_content, export_hash = generate_csv_and_hash(events, include_pii=include_pii)
        chain_verification = persistence.verify_chain(tenant_id=tenant_id)
        completeness_summary = _build_completeness_summary(events)

        # Log the recall export. If the audit-log write fails,
        # ``log_recall_export`` raises :class:`AuditLogWriteError`,
        # which is translated into a 5xx below — the export must not
        # succeed without its chain-of-custody row (issue #1215).
        log_recall_export(
            db_session=db_session,
            tenant_id=tenant_id,
            events=events,
            export_hash=export_hash,
            format=format,
            tlc=tlc,
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
            user_email=user_email,
            request_id=request_id,
            user_agent=user_agent,
            source_ip=source_ip,
            product=product,
            location=location,
            event_type=event_type,
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
                include_pii=include_pii,
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
                "pii_redacted": not include_pii,
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
            include_pii=include_pii,
        )

    except HTTPException:
        raise
    except AuditLogWriteError as e:
        logger.error(
            "fda_recall_export_audit_log_blocked",
            extra={
                "tenant_id": tenant_id,
                "user_id": user_id,
                "request_id": request_id,
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=503,
            detail=(
                "FDA export halted: audit-log write failed. The FSMA 204 "
                "chain-of-custody requirement prevents returning an export "
                "without a corresponding audit-trail row. Retry after the "
                "underlying storage is restored."
            ),
        ) from e
    except (ImportError, ValueError, RuntimeError, OSError) as e:
        logger.error("fda_recall_export_failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Recall export failed. Check server logs for details.")
    finally:
        if db_session:
            db_session.close()
