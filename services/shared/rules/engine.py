"""
Versioned Rules Engine for FSMA 204 Compliance.

Loads rule definitions from the database, evaluates canonical events
against applicable rules, and persists evaluation results.

Usage:
    from shared.rules.engine import RulesEngine

    engine = RulesEngine(db_session)
    results = engine.evaluate_event(canonical_event)
"""

import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.observability.workflow_logger import workflow_span

from shared.rules.types import RuleDefinition, RuleEvaluationResult, EvaluationSummary
from shared.rules.evaluators.stateless import EVALUATORS
from shared.rules.evaluators.relational import RELATIONAL_EVALUATORS

logger = logging.getLogger("rules-engine")


class RulesEngine:
    """
    Versioned FSMA 204 compliance rules engine.

    Loads rule definitions from the database, evaluates canonical events
    against applicable rules, and persists evaluation results.
    """

    def __init__(self, session: Session):
        self.session = session
        self._rules_cache: Optional[List[RuleDefinition]] = None

    def load_active_rules(self) -> List[RuleDefinition]:
        """Load all active (non-retired) rule definitions."""
        rows = self.session.execute(
            text("""
                SELECT rule_id, rule_version, title, description,
                       severity, category, applicability_conditions,
                       citation_reference, effective_date, retired_date,
                       evaluation_logic, failure_reason_template,
                       remediation_suggestion
                FROM fsma.rule_definitions
                WHERE retired_date IS NULL
                  AND effective_date <= CURRENT_DATE
                ORDER BY severity DESC, category, title
            """)
        ).fetchall()

        rules = []
        for r in rows:
            rules.append(RuleDefinition(
                rule_id=str(r[0]),
                rule_version=r[1],
                title=r[2],
                description=r[3],
                severity=r[4],
                category=r[5],
                applicability_conditions=r[6] if isinstance(r[6], dict) else json.loads(r[6] or "{}"),
                citation_reference=r[7],
                effective_date=r[8],
                retired_date=r[9],
                evaluation_logic=r[10] if isinstance(r[10], dict) else json.loads(r[10] or "{}"),
                failure_reason_template=r[11],
                remediation_suggestion=r[12],
            ))

        self._rules_cache = rules
        return rules

    def get_applicable_rules(
        self,
        event_type: str,
        rules: Optional[List[RuleDefinition]] = None,
    ) -> List[RuleDefinition]:
        """Filter rules to those applicable to the given event type."""
        if rules is None:
            rules = self._rules_cache or self.load_active_rules()

        applicable = []
        for rule in rules:
            conditions = rule.applicability_conditions
            cte_types = conditions.get("cte_types", [])

            if not cte_types or event_type in cte_types or "all" in cte_types:
                applicable.append(rule)

        return applicable

    def evaluate_event(
        self,
        event_data: Dict[str, Any],
        persist: bool = True,
        tenant_id: Optional[str] = None,
    ) -> EvaluationSummary:
        """
        Evaluate a canonical event against all applicable rules.

        Args:
            event_data: Dict representation of a TraceabilityEvent.
            persist: If True, write evaluation results to database.
            tenant_id: Tenant ID for persisting results.

        Returns:
            EvaluationSummary with all results.
        """
        event_type = event_data.get("event_type", "")
        event_id = event_data.get("event_id", "")

        with workflow_span("compliance_evaluation",
                           tenant_id=tenant_id or "") as span:
            applicable_rules = self.get_applicable_rules(event_type)

            summary = EvaluationSummary(
                event_id=event_id,
                total_rules=len(applicable_rules),
            )

            for rule in applicable_rules:
                result = self._evaluate_single_rule(event_data, rule)
                summary.results.append(result)

                if result.result == "pass":
                    summary.passed += 1
                elif result.result == "fail":
                    summary.failed += 1
                    if result.severity == "critical":
                        summary.critical_failures.append(result)
                elif result.result == "warn":
                    summary.warned += 1
                elif result.result in ("skip", "error"):
                    summary.skipped += 1

            if persist and tenant_id:
                self._persist_evaluations(tenant_id, event_id, summary.results)

            outcome = "fail" if summary.failed > 0 else "pass"
            span.set_outcome(outcome,
                             event_id=event_id,
                             rule_count=len(applicable_rules),
                             passed=summary.passed,
                             failed=summary.failed,
                             warned=summary.warned)

        return summary

    def evaluate_events_batch(
        self,
        events: List[Dict[str, Any]],
        tenant_id: str,
        persist: bool = True,
    ) -> List[EvaluationSummary]:
        """Evaluate multiple events against all applicable rules."""
        rules = self.load_active_rules()
        summaries = []

        for event_data in events:
            event_type = event_data.get("event_type", "")
            event_id = event_data.get("event_id", "")

            applicable = self.get_applicable_rules(event_type, rules)
            summary = EvaluationSummary(
                event_id=event_id,
                total_rules=len(applicable),
            )

            for rule in applicable:
                result = self._evaluate_single_rule(event_data, rule)
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

            summaries.append(summary)

        if persist:
            all_results = []
            for summary in summaries:
                for r in summary.results:
                    all_results.append((summary.event_id, r))
            self._batch_persist_evaluations(tenant_id, all_results)

        return summaries

    def _evaluate_single_rule(
        self,
        event_data: Dict[str, Any],
        rule: RuleDefinition,
    ) -> RuleEvaluationResult:
        """Evaluate a single rule against a single event."""
        logic = rule.evaluation_logic
        eval_type = logic.get("type", "field_presence")

        evaluator = EVALUATORS.get(eval_type)
        if evaluator:
            try:
                return evaluator(event_data, logic, rule)
            except Exception as e:
                logger.warning(
                    "rule_evaluation_error",
                    extra={"rule_id": rule.rule_id, "error": str(e)},
                )
                return RuleEvaluationResult(
                    rule_id=rule.rule_id,
                    rule_version=rule.rule_version,
                    rule_title=rule.title,
                    severity=rule.severity,
                    result="error",
                    why_failed=f"Evaluation error: {str(e)}",
                    category=rule.category,
                )

        relational_evaluator = RELATIONAL_EVALUATORS.get(eval_type)
        if relational_evaluator:
            if self.session is None:
                return RuleEvaluationResult(
                    rule_id=rule.rule_id,
                    rule_version=rule.rule_version,
                    rule_title=rule.title,
                    severity=rule.severity,
                    result="skip",
                    why_failed=f"Relational rule '{eval_type}' requires DB session",
                    category=rule.category,
                )
            try:
                return relational_evaluator(event_data, logic, rule, self.session)
            except Exception as e:
                logger.warning(
                    "relational_rule_evaluation_error",
                    extra={"rule_id": rule.rule_id, "error": str(e)},
                )
                return RuleEvaluationResult(
                    rule_id=rule.rule_id,
                    rule_version=rule.rule_version,
                    rule_title=rule.title,
                    severity=rule.severity,
                    result="error",
                    why_failed=f"Evaluation error: {str(e)}",
                    category=rule.category,
                )

        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_version=rule.rule_version,
            rule_title=rule.title,
            severity=rule.severity,
            result="skip",
            why_failed=f"Unknown evaluation type: {eval_type}",
            category=rule.category,
        )

    def _persist_evaluations(
        self,
        tenant_id: str,
        event_id: str,
        results: List[RuleEvaluationResult],
    ) -> None:
        """Persist evaluation results to database."""
        for r in results:
            try:
                self.session.execute(
                    text("""
                        INSERT INTO fsma.rule_evaluations (
                            evaluation_id, tenant_id, event_id,
                            rule_id, rule_version, result,
                            why_failed, evidence_fields_inspected,
                            confidence
                        ) VALUES (
                            :eval_id, :tenant_id, :event_id,
                            :rule_id, :rule_version, :result,
                            :why_failed, CAST(:evidence AS jsonb),
                            :confidence
                        )
                    """),
                    {
                        "eval_id": r.evaluation_id,
                        "tenant_id": tenant_id,
                        "event_id": event_id,
                        "rule_id": r.rule_id,
                        "rule_version": r.rule_version,
                        "result": r.result,
                        "why_failed": r.why_failed,
                        "evidence": json.dumps(r.evidence_fields_inspected, default=str),
                        "confidence": r.confidence,
                    },
                )
            except Exception as e:
                logger.error(
                    "evaluation_persist_failed",
                    extra={"rule_id": r.rule_id, "error": str(e)},
                )
                raise

    def _batch_persist_evaluations(
        self,
        tenant_id: str,
        results: List[tuple],  # (event_id, RuleEvaluationResult)
    ) -> None:
        """Batch persist evaluation results."""
        for chunk_start in range(0, len(results), 100):
            chunk = results[chunk_start:chunk_start + 100]
            values_clauses = []
            params: Dict[str, Any] = {}
            for i, (event_id, r) in enumerate(chunk):
                values_clauses.append(
                    f"(:eid_{i}, :tid_{i}, :evid_{i}, :rid_{i}, :rv_{i}, "
                    f":res_{i}, :why_{i}, CAST(:ev_{i} AS jsonb), :conf_{i})"
                )
                params.update({
                    f"eid_{i}": r.evaluation_id,
                    f"tid_{i}": tenant_id,
                    f"evid_{i}": event_id,
                    f"rid_{i}": r.rule_id,
                    f"rv_{i}": r.rule_version,
                    f"res_{i}": r.result,
                    f"why_{i}": r.why_failed,
                    f"ev_{i}": json.dumps(r.evidence_fields_inspected, default=str),
                    f"conf_{i}": r.confidence,
                })

            if values_clauses:
                sql = f"""
                    INSERT INTO fsma.rule_evaluations (
                        evaluation_id, tenant_id, event_id,
                        rule_id, rule_version, result,
                        why_failed, evidence_fields_inspected, confidence
                    ) VALUES {', '.join(values_clauses)}
                """
                try:
                    self.session.execute(text(sql), params)
                except Exception as e:
                    logger.error("batch_eval_persist_failed: %s", str(e))
                    raise
