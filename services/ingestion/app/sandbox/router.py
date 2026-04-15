"""
Sandbox Evaluation Router.

Provides POST /api/v1/sandbox/evaluate — a stateless endpoint that accepts
raw CTE events (JSON or CSV), runs normalization + FSMA 204 rule evaluation,
and returns results WITHOUT persisting anything.

This powers the live demo on the marketing site, letting prospects drop their
own data and see RegEngine's validation in action.

No auth required. No data stored. Rate-limited to prevent abuse.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request

from app.sandbox.csv_parser import _normalize_for_rules, _parse_csv_to_events
from app.sandbox.evaluators import (
    _evaluate_event_stateless,
    _evaluate_relational_in_memory,
)
from app.sandbox.models import (
    EventEvaluationResponse,
    RuleResultResponse,
    SandboxRequest,
    SandboxResponse,
    SandboxTraceRequest,
    TraceGraphResponse,
)
from app.sandbox.rate_limiting import _check_sandbox_rate_limit
from app.sandbox.tracer import _trace_in_memory, sandbox_trace as _sandbox_trace_impl
from app.sandbox.validation import (
    _detect_duplicate_lots,
    _detect_entity_mismatches,
    _validate_kdes,
)

logger = logging.getLogger("sandbox")

router = APIRouter(prefix="/api/v1/sandbox", tags=["Sandbox"])


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/evaluate",
    response_model=SandboxResponse,
    summary="Evaluate traceability events (stateless sandbox)",
    description=(
        "Accept CTE events as JSON or CSV, run FSMA 204 KDE validation and "
        "rules evaluation, and return results. No data is persisted. "
        "No authentication required. Rate-limited to 30 requests/minute."
    ),
)
async def sandbox_evaluate(payload: SandboxRequest, request: Request) -> SandboxResponse:
    """Stateless evaluation of traceability events against FSMA 204 rules."""
    # Rate limit by IP
    client_ip = request.client.host if request.client else "unknown"
    _check_sandbox_rate_limit(client_ip)

    # Parse events from JSON or CSV
    raw_events: List[Dict[str, Any]] = []

    if payload.csv:
        try:
            raw_events = _parse_csv_to_events(payload.csv)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"CSV parsing error: {str(e)}")
        if not raw_events:
            raise HTTPException(status_code=400, detail="No valid events found in CSV. Ensure 'cte_type' column exists.")

    elif payload.events:
        for ev in payload.events:
            raw_events.append(ev.model_dump())
    else:
        raise HTTPException(status_code=400, detail="Provide either 'events' (JSON) or 'csv' (raw CSV text)")

    # Cap at 50 events per request
    if len(raw_events) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 events per sandbox request")

    # Detect duplicate lot codes within same CTE type
    dup_warnings_by_index = _detect_duplicate_lots(raw_events)
    all_duplicate_warnings: List[str] = []
    for idx in sorted(dup_warnings_by_index):
        all_duplicate_warnings.extend(dup_warnings_by_index[idx])

    # Normalize all events first (needed for relational checks)
    all_canonical: List[Dict[str, Any]] = []
    for raw_event in raw_events:
        all_canonical.append(_normalize_for_rules(raw_event))

    # Run cross-event relational validation (temporal order, identity, mass balance)
    relational_results = _evaluate_relational_in_memory(all_canonical)

    # Evaluate each event
    event_results: List[EventEvaluationResponse] = []
    total_kde_errors = 0
    total_rule_failures = 0
    compliant_count = 0
    all_blocking_reasons: List[str] = []

    for i, raw_event in enumerate(raw_events):
        canonical = all_canonical[i]

        # Step 1: KDE validation
        kde_errors = _validate_kdes(raw_event)
        total_kde_errors += len(kde_errors)

        # Step 2: Stateless per-event rules evaluation
        summary = _evaluate_event_stateless(canonical)

        # Step 3: Merge relational results for this event
        event_id = canonical.get("event_id", "")
        rel_results = relational_results.get(event_id, [])
        for rr in rel_results:
            summary.results.append(rr)
            summary.total_rules += 1
            if rr.result == "pass":
                summary.passed += 1
            elif rr.result == "fail":
                summary.failed += 1
                if rr.severity == "critical":
                    summary.critical_failures.append(rr)
            elif rr.result == "warn":
                summary.warned += 1
            else:
                summary.skipped += 1

        total_rule_failures += summary.failed

        # Build blocking defects list
        blocking = []
        for r in summary.results:
            if r.result == "fail" and r.severity == "critical":
                reason = r.why_failed or r.rule_title
                blocking.append(RuleResultResponse(
                    rule_title=r.rule_title,
                    severity=r.severity,
                    result=r.result,
                    why_failed=r.why_failed,
                    citation=r.citation_reference,
                    remediation=r.remediation_suggestion,
                    category=r.category,
                    evidence=r.evidence_fields_inspected or None,
                ))
                all_blocking_reasons.append(f"Event {i+1} ({raw_event.get('cte_type', '?')}): {reason}")

        # Inject duplicate lot warnings into kde_errors
        if i in dup_warnings_by_index:
            kde_errors.extend(dup_warnings_by_index[i])
            total_kde_errors += len(dup_warnings_by_index[i])

        is_compliant = len(kde_errors) == 0 and summary.compliant
        if is_compliant:
            compliant_count += 1

        event_results.append(EventEvaluationResponse(
            event_index=i,
            cte_type=raw_event.get("cte_type", "unknown"),
            traceability_lot_code=raw_event.get("traceability_lot_code", ""),
            product_description=raw_event.get("product_description", ""),
            kde_errors=kde_errors,
            rules_evaluated=summary.total_rules,
            rules_passed=summary.passed,
            rules_failed=summary.failed,
            rules_warned=summary.warned,
            compliant=is_compliant,
            blocking_defects=blocking,
            all_results=[
                RuleResultResponse(
                    rule_title=r.rule_title,
                    severity=r.severity,
                    result=r.result,
                    why_failed=r.why_failed,
                    citation=r.citation_reference,
                    remediation=r.remediation_suggestion,
                    category=r.category,
                    evidence=r.evidence_fields_inspected or None,
                )
                for r in summary.results
            ],
        ))

    # Deduplicate blocking reasons
    unique_blocking = list(dict.fromkeys(all_blocking_reasons))

    # Detect entity name mismatches across all events
    entity_warnings = _detect_entity_mismatches(raw_events)

    return SandboxResponse(
        total_events=len(raw_events),
        compliant_events=compliant_count,
        non_compliant_events=len(raw_events) - compliant_count,
        total_kde_errors=total_kde_errors,
        total_rule_failures=total_rule_failures,
        submission_blocked=len(unique_blocking) > 0,
        blocking_reasons=unique_blocking,
        duplicate_warnings=all_duplicate_warnings,
        entity_warnings=entity_warnings,
        events=event_results,
    )


@router.post(
    "/trace",
    response_model=TraceGraphResponse,
    summary="In-memory lot trace-back / trace-forward (stateless)",
    description=(
        "Accepts CSV + a seed TLC, traces upstream and/or downstream through "
        "the supply chain using BFS on lot code linkages. No data persisted. "
        "Returns a graph of nodes (events) and edges (linkages)."
    ),
)
async def sandbox_trace(payload: SandboxTraceRequest, request: Request) -> TraceGraphResponse:
    """Stateless in-memory lot tracing for the sandbox."""
    return await _sandbox_trace_impl(payload, request)
