"""
Audit Export Log & Activity Feed.

Provides endpoints to query the export audit trail, chain verification
history, and a combined activity feed for tenant observability.

Endpoints:
    POST /api/v1/audit/exports/{tenant_id}        — Export audit trail
    POST /api/v1/audit/verifications/{tenant_id}   — Chain verification history
    GET  /api/v1/audit/activity/{tenant_id}        — Combined activity feed
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.webhook_compat import _verify_api_key

logger = logging.getLogger("audit-export-log")

router = APIRouter(prefix="/api/v1/audit", tags=["Audit Trail"])


# ---------------------------------------------------------------------------
# In-memory fallback store for verification results
# ---------------------------------------------------------------------------

# In-memory store — ephemeral data (export verification tokens with short TTL). Intentionally not persisted.
_verification_store: dict[str, dict] = {}
_verification_store_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class ExportRecord(BaseModel):
    """A single FDA export log entry."""

    id: str
    tenant_id: str
    export_type: Optional[str] = None
    record_count: int = 0
    sha256_hash: Optional[str] = None
    created_at: Optional[str] = None
    traceability_lot_code: Optional[str] = None
    format: Optional[str] = None


class ExportAuditResponse(BaseModel):
    """Response for export audit trail query."""

    tenant_id: str
    exports: list[ExportRecord] = Field(default_factory=list)
    total: int = 0


class ExportQueryRequest(BaseModel):
    """Optional filters for the export audit query."""

    start_date: Optional[str] = Field(None, description="ISO date filter start")
    end_date: Optional[str] = Field(None, description="ISO date filter end")
    limit: int = Field(50, ge=1, le=500, description="Max results")


class VerificationRecord(BaseModel):
    """A single chain verification log entry."""

    id: str
    tenant_id: str
    chain_valid: Optional[bool] = None
    chain_length: int = 0
    errors: list[str] = Field(default_factory=list)
    completed_at: Optional[str] = None


class VerificationHistoryResponse(BaseModel):
    """Response for verification history query."""

    tenant_id: str
    verifications: list[VerificationRecord] = Field(default_factory=list)
    total: int = 0


class VerificationQueryRequest(BaseModel):
    """Optional filters for the verification history query."""

    limit: int = Field(50, ge=1, le=500, description="Max results")


class ActivityEntry(BaseModel):
    """A single entry in the combined activity feed."""

    id: str
    tenant_id: str
    activity_type: str  # "export", "verification", "ingestion"
    summary: str
    timestamp: str
    details: Optional[dict] = None


class ActivityFeedResponse(BaseModel):
    """Paginated combined activity feed."""

    tenant_id: str
    activities: list[ActivityEntry] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 50


# ---------------------------------------------------------------------------
# Database query helpers
# ---------------------------------------------------------------------------


def _query_exports(tenant_id: str, start_date: Optional[str], end_date: Optional[str], limit: int) -> Optional[list[dict]]:
    """Query fda_export_log from database."""
    try:
        from shared.database import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            conditions = ["tenant_id = :tid"]
            params: dict = {"tid": tenant_id, "lim": limit}

            if start_date:
                conditions.append("created_at >= :start")
                params["start"] = start_date
            if end_date:
                conditions.append("created_at <= :end")
                params["end"] = end_date

            where_clause = " AND ".join(conditions)
            rows = db.execute(
                text(f"""
                    SELECT id, tenant_id, export_type, record_count,
                           sha256_hash, created_at, traceability_lot_code, format
                    FROM fsma.fda_export_log
                    WHERE {where_clause}
                    ORDER BY created_at DESC
                    LIMIT :lim
                """),
                params,
            ).fetchall()

            return [
                {
                    "id": str(row[0]),
                    "tenant_id": row[1],
                    "export_type": row[2],
                    "record_count": row[3] or 0,
                    "sha256_hash": row[4],
                    "created_at": row[5].isoformat() if hasattr(row[5], "isoformat") else str(row[5]) if row[5] else None,
                    "traceability_lot_code": row[6],
                    "format": row[7],
                }
                for row in rows
            ]
        finally:
            db.close()
    except Exception as exc:
        logger.warning("export_log_query_failed error=%s", str(exc))
        return None


def _query_verifications(tenant_id: str, limit: int) -> Optional[list[dict]]:
    """Query chain_verification_log from database, with in-memory fallback."""
    try:
        from shared.database import SessionLocal
        from sqlalchemy import text
        import json

        db = SessionLocal()
        try:
            rows = db.execute(
                text("""
                    SELECT id, tenant_id, chain_valid, chain_length, errors, completed_at
                    FROM fsma.chain_verification_log
                    WHERE tenant_id = :tid
                    ORDER BY completed_at DESC
                    LIMIT :lim
                """),
                {"tid": tenant_id, "lim": limit},
            ).fetchall()

            return [
                {
                    "id": str(row[0]),
                    "tenant_id": row[1],
                    "chain_valid": row[2],
                    "chain_length": row[3] or 0,
                    "errors": json.loads(row[4]) if isinstance(row[4], str) else (row[4] or []),
                    "completed_at": row[5].isoformat() if hasattr(row[5], "isoformat") else str(row[5]) if row[5] else None,
                }
                for row in rows
            ]
        finally:
            db.close()
    except Exception as exc:
        logger.debug("verification_log_query_failed error=%s (using in-memory fallback)", str(exc))
        return None


def _get_verification_fallback(tenant_id: str, limit: int) -> list[dict]:
    """Return verification records from in-memory store and chain_verification_job store."""
    results = []

    # Pull from the chain_verification_job in-memory store
    try:
        from app.chain_verification_job import _verification_jobs, _verification_lock

        with _verification_lock:
            for job_id, job in _verification_jobs.items():
                if job.get("tenant_id") == tenant_id and job.get("status") == "completed":
                    results.append({
                        "id": job_id,
                        "tenant_id": tenant_id,
                        "chain_valid": job.get("chain_valid"),
                        "chain_length": job.get("chain_length", 0),
                        "errors": job.get("errors", []),
                        "completed_at": job.get("completed_at"),
                    })
    except ImportError:
        pass

    # Also check local fallback store
    with _verification_store_lock:
        for vid, rec in _verification_store.items():
            if rec.get("tenant_id") == tenant_id:
                results.append(rec)

    # Sort by completed_at descending, limit
    results.sort(key=lambda r: r.get("completed_at") or "", reverse=True)
    return results[:limit]


def _query_ingestions(tenant_id: str, limit: int) -> list[dict]:
    """Query recent CTE ingestion events for the activity feed."""
    try:
        from shared.database import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            rows = db.execute(
                text("""
                    SELECT id, tenant_id, event_type, traceability_lot_code, ingested_at
                    FROM fsma.cte_events
                    WHERE tenant_id = :tid
                    ORDER BY ingested_at DESC
                    LIMIT :lim
                """),
                {"tid": tenant_id, "lim": limit},
            ).fetchall()

            return [
                {
                    "id": str(row[0]),
                    "tenant_id": row[1],
                    "activity_type": "ingestion",
                    "summary": f"CTE ingested: {row[2]} for TLC {row[3]}",
                    "timestamp": row[4].isoformat() if hasattr(row[4], "isoformat") else str(row[4]) if row[4] else "",
                    "details": {
                        "event_type": row[2],
                        "traceability_lot_code": row[3],
                    },
                }
                for row in rows
            ]
        finally:
            db.close()
    except Exception as exc:
        logger.debug("ingestion_query_failed error=%s", str(exc))
        return []


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/exports/{tenant_id}",
    response_model=ExportAuditResponse,
    summary="Query export audit trail",
)
async def query_export_audit_trail(
    tenant_id: str,
    request: ExportQueryRequest = None,
    _auth=Depends(_verify_api_key),
):
    """Return the FDA export audit trail for a tenant, with optional date filters."""
    if request is None:
        request = ExportQueryRequest()

    exports_raw = _query_exports(tenant_id, request.start_date, request.end_date, request.limit)

    if exports_raw is None:
        # DB unavailable — return empty
        logger.info("export_audit_trail tenant_id=%s source=empty (db unavailable)", tenant_id)
        return ExportAuditResponse(tenant_id=tenant_id, exports=[], total=0)

    exports = [ExportRecord(**rec) for rec in exports_raw]
    logger.info("export_audit_trail tenant_id=%s count=%d", tenant_id, len(exports))

    return ExportAuditResponse(
        tenant_id=tenant_id,
        exports=exports,
        total=len(exports),
    )


@router.post(
    "/verifications/{tenant_id}",
    response_model=VerificationHistoryResponse,
    summary="Query chain verification history",
)
async def query_verification_history(
    tenant_id: str,
    request: VerificationQueryRequest = None,
    _auth=Depends(_verify_api_key),
):
    """Return the chain verification history for a tenant."""
    if request is None:
        request = VerificationQueryRequest()

    verifications_raw = _query_verifications(tenant_id, request.limit)

    if verifications_raw is None:
        # DB table doesn't exist — use in-memory fallback
        verifications_raw = _get_verification_fallback(tenant_id, request.limit)

    verifications = [VerificationRecord(**rec) for rec in verifications_raw]
    logger.info("verification_history tenant_id=%s count=%d", tenant_id, len(verifications))

    return VerificationHistoryResponse(
        tenant_id=tenant_id,
        verifications=verifications,
        total=len(verifications),
    )


@router.get(
    "/activity/{tenant_id}",
    response_model=ActivityFeedResponse,
    summary="Combined activity feed",
)
async def get_activity_feed(
    tenant_id: str,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    _auth=Depends(_verify_api_key),
):
    """Return a combined, paginated activity feed of exports, verifications,
    and ingestions for a tenant, sorted by timestamp descending.
    """
    activities: list[dict] = []

    # 1. Exports
    exports_raw = _query_exports(tenant_id, None, None, limit=page_size * 2)
    if exports_raw:
        for exp in exports_raw:
            activities.append({
                "id": exp["id"],
                "tenant_id": tenant_id,
                "activity_type": "export",
                "summary": f"FDA export: {exp.get('export_type', 'standard')} — {exp.get('record_count', 0)} records",
                "timestamp": exp.get("created_at") or "",
                "details": {
                    "sha256_hash": exp.get("sha256_hash"),
                    "format": exp.get("format"),
                    "traceability_lot_code": exp.get("traceability_lot_code"),
                },
            })

    # 2. Verifications
    verifications_raw = _query_verifications(tenant_id, limit=page_size * 2)
    if verifications_raw is None:
        verifications_raw = _get_verification_fallback(tenant_id, limit=page_size * 2)
    for ver in verifications_raw:
        status = "passed" if ver.get("chain_valid") else "failed"
        activities.append({
            "id": ver["id"],
            "tenant_id": tenant_id,
            "activity_type": "verification",
            "summary": f"Chain verification {status}: {ver.get('chain_length', 0)} entries",
            "timestamp": ver.get("completed_at") or "",
            "details": {
                "chain_valid": ver.get("chain_valid"),
                "chain_length": ver.get("chain_length"),
                "error_count": len(ver.get("errors", [])),
            },
        })

    # 3. Ingestions
    ingestions = _query_ingestions(tenant_id, limit=page_size * 2)
    activities.extend(ingestions)

    # Sort all by timestamp descending
    activities.sort(key=lambda a: a.get("timestamp") or "", reverse=True)

    # Paginate
    total = len(activities)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = activities[start:end]

    entries = [ActivityEntry(**item) for item in page_items]

    logger.info(
        "activity_feed tenant_id=%s total=%d page=%d page_size=%d",
        tenant_id, total, page, page_size,
    )

    return ActivityFeedResponse(
        tenant_id=tenant_id,
        activities=entries,
        total=total,
        page=page,
        page_size=page_size,
    )
