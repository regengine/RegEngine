"""
Versioned Rules Engine for FSMA 204 Compliance.

Loads rule definitions from the database, evaluates canonical events
against applicable rules, and persists evaluation results.

Usage:
    from shared.rules.engine import RulesEngine

    engine = RulesEngine(db_session)
    # tenant_id is REQUIRED for relational evaluation — it must come from
    # the authenticated request context, NOT from the event payload (#1344).
    results = engine.evaluate_event(canonical_event, tenant_id="tenant-abc")

Correctness hardening (2026-04-17):
    - #1344: relational evaluators ignore event_data['tenant_id'] — the
             authenticated tenant is passed through from the caller and
             used for all cross-event DB lookups.
    - #1346: non-FTL foods are transparently skipped with
             result='not_ftl_scoped' instead of being stamped compliant.
    - #1347: empty/missing rule sets no longer produce compliant=True;
             EvaluationSummary.compliant returns None (no verdict).
    - #1354: evaluator errors are counted as failed (not skipped) so a
             crash cannot produce a green compliance stamp.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.rules.types import RuleDefinition, RuleEvaluationResult, EvaluationSummary
from shared.rules.evaluators.stateless import EVALUATORS
from shared.rules.evaluators.relational import (
    RELATIONAL_EVALUATORS,
    RelatedEventsCache,
    fetch_related_events_batch,
)
from shared.rules.ftl import (
    is_ftl_food,
    event_has_ftl_hint,
    get_ftl_category,
    rule_applies_to_ftl_category,
)

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
        event_ftl_category: Optional[str] = None,
        event_is_ftl: Optional[bool] = None,
    ) -> List[RuleDefinition]:
        """Filter rules to those applicable to the given event type AND FTL category (#1346).

        A rule is applicable if:
          - Its cte_types list matches the event_type (or is empty / contains "all"), AND
          - EITHER the event is on the FTL and the rule's ftl_scope includes
            the event's category (or is "ALL" / omitted), OR the rule
            explicitly opts in to non-FTL coverage via ftl_scope=["NON_FTL"].

        If ``event_is_ftl`` is None (unknown), we still return only rules
        that have been marked non-FTL-scoped so that we don't silently
        stamp an unclassified event "compliant" (#1346).
        """
        if rules is None:
            # Use cache if explicitly populated (even with an empty list — a
            # tenant with zero seeded rules is a valid state, not a cache miss).
            if self._rules_cache is not None:
                rules = self._rules_cache
            else:
                rules = self.load_active_rules()

        applicable = []
        for rule in rules:
            conditions = rule.applicability_conditions or {}
            cte_types = conditions.get("cte_types", [])

            cte_match = (
                not cte_types
                or event_type in cte_types
                or "all" in cte_types
            )
            if not cte_match:
                continue

            ftl_scope = conditions.get("ftl_scope") or []
            scope_tokens = {
                s.strip().upper()
                for s in ftl_scope
                if isinstance(s, str) and s.strip()
            }

            # "ANY" scope — rule fires regardless of FTL status.
            if "ANY" in scope_tokens:
                applicable.append(rule)
                continue

            # "NON_FTL" scope — fires when the event is explicitly NOT on
            # the FTL OR its FTL status is unknown. This is how the
            # "FTL classification required" meta-rule runs without being
            # masked by the "unknown -> skip everything" default.
            if "NON_FTL" in scope_tokens and event_is_ftl is not True:
                applicable.append(rule)
                continue

            # Default path — rule targets FTL foods.
            if event_is_ftl is True:
                if rule_applies_to_ftl_category(conditions, event_ftl_category):
                    applicable.append(rule)
            else:
                # Explicitly non-FTL OR unknown — do NOT apply FTL rules.
                # Caller will observe total_rules == 0 (or only NON_FTL
                # rules fired) and must treat the event as no_verdict
                # rather than compliant (#1346).
                continue

        return applicable

    def evaluate_event(
        self,
        event_data: Dict[str, Any],
        persist: bool = True,
        *,
        tenant_id: Optional[str] = None,
    ) -> EvaluationSummary:
        """
        Evaluate a canonical event against all applicable rules.

        Args:
            event_data: Dict representation of a TraceabilityEvent.
            persist: If True, write evaluation results to database.
            tenant_id: REQUIRED for relational rules (#1344). Must come from
                the authenticated request context. Any tenant_id in
                event_data is IGNORED.

        Returns:
            EvaluationSummary with all results. See EvaluationSummary for
            tri-state `compliant` semantics (#1347).
        """
        event_type = event_data.get("event_type", "")
        event_id = event_data.get("event_id", "")

        # #1346 — FTL classification
        event_is_ftl = is_ftl_food(event_data)
        event_ftl_category = get_ftl_category(event_data)
        has_ftl_hint = event_has_ftl_hint(event_data)

        applicable_rules = self.get_applicable_rules(
            event_type,
            event_ftl_category=event_ftl_category,
            event_is_ftl=event_is_ftl,
        )

        # #1347 — structure the no-verdict branch explicitly.
        summary = EvaluationSummary(
            event_id=event_id,
            total_rules=len(applicable_rules),
        )

        if not applicable_rules:
            # The engine has rules but none apply. Distinguish why.
            if event_is_ftl is False:
                summary.no_verdict_reason = "not_ftl_scoped"
            elif not has_ftl_hint:
                summary.no_verdict_reason = "ftl_classification_missing"
            else:
                summary.no_verdict_reason = "no_rules_loaded"
            logger.info(
                "rules_engine_no_verdict",
                extra={
                    "event_id": event_id,
                    "event_type": event_type,
                    "reason": summary.no_verdict_reason,
                    "event_is_ftl": event_is_ftl,
                    "event_ftl_category": event_ftl_category,
                },
            )
            return summary

        # #1365 — one cache per evaluate_event() call; all relational
        # evaluators for this event share it, so fetch_related_events
        # runs at most once per (tlc, tenant, exclude_event_id).
        related_events_cache: RelatedEventsCache = {}

        for rule in applicable_rules:
            result = self._evaluate_single_rule(
                event_data,
                rule,
                tenant_id=tenant_id,
                related_events_cache=related_events_cache,
            )
            summary.results.append(result)
            self._tally_result(summary, result)

        # #1346 — a non-FTL event that only hit meta-rules (e.g. the
        # "FTL classification must be present" sanity check) should NOT
        # receive a green compliance stamp. Surface the gap instead.
        if event_is_ftl is False:
            summary.no_verdict_reason = "not_ftl_scoped"

        if persist and tenant_id:
            self._persist_evaluations(tenant_id, event_id, summary.results)

        return summary

    def evaluate_events_batch(
        self,
        events: List[Dict[str, Any]],
        tenant_id: str,
        persist: bool = True,
    ) -> List[EvaluationSummary]:
        """Evaluate multiple events against all applicable rules.

        tenant_id is REQUIRED and must come from the authenticated context
        (#1344). Event payload tenant_id fields are ignored.
        """
        if not tenant_id:
            # Fail-closed — without a tenant context we cannot safely run
            # relational evaluators.
            raise ValueError("tenant_id is required for batch evaluation")

        rules = self.load_active_rules()
        summaries = []

        # #1365 — batch-prefetch related events for every (TLC, event_id)
        # pair in the input set with a single query, instead of letting
        # each relational rule trigger its own round-trip. The shared
        # cache is passed to every _evaluate_single_rule call below.
        batch_cache: RelatedEventsCache = {}
        if self.session is not None:
            tlc_pairs = [
                (e.get("traceability_lot_code"), e.get("event_id"))
                for e in events
                if e.get("traceability_lot_code")
            ]
            if tlc_pairs:
                try:
                    fetch_related_events_batch(
                        self.session, tlc_pairs, tenant_id, cache=batch_cache,
                    )
                except Exception as exc:
                    # A prefetch failure should not abort the whole batch —
                    # individual evaluators will fall back to per-event
                    # queries (and log their own errors) via the empty
                    # cache. Warn so SRE can spot the degraded path.
                    logger.warning(
                        "batch_prefetch_related_events_failed",
                        extra={"error": str(exc), "tenant_id": tenant_id},
                    )

        for event_data in events:
            event_type = event_data.get("event_type", "")
            event_id = event_data.get("event_id", "")

            event_is_ftl = is_ftl_food(event_data)
            event_ftl_category = get_ftl_category(event_data)
            has_ftl_hint = event_has_ftl_hint(event_data)

            applicable = self.get_applicable_rules(
                event_type,
                rules,
                event_ftl_category=event_ftl_category,
                event_is_ftl=event_is_ftl,
            )
            summary = EvaluationSummary(
                event_id=event_id,
                total_rules=len(applicable),
            )

            if not applicable:
                if event_is_ftl is False:
                    summary.no_verdict_reason = "not_ftl_scoped"
                elif not has_ftl_hint:
                    summary.no_verdict_reason = "ftl_classification_missing"
                else:
                    summary.no_verdict_reason = "no_rules_loaded"
                summaries.append(summary)
                continue

            # #1365 — per-event cache shared by the relational rules in
            # this event's evaluation. The batch prefetch below warms
            # this cache with a single roundtrip before evaluation.
            related_events_cache = batch_cache

            for rule in applicable:
                result = self._evaluate_single_rule(
                    event_data,
                    rule,
                    tenant_id=tenant_id,
                    related_events_cache=related_events_cache,
                )
                summary.results.append(result)
                self._tally_result(summary, result)

            summaries.append(summary)

        if persist:
            all_results = []
            for summary in summaries:
                for r in summary.results:
                    all_results.append((summary.event_id, r))
            self._batch_persist_evaluations(tenant_id, all_results)

        return summaries

    @staticmethod
    def _tally_result(summary: EvaluationSummary, result: RuleEvaluationResult) -> None:
        """Update summary counters based on a single rule result.

        #1354 — errors are counted as `errored`, not `skipped`, and the
        `compliant` property treats `errored > 0` as non-compliant.
        """
        if result.result == "pass":
            summary.passed += 1
        elif result.result == "fail":
            summary.failed += 1
            if result.severity == "critical":
                summary.critical_failures.append(result)
        elif result.result == "warn":
            summary.warned += 1
        elif result.result == "error":
            summary.errored += 1
            # Critical errors should be surfaced alongside critical failures
            # so callers see the evaluator crash in the regulator-facing log.
            if result.severity == "critical":
                summary.critical_failures.append(result)
        elif result.result == "not_ftl_scoped":
            summary.not_ftl_scoped += 1
        else:  # "skip" or any unknown intentional outcome
            summary.skipped += 1

    def _evaluate_single_rule(
        self,
        event_data: Dict[str, Any],
        rule: RuleDefinition,
        *,
        tenant_id: Optional[str] = None,
        related_events_cache: Optional[RelatedEventsCache] = None,
    ) -> RuleEvaluationResult:
        """Evaluate a single rule against a single event.

        tenant_id is only required for relational evaluators (#1344). If a
        relational rule is dispatched without tenant_id, it is treated as
        an error (not a silent skip) so missing context is never treated
        as compliant.

        related_events_cache is threaded into relational evaluators so
        rules for the same event share a single DB fetch (#1365).
        """
        logic = rule.evaluation_logic
        eval_type = logic.get("type", "field_presence")

        evaluator = EVALUATORS.get(eval_type)
        if evaluator:
            try:
                return evaluator(event_data, logic, rule)
            except Exception as e:
                # #1354 — evaluator crashes must not fail-open as "skip".
                logger.error(
                    "rule_evaluation_error",
                    extra={
                        "rule_id": rule.rule_id,
                        "rule_title": rule.title,
                        "eval_type": eval_type,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )
                return RuleEvaluationResult(
                    rule_id=rule.rule_id,
                    rule_version=rule.rule_version,
                    rule_title=rule.title,
                    severity=rule.severity,
                    result="error",
                    why_failed=f"Evaluator crashed ({type(e).__name__}): {str(e)}",
                    category=rule.category,
                )

        relational_evaluator = RELATIONAL_EVALUATORS.get(eval_type)
        if relational_evaluator:
            if self.session is None:
                # No session — can't run relational checks. This is a
                # configuration error, not a compliance pass; report as
                # an error so it counts against the stamp (#1354).
                logger.error(
                    "relational_rule_no_session",
                    extra={"rule_id": rule.rule_id, "eval_type": eval_type},
                )
                return RuleEvaluationResult(
                    rule_id=rule.rule_id,
                    rule_version=rule.rule_version,
                    rule_title=rule.title,
                    severity=rule.severity,
                    result="error",
                    why_failed=f"Relational rule '{eval_type}' requires a DB session",
                    category=rule.category,
                )
            if not tenant_id:
                # #1344 — without an authenticated tenant, a relational
                # evaluator could read another tenant's events via a
                # forged payload field. Refuse to dispatch.
                logger.error(
                    "relational_rule_missing_tenant_context",
                    extra={"rule_id": rule.rule_id, "eval_type": eval_type},
                )
                return RuleEvaluationResult(
                    rule_id=rule.rule_id,
                    rule_version=rule.rule_version,
                    rule_title=rule.title,
                    severity=rule.severity,
                    result="error",
                    why_failed=(
                        f"Relational rule '{eval_type}' requires an authenticated "
                        "tenant_id from request context"
                    ),
                    category=rule.category,
                )
            try:
                return relational_evaluator(
                    event_data, logic, rule, self.session,
                    tenant_id=tenant_id,
                    related_events_cache=related_events_cache,
                )
            except Exception as e:
                logger.error(
                    "relational_rule_evaluation_error",
                    extra={
                        "rule_id": rule.rule_id,
                        "rule_title": rule.title,
                        "eval_type": eval_type,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )
                return RuleEvaluationResult(
                    rule_id=rule.rule_id,
                    rule_version=rule.rule_version,
                    rule_title=rule.title,
                    severity=rule.severity,
                    result="error",
                    why_failed=f"Evaluator crashed ({type(e).__name__}): {str(e)}",
                    category=rule.category,
                )

        # #1354 — an unknown eval_type used to return result="skip", which
        # meant rules with a typo in their JSON or a newer eval_type that
        # hasn't been deployed yet silently counted as compliant. Treat
        # it as a configuration error so it fails the stamp.
        logger.error(
            "rule_unknown_eval_type",
            extra={"rule_id": rule.rule_id, "eval_type": eval_type},
        )
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_version=rule.rule_version,
            rule_title=rule.title,
            severity=rule.severity,
            result="error",
            why_failed=f"Unknown evaluation type '{eval_type}' — rule cannot be evaluated",
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
