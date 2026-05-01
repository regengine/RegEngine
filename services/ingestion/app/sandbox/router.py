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

import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

import structlog
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text

from app.sandbox.csv_parser import (
    _collect_value_normalizations,
    _normalize_for_rules,
    _parse_csv_to_events,
)
from app.sandbox.evaluators import (
    _evaluate_event_stateless,
    _evaluate_relational_in_memory,
)
from app.sandbox.models import (
    EventEvaluationResponse,
    NormalizationAction,
    RuleResultResponse,
    SandboxRequest,
    SandboxResponse,
    SandboxShareRequest,
    SandboxShareResponse,
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

logger = structlog.get_logger("sandbox")

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
    all_normalizations: List[Dict[str, str]] = []

    if payload.csv:
        # Enforce sandbox-specific payload size limit (2MB)
        if len(payload.csv) > 2_000_000:
            raise HTTPException(
                status_code=413,
                detail="CSV text too large for sandbox (max 2MB). Contact us for unlimited evaluation.",
            )
        try:
            raw_events = _parse_csv_to_events(
                payload.csv,
                erp_preset=payload.erp_preset,
                track_normalizations=True,
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"CSV parsing error: {str(e)}")
        if not raw_events:
            raise HTTPException(status_code=400, detail="No valid events found in CSV. Ensure 'cte_type' column exists.")

        # Extract header-level normalizations tracked during parsing
        all_normalizations = raw_events[0].pop("__normalizations__", [])

    elif payload.events:
        for ev in payload.events:
            raw_events.append(ev.model_dump())
    else:
        raise HTTPException(status_code=400, detail="Provide either 'events' (JSON) or 'csv' (raw CSV text)")

    # Cap at 500 events per request
    if len(raw_events) > 500:
        raise HTTPException(
            status_code=400,
            detail=f"Your file has {len(raw_events)} events. Sandbox evaluates up to 500. Contact us for unlimited evaluation.",
        )

    # Detect duplicate lot codes within same CTE type
    dup_warnings_by_index = _detect_duplicate_lots(raw_events)
    all_duplicate_warnings: List[str] = []
    for idx in sorted(dup_warnings_by_index):
        all_duplicate_warnings.extend(dup_warnings_by_index[idx])

    # Normalize all events first (needed for relational checks)
    all_canonical: List[Dict[str, Any]] = []
    for raw_event in raw_events:
        all_canonical.append(_normalize_for_rules(raw_event))

    # Collect value-level normalizations (UOM, CTE type) by diffing raw vs canonical
    all_normalizations.extend(_collect_value_normalizations(raw_events, all_canonical))

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
        for error in kde_errors:
            all_blocking_reasons.append(
                f"Event {i+1} ({raw_event.get('cte_type', '?')}): {error}"
            )

        # Step 2: Stateless per-event rules evaluation
        summary = _evaluate_event_stateless(
            canonical, include_custom=payload.include_custom_rules,
        )

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

        is_compliant = len(kde_errors) == 0 and summary.compliant is True
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
        normalizations=[
            NormalizationAction(**n) for n in all_normalizations
        ],
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


# ---------------------------------------------------------------------------
# Share endpoints
# ---------------------------------------------------------------------------

# In-memory share rate limiter (10/hour per IP)
_share_buckets: Dict[str, list] = {}
_SHARE_RATE_LIMIT = 10
_SHARE_WINDOW = 3600


@router.post(
    "/share",
    response_model=SandboxShareResponse,
    summary="Create a shareable link for sandbox results",
)
async def sandbox_share(payload: SandboxShareRequest, request: Request) -> SandboxShareResponse:
    """Store evaluation results and return a shareable URL."""
    client_ip = request.client.host if request.client else "unknown"

    # Rate limit shares (10/hour per IP)
    now = datetime.now(timezone.utc).timestamp()
    bucket = _share_buckets.setdefault(client_ip, [])
    bucket[:] = [t for t in bucket if now - t < _SHARE_WINDOW]
    if len(bucket) >= _SHARE_RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Share rate limit exceeded. Try again later.")
    bucket.append(now)

    share_id = secrets.token_urlsafe(12)
    ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()[:16]
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)

    try:
        from shared.database import get_db
        with get_db() as db:
            db.execute(
                text(
                    "INSERT INTO sandbox_shares (id, csv_text, result_json, ip_hash, expires_at) "
                    "VALUES (:id, :csv, :result, :ip_hash, :expires_at)"
                ),
                {
                    "id": share_id,
                    "csv": payload.csv,
                    "result": payload.result.model_dump_json(),
                    "ip_hash": ip_hash,
                    "expires_at": expires_at,
                },
            )
            db.commit()
    except Exception as e:
        logger.error("sandbox_share_error", error=str(e))
        raise HTTPException(status_code=503, detail="Sharing is temporarily unavailable.")

    return SandboxShareResponse(
        share_id=share_id,
        share_url=f"/sandbox/results/{share_id}?utm_source=sandbox_share&utm_medium=link",
        expires_at=expires_at.isoformat(),
    )


@router.get(
    "/share/{share_id}",
    response_model=SandboxResponse,
    summary="Retrieve shared sandbox results",
)
async def sandbox_share_get(share_id: str) -> SandboxResponse:
    """Retrieve shared evaluation results by ID."""
    if len(share_id) > 20:
        raise HTTPException(status_code=400, detail="Invalid share ID")

    try:
        from shared.database import get_db
        with get_db() as db:
            row = db.execute(
                text(
                    "UPDATE sandbox_shares SET view_count = view_count + 1 "
                    "WHERE id = :id AND expires_at > now() "
                    "RETURNING result_json"
                ),
                {"id": share_id},
            ).fetchone()
            db.commit()
    except Exception as e:
        logger.error("sandbox_share_get_error", error=str(e))
        raise HTTPException(status_code=503, detail="Share retrieval temporarily unavailable.")

    if not row:
        raise HTTPException(status_code=404, detail="Shared result not found or expired.")

    import json
    result_data = row[0] if isinstance(row[0], dict) else json.loads(row[0])
    return SandboxResponse(**result_data)
