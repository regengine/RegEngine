"""
Canonical Record Detail Router.

Provides API endpoints for accessing canonical traceability events
with full provenance — answering the five questions every record must answer:
    1. What is this?
    2. Where did it come from?
    3. What rules were applied?
    4. What failed?
    5. What must happen next?

Endpoints:
    GET    /api/v1/records/{event_id}              — Full record with provenance
    GET    /api/v1/records                          — List/search canonical events
    GET    /api/v1/records/{event_id}/evaluations   — Rule evaluations for record
    GET    /api/v1/records/{event_id}/history        — Amendment chain
    GET    /api/v1/records/ingestion-runs            — List ingestion runs
    GET    /api/v1/records/ingestion-runs/{run_id}   — Ingestion run detail
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import SQLAlchemyError

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.authz import require_permission, IngestionPrincipal
from app.tenant_validation import validate_tenant_id

logger = logging.getLogger("canonical-records")

router = APIRouter(prefix="/api/v1/records", tags=["Canonical Records"])

# Defense-in-depth: whitelist of fragments allowed in dynamic WHERE clauses.
# All filter columns are hardcoded in endpoint logic — this assertion catches
# regressions if a future change introduces an unsafe column reference.
_ALLOWED_WHERE_FRAGMENTS = frozenset({
    "tenant_id = :tid",
    "traceability_lot_code = :tlc",
    "event_type = :event_type",
    "status = :status",
    "source_system = :source_system",
    "event_timestamp >= :start_date",
    "event_timestamp <= :end_date",
})


# ---------------------------------------------------------------------------
# DB Session
# ---------------------------------------------------------------------------

def _get_db_session():
    try:
        from shared.database import SessionLocal
        db = SessionLocal()
        try:
            yield db
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            raise
        finally:
            db.close()
    except Exception as e:
        logger.warning("database_unavailable: %s", str(e))
        yield None


def _resolve_tenant(tenant_id: Optional[str], principal: IngestionPrincipal) -> str:
    tid = tenant_id or principal.tenant_id
    if not tid:
        raise HTTPException(status_code=400, detail="Tenant context required")
    validate_tenant_id(tid)
    return tid


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "",
    summary="List canonical traceability events",
    description="Search and filter canonical events with provenance metadata.",
)
async def list_records(
    tenant_id: Optional[str] = Query(None),
    tlc: Optional[str] = Query(None, description="Filter by traceability lot code"),
    event_type: Optional[str] = Query(None),
    status: Optional[str] = Query("active"),
    source_system: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
    principal: IngestionPrincipal = Depends(require_permission("records.read")),
    db_session=Depends(_get_db_session),
):
    if db_session is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    tid = _resolve_tenant(tenant_id, principal)
    from sqlalchemy import text

    where_clauses = ["tenant_id = :tid"]
    params: Dict[str, Any] = {"tid": tid, "lim": limit, "off": offset}

    if tlc:
        where_clauses.append("traceability_lot_code = :tlc")
        params["tlc"] = tlc
    if event_type:
        where_clauses.append("event_type = :event_type")
        params["event_type"] = event_type
    if status:
        where_clauses.append("status = :status")
        params["status"] = status
    if source_system:
        where_clauses.append("source_system = :source_system")
        params["source_system"] = source_system
    if start_date:
        where_clauses.append("event_timestamp >= :start_date")
        params["start_date"] = start_date
    if end_date:
        where_clauses.append("event_timestamp <= :end_date")
        params["end_date"] = end_date

    assert all(c in _ALLOWED_WHERE_FRAGMENTS for c in where_clauses), (
        f"Unexpected WHERE fragment in canonical query: {where_clauses}"
    )
    where = " AND ".join(where_clauses)

    # WHERE clause is built from _ALLOWED_WHERE_FRAGMENTS only (asserted above)
    count_row = db_session.execute(
        text("SELECT COUNT(*) FROM fsma.traceability_events WHERE " + where),
        params,
    ).fetchone()
    total = count_row[0] if count_row else 0

    rows = db_session.execute(
        text(
            "SELECT event_id, event_type, traceability_lot_code,"
            " product_reference, quantity, unit_of_measure,"
            " from_facility_reference, to_facility_reference,"
            " event_timestamp, source_system, status,"
            " confidence_score, schema_version, created_at"
            " FROM fsma.traceability_events"
            " WHERE " + where +
            " ORDER BY event_timestamp DESC"
            " LIMIT :lim OFFSET :off"
        ),
        params,
    ).fetchall()

    events = [
        {
            "event_id": str(r[0]),
            "event_type": r[1],
            "traceability_lot_code": r[2],
            "product_reference": r[3],
            "quantity": float(r[4]) if r[4] else 0,
            "unit_of_measure": r[5],
            "from_facility_reference": r[6],
            "to_facility_reference": r[7],
            "event_timestamp": r[8].isoformat() if r[8] else None,
            "source_system": r[9],
            "status": r[10],
            "confidence_score": float(r[11]) if r[11] else 1.0,
            "schema_version": r[12],
            "created_at": r[13].isoformat() if r[13] else None,
        }
        for r in rows
    ]
    return {"tenant_id": tid, "events": events, "total": total}


@router.get(
    "/ingestion-runs",
    summary="List ingestion runs",
)
async def list_ingestion_runs(
    tenant_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
    principal: IngestionPrincipal = Depends(require_permission("records.read")),
    db_session=Depends(_get_db_session),
):
    if db_session is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    tid = _resolve_tenant(tenant_id, principal)
    from sqlalchemy import text

    where_parts = ["tenant_id = :tid"]
    params: Dict[str, Any] = {"tid": tid, "lim": limit}
    if status:
        where_parts.append("status = :status")
        params["status"] = status

    assert all(c in _ALLOWED_WHERE_FRAGMENTS for c in where_parts), (
        f"Unexpected WHERE fragment in ingestion-runs query: {where_parts}"
    )
    where = " AND ".join(where_parts)

    rows = db_session.execute(
        text(
            "SELECT id, source_system, source_file_name, record_count,"
            " accepted_count, rejected_count, status, mapper_version,"
            " initiated_by, started_at, completed_at"
            " FROM fsma.ingestion_runs"
            " WHERE " + where +
            " ORDER BY started_at DESC"
            " LIMIT :lim"
        ),
        params,
    ).fetchall()

    runs = [
        {
            "id": str(r[0]),
            "source_system": r[1],
            "source_file_name": r[2],
            "record_count": r[3],
            "accepted_count": r[4],
            "rejected_count": r[5],
            "status": r[6],
            "mapper_version": r[7],
            "initiated_by": r[8],
            "started_at": r[9].isoformat() if r[9] else None,
            "completed_at": r[10].isoformat() if r[10] else None,
        }
        for r in rows
    ]
    return {"tenant_id": tid, "runs": runs, "total": len(runs)}


@router.get(
    "/ingestion-runs/{run_id}",
    summary="Get ingestion run detail",
)
async def get_ingestion_run(
    run_id: str,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("records.read")),
    db_session=Depends(_get_db_session),
):
    if db_session is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    tid = _resolve_tenant(tenant_id, principal)
    from sqlalchemy import text

    row = db_session.execute(
        text("""
            SELECT id, source_system, source_file_name, source_file_hash,
                   source_file_size, record_count, accepted_count, rejected_count,
                   status, mapper_version, schema_version, initiated_by,
                   started_at, completed_at, errors
            FROM fsma.ingestion_runs
            WHERE tenant_id = :tid AND id = :rid
        """),
        {"tid": tid, "rid": run_id},
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Ingestion run not found")

    return {
        "id": str(row[0]),
        "source_system": row[1],
        "source_file_name": row[2],
        "source_file_hash": row[3],
        "source_file_size": row[4],
        "record_count": row[5],
        "accepted_count": row[6],
        "rejected_count": row[7],
        "status": row[8],
        "mapper_version": row[9],
        "schema_version": row[10],
        "initiated_by": row[11],
        "started_at": row[12].isoformat() if row[12] else None,
        "completed_at": row[13].isoformat() if row[13] else None,
        "errors": row[14] if isinstance(row[14], list) else json.loads(row[14] or "[]"),
    }


@router.get(
    "/{event_id}",
    summary="Get canonical record with full provenance",
    description=(
        "Returns the complete canonical event including raw payload, normalized payload, "
        "provenance metadata, rule evaluations, and amendment chain."
    ),
)
async def get_record(
    event_id: str,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("records.read")),
    db_session=Depends(_get_db_session),
):
    if db_session is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    tid = _resolve_tenant(tenant_id, principal)
    from shared.canonical_persistence import CanonicalEventStore
    store = CanonicalEventStore(db_session, dual_write=False)
    event = store.get_event(tid, event_id)

    if not event:
        raise HTTPException(status_code=404, detail="Record not found")

    # Enrich with rule evaluations
    from sqlalchemy import text
    eval_rows = db_session.execute(
        text("""
            SELECT e.result, e.why_failed, r.title, r.severity,
                   r.citation_reference, r.remediation_suggestion, r.category
            FROM fsma.rule_evaluations e
            JOIN fsma.rule_definitions r ON r.rule_id = e.rule_id
            WHERE e.tenant_id = :tid AND e.event_id = :eid
            ORDER BY r.severity DESC
        """),
        {"tid": tid, "eid": event_id},
    ).fetchall()

    event["rule_evaluations"] = [
        {
            "result": r[0],
            "why_failed": r[1],
            "rule_title": r[2],
            "severity": r[3],
            "citation_reference": r[4],
            "remediation_suggestion": r[5],
            "category": r[6],
        }
        for r in eval_rows
    ]

    # Enrich with exception cases
    exc_rows = db_session.execute(
        text("""
            SELECT case_id, severity, status, recommended_remediation, owner_user_id, due_date
            FROM fsma.exception_cases
            WHERE tenant_id = :tid AND :eid = ANY(linked_event_ids)
        """),
        {"tid": tid, "eid": event_id},
    ).fetchall()

    event["exception_cases"] = [
        {
            "case_id": str(r[0]),
            "severity": r[1],
            "status": r[2],
            "recommended_remediation": r[3],
            "owner_user_id": r[4],
            "due_date": r[5].isoformat() if r[5] else None,
        }
        for r in exc_rows
    ]

    # Amendment chain
    if event.get("supersedes_event_id"):
        event["amendment_chain"] = _get_amendment_chain(db_session, tid, event_id)

    return event


@router.get(
    "/{event_id}/history",
    summary="Get amendment chain for a record",
)
async def get_record_history(
    event_id: str,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("records.read")),
    db_session=Depends(_get_db_session),
):
    if db_session is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    tid = _resolve_tenant(tenant_id, principal)
    chain = _get_amendment_chain(db_session, tid, event_id)
    return {"event_id": event_id, "amendment_chain": chain}


def _get_amendment_chain(db_session, tenant_id: str, event_id: str) -> List[Dict]:
    """Walk the amendment chain (supersedes_event_id links) in both directions."""
    from sqlalchemy import text

    # Find all versions: predecessors and successors
    chain = []

    # Walk backward (this event supersedes what?)
    current_id = event_id
    for _ in range(50):  # safety limit
        row = db_session.execute(
            text("""
                SELECT event_id, supersedes_event_id, event_type, status,
                       created_at, amended_at
                FROM fsma.traceability_events
                WHERE tenant_id = :tid AND event_id = :eid
            """),
            {"tid": tenant_id, "eid": current_id},
        ).fetchone()
        if not row or not row[1]:
            break
        chain.insert(0, {
            "event_id": str(row[1]),
            "superseded_by": str(row[0]),
            "status": "superseded",
        })
        current_id = str(row[1])

    # Walk forward (what supersedes this event?)
    current_id = event_id
    for _ in range(50):
        row = db_session.execute(
            text("""
                SELECT event_id, status, created_at
                FROM fsma.traceability_events
                WHERE tenant_id = :tid AND supersedes_event_id = :eid
            """),
            {"tid": tenant_id, "eid": current_id},
        ).fetchone()
        if not row:
            break
        chain.append({
            "event_id": str(row[0]),
            "supersedes": current_id,
            "status": row[1],
            "created_at": row[2].isoformat() if row[2] else None,
        })
        current_id = str(row[0])

    return chain
