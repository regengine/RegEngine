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
            None  — no rules loaded / all scoped out / all skipped /
                    nothing evaluated.
                    Callers MUST NOT treat None as compliant. It is an
                    explicit "no verdict" signal that should surface as
                    an exact no-verdict reason downstream.

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
        # Failure evidence always wins over no-verdict metadata. A classifier
        # hint must not hide a rule failure or evaluator error.
        if self.failed > 0 or self.errored > 0:
            return False
        # #1347 — fail-closed on empty / no-verdict rulesets.
        if self.total_rules == 0:
            return None
        # #1346 — explicit no-verdict signal wins over rule tallies.
        # Non-FTL events and classification-missing events never produce
        # a positive compliance stamp, even if the few meta-rules that
        # ran happened to pass.
        if self.no_verdict_reason:
            return None
        # Any mix of skipped/scoped-out/uncounted outcomes asserts nothing
        # about compliance when no rule produced affirmative evidence.
        if self.passed == 0 and self.warned == 0:
            return None
        return True

    @property
    def verdict(self) -> str:
        """Persistable event-level verdict: ``pass`` | ``fail`` | ``no_verdict``.

        This is what ``RulesEngine`` stamps on
        ``fsma.traceability_events.evaluation_verdict`` so SQL consumers
        (FDA export, auditor list) can see the tri-state outcome instead of
        re-deriving it from per-rule rows — which loses the summary-level
        no-verdict context (non-FTL meta-pass) entirely.
        """
        compliant = self.compliant
        if compliant is True:
            return "pass"
        if compliant is False:
            return "fail"
        return "no_verdict"

    @property
    def verdict_reason(self) -> Optional[str]:
        """Why ``verdict`` is ``no_verdict``; ``None`` for pass/fail."""
        if self.compliant is not None:
            return None
        if self.no_verdict_reason:
            return self.no_verdict_reason
        if self.total_rules == 0:
            return "nothing_evaluated"
        if self.not_ftl_scoped >= self.total_rules:
            return "not_ftl_scoped"
        if self.skipped + self.not_ftl_scoped >= self.total_rules:
            return "all_rules_skipped"
        return "nothing_evaluated"
