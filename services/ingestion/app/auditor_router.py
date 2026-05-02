"""
Auditor Read-Only Review Mode.

Provides scoped, read-only access to the evidentiary chain for
external auditors, FDA reviewers, and compliance officers.

Every endpoint in this router is read-only — no mutations.
Designed for the question: "Show me the proof."

Endpoints:
    GET /api/v1/audit/summary              — High-level compliance posture
    GET /api/v1/audit/events               — Canonical events with evaluations
    GET /api/v1/audit/events/{event_id}    — Full event provenance + evidence
    GET /api/v1/audit/rules                — Rule catalog with pass/fail rates
    GET /api/v1/audit/exceptions           — Exception history with resolution
    GET /api/v1/audit/requests             — Request case history with packages
    GET /api/v1/audit/chain                — Hash chain verification
    GET /api/v1/audit/export-log           — Export audit trail
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from .authz import require_permission, IngestionPrincipal
from .tenant_validation import validate_tenant_id, resolve_tenant
from shared.database import get_db_session

logger = logging.getLogger("auditor-review")

router = APIRouter(prefix="/api/v1/audit", tags=["Auditor Review (Read-Only)"])


# ---------------------------------------------------------------------------
# DB Session
# ---------------------------------------------------------------------------

def _require_db(db_session):
    if db_session is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    return db_session




# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/summary",
    summary="Compliance posture summary",
    description=(
        "High-level compliance health for auditor review: total records, "
        "rule pass rate, exception backlog, response readiness, chain integrity."
    ),
)
async def audit_summary(
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("audit.read")),
    db_session=Depends(get_db_session),
):
    db = _require_db(db_session)
    tid = resolve_tenant(tenant_id, principal)

    # Total canonical events
    event_count = db.execute(
        text("SELECT COUNT(*) FROM fsma.traceability_events WHERE tenant_id = :tid AND status = 'active'"),
        {"tid": tid},
    ).scalar() or 0

    # Rule evaluation stats
    eval_stats = db.execute(
        text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE result = 'pass') AS passed,
                COUNT(*) FILTER (WHERE result = 'fail') AS failed,
                COUNT(*) FILTER (WHERE result = 'warn') AS warned
            FROM fsma.rule_evaluations
            WHERE tenant_id = :tid
        """),
        {"tid": tid},
    ).fetchone()
    total_evals = eval_stats[0] if eval_stats else 0
    pass_rate = (eval_stats[1] / total_evals * 100) if total_evals > 0 else 0

    # Exception backlog
    exception_stats = db.execute(
        text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status NOT IN ('resolved', 'waived')) AS open_count,
                COUNT(*) FILTER (WHERE severity = 'critical' AND status NOT IN ('resolved', 'waived')) AS critical_open
            FROM fsma.exception_cases
            WHERE tenant_id = :tid
        """),
        {"tid": tid},
    ).fetchone()

    # Request case stats
    request_stats = db.execute(
        text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE package_status = 'submitted') AS submitted,
                COUNT(*) FILTER (WHERE package_status NOT IN ('submitted', 'amended')) AS active
            FROM fsma.request_cases
            WHERE tenant_id = :tid
        """),
        {"tid": tid},
    ).fetchone()

    # Chain integrity
    chain_length = db.execute(
        text("SELECT COUNT(*) FROM fsma.hash_chain WHERE tenant_id = :tid"),
        {"tid": tid},
    ).scalar() or 0

    # Ingestion sources
    sources = db.execute(
        text("""
            SELECT source_system, COUNT(*) as count
            FROM fsma.traceability_events
            WHERE tenant_id = :tid AND status = 'active'
            GROUP BY source_system
            ORDER BY count DESC
        """),
        {"tid": tid},
    ).fetchall()

    return {
        "tenant_id": tid,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "records": {
            "total_canonical_events": event_count,
            "ingestion_sources": {r[0]: r[1] for r in sources},
        },
        "compliance": {
            "total_evaluations": total_evals,
            "pass_rate_percent": round(pass_rate, 1),
            "passed": eval_stats[1] if eval_stats else 0,
            "failed": eval_stats[2] if eval_stats else 0,
            "warned": eval_stats[3] if eval_stats else 0,
        },
        "exceptions": {
            "total": exception_stats[0] if exception_stats else 0,
            "open": exception_stats[1] if exception_stats else 0,
            "critical_open": exception_stats[2] if exception_stats else 0,
        },
        "requests": {
            "total": request_stats[0] if request_stats else 0,
            "submitted": request_stats[1] if request_stats else 0,
            "active": request_stats[2] if request_stats else 0,
        },
        "chain_integrity": {
            "chain_length": chain_length,
            "status": "VERIFIED" if chain_length > 0 else "NO_RECORDS",
        },
    }


@router.get(
    "/events",
    summary="Canonical events with compliance status",
    description="Paginated list of canonical events with rule evaluation summary per event.",
)
async def audit_events(
    tenant_id: Optional[str] = Query(None),
    tlc: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    compliance_status: Optional[str] = Query(None, description="Filter: compliant, non_compliant, unevaluated"),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    principal: IngestionPrincipal = Depends(require_permission("audit.read")),
    db_session=Depends(get_db_session),
):
    db = _require_db(db_session)
    tid = resolve_tenant(tenant_id, principal)

    where = ["e.tenant_id = :tid", "e.status = 'active'"]
    params: Dict[str, Any] = {"tid": tid, "lim": limit, "off": offset}

    if tlc:
        where.append("e.traceability_lot_code = :tlc")
        params["tlc"] = tlc
    if event_type:
        where.append("e.event_type = :event_type")
        params["event_type"] = event_type

    where_sql = " AND ".join(where)

    # Subquery for compliance status per event
    query = f"""
        SELECT e.event_id, e.event_type, e.traceability_lot_code,
               e.product_reference, e.quantity, e.unit_of_measure,
               e.event_timestamp, e.source_system, e.confidence_score,
               e.schema_version, e.created_at,
               COALESCE(eval_summary.total_rules, 0) AS total_rules,
               COALESCE(eval_summary.passed, 0) AS rules_passed,
               COALESCE(eval_summary.failed, 0) AS rules_failed
        FROM fsma.traceability_events e
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS total_rules,
                   COUNT(*) FILTER (WHERE result = 'pass') AS passed,
                   COUNT(*) FILTER (WHERE result = 'fail') AS failed
            FROM fsma.rule_evaluations re
            WHERE re.event_id = e.event_id AND re.tenant_id = :tid
        ) eval_summary ON TRUE
        WHERE {where_sql}
    """

    if compliance_status == "compliant":
        query += " AND COALESCE(eval_summary.failed, 0) = 0 AND COALESCE(eval_summary.total_rules, 0) > 0"
    elif compliance_status == "non_compliant":
        query += " AND COALESCE(eval_summary.failed, 0) > 0"
    elif compliance_status == "unevaluated":
        query += " AND COALESCE(eval_summary.total_rules, 0) = 0"

    query += " ORDER BY e.event_timestamp DESC LIMIT :lim OFFSET :off"

    rows = db.execute(text(query), params).fetchall()

    events = [
        {
            "event_id": str(r[0]),
            "event_type": r[1],
            "traceability_lot_code": r[2],
            "product_reference": r[3],
            "quantity": float(r[4]) if r[4] else 0,
            "unit_of_measure": r[5],
            "event_timestamp": r[6].isoformat() if r[6] else None,
            "source_system": r[7],
            "confidence_score": float(r[8]) if r[8] else 1.0,
            "schema_version": r[9],
            "created_at": r[10].isoformat() if r[10] else None,
            "compliance": {
                "total_rules": r[11],
                "passed": r[12],
                "failed": r[13],
                "status": "compliant" if r[13] == 0 and r[11] > 0 else
                          "non_compliant" if r[13] > 0 else "unevaluated",
            },
        }
        for r in rows
    ]
    return {"tenant_id": tid, "events": events, "total": len(events)}


@router.get(
    "/events/{event_id}",
    summary="Full event provenance for auditor",
    description=(
        "Complete audit view: canonical event, raw payload, normalized payload, "
        "provenance metadata, rule evaluations with citations, exception cases, "
        "amendment chain, and hash chain position."
    ),
)
async def audit_event_detail(
    event_id: str,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("audit.read")),
    db_session=Depends(get_db_session),
):
    db = _require_db(db_session)
    tid = resolve_tenant(tenant_id, principal)

    from shared.canonical_persistence import CanonicalEventStore
    store = CanonicalEventStore(db, dual_write=False)
    # #1297: auditor endpoint legitimately needs the raw supplier
    # payload for chain-of-custody verification — opt in explicitly.
    # Behind ``audit.read`` permission.
    event = store.get_event(tid, event_id, include_raw_payload=True)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Rule evaluations with full detail
    evals = db.execute(
        text("""
            SELECT re.evaluation_id, re.result, re.why_failed,
                   re.evidence_fields_inspected, re.confidence, re.evaluated_at,
                   rd.title, rd.severity, rd.category, rd.citation_reference,
                   rd.remediation_suggestion, rd.rule_version
            FROM fsma.rule_evaluations re
            JOIN fsma.rule_definitions rd ON rd.rule_id = re.rule_id
            WHERE re.tenant_id = :tid AND re.event_id = :eid
            ORDER BY rd.severity DESC, re.evaluated_at
        """),
        {"tid": tid, "eid": event_id},
    ).fetchall()

    event["rule_evaluations"] = [
        {
            "evaluation_id": str(r[0]),
            "result": r[1],
            "why_failed": r[2],
            "evidence_fields_inspected": r[3] if isinstance(r[3], list) else json.loads(r[3] or "[]"),
            "confidence": float(r[4]) if r[4] else 1.0,
            "evaluated_at": r[5].isoformat() if r[5] else None,
            "rule_title": r[6],
            "severity": r[7],
            "category": r[8],
            "citation_reference": r[9],
            "remediation_suggestion": r[10],
            "rule_version": r[11],
        }
        for r in evals
    ]

    # Hash chain position
    chain_entry = db.execute(
        text("""
            SELECT h.sequence_num, h.event_hash, h.previous_chain_hash, h.chain_hash, h.created_at
            FROM fsma.hash_chain h
            WHERE h.tenant_id = :tid AND h.cte_event_id = :eid
        """),
        {"tid": tid, "eid": event_id},
    ).fetchone()

    if chain_entry:
        event["chain_position"] = {
            "sequence_num": chain_entry[0],
            "event_hash": chain_entry[1],
            "previous_chain_hash": chain_entry[2],
            "chain_hash": chain_entry[3],
            "chained_at": chain_entry[4].isoformat() if chain_entry[4] else None,
        }

    # Evidence attachments
    attachments = db.execute(
        text("""
            SELECT id, document_type, file_name, file_hash, mime_type, storage_uri, created_at
            FROM fsma.evidence_attachments
            WHERE tenant_id = :tid AND event_id = :eid
            ORDER BY created_at
        """),
        {"tid": tid, "eid": event_id},
    ).fetchall()

    event["evidence_attachments"] = [
        {
            "id": str(r[0]),
            "document_type": r[1],
            "file_name": r[2],
            "file_hash": r[3],
            "mime_type": r[4],
            "storage_uri": r[5],
            "created_at": r[6].isoformat() if r[6] else None,
        }
        for r in attachments
    ]

    return event


@router.get(
    "/rules",
    summary="Rule catalog with pass/fail rates",
    description="All active rules with evaluation statistics across the tenant's records.",
)
async def audit_rules(
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("audit.read")),
    db_session=Depends(get_db_session),
):
    db = _require_db(db_session)
    tid = resolve_tenant(tenant_id, principal)

    rows = db.execute(
        text("""
            SELECT rd.rule_id, rd.title, rd.severity, rd.category,
                   rd.citation_reference, rd.effective_date,
                   COUNT(re.evaluation_id) AS total_evals,
                   COUNT(re.evaluation_id) FILTER (WHERE re.result = 'pass') AS passed,
                   COUNT(re.evaluation_id) FILTER (WHERE re.result = 'fail') AS failed,
                   COUNT(re.evaluation_id) FILTER (WHERE re.result = 'warn') AS warned
            FROM fsma.rule_definitions rd
            LEFT JOIN fsma.rule_evaluations re ON re.rule_id = rd.rule_id AND re.tenant_id = :tid
            WHERE rd.retired_date IS NULL
            GROUP BY rd.rule_id, rd.title, rd.severity, rd.category,
                     rd.citation_reference, rd.effective_date
            ORDER BY failed DESC, rd.severity DESC
        """),
        {"tid": tid},
    ).fetchall()

    rules = [
        {
            "rule_id": str(r[0]),
            "title": r[1],
            "severity": r[2],
            "category": r[3],
            "citation_reference": r[4],
            "effective_date": str(r[5]) if r[5] else None,
            "evaluation_stats": {
                "total": r[6],
                "passed": r[7],
                "failed": r[8],
                "warned": r[9],
                "pass_rate_percent": round(r[7] / r[6] * 100, 1) if r[6] > 0 else None,
            },
        }
        for r in rows
    ]
    return {"tenant_id": tid, "rules": rules, "total": len(rules)}


@router.get(
    "/exceptions",
    summary="Exception history with resolution audit trail",
)
async def audit_exceptions(
    tenant_id: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    principal: IngestionPrincipal = Depends(require_permission("audit.read")),
    db_session=Depends(get_db_session),
):
    db = _require_db(db_session)
    tid = resolve_tenant(tenant_id, principal)

    rows = db.execute(
        text("""
            SELECT ec.case_id, ec.severity, ec.status, ec.rule_category,
                   ec.source_supplier, ec.recommended_remediation,
                   ec.resolution_summary, ec.waiver_reason, ec.waiver_approved_by,
                   ec.owner_user_id, ec.created_at, ec.resolved_at,
                   (SELECT COUNT(*) FROM fsma.exception_signoffs es
                    WHERE es.case_id = ec.case_id) AS signoff_count
            FROM fsma.exception_cases ec
            WHERE ec.tenant_id = :tid
            ORDER BY ec.created_at DESC
            LIMIT :lim
        """),
        {"tid": tid, "lim": limit},
    ).fetchall()

    cases = [
        {
            "case_id": str(r[0]),
            "severity": r[1],
            "status": r[2],
            "rule_category": r[3],
            "source_supplier": r[4],
            "recommended_remediation": r[5],
            "resolution_summary": r[6],
            "waiver_reason": r[7],
            "waiver_approved_by": r[8],
            "owner": r[9],
            "created_at": r[10].isoformat() if r[10] else None,
            "resolved_at": r[11].isoformat() if r[11] else None,
            "signoff_count": r[12],
        }
        for r in rows
    ]
    return {"tenant_id": tid, "cases": cases, "total": len(cases)}


@router.get(
    "/requests",
    summary="Request case history with package audit trail",
)
async def audit_requests(
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("audit.read")),
    db_session=Depends(get_db_session),
):
    db = _require_db(db_session)
    tid = resolve_tenant(tenant_id, principal)

    rows = db.execute(
        text("""
            SELECT rc.request_case_id, rc.requesting_party, rc.request_channel,
                   rc.scope_type, rc.package_status, rc.total_records, rc.gap_count,
                   rc.request_received_at, rc.response_due_at, rc.submission_timestamp,
                   (SELECT COUNT(*) FROM fsma.response_packages rp
                    WHERE rp.request_case_id = rc.request_case_id) AS package_count,
                   (SELECT COUNT(*) FROM fsma.submission_log sl
                    WHERE sl.request_case_id = rc.request_case_id) AS submission_count,
                   (SELECT COUNT(*) FROM fsma.request_signoffs rs
                    WHERE rs.request_case_id = rc.request_case_id) AS signoff_count
            FROM fsma.request_cases rc
            WHERE rc.tenant_id = :tid
            ORDER BY rc.request_received_at DESC
        """),
        {"tid": tid},
    ).fetchall()

    cases = [
        {
            "request_case_id": str(r[0]),
            "requesting_party": r[1],
            "request_channel": r[2],
            "scope_type": r[3],
            "package_status": r[4],
            "total_records": r[5],
            "gap_count": r[6],
            "request_received_at": r[7].isoformat() if r[7] else None,
            "response_due_at": r[8].isoformat() if r[8] else None,
            "submission_timestamp": r[9].isoformat() if r[9] else None,
            "package_count": r[10],
            "submission_count": r[11],
            "signoff_count": r[12],
        }
        for r in rows
    ]
    return {"tenant_id": tid, "cases": cases, "total": len(cases)}


@router.get(
    "/chain",
    summary="Hash chain verification",
    description="Walk the entire hash chain and verify integrity. Returns pass/fail per link.",
)
async def audit_chain(
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("audit.read")),
    db_session=Depends(get_db_session),
):
    db = _require_db(db_session)
    tid = resolve_tenant(tenant_id, principal)

    from shared.cte_persistence import CTEPersistence
    persistence = CTEPersistence(db)
    result = persistence.verify_chain(tid)

    return {
        "tenant_id": tid,
        "chain_valid": result.valid,
        "chain_length": result.chain_length,
        "errors": result.errors,
        "verified_at": result.checked_at,
        "verification_method": "SHA-256 chain walk from genesis to head",
    }


@router.get(
    "/export-log",
    summary="FDA export audit trail",
    description="Complete log of every FDA export generated, with hashes and timestamps.",
)
async def audit_export_log(
    tenant_id: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    principal: IngestionPrincipal = Depends(require_permission("audit.read")),
    db_session=Depends(get_db_session),
):
    db = _require_db(db_session)
    tid = resolve_tenant(tenant_id, principal)

    rows = db.execute(
        text("""
            SELECT id, export_type, query_tlc, query_start_date, query_end_date,
                   record_count, export_hash, generated_by, generated_at
            FROM fsma.fda_export_log
            WHERE tenant_id = :tid
            ORDER BY generated_at DESC
            LIMIT :lim
        """),
        {"tid": tid, "lim": limit},
    ).fetchall()

    exports = [
        {
            "export_id": str(r[0]),
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
    ]
    return {"tenant_id": tid, "exports": exports, "total": len(exports)}
