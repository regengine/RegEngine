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

import csv
import io
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.webhook_models import (
    REQUIRED_KDES_BY_CTE,
    WebhookCTEType,
)
from shared.rules_engine import (
    FSMA_RULE_SEEDS,
    RuleDefinition,
    RuleEvaluationResult,
    EvaluationSummary,
    _EVALUATORS,
    _get_nested_value,
)

logger = logging.getLogger("sandbox")

router = APIRouter(prefix="/api/v1/sandbox", tags=["Sandbox"])


# ---------------------------------------------------------------------------
# Rate Limiting (simple in-memory, per-IP)
# ---------------------------------------------------------------------------

_rate_buckets: Dict[str, list] = {}
_SANDBOX_RATE_LIMIT = 30  # requests per minute
_SANDBOX_WINDOW = 60


def _check_sandbox_rate_limit(client_ip: str) -> None:
    """Simple per-IP rate limit for sandbox endpoint."""
    now = datetime.now(timezone.utc).timestamp()
    bucket = _rate_buckets.setdefault(client_ip, [])
    # Prune old entries
    bucket[:] = [t for t in bucket if now - t < _SANDBOX_WINDOW]
    if len(bucket) >= _SANDBOX_RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Sandbox rate limit exceeded. Try again in a minute.",
        )
    bucket.append(now)


# ---------------------------------------------------------------------------
# In-Memory Rules (no DB needed)
# ---------------------------------------------------------------------------

def _build_rules_from_seeds() -> List[RuleDefinition]:
    """Build RuleDefinition objects from FSMA_RULE_SEEDS without touching the database."""
    rules = []
    for i, seed in enumerate(FSMA_RULE_SEEDS):
        rules.append(RuleDefinition(
            rule_id=f"sandbox-rule-{i:03d}",
            rule_version=1,
            title=seed["title"],
            description=seed.get("description"),
            severity=seed["severity"],
            category=seed["category"],
            applicability_conditions=seed.get("applicability_conditions", {}),
            citation_reference=seed.get("citation_reference"),
            effective_date=datetime.now(timezone.utc).date(),
            retired_date=None,
            evaluation_logic=seed["evaluation_logic"],
            failure_reason_template=seed["failure_reason_template"],
            remediation_suggestion=seed.get("remediation_suggestion"),
        ))
    return rules


_SANDBOX_RULES = _build_rules_from_seeds()


def _get_applicable_rules(event_type: str) -> List[RuleDefinition]:
    """Filter sandbox rules to those applicable to the given event type."""
    applicable = []
    for rule in _SANDBOX_RULES:
        cte_types = rule.applicability_conditions.get("cte_types", [])
        if not cte_types or event_type in cte_types or "all" in cte_types:
            applicable.append(rule)
    return applicable


def _evaluate_event_stateless(event_data: Dict[str, Any]) -> EvaluationSummary:
    """Evaluate an event against all applicable rules without any DB interaction."""
    event_type = event_data.get("event_type", "")
    event_id = event_data.get("event_id", str(uuid4()))

    applicable = _get_applicable_rules(event_type)
    summary = EvaluationSummary(
        event_id=event_id,
        total_rules=len(applicable),
    )

    for rule in applicable:
        logic = rule.evaluation_logic
        eval_type = logic.get("type", "field_presence")
        evaluator = _EVALUATORS.get(eval_type)

        if not evaluator:
            result = RuleEvaluationResult(
                rule_id=rule.rule_id,
                rule_version=rule.rule_version,
                rule_title=rule.title,
                severity=rule.severity,
                result="skip",
                why_failed=f"Unknown evaluation type: {eval_type}",
                category=rule.category,
            )
        else:
            try:
                result = evaluator(event_data, logic, rule)
            except Exception as e:
                result = RuleEvaluationResult(
                    rule_id=rule.rule_id,
                    rule_version=rule.rule_version,
                    rule_title=rule.title,
                    severity=rule.severity,
                    result="skip",
                    why_failed=f"Evaluation error: {str(e)}",
                    category=rule.category,
                )

        summary.results.append(result)
        if result.result == "pass":
            summary.passed += 1
        elif result.result == "fail":
            summary.failed += 1
            if result.severity == "critical":
                summary.critical_failures.append(result)
        elif result.result == "warn":
            summary.warned += 1
        else:
            summary.skipped += 1

    return summary


# ---------------------------------------------------------------------------
# CSV Parsing
# ---------------------------------------------------------------------------

# Map common CSV column headers to our internal field names
_CSV_COLUMN_MAP = {
    "cte_type": "cte_type",
    "event_type": "cte_type",
    "type": "cte_type",
    "traceability_lot_code": "traceability_lot_code",
    "tlc": "traceability_lot_code",
    "lot_code": "traceability_lot_code",
    "lot": "traceability_lot_code",
    "product_description": "product_description",
    "product": "product_description",
    "description": "product_description",
    "commodity": "product_description",
    "quantity": "quantity",
    "qty": "quantity",
    "unit_of_measure": "unit_of_measure",
    "unit": "unit_of_measure",
    "uom": "unit_of_measure",
    "location_gln": "location_gln",
    "gln": "location_gln",
    "location_name": "location_name",
    "location": "location_name",
    "facility": "location_name",
    "timestamp": "timestamp",
    "date": "timestamp",
    "event_date": "timestamp",
}

# Fields that go into kdes dict rather than top-level
_KDE_FIELDS = {
    "harvest_date", "cooling_date", "packing_date", "landing_date",
    "ship_date", "receive_date", "transformation_date",
    "ship_from_location", "ship_to_location", "ship_from_gln", "ship_to_gln",
    "receiving_location", "reference_document", "carrier",
    "harvester_business_name", "tlc_source_reference", "immediate_previous_source",
    "input_traceability_lot_codes", "temperature", "field_name",
}


def _parse_csv_to_events(csv_text: str) -> List[Dict[str, Any]]:
    """Parse CSV text into a list of event dicts matching our JSON format."""
    reader = csv.DictReader(io.StringIO(csv_text))
    events = []

    for row in reader:
        event: Dict[str, Any] = {"kdes": {}}
        for col, value in row.items():
            if not col or not value or not value.strip():
                continue
            col_lower = col.strip().lower().replace(" ", "_")
            mapped = _CSV_COLUMN_MAP.get(col_lower)

            if mapped:
                if mapped == "quantity":
                    try:
                        event[mapped] = float(value.strip())
                    except ValueError:
                        event[mapped] = value.strip()
                else:
                    event[mapped] = value.strip()
            elif col_lower in _KDE_FIELDS:
                event["kdes"][col_lower] = value.strip()
            else:
                # Unknown columns go into kdes
                event["kdes"][col_lower] = value.strip()

        # Default timestamp if missing
        if "timestamp" not in event:
            event["timestamp"] = datetime.now(timezone.utc).isoformat()

        if "cte_type" in event:
            events.append(event)

    return events


# ---------------------------------------------------------------------------
# Normalization (webhook event → canonical-like dict for rules engine)
# ---------------------------------------------------------------------------

def _normalize_for_rules(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a raw event dict into the canonical format expected by the rules engine.
    Maps webhook-style fields to canonical TraceabilityEvent field names.
    """
    kdes = dict(event.get("kdes", {}))
    event_type = event.get("cte_type", "")

    # Build facility references from available data
    from_facility = (
        event.get("location_gln")
        or kdes.get("ship_from_gln")
        or kdes.get("ship_from_location")
        or event.get("location_name")
    )
    to_facility = (
        kdes.get("ship_to_gln")
        or kdes.get("ship_to_location")
        or kdes.get("receiving_location")
    )

    if event_type == "shipping":
        from_facility = from_facility or event.get("location_name")
    elif event_type == "receiving":
        to_facility = to_facility or event.get("location_name") or event.get("location_gln")

    return {
        "event_id": str(uuid4()),
        "event_type": event_type,
        "traceability_lot_code": event.get("traceability_lot_code", ""),
        "product_reference": event.get("product_description", ""),
        "quantity": event.get("quantity"),
        "unit_of_measure": event.get("unit_of_measure", ""),
        "event_timestamp": event.get("timestamp", ""),
        "from_facility_reference": from_facility,
        "to_facility_reference": to_facility,
        "from_entity_reference": kdes.get("ship_from_entity") or kdes.get("harvester_business_name"),
        "to_entity_reference": kdes.get("ship_to_entity") or kdes.get("immediate_previous_source"),
        "transport_reference": kdes.get("carrier") or kdes.get("transport_reference"),
        "kdes": kdes,
    }


# ---------------------------------------------------------------------------
# KDE Validation (reused from webhook_router_v2 logic)
# ---------------------------------------------------------------------------

def _validate_kdes(event: Dict[str, Any]) -> List[str]:
    """Validate required KDEs for a raw event dict."""
    errors: List[str] = []
    cte_type_str = event.get("cte_type", "")

    try:
        cte_type = WebhookCTEType(cte_type_str)
    except ValueError:
        valid_types = [t.value for t in WebhookCTEType]
        return [f"Invalid CTE type '{cte_type_str}'. Valid types: {', '.join(valid_types)}"]

    required = REQUIRED_KDES_BY_CTE.get(cte_type, [])
    kdes = event.get("kdes", {})

    available = {
        "traceability_lot_code": event.get("traceability_lot_code"),
        "product_description": event.get("product_description"),
        "quantity": event.get("quantity"),
        "unit_of_measure": event.get("unit_of_measure"),
        "location_name": event.get("location_name"),
        "location_gln": event.get("location_gln"),
        **kdes,
    }

    for kde_name in required:
        val = available.get(kde_name)
        if val is None or (isinstance(val, str) and val.strip() == ""):
            errors.append(f"Missing required KDE '{kde_name}' for {cte_type_str} CTE")

    return errors


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class SandboxEvent(BaseModel):
    """A single event for sandbox evaluation."""
    cte_type: str = Field(..., description="CTE type (harvesting, shipping, receiving, etc.)")
    traceability_lot_code: str = Field(..., description="Traceability Lot Code")
    product_description: str = Field(default="", description="Product name")
    quantity: Optional[float] = Field(default=None, description="Quantity")
    unit_of_measure: str = Field(default="", description="Unit of measure")
    location_gln: Optional[str] = Field(default=None, description="GLN")
    location_name: Optional[str] = Field(default=None, description="Location name")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp",
    )
    kdes: Dict[str, Any] = Field(default_factory=dict, description="Additional KDEs")


class SandboxRequest(BaseModel):
    """Request body for sandbox evaluation."""
    events: Optional[List[SandboxEvent]] = Field(default=None, description="JSON events")
    csv: Optional[str] = Field(default=None, description="Raw CSV text")


class RuleResultResponse(BaseModel):
    """A single rule evaluation result."""
    rule_title: str
    severity: str
    result: str  # pass, fail, warn, skip
    why_failed: Optional[str] = None
    citation: Optional[str] = None
    remediation: Optional[str] = None
    category: str


class EventEvaluationResponse(BaseModel):
    """Evaluation results for a single event."""
    event_index: int
    cte_type: str
    traceability_lot_code: str
    product_description: str
    kde_errors: List[str]
    rules_evaluated: int
    rules_passed: int
    rules_failed: int
    rules_warned: int
    compliant: bool
    blocking_defects: List[RuleResultResponse]
    all_results: List[RuleResultResponse]


class SandboxResponse(BaseModel):
    """Response from sandbox evaluation."""
    total_events: int
    compliant_events: int
    non_compliant_events: int
    total_kde_errors: int
    total_rule_failures: int
    submission_blocked: bool
    blocking_reasons: List[str]
    events: List[EventEvaluationResponse]


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

    # Evaluate each event
    event_results: List[EventEvaluationResponse] = []
    total_kde_errors = 0
    total_rule_failures = 0
    compliant_count = 0
    all_blocking_reasons: List[str] = []

    for i, raw_event in enumerate(raw_events):
        # Step 1: KDE validation
        kde_errors = _validate_kdes(raw_event)
        total_kde_errors += len(kde_errors)

        # Step 2: Normalize for rules engine
        canonical = _normalize_for_rules(raw_event)

        # Step 3: Rules evaluation
        summary = _evaluate_event_stateless(canonical)
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
                ))
                all_blocking_reasons.append(f"Event {i+1} ({raw_event.get('cte_type', '?')}): {reason}")

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
                )
                for r in summary.results
            ],
        ))

    # Deduplicate blocking reasons
    unique_blocking = list(dict.fromkeys(all_blocking_reasons))

    return SandboxResponse(
        total_events=len(raw_events),
        compliant_events=compliant_count,
        non_compliant_events=len(raw_events) - compliant_count,
        total_kde_errors=total_kde_errors,
        total_rule_failures=total_rule_failures,
        submission_blocked=len(unique_blocking) > 0,
        blocking_reasons=unique_blocking,
        events=event_results,
    )
