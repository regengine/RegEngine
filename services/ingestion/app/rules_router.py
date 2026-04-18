"""
Rule Evaluation Router.

Provides API endpoints for the versioned FSMA 204 compliance rules engine —
evaluate events, inspect rules, view evaluation history, and seed rule definitions.

Endpoints:
    GET    /api/v1/rules                           — List active rule definitions
    GET    /api/v1/rules/{rule_id}                  — Get rule detail
    POST   /api/v1/rules/evaluate                   — Evaluate event against rules
    POST   /api/v1/rules/evaluate-batch             — Evaluate multiple events
    GET    /api/v1/rules/evaluations/{event_id}     — Get evaluations for an event
    POST   /api/v1/rules/seed                       — Seed built-in rule definitions
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.authz import require_permission, IngestionPrincipal
from app.tenant_validation import validate_tenant_id, resolve_tenant
from shared.pagination import PaginationParams
from shared.database import get_db_session

# Backwards-compat alias: tests and older callers override this private name
# via ``app.dependency_overrides[_get_db_session]``. Keep it pointing at the
# canonical shared helper so dependency overrides work on either import path.
_get_db_session = get_db_session

logger = logging.getLogger("rules-router")

router = APIRouter(prefix="/api/v1/rules", tags=["Rules Engine"])


def _db_unavailable():
    raise HTTPException(status_code=503, detail="Database unavailable")


def _get_engine(db_session):
    if db_session is None:
        _db_unavailable()
    from shared.rules_engine import RulesEngine
    return RulesEngine(db_session)




# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------

class EvaluateEventRequest(BaseModel):
    """Event data to evaluate against compliance rules."""
    event_id: str
    event_type: str
    traceability_lot_code: str
    product_reference: Optional[str] = None
    quantity: Optional[float] = None
    unit_of_measure: Optional[str] = None
    from_facility_reference: Optional[str] = None
    to_facility_reference: Optional[str] = None
    from_entity_reference: Optional[str] = None
    to_entity_reference: Optional[str] = None
    transport_reference: Optional[str] = None
    kdes: Dict[str, Any] = Field(default_factory=dict)


class EvaluateBatchRequest(BaseModel):
    events: List[EvaluateEventRequest]


class EvaluationResponse(BaseModel):
    event_id: str
    compliant: Optional[bool]  # tri-state — None when no verdict (#1347, #1346)
    no_verdict_reason: Optional[str] = None
    total_rules: int
    passed: int
    failed: int
    warned: int
    errored: int = 0
    not_ftl_scoped: int = 0
    critical_failures: List[Dict[str, Any]] = Field(default_factory=list)
    results: List[Dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "",
    summary="List active rule definitions",
    description="Returns all non-retired compliance rules with citations and evaluation logic.",
)
async def list_rules(
    category: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    cte_type: Optional[str] = Query(None),
    pagination: PaginationParams = Depends(),
    principal: IngestionPrincipal = Depends(require_permission("rules.read")),
    db_session=Depends(get_db_session),
):
    try:
        engine = _get_engine(db_session)
        rules = engine.load_active_rules()
    except RuntimeError:
        _db_unavailable()

    # Optional filters
    if category:
        rules = [r for r in rules if r.category == category]
    if severity:
        rules = [r for r in rules if r.severity == severity]
    if cte_type:
        rules = engine.get_applicable_rules(cte_type, rules)

    total = len(rules)
    rules = rules[pagination.skip : pagination.skip + pagination.limit]

    return {
        "rules": [
            {
                "rule_id": r.rule_id,
                "rule_version": r.rule_version,
                "title": r.title,
                "description": r.description,
                "severity": r.severity,
                "category": r.category,
                "citation_reference": r.citation_reference,
                "applicability_conditions": r.applicability_conditions,
                "failure_reason_template": r.failure_reason_template,
                "remediation_suggestion": r.remediation_suggestion,
                "effective_date": str(r.effective_date) if r.effective_date else None,
            }
            for r in rules
        ],
        "total": total,
        "skip": pagination.skip,
        "limit": pagination.limit,
    }


@router.get(
    "/{rule_id}",
    summary="Get rule detail",
)
async def get_rule(
    rule_id: str,
    principal: IngestionPrincipal = Depends(require_permission("rules.read")),
    db_session=Depends(get_db_session),
):
    engine = _get_engine(db_session)
    rules = engine.load_active_rules()
    for r in rules:
        if r.rule_id == rule_id:
            return {
                "rule_id": r.rule_id,
                "rule_version": r.rule_version,
                "title": r.title,
                "description": r.description,
                "severity": r.severity,
                "category": r.category,
                "citation_reference": r.citation_reference,
                "applicability_conditions": r.applicability_conditions,
                "evaluation_logic": r.evaluation_logic,
                "failure_reason_template": r.failure_reason_template,
                "remediation_suggestion": r.remediation_suggestion,
                "effective_date": str(r.effective_date) if r.effective_date else None,
            }
    raise HTTPException(status_code=404, detail="Rule not found")


@router.post(
    "/evaluate",
    summary="Evaluate a single event against all applicable rules",
    description=(
        "Returns pass/fail/warn for each rule with human-readable explanations. "
        "Every failure includes citation, evidence fields inspected, and remediation suggestion."
    ),
    response_model=EvaluationResponse,
)
async def evaluate_event(
    body: EvaluateEventRequest,
    tenant_id: Optional[str] = Query(None),
    persist: bool = Query(True, description="Persist evaluation results to database"),
    principal: IngestionPrincipal = Depends(require_permission("rules.evaluate")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    try:
        engine = _get_engine(db_session)
        event_data = body.model_dump()
        summary = engine.evaluate_event(event_data, persist=persist, tenant_id=tid)
    except RuntimeError:
        _db_unavailable()

    return EvaluationResponse(
        event_id=body.event_id,
        compliant=summary.compliant,
        no_verdict_reason=summary.no_verdict_reason,
        total_rules=summary.total_rules,
        passed=summary.passed,
        failed=summary.failed,
        warned=summary.warned,
        errored=summary.errored,
        not_ftl_scoped=summary.not_ftl_scoped,
        critical_failures=[
            {
                "rule_id": f.rule_id,
                "rule_title": f.rule_title,
                "severity": f.severity,
                "why_failed": f.why_failed,
                "citation_reference": f.citation_reference,
                "remediation_suggestion": f.remediation_suggestion,
                "evidence": f.evidence_fields_inspected,
            }
            for f in summary.critical_failures
        ],
        results=[
            {
                "rule_id": r.rule_id,
                "rule_title": r.rule_title,
                "severity": r.severity,
                "result": r.result,
                "why_failed": r.why_failed,
                "citation_reference": r.citation_reference,
                "remediation_suggestion": r.remediation_suggestion,
                "evidence": r.evidence_fields_inspected,
                "category": r.category,
            }
            for r in summary.results
        ],
    )


@router.post(
    "/evaluate-batch",
    summary="Evaluate multiple events against all applicable rules",
)
async def evaluate_batch(
    body: EvaluateBatchRequest,
    tenant_id: Optional[str] = Query(None),
    persist: bool = Query(True),
    principal: IngestionPrincipal = Depends(require_permission("rules.evaluate")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    engine = _get_engine(db_session)

    events_data = [e.model_dump() for e in body.events]
    summaries = engine.evaluate_events_batch(events_data, tid, persist=persist)

    # #1347 / #1346 — compliant is tri-state. None is "no verdict" and
    # must not silently roll into the compliant count.
    return {
        "total_events": len(summaries),
        "compliant_count": sum(1 for s in summaries if s.compliant is True),
        "non_compliant_count": sum(1 for s in summaries if s.compliant is False),
        "no_verdict_count": sum(1 for s in summaries if s.compliant is None),
        "summaries": [
            {
                "event_id": s.event_id,
                "compliant": s.compliant,
                "no_verdict_reason": s.no_verdict_reason,
                "passed": s.passed,
                "failed": s.failed,
                "warned": s.warned,
                "errored": s.errored,
                "not_ftl_scoped": s.not_ftl_scoped,
                "critical_count": len(s.critical_failures),
            }
            for s in summaries
        ],
    }


@router.get(
    "/evaluations/{event_id}",
    summary="Get rule evaluations for an event",
)
async def get_event_evaluations(
    event_id: str,
    tenant_id: Optional[str] = Query(None),
    result_filter: Optional[str] = Query(None, alias="result"),
    principal: IngestionPrincipal = Depends(require_permission("rules.read")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    if db_session is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    from sqlalchemy import text
    query = """
        SELECT e.evaluation_id, e.rule_id, e.rule_version, e.result,
               e.why_failed, e.evidence_fields_inspected, e.confidence,
               e.evaluated_at, r.title, r.severity, r.category,
               r.citation_reference, r.remediation_suggestion
        FROM fsma.rule_evaluations e
        JOIN fsma.rule_definitions r ON r.rule_id = e.rule_id
        WHERE e.tenant_id = :tid AND e.event_id = :eid
    """
    params: Dict[str, Any] = {"tid": tid, "eid": event_id}
    if result_filter:
        query += " AND e.result = :result"
        params["result"] = result_filter
    query += " ORDER BY r.severity DESC, e.evaluated_at DESC"

    rows = db_session.execute(text(query), params).fetchall()
    evaluations = [
        {
            "evaluation_id": str(r[0]),
            "rule_id": str(r[1]),
            "rule_version": r[2],
            "result": r[3],
            "why_failed": r[4],
            "evidence_fields_inspected": r[5] if isinstance(r[5], list) else json.loads(r[5] or "[]"),
            "confidence": float(r[6]) if r[6] else 1.0,
            "evaluated_at": r[7].isoformat() if r[7] else None,
            "rule_title": r[8],
            "severity": r[9],
            "category": r[10],
            "citation_reference": r[11],
            "remediation_suggestion": r[12],
        }
        for r in rows
    ]
    return {"event_id": event_id, "evaluations": evaluations, "total": len(evaluations)}


@router.post(
    "/seed",
    summary="Seed built-in FSMA rule definitions",
    description="Idempotent — inserts only rules that don't already exist.",
)
async def seed_rules(
    principal: IngestionPrincipal = Depends(require_permission("rules.write")),
    db_session=Depends(get_db_session),
):
    if db_session is None:
        _db_unavailable()
    try:
        from shared.rules_engine import seed_rule_definitions
        count = seed_rule_definitions(db_session)
    except RuntimeError:
        _db_unavailable()
    return {"seeded": count, "status": "ok"}
