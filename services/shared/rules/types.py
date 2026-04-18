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
    """Result of evaluating a single rule against a single event.

    result values:
        pass            — rule passed
        fail            — rule failed (counts against compliance)
        warn            — rule produced a warning (does not fail compliance)
        skip            — rule was not applicable or intentionally skipped
        not_ftl_scoped  — product is not on the FDA Food Traceability List; rule
                          is intentionally not evaluated (transparent skip,
                          never produces a positive compliance stamp)
        error           — evaluator raised an exception; treated as a FAIL for
                          compliance purposes (#1354) — "skip" would be
                          fail-open, which is unsafe for a regulatory stamp.
    """
    evaluation_id: str = field(default_factory=lambda: str(uuid4()))
    rule_id: str = ""
    rule_version: int = 1
    rule_title: str = ""
    severity: str = "warning"
    result: str = "pass"  # pass | fail | warn | skip | not_ftl_scoped | error
    why_failed: Optional[str] = None
    evidence_fields_inspected: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 1.0
    citation_reference: Optional[str] = None
    remediation_suggestion: Optional[str] = None
    category: str = "kde_presence"


@dataclass
class EvaluationSummary:
    """Summary of all rule evaluations for a single event.

    Compliance semantics (#1347, #1354):
        compliant is tri-state:
            True  — at least one rule ran and all failures are zero
            False — at least one rule failed (or errored — #1354)
            None  — no rules loaded / all scoped out / nothing evaluated.
                    Callers MUST NOT treat None as compliant. It is an
                    explicit "no verdict" signal that should surface as
                    'no_rules_loaded' or 'not_ftl_scoped' downstream.

        Historically `compliant` was a bool that returned True whenever
        failed == 0 — including when total_rules == 0. That was a
        fail-open bug: tenants with empty rule tables received a green
        compliance stamp. See #1347.
    """
    event_id: str = ""
    total_rules: int = 0
    passed: int = 0
    failed: int = 0
    warned: int = 0
    skipped: int = 0
    errored: int = 0  # #1354 — explicit counter for evaluator crashes
    not_ftl_scoped: int = 0  # #1346 — rules scoped out because non-FTL product
    no_verdict_reason: Optional[str] = None  # e.g. "no_rules_loaded" / "not_ftl_scoped"
    results: List[RuleEvaluationResult] = field(default_factory=list)
    critical_failures: List[RuleEvaluationResult] = field(default_factory=list)

    @property
    def compliant(self) -> Optional[bool]:
        """Tri-state compliance — see class docstring."""
        # #1347 — fail-closed on empty / no-verdict rulesets.
        if self.total_rules == 0:
            return None
        # #1346 — explicit no-verdict signal wins over rule tallies.
        # Non-FTL events and classification-missing events never produce
        # a positive compliance stamp, even if the few meta-rules that
        # ran happened to pass.
        if self.no_verdict_reason:
            return None
        # If every rule was scoped out (non-FTL product), no verdict.
        if self.not_ftl_scoped >= self.total_rules:
            return None
        # #1354 — errors count against compliance, not as skips.
        return self.failed == 0 and self.errored == 0
