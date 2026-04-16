"""
Sandbox Pydantic request/response models.

Moved from sandbox_router.py — pure data models, no business logic.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


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
    include_custom_rules: bool = Field(default=False, description="Include demo custom business rules")


class RuleResultResponse(BaseModel):
    """A single rule evaluation result."""
    rule_title: str
    severity: str
    result: str  # pass, fail, warn, skip
    why_failed: Optional[str] = None
    citation: Optional[str] = None
    remediation: Optional[str] = None
    category: str
    evidence: Optional[List[Dict[str, Any]]] = None


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


class NormalizationAction(BaseModel):
    """A single normalization action performed on the input data."""
    field: str = Field(..., description="Canonical field name")
    original: str = Field(..., description="Original value from the input")
    normalized: str = Field(..., description="Normalized/canonical value")
    action_type: str = Field(..., description="Type: header_alias, uom_normalize, cte_type_normalize")
    reasoning: str = Field(default="", description="Human-readable explanation of why this normalization is suggested")
    event_index: int = Field(default=-1, description="Index of the event this applies to (-1 = document-level, e.g. header aliases)")


class SandboxResponse(BaseModel):
    """Response from sandbox evaluation."""
    total_events: int
    compliant_events: int
    non_compliant_events: int
    total_kde_errors: int
    total_rule_failures: int
    submission_blocked: bool
    blocking_reasons: List[str]
    duplicate_warnings: List[str] = Field(default_factory=list, description="Warnings about duplicate lot codes within same CTE type")
    entity_warnings: List[str] = Field(default_factory=list, description="Warnings about possible entity name mismatches that may need standardization")
    normalizations: List[NormalizationAction] = Field(default_factory=list, description="Normalizations applied to input data")
    events: List[EventEvaluationResponse]


# ---------------------------------------------------------------------------
# Trace-Back / Recall Models
# ---------------------------------------------------------------------------

class TraceDirection(str):
    UPSTREAM = "upstream"
    DOWNSTREAM = "downstream"
    BOTH = "both"


class TraceNode(BaseModel):
    """A single node in the trace graph — one CTE event."""
    event_index: int
    cte_type: str
    traceability_lot_code: str
    product_description: str
    quantity: Optional[float] = None
    unit_of_measure: str = ""
    timestamp: str = ""
    location_name: str = ""
    facility_from: str = ""
    facility_to: str = ""
    depth: int = 0


class TraceEdge(BaseModel):
    """A directed edge linking two events in the trace graph."""
    from_event_index: int
    to_event_index: int
    link_type: str  # "same_lot", "transformation_input", "facility_handoff"
    lot_code: str


class TraceGraphResponse(BaseModel):
    """Full trace-back / trace-forward result."""
    seed_tlc: str
    direction: str
    nodes: List[TraceNode]
    edges: List[TraceEdge]
    lots_touched: List[str]
    facilities: List[str]
    max_depth: int
    total_quantity: float = 0.0


class SandboxTraceRequest(BaseModel):
    """Request for in-memory lot tracing."""
    csv: str = Field(..., description="Raw CSV text with CTE events")
    tlc: str = Field(..., description="Traceability Lot Code to trace from")
    direction: str = Field(default="both", description="'upstream', 'downstream', or 'both'")
    max_depth: int = Field(default=10, description="Max traversal depth")


# ---------------------------------------------------------------------------
# Share Models
# ---------------------------------------------------------------------------

class SandboxShareRequest(BaseModel):
    """Request to share sandbox evaluation results."""
    csv: str = Field(..., description="Raw CSV text")
    result: SandboxResponse = Field(..., description="Evaluation result to share")


class SandboxShareResponse(BaseModel):
    """Response after creating a shared result."""
    share_id: str
    share_url: str
    expires_at: str
