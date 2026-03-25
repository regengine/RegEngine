from __future__ import annotations

from typing import Any, Optional
from urllib.parse import quote
from uuid import UUID

import httpx
import structlog
from shared.resilient_http import resilient_client
from fastapi import APIRouter, Depends, HTTPException, Request
from shared.metrics_auth import require_metrics_key
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .config import settings
from .query_planner import QueryPlan, parse_query
from shared.auth import APIKey, require_api_key
from shared.api_key_store import APIKeyResponse
from shared.funnel_events import emit_funnel_event
from shared.permissions import has_permission

logger = structlog.get_logger("nlp.test")
router = APIRouter()


class TraceabilityQueryRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=500)
    limit: int = Field(default=50, ge=1, le=200)
    starting_after: Optional[str] = Field(default=None, max_length=128)


class QueryEvidence(BaseModel):
    endpoint: str
    params: dict[str, Any] = Field(default_factory=dict)
    result_count: int = 0
    next_cursor: Optional[str] = None


class TraceabilityQueryResponse(BaseModel):
    intent: str
    filters: dict[str, Any]
    answer: str
    results: list[dict[str, Any]]
    evidence: list[QueryEvidence]
    confidence: float
    warnings: list[str] = Field(default_factory=list)


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/metrics", dependencies=[Depends(require_metrics_key)])
def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.post(
    "/query/traceability",
    response_model=TraceabilityQueryResponse,
    summary="Natural language traceability query",
)
async def query_traceability(
    payload: TraceabilityQueryRequest,
    request: Request,
    api_key: APIKey | APIKeyResponse = Depends(require_api_key),
) -> TraceabilityQueryResponse:
    scopes = list(getattr(api_key, "scopes", []) or [])
    if not has_permission(scopes, "graph.query"):
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions: requires 'graph.query'",
        )

    tenant_id = _resolve_tenant_id(api_key, request)
    plan = parse_query(
        payload.query,
        limit=payload.limit,
        starting_after=payload.starting_after,
    )

    results, evidence, answer = await _execute_query_plan(
        request=request,
        tenant_id=tenant_id,
        plan=plan,
    )

    emit_funnel_event(
        tenant_id=tenant_id,
        event_name="first_nlp_query",
        metadata={
            "intent": plan.intent,
            "confidence": plan.confidence,
        },
    )

    filters = plan.model_dump(
        exclude={"intent", "warnings", "confidence"},
        exclude_none=True,
    )

    return TraceabilityQueryResponse(
        intent=plan.intent,
        filters=filters,
        answer=answer,
        results=results,
        evidence=evidence,
        confidence=plan.confidence,
        warnings=plan.warnings,
    )


def _resolve_tenant_id(
    api_key: APIKey | APIKeyResponse,
    request: Request,
) -> str:
    candidates: list[Optional[str]] = [
        getattr(api_key, "tenant_id", None),
        request.headers.get("X-Tenant-ID"),
        request.headers.get("X-RegEngine-Tenant-ID"),
        request.query_params.get("tenant_id"),
    ]

    for candidate in candidates:
        if not candidate:
            continue
        try:
            return str(UUID(str(candidate)))
        except ValueError:
            continue

    raise HTTPException(
        status_code=401,
        detail="Tenant context not found on API key or request",
    )


async def _execute_query_plan(
    *,
    request: Request,
    tenant_id: str,
    plan: QueryPlan,
) -> tuple[list[dict[str, Any]], list[QueryEvidence], str]:
    if plan.intent == "trace_forward":
        if not plan.tlc:
            return [], [], "No lot code was detected for downstream tracing."
        endpoint = f"/api/v1/fsma/traceability/trace/forward/{quote(plan.tlc)}"
        payload = await _graph_get(request, tenant_id, endpoint, params={})
        facilities = payload.get("facilities", [])
        downstream_lots = payload.get("downstream_lots", [])
        answer = (
            f"Found {len(facilities)} downstream facilities and "
            f"{len(downstream_lots)} downstream lots for {plan.tlc}."
        )
        return [payload], [QueryEvidence(endpoint=endpoint, result_count=1)], answer

    if plan.intent == "trace_backward":
        if not plan.tlc:
            return [], [], "No lot code was detected for source tracing."
        endpoint = f"/api/v1/fsma/traceability/trace/backward/{quote(plan.tlc)}"
        payload = await _graph_get(request, tenant_id, endpoint, params={})
        facilities = payload.get("facilities", [])
        source_lots = payload.get("source_lots", [])
        answer = (
            f"Found {len(source_lots)} source lots across "
            f"{len(facilities)} facilities for {plan.tlc}."
        )
        return [payload], [QueryEvidence(endpoint=endpoint, result_count=1)], answer

    if plan.intent == "lot_timeline":
        if not plan.tlc:
            return [], [], "No lot code was detected for timeline lookup."
        endpoint = f"/api/v1/fsma/traceability/timeline/{quote(plan.tlc)}"
        payload = await _graph_get(request, tenant_id, endpoint, params={})
        events = payload.get("events", [])
        answer = f"Found {len(events)} events in the timeline for {plan.tlc}."
        return events, [QueryEvidence(endpoint=endpoint, result_count=len(events))], answer

    if plan.intent == "compliance_gaps":
        endpoint = "/api/v1/fsma/compliance/gaps"
        payload = await _graph_get(request, tenant_id, endpoint, params={})
        gaps = payload.get("events_with_gaps", [])
        answer = f"Found {len(gaps)} events with missing KDEs."
        return gaps, [QueryEvidence(endpoint=endpoint, result_count=len(gaps))], answer

    if plan.intent == "orphan_lots":
        endpoint = "/api/v1/fsma/compliance/gaps/orphans"
        params = {"days_stagnant": plan.days_stagnant or 30}
        payload = await _graph_get(request, tenant_id, endpoint, params=params)
        orphans = payload.get("orphans", [])
        answer = (
            f"Found {len(orphans)} orphaned lots with at least "
            f"{params['days_stagnant']} stagnant days."
        )
        return orphans, [QueryEvidence(endpoint=endpoint, params=params, result_count=len(orphans))], answer

    # Default: events_search
    endpoint = "/api/v1/fsma/traceability/search/events"
    params = {
        "start_date": plan.start_date,
        "end_date": plan.end_date,
        "product_contains": plan.product_contains,
        "facility_contains": plan.facility_contains,
        "cte_type": plan.cte_type,
        "limit": plan.limit,
        "starting_after": plan.starting_after,
    }
    params = {k: v for k, v in params.items() if v is not None}

    payload = await _graph_get(request, tenant_id, endpoint, params=params)
    events = payload.get("events", [])
    count = int(payload.get("count", len(events)))
    next_cursor = payload.get("next_cursor")

    if count:
        answer = f"Found {count} matching traceability events."
    else:
        answer = "No matching traceability events were found for the requested filters."

    evidence = [
        QueryEvidence(
            endpoint=endpoint,
            params=params,
            result_count=count,
            next_cursor=next_cursor,
        )
    ]
    return events, evidence, answer


async def _graph_get(
    request: Request,
    tenant_id: str,
    endpoint: str,
    params: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    api_key = request.headers.get("X-RegEngine-API-Key")
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    headers = {
        "X-RegEngine-API-Key": api_key,
    }
    request_id = request.headers.get("X-Request-ID")
    if request_id:
        headers["X-Request-ID"] = request_id

    # Always forward tenant context for downstream isolation
    headers["X-RegEngine-Tenant-ID"] = tenant_id

    internal_secret = settings.internal_service_secret
    if internal_secret:
        headers["X-RegEngine-Internal-Secret"] = internal_secret

    url = f"{settings.graph_service_url.rstrip('/')}{endpoint}"

    try:
        async with resilient_client(timeout=settings.graph_request_timeout_s, circuit_name="graph-service") as client:
            response = await client.get(url, headers=headers, params=params)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Graph service request failed: {exc}",
        ) from exc

    if response.status_code >= 500:
        raise HTTPException(
            status_code=502,
            detail=f"Graph service error ({response.status_code}): {response.text[:500]}",
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Graph service rejected request: {response.text[:500]}",
        )

    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail="Graph service returned non-JSON response",
        ) from exc
