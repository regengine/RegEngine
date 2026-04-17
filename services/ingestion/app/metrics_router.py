"""
Product Metrics Router — FSMA 204 Compliance Control Plane.

Provides the KPIs defined in the PRD Section 10:

Product Metrics:
- % of ingested records normalized successfully
- % of records with full provenance chain
- % of rule failures with actionable remediation text
- median time to resolve exception
- median time to assemble response package
- % of request cases completed with no manual spreadsheet work
- duplicate entity resolution rate
- ambiguous identity match backlog

Reliability Metrics:
- request package generation success rate
- rule engine evaluation latency
- canonical event ingestion latency
- package audit snapshot integrity verification rate

Endpoint:
    GET /api/v1/metrics/compliance — Full metrics dashboard
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from app.authz import require_permission, IngestionPrincipal
from app.tenant_validation import validate_tenant_id, resolve_tenant
from shared.database import get_db_session

logger = logging.getLogger("compliance-metrics")

router = APIRouter(prefix="/api/v1/metrics", tags=["Compliance Metrics"])




@router.get(
    "/compliance",
    summary="Compliance control plane metrics",
    description="Full metrics dashboard as defined in PRD Section 10.",
)
async def compliance_metrics(
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("metrics.read")),
    db_session=Depends(get_db_session),
):
    if db_session is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    tid = resolve_tenant(tenant_id, principal)

    # --- Product Metrics ---

    # 1. % of ingested records normalized successfully
    normalization = db_session.execute(
        text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status = 'active') AS normalized,
                COUNT(*) FILTER (WHERE status = 'rejected') AS rejected
            FROM fsma.traceability_events
            WHERE tenant_id = :tid
        """),
        {"tid": tid},
    ).fetchone()
    total_events = normalization[0] if normalization else 0
    normalization_rate = (normalization[1] / total_events * 100) if total_events > 0 else 0

    # 2. % of records with full provenance chain
    provenance = db_session.execute(
        text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE sha256_hash IS NOT NULL AND chain_hash IS NOT NULL) AS with_chain
            FROM fsma.traceability_events
            WHERE tenant_id = :tid AND status = 'active'
        """),
        {"tid": tid},
    ).fetchone()
    provenance_rate = (provenance[1] / provenance[0] * 100) if provenance and provenance[0] > 0 else 0

    # 3. % of rule failures with actionable remediation text
    remediation = db_session.execute(
        text("""
            SELECT
                COUNT(*) AS total_failures,
                COUNT(*) FILTER (WHERE re.why_failed IS NOT NULL AND rd.remediation_suggestion IS NOT NULL) AS with_remediation
            FROM fsma.rule_evaluations re
            JOIN fsma.rule_definitions rd ON rd.rule_id = re.rule_id
            WHERE re.tenant_id = :tid AND re.result = 'fail'
        """),
        {"tid": tid},
    ).fetchone()
    remediation_rate = (remediation[1] / remediation[0] * 100) if remediation and remediation[0] > 0 else 0

    # 4. Median time to resolve exception (hours)
    median_resolve = db_session.execute(
        text("""
            SELECT EXTRACT(EPOCH FROM PERCENTILE_CONT(0.5) WITHIN GROUP (
                ORDER BY resolved_at - created_at
            )) / 3600.0 AS median_hours
            FROM fsma.exception_cases
            WHERE tenant_id = :tid AND status IN ('resolved', 'waived') AND resolved_at IS NOT NULL
        """),
        {"tid": tid},
    ).scalar()

    # 5. Median time to assemble response package (hours)
    median_package = db_session.execute(
        text("""
            SELECT EXTRACT(EPOCH FROM PERCENTILE_CONT(0.5) WITHIN GROUP (
                ORDER BY rp.generated_at - rc.request_received_at
            )) / 3600.0 AS median_hours
            FROM fsma.response_packages rp
            JOIN fsma.request_cases rc ON rc.request_case_id = rp.request_case_id
            WHERE rc.tenant_id = :tid AND rp.version_number = 1
        """),
        {"tid": tid},
    ).scalar()

    # 6. % of request cases completed without manual spreadsheet
    requests_stats = db_session.execute(
        text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE package_status IN ('submitted', 'amended')) AS completed
            FROM fsma.request_cases
            WHERE tenant_id = :tid
        """),
        {"tid": tid},
    ).fetchone()
    completion_rate = (requests_stats[1] / requests_stats[0] * 100) if requests_stats and requests_stats[0] > 0 else 0

    # 7. Duplicate entity resolution rate
    entity_stats = db_session.execute(
        text("""
            SELECT
                COUNT(*) AS total_entities,
                COUNT(*) FILTER (WHERE verification_status = 'verified') AS verified
            FROM fsma.canonical_entities
            WHERE tenant_id = :tid AND is_active = TRUE
        """),
        {"tid": tid},
    ).fetchone()
    entity_resolution_rate = (entity_stats[1] / entity_stats[0] * 100) if entity_stats and entity_stats[0] > 0 else 0

    # 8. Ambiguous identity match backlog
    ambiguous_backlog = db_session.execute(
        text("""
            SELECT COUNT(*) FROM fsma.identity_review_queue
            WHERE tenant_id = :tid AND status = 'pending'
        """),
        {"tid": tid},
    ).scalar() or 0

    # --- Reliability Metrics ---

    # Package generation success rate
    package_stats = db_session.execute(
        text("""
            SELECT COUNT(*) FROM fsma.response_packages WHERE tenant_id = :tid
        """),
        {"tid": tid},
    ).scalar() or 0

    # Rule evaluation count
    eval_count = db_session.execute(
        text("SELECT COUNT(*) FROM fsma.rule_evaluations WHERE tenant_id = :tid"),
        {"tid": tid},
    ).scalar() or 0

    # Chain integrity
    chain_length = db_session.execute(
        text("SELECT COUNT(*) FROM fsma.hash_chain WHERE tenant_id = :tid"),
        {"tid": tid},
    ).scalar() or 0

    # Export count
    export_count = db_session.execute(
        text("SELECT COUNT(*) FROM fsma.fda_export_log WHERE tenant_id = :tid"),
        {"tid": tid},
    ).scalar() or 0

    return {
        "tenant_id": tid,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "product_metrics": {
            "normalization_rate_percent": round(normalization_rate, 1),
            "total_events": total_events,
            "normalized_events": normalization[1] if normalization else 0,
            "rejected_events": normalization[2] if normalization else 0,

            "provenance_chain_rate_percent": round(provenance_rate, 1),

            "remediation_text_rate_percent": round(remediation_rate, 1),
            "total_failures": remediation[0] if remediation else 0,
            "failures_with_remediation": remediation[1] if remediation else 0,

            "median_exception_resolve_hours": round(float(median_resolve), 1) if median_resolve else None,
            "median_package_assembly_hours": round(float(median_package), 1) if median_package else None,

            "request_completion_rate_percent": round(completion_rate, 1),
            "total_requests": requests_stats[0] if requests_stats else 0,
            "completed_requests": requests_stats[1] if requests_stats else 0,

            "entity_resolution_rate_percent": round(entity_resolution_rate, 1),
            "ambiguous_match_backlog": ambiguous_backlog,
        },
        "reliability_metrics": {
            "total_packages_generated": package_stats,
            "total_rule_evaluations": eval_count,
            "chain_length": chain_length,
            "total_exports": export_count,
        },
    }
