"""
Data types for the FSMA 204 Rules Engine.

RuleDefinition: A versioned compliance rule (policy artifact, not code).
RuleEvaluationResult: Result of evaluating one rule against one event.
EvaluationSummary: Aggregate results for all rules on a single event.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional
from uuid import uuid4


@dataclass
class RuleDefinition:
    """A versioned compliance rule."""
    rule_id: str
    rule_version: int
    title: str
    description: Optional[str]
    severity: str  # critical, warning, info
    category: str
    applicability_conditions: Dict[str, Any]
    citation_reference: Optional[str]
    effective_date: date
    retired_date: Optional[date]
    evaluation_logic: Dict[str, Any]
    failure_reason_template: str
    remediation_suggestion: Optional[str]


@dataclass
class RuleEvaluationResult:
    """Result of evaluating a single rule against a single event."""
    evaluation_id: str = field(default_factory=lambda: str(uuid4()))
    rule_id: str = ""
    rule_version: int = 1
    rule_title: str = ""
    severity: str = "warning"
    result: str = "pass"  # pass, fail, warn, skip
    why_failed: Optional[str] = None
    evidence_fields_inspected: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 1.0
    citation_reference: Optional[str] = None
    remediation_suggestion: Optional[str] = None
    category: str = "kde_presence"


@dataclass
class EvaluationSummary:
    """Summary of all rule evaluations for a single event."""
    event_id: str = ""
    total_rules: int = 0
    passed: int = 0
    failed: int = 0
    warned: int = 0
    skipped: int = 0
    results: List[RuleEvaluationResult] = field(default_factory=list)
    critical_failures: List[RuleEvaluationResult] = field(default_factory=list)

    @property
    def compliant(self) -> bool:
        return self.failed == 0
