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
    GET  /api/v1/fda/export/recall      — Recall-filtered FDA export
    POST /api/v1/fda/export/verify      — Verify a previous export's integrity
    GET  /api/v1/fda/export/v2          — Export from canonical model with compliance columns
    GET  /api/v1/fda/export/merkle-root — Merkle root for a tenant's hash chain
    GET  /api/v1/fda/export/merkle-proof — Merkle inclusion proof for a specific event
    GET  /api/v1/fda/trace/{tlc}        — Trace transformation graph for a TLC
"""

from __future__ import annotations

import hashlib
import io
import logging
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from ..authz import IngestionPrincipal, require_permission
from ..export_models import ExportHistoryResponse, ExportVerifyResponse
from shared.fda_export import (
    ExportWindowError,
    MAX_EXPORT_WINDOW_DAYS,
    validate_export_window,
)
from shared.permissions import has_permission as _has_permission
from ..fda_export_service import (
    _build_chain_verification_payload,
    _build_completeness_summary,
    _build_fda_package,
    _generate_csv,
    _generate_csv_v2,
    _generate_pdf,
    _safe_filename_token,
)
from ..subscription_gate import require_active_subscription
from ..webhook_models import REQUIRED_KDES_BY_CTE, WebhookCTEType

from .formatters import (
    build_compliance_headers,
    build_csv_response,
    build_package_response,
    build_pdf_response,
    generate_csv_and_hash,
    generate_csv_v2_and_hash,
    make_timestamp,
    safe_filename_token,
)
from .merkle import get_merkle_root_handler, get_merkle_proof_handler
from .queries import (
    AuditLogWriteError,
    build_recall_where_clause,
    build_v2_where_clause,
    fetch_export_log_history,
    fetch_recall_events,
    fetch_trace_graph_data,
    fetch_v2_events,
    format_export_log_rows,
    log_recall_export,
    log_v2_export,
    rows_to_event_dicts,
    v2_rows_to_event_dicts,
)
from .recall import export_recall_filtered_handler
from .verification import verify_export_handler

logger = logging.getLogger("fda-export")

router = APIRouter(prefix="/api/v1/fda", tags=["FDA Export"])


# FSMA-204 expects "adequate and reliable" traceability. We treat a
# required-KDE coverage ratio below this threshold as a gate: exports
# require an explicit ``allow_incomplete=true`` acknowledgement, and
# every bypass is logged for audit review (issue #1222).
_KDE_COVERAGE_THRESHOLD = 0.80


def _enforce_kde_coverage_gate(
    *,
    completeness_summary: dict,
    allow_incomplete: bool,
    identity: dict,
    tenant_id: str,
    export_scope: str,
) -> None:
    """Raise HTTPException(409) when KDE coverage is below threshold
    and the caller has not acknowledged via ``allow_incomplete=true``.

    Bypasses are emitted at WARNING so they surface in ops dashboards
    (issue #1222).
    """
    kde_coverage = completeness_summary["required_kde_coverage_ratio"]
    if kde_coverage >= _KDE_COVERAGE_THRESHOLD:
        return
    if not allow_incomplete:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "kde_coverage_below_threshold",
                "kde_coverage_ratio": kde_coverage,
                "threshold": _KDE_COVERAGE_THRESHOLD,
                "events_with_missing_required_fields": completeness_summary[
                    "events_with_missing_required_fields"
                ],
                "missing_required_by_field": completeness_summary.get(
                    "missing_required_by_field", {}
                ),
                "message": (
                    f"Required-KDE coverage is {kde_coverage:.2%}, below "
                    f"the {_KDE_COVERAGE_THRESHOLD:.0%} FSMA-204 threshold. "
                    "This export would not meet 'adequate and reliable' "
                    "traceability. Fix missing KDEs, or re-submit with "
                    "allow_incomplete=true if the gap is acceptable for "
                    "this recall scope."
                ),
            },
        )
    logger.warning(
        "fda_export_coverage_gate_bypass",
        extra={
            "tenant_id": tenant_id,
            "user_id": identity["user_id"],
            "request_id": identity["request_id"],
            "export_scope": export_scope,
            "kde_coverage_ratio": kde_coverage,
            "threshold": _KDE_COVERAGE_THRESHOLD,
            "events_with_missing_required_fields": completeness_summary[
                "events_with_missing_required_fields"
            ],
        },
    )


# ---------------------------------------------------------------------------
# PII Redaction (issue #1219)
# ---------------------------------------------------------------------------

# Permission required to opt in to ``include_pii=true`` on an FDA export.
# This is a strictly narrower scope than ``fda.export`` — every caller who
# can generate exports can get a redacted CSV, but only callers who carry
# ``fda.export.pii`` can get facility names / shipping addresses.
_PII_PERMISSION = "fda.export.pii"


def _authorize_pii_access(
    *,
    include_pii: bool,
    principal: IngestionPrincipal,
    identity: dict,
    tenant_id: str,
    export_scope: str,
) -> None:
    """Authorize ``include_pii=true`` and emit an audit line.

    Contract (issue #1219):
      • ``include_pii=False`` (the default): no-op; PII is redacted.
      • ``include_pii=True`` + principal has ``fda.export.pii`` or ``*``:
        allowed. An explicit audit line is logged so every PII-bearing
        export appears in the ops dashboard even when downstream audit
        tables don't yet have a column for the flag.
      • ``include_pii=True`` + principal lacks the permission:
        raises ``HTTPException(403)``. We log the refused attempt at
        WARNING so repeated refusals surface as a security signal.
    """
    if not include_pii:
        return

    scopes = principal.scopes or []
    if not _has_permission(scopes, _PII_PERMISSION):
        logger.warning(
            "fda_export_pii_access_denied",
            extra={
                "tenant_id": tenant_id,
                "user_id": identity["user_id"],
                "request_id": identity["request_id"],
                "export_scope": export_scope,
                "required_permission": _PII_PERMISSION,
            },
        )
        raise HTTPException(
            status_code=403,
            detail=(
                f"include_pii=true requires the '{_PII_PERMISSION}' "
                "permission. Facility names and shipping locations are "
                "redacted by default; contact your tenant admin if you "
                "need the un-redacted export."
            ),
        )

    # Audit line for every allowed PII export. This is INFO-level because
    # legitimate auditors will exercise this path; the existing audit
    # table will pick up user_id/request_id already, but we want the
    # structured line to join easily on ``pii_included=true``.
    logger.info(
        "fda_export_pii_included",
        extra={
            "tenant_id": tenant_id,
            "user_id": identity["user_id"],
            "user_email": identity["user_email"],
            "request_id": identity["request_id"],
            "user_agent": identity["user_agent"],
            "source_ip": identity["source_ip"],
            "export_scope": export_scope,
            "pii_included": True,
        },
    )


def _audit_identity(
    request: Request,
    principal: IngestionPrincipal,
) -> dict[str, Optional[str]]:
    """Collect FSMA-204 audit-trail identity fields from the request.

    Captures the authenticated actor (``user_id``) plus request-precise
    metadata (``request_id``, ``user_agent``, ``source_ip``) so the
    FDA export log can answer the "who exported tenant X's trace at 3am
    last Saturday?" question (issue #1205).
    """
    client_ip = request.client.host if request.client else None
    return {
        "user_id": getattr(principal, "key_id", None),
        "user_email": getattr(principal, "user_email", None),
        "request_id": request.headers.get("X-Request-ID")
        or request.headers.get("X-Correlation-ID"),
        "user_agent": request.headers.get("User-Agent"),
        "source_ip": request.headers.get("X-Forwarded-For", client_ip)
        or client_ip,
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
    responses={
        200: {
            "content": {
                "text/csv": {},
                "application/zip": {},
                "application/pdf": {},
            },
            "description": "FDA-compliant CSV, ZIP package, or PDF report",
        },
    },
)
async def export_fda_spreadsheet(
    request: Request,
    tlc: str = Query(..., description="Traceability Lot Code to trace"),
    start_date: Optional[str] = Query(None, description="Start date filter (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date filter (YYYY-MM-DD)"),
    format: Literal["package", "csv", "pdf"] = Query(
        default="package",
        description="Export format: package (zip bundle), csv, or pdf",
    ),
    tenant_id: str = Query(..., description="Tenant identifier"),
    allow_incomplete: bool = Query(
        default=False,
        description=(
            "Acknowledge that KDE coverage may be below the 80% FSMA-204 "
            "threshold. Required to bypass the coverage gate; every bypass "
            "is recorded in the audit trail."
        ),
    ),
    include_pii: bool = Query(
        default=False,
        description=(
            "Include facility names and shipping locations in the export. "
            "Defaults to false: these columns are redacted to '[REDACTED]' "
            "and GLNs / FDA registration numbers are used as the regulatory "
            "entity keys. Setting this to true requires the 'fda.export.pii' "
            "permission and is recorded in the audit trail (issue #1219)."
        ),
    ),
    principal: IngestionPrincipal = Depends(require_permission("fda.export")),
    _subscription=Depends(require_active_subscription),
):
    """Generate and return an FDA-compliant traceability export."""
    # FSMA 204 §1.1455(c) requires a tamper-evident audit trail identifying
    # WHO produced each export and WHEN (issue #1205). Identity fields must
    # resolve from the authenticated principal — never from the request
    # body — or the handler must refuse to produce an export.
    identity = _audit_identity(request, principal)
    if not identity["user_id"]:
        raise HTTPException(
            status_code=401,
            detail=(
                "FDA export requires an authenticated principal with a "
                "resolvable key_id. Cannot generate export without an "
                "FSMA-204 audit-trail actor."
            ),
        )

    # Authorize PII access BEFORE any DB work (issue #1219). Callers
    # without ``fda.export.pii`` get a 403 fast; no query/audit cost.
    _authorize_pii_access(
        include_pii=include_pii,
        principal=principal,
        identity=identity,
        tenant_id=tenant_id,
        export_scope=f"tlc:{tlc}",
    )

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

        # Generate CSV as canonical export evidence. The ``include_pii``
        # flag flows from the query string → authorization gate → CSV
        # generator; the generated hash covers the redacted (or full)
        # content exactly, so ``verify_export`` can reproduce it.
        csv_content = _generate_csv(events, include_pii=include_pii)
        export_hash = hashlib.sha256(csv_content.encode("utf-8")).hexdigest()
        chain_verification = persistence.verify_chain(tenant_id=tenant_id)
        completeness_summary = _build_completeness_summary(events)

        # Enforce the KDE coverage gate (#1222). Callers may bypass by
        # passing ``allow_incomplete=true``; every bypass is logged.
        _enforce_kde_coverage_gate(
            completeness_summary=completeness_summary,
            allow_incomplete=allow_incomplete,
            identity=identity,
            tenant_id=tenant_id,
            export_scope=f"tlc:{tlc}",
        )

        # Log the export. ``persistence.log_export`` writes the minimal
        # canonical row; the structured INFO line below captures the full
        # identity + filter context so log shippers can reconstruct the
        # FSMA-204 chain-of-custody even if the schema hasn't been
        # migrated to add columns for user_id/request_id yet.
        generated_by = f"user:{identity['user_id']}" + (
            f":request:{identity['request_id']}"
            if identity["request_id"]
            else ""
        )
        try:
            persistence.log_export(
                tenant_id=tenant_id,
                export_hash=export_hash,
                record_count=len(events),
                query_tlc=tlc,
                query_start_date=start_date,
                query_end_date=end_date,
                generated_by=generated_by,
                export_type="fda_spreadsheet_package" if format == "package" else "fda_spreadsheet",
            )
            db_session.commit()
        except Exception as exc:
            db_session.rollback()
            logger.error(
                "fda_export_audit_log_failed",
                extra={
                    "tenant_id": tenant_id,
                    "user_id": identity["user_id"],
                    "request_id": identity["request_id"],
                    "export_hash": export_hash[:16],
                    "error": str(exc),
                },
                exc_info=True,
            )
            raise HTTPException(
                status_code=503,
                detail=(
                    "FDA export halted: audit-log write failed. The "
                    "FSMA 204 chain-of-custody requirement prevents "
                    "returning an export without a corresponding "
                    "audit-trail row."
                ),
            ) from exc

        # Structured audit line — captured regardless of DB schema version.
        logger.info(
            "fda_export_audit",
            extra={
                "tenant_id": tenant_id,
                "user_id": identity["user_id"],
                "user_email": identity["user_email"],
                "request_id": identity["request_id"],
                "user_agent": identity["user_agent"],
                "source_ip": identity["source_ip"],
                "export_type": "fda_spreadsheet_package" if format == "package" else "fda_spreadsheet",
                "export_hash": export_hash,
                "record_count": len(events),
                "filters_applied": {
                    "tlc": tlc,
                    "start_date": start_date,
                    "end_date": end_date,
                    "format": format,
                },
                "pii_included": include_pii,
                "initiated_at_utc": datetime.now(timezone.utc).isoformat(),
            },
        )

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
                "pii_included": include_pii,
            },
        )

        kde_coverage = completeness_summary["required_kde_coverage_ratio"]
        kde_warnings = completeness_summary["events_with_missing_required_fields"]
        compliance_headers: dict[str, str] = {
            "X-KDE-Coverage": str(kde_coverage),
            "X-KDE-Warnings": str(kde_warnings),
            "X-PII-Redacted": "false" if include_pii else "true",
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
                include_pii=include_pii,
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
                include_pii=include_pii,
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

        if format == "pdf":
            pdf_bytes = _generate_pdf(
                events,
                metadata={
                    "tlc": tlc,
                    "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "start_date": start_date,
                    "end_date": end_date,
                },
                include_pii=include_pii,
            )
            filename = f"fda_export_{safe_tlc}_{timestamp}.pdf"
            return StreamingResponse(
                io.BytesIO(pdf_bytes),
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename={filename}",
                    "X-Export-Hash": export_hash,
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
                "application/pdf": {},
            },
            "description": "FDA-compliant CSV, ZIP package, or PDF report",
        },
    },
)
async def export_all_events(
    request: Request,
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    event_type: Optional[str] = Query(None, description="Filter by CTE type"),
    format: Literal["package", "csv", "pdf"] = Query(
        default="csv",
        description="Export format: package (zip bundle), csv, or pdf",
    ),
    tenant_id: str = Query(..., description="Tenant identifier"),
    allow_incomplete: bool = Query(
        default=False,
        description=(
            "Acknowledge KDE coverage <80% and proceed. Every bypass is "
            "recorded in the audit trail."
        ),
    ),
    include_pii: bool = Query(
        default=False,
        description=(
            "Include facility names and shipping locations in the export. "
            "Requires 'fda.export.pii' permission; defaults to false (issue #1219)."
        ),
    ),
    principal: IngestionPrincipal = Depends(require_permission("fda.export")),
    _subscription=Depends(require_active_subscription),
):
    """Export all events as FDA-format CSV."""
    # FSMA 204 §1.1455(c) audit-trail identity (issue #1205).
    identity = _audit_identity(request, principal)
    if not identity["user_id"]:
        raise HTTPException(
            status_code=401,
            detail=(
                "FDA export requires an authenticated principal with a "
                "resolvable key_id."
            ),
        )

    # EPIC-L (#1655): the ``/export/all`` path is the full-tenant-dump
    # risk surface. Require both dates and cap the window at 90 days
    # so a caller can't materialize the entire retention window in
    # one synchronous request.
    try:
        validate_export_window(start_date, end_date)
    except ExportWindowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Authorize PII access (issue #1219).
    _authorize_pii_access(
        include_pii=include_pii,
        principal=principal,
        identity=identity,
        tenant_id=tenant_id,
        export_scope="all_events",
    )

    db_session = None
    try:
        from shared.database import SessionLocal
        from shared.cte_persistence import CTEPersistence

        db_session = SessionLocal()
        persistence = CTEPersistence(db_session)

        _EXPORT_LIMIT = 10000
        events, total = persistence.query_all_events(
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
            event_type=event_type,
            limit=_EXPORT_LIMIT,
        )

        # Batch-fetch by distinct TLCs to avoid O(N*M) query amplification
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

        # EPIC-L (#1655): no empty-success exports. An FDA-formatted CSV
        # with zero data rows looks identical to a complete "no compliance
        # activity" response and is easy to misread. Fail loudly instead.
        if not deduped:
            raise HTTPException(
                status_code=404,
                detail=(
                    "No traceability records found for the requested "
                    "window. Widen the date range or verify tenant_id."
                ),
            )

        csv_content = _generate_csv(deduped, include_pii=include_pii)
        export_hash = hashlib.sha256(csv_content.encode("utf-8")).hexdigest()
        chain_verification = persistence.verify_chain(tenant_id=tenant_id)
        completeness_summary = _build_completeness_summary(deduped)

        # KDE coverage gate (#1222).
        _enforce_kde_coverage_gate(
            completeness_summary=completeness_summary,
            allow_incomplete=allow_incomplete,
            identity=identity,
            tenant_id=tenant_id,
            export_scope="all_events",
        )

        generated_by = f"user:{identity['user_id']}" + (
            f":request:{identity['request_id']}"
            if identity["request_id"]
            else ""
        )
        try:
            persistence.log_export(
                tenant_id=tenant_id,
                export_hash=export_hash,
                record_count=len(deduped),
                query_start_date=start_date,
                query_end_date=end_date,
                generated_by=generated_by,
                export_type="fda_export_all_package" if format == "package" else "fda_export_all",
            )
            db_session.commit()
        except Exception as exc:
            db_session.rollback()
            logger.error(
                "fda_export_all_audit_log_failed",
                extra={
                    "tenant_id": tenant_id,
                    "user_id": identity["user_id"],
                    "request_id": identity["request_id"],
                    "export_hash": export_hash[:16],
                    "error": str(exc),
                },
                exc_info=True,
            )
            raise HTTPException(
                status_code=503,
                detail=(
                    "FDA export halted: audit-log write failed. The "
                    "FSMA 204 chain-of-custody requirement prevents "
                    "returning an export without a corresponding "
                    "audit-trail row."
                ),
            ) from exc

        logger.info(
            "fda_export_all_audit",
            extra={
                "tenant_id": tenant_id,
                "user_id": identity["user_id"],
                "user_email": identity["user_email"],
                "request_id": identity["request_id"],
                "user_agent": identity["user_agent"],
                "source_ip": identity["source_ip"],
                "export_type": "fda_export_all_package" if format == "package" else "fda_export_all",
                "export_hash": export_hash,
                "record_count": len(deduped),
                "filters_applied": {
                    "start_date": start_date,
                    "end_date": end_date,
                    "event_type": event_type,
                    "format": format,
                },
                "pii_included": include_pii,
                "initiated_at_utc": datetime.now(timezone.utc).isoformat(),
            },
        )

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        kde_coverage = completeness_summary["required_kde_coverage_ratio"]
        kde_warnings = completeness_summary["events_with_missing_required_fields"]
        compliance_headers: dict[str, str] = {
            "X-KDE-Coverage": str(kde_coverage),
            "X-KDE-Warnings": str(kde_warnings),
            "X-Total-Count": str(total),
            "X-PII-Redacted": "false" if include_pii else "true",
        }
        if total > _EXPORT_LIMIT:
            compliance_headers["X-Truncated"] = (
                f"Result set truncated to {_EXPORT_LIMIT} events out of {total}. "
                "Use date filters to narrow the query."
            )
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
                include_pii=include_pii,
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
                include_pii=include_pii,
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

        if format == "pdf":
            pdf_bytes = _generate_pdf(
                deduped,
                metadata={
                    "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "start_date": start_date,
                    "end_date": end_date,
                },
                include_pii=include_pii,
            )
            filename = f"fda_export_all_{timestamp}.pdf"
            return StreamingResponse(
                io.BytesIO(pdf_bytes),
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename={filename}",
                    "X-Export-Hash": export_hash,
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

    except HTTPException:
        raise
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

        rows = fetch_export_log_history(db_session, tenant_id, limit)
        return format_export_log_rows(rows, tenant_id)

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
    request: Request,
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
    allow_incomplete: bool = Query(
        default=False,
        description=(
            "Acknowledge KDE coverage <80% and proceed. Every bypass is "
            "recorded in the audit trail."
        ),
    ),
    include_pii: bool = Query(
        default=False,
        description=(
            "Include facility names and shipping locations. Requires "
            "'fda.export.pii' permission; defaults to false (issue #1219)."
        ),
    ),
    principal: IngestionPrincipal = Depends(require_permission("fda.export")),
    _subscription=Depends(require_active_subscription),
):
    """Generate recall-filtered FDA export with flexible search criteria."""
    identity = _audit_identity(request, principal)
    if not identity["user_id"]:
        raise HTTPException(
            status_code=401,
            detail=(
                "FDA recall export requires an authenticated principal "
                "with a resolvable key_id."
            ),
        )

    # Authorize PII access (issue #1219). Recall exports are especially
    # sensitive: they get shared outside the regulated entity, so the
    # PII-inclusion permission check runs here too.
    _authorize_pii_access(
        include_pii=include_pii,
        principal=principal,
        identity=identity,
        tenant_id=tenant_id,
        export_scope="recall",
    )

    return await export_recall_filtered_handler(
        tenant_id=tenant_id,
        product=product,
        location=location,
        tlc=tlc,
        event_type=event_type,
        start_date=start_date,
        end_date=end_date,
        format=format,
        user_id=identity["user_id"],
        user_email=identity["user_email"],
        request_id=identity["request_id"],
        user_agent=identity["user_agent"],
        source_ip=identity["source_ip"],
        include_pii=include_pii,
    )


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
    return await verify_export_handler(
        export_id=export_id,
        tenant_id=tenant_id,
    )


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
    request: Request,
    tenant_id: str = Query(..., description="Tenant identifier"),
    tlc: Optional[str] = Query(None, description="Traceability Lot Code filter (exact or partial with %%)"),
    start_date: Optional[str] = Query(None, description="Start date filter (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date filter (YYYY-MM-DD)"),
    event_type: Optional[str] = Query(None, description="Filter by CTE type"),
    format: Literal["package", "csv"] = Query(
        default="csv",
        description="Export format: package (zip bundle) or csv",
    ),
    allow_incomplete: bool = Query(
        default=False,
        description=(
            "Acknowledge KDE coverage <80% and proceed. Every bypass is "
            "recorded in the audit trail."
        ),
    ),
    include_pii: bool = Query(
        default=False,
        description=(
            "Include facility names and shipping locations in the export. "
            "Requires 'fda.export.pii' permission; defaults to false (issue #1219)."
        ),
    ),
    principal: IngestionPrincipal = Depends(require_permission("fda.export")),
    _subscription=Depends(require_active_subscription),
):
    """Generate FDA-compliant traceability export from the canonical model with rule evaluation results."""
    identity = _audit_identity(request, principal)
    if not identity["user_id"]:
        raise HTTPException(
            status_code=401,
            detail=(
                "FDA v2 export requires an authenticated principal "
                "with a resolvable key_id."
            ),
        )

    if not tlc:
        try:
            validate_export_window(start_date, end_date)
        except ExportWindowError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    elif start_date or end_date:
        try:
            validate_export_window(start_date, end_date)
        except ExportWindowError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Authorize PII access (issue #1219).
    _authorize_pii_access(
        include_pii=include_pii,
        principal=principal,
        identity=identity,
        tenant_id=tenant_id,
        export_scope=f"v2:{tlc or 'all'}",
    )
    db_session = None
    try:
        from shared.database import SessionLocal
        from shared.cte_persistence import CTEPersistence

        db_session = SessionLocal()
        persistence = CTEPersistence(db_session)

        # ----- Build dynamic WHERE clause -----
        where_clause, params = build_v2_where_clause(
            tenant_id=tenant_id,
            tlc=tlc,
            event_type=event_type,
            start_date=start_date,
            end_date=end_date,
        )

        # ----- Query from canonical model with rule evaluations -----
        rows = fetch_v2_events(db_session, where_clause, params)
        if len(rows) > 10000:
            raise HTTPException(
                status_code=413,
                detail=(
                    "V2 export exceeds the 10000-record synchronous limit. "
                    "Narrow the date range or request a paginated/offline export."
                ),
            )

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
        events = v2_rows_to_event_dicts(rows)

        # ----- Generate CSV with compliance columns -----
        csv_content, export_hash = generate_csv_v2_and_hash(events, include_pii=include_pii)
        chain_verification = persistence.verify_chain(tenant_id=tenant_id)
        completeness_summary = _build_completeness_summary(events)
        _enforce_kde_coverage_gate(
            completeness_summary=completeness_summary,
            allow_incomplete=allow_incomplete,
            identity=identity,
            tenant_id=tenant_id,
            export_scope=f"v2:{tlc or 'all'}",
        )

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
        # Raises AuditLogWriteError on DB failure (caught below) so the
        # export cannot succeed without its FSMA-204 chain-of-custody row.
        log_v2_export(
            db_session=db_session,
            tenant_id=tenant_id,
            events=events,
            export_hash=export_hash,
            format=format,
            tlc=tlc,
            start_date=start_date,
            end_date=end_date,
            user_id=identity["user_id"],
            user_email=identity["user_email"],
            request_id=identity["request_id"],
            user_agent=identity["user_agent"],
            source_ip=identity["source_ip"],
        )

        timestamp = make_timestamp()
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
                "pii_included": include_pii,
            },
        )

        if format == "package":
            # Build chain verification payload with provenance metadata
            chain_payload_extras = {
                "data_source": "fsma.traceability_events (canonical model)",
                "compliance_summary": {
                    "total_events": total_events,
                    "events_passing": events_passing,
                    "events_failing": events_failing,
                    "events_no_rules": events_no_rules,
                    "compliance_rate": round(events_passing / total_events, 4) if total_events else 0,
                },
                "provenance": {
                    "source_table": "fsma.traceability_events",
                    "rule_tables": ["fsma.rule_evaluations", "fsma.rule_definitions"],
                    "export_version": "2.0",
                },
                "attestation": {
                    "attested_by": "regengine-fda-export-router-v2",
                    "assertion": (
                        "Package generated from canonical fsma.traceability_events "
                        "with rule evaluation results and chain verification."
                    ),
                },
            }

            filename = f"fda_v2_package_{scope}_{timestamp}.zip"
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
                    "X-Export-Version": "2.0",
                    "X-KDE-Coverage": str(completeness_summary["required_kde_coverage_ratio"]),
                    "X-Compliance-Rate": str(
                        round(events_passing / total_events, 4) if total_events else 0
                    ),
                },
                chain_payload_extras=chain_payload_extras,
                include_pii=include_pii,
            )

        # CSV-only response
        filename = f"fda_v2_export_{scope}_{timestamp}.csv"
        return build_csv_response(
            csv_content=csv_content,
            filename=filename,
            export_hash=export_hash,
            record_count=len(events),
            chain_valid=chain_verification.valid,
            extra_headers={
                "X-Export-Version": "2.0",
                "X-KDE-Coverage": str(completeness_summary["required_kde_coverage_ratio"]),
                "X-Compliance-Rate": str(
                    round(events_passing / total_events, 4) if total_events else 0
                ),
            },
            include_pii=include_pii,
        )

    except HTTPException:
        raise
    except AuditLogWriteError as e:
        logger.error(
            "fda_export_v2_audit_log_blocked",
            extra={
                "tenant_id": tenant_id,
                "user_id": identity["user_id"],
                "request_id": identity["request_id"],
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=503,
            detail=(
                "FDA v2 export halted: audit-log write failed. The "
                "FSMA 204 chain-of-custody requirement prevents returning "
                "an export without a corresponding audit-trail row."
            ),
        ) from e
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
    return await get_merkle_root_handler(tenant_id)


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
    return await get_merkle_proof_handler(tenant_id, event_id)


# ---------------------------------------------------------------------------
# Transformation trace graph
# ---------------------------------------------------------------------------

@router.get(
    "/trace/{tlc}",
    summary="Trace transformation graph for a TLC",
    description=(
        "Returns all TLCs reachable from the given lot code via "
        "fsma.transformation_links — both upstream inputs and downstream outputs.  "
        "Also returns the full CTE event count per linked lot so the UI can "
        "show the trace tree without fetching the full FDA export."
    ),
    tags=["Traceability"],
)
async def trace_transformation_graph(
    tlc: str,
    tenant_id: str = Query(..., description="Tenant identifier"),
    depth: int = Query(default=5, ge=1, le=10, description="Max traversal depth"),
    _auth=Depends(require_permission("fda.read")),
    _subscription=Depends(require_active_subscription),
) -> dict:
    """Return the transformation graph rooted at a given TLC."""
    db_session = None
    try:
        from shared.database import SessionLocal
        from shared.cte_persistence import CTEPersistence

        db_session = SessionLocal()
        persistence = CTEPersistence(db_session)

        return fetch_trace_graph_data(
            db_session=db_session,
            persistence=persistence,
            tenant_id=tenant_id,
            tlc=tlc,
            depth=depth,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("trace_graph_failed", extra={"error": str(e), "tlc": tlc})
        raise HTTPException(status_code=500, detail="Trace graph query failed.")
    finally:
        if db_session:
            db_session.close()
