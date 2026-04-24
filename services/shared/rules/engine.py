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
    fetch_related_events,
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

    #: Default rule-cache time-to-live (seconds). Long-lived
    #: ``RulesEngine`` instances (e.g. a future worker process holding
    #: one engine across many events) otherwise serve stale rules
    #: indefinitely when an admin retires or adds a rule (#1371).
    #: Today's call sites all instantiate per-request, so the TTL is a
    #: defense-in-depth measure with negligible cost in the
    #: short-lived case. Override via the ``cache_ttl_seconds`` ctor
    #: argument (0 disables caching entirely — useful in tests).
    DEFAULT_CACHE_TTL_SECONDS: int = 60

    def __init__(
        self,
        session: Session,
        *,
        cache_ttl_seconds: Optional[int] = None,
    ):
        self.session = session
        self._cache_ttl_seconds: int = (
            cache_ttl_seconds
            if cache_ttl_seconds is not None
            else self.DEFAULT_CACHE_TTL_SECONDS
        )
        self._rules_cache: Optional[List[RuleDefinition]] = None
        # Monotonic timestamp (seconds) of the most recent
        # ``load_active_rules`` call; ``None`` until the cache is
        # populated. Used to decide whether the cached list is still
        # fresh. Monotonic clock so system-time adjustments don't
        # affect freshness math (#1371).
        self._rules_cache_loaded_at: Optional[float] = None

    def _is_cache_fresh(self) -> bool:
        """Is the per-instance rule cache still within its TTL?"""
        if self._rules_cache is None or self._rules_cache_loaded_at is None:
            return False
        if self._cache_ttl_seconds <= 0:
            # TTL disabled → always treat as stale so every call reloads.
            return False
        import time as _time
        age = _time.monotonic() - self._rules_cache_loaded_at
        return age < self._cache_ttl_seconds

    def invalidate_cache(self) -> None:
        """Explicitly bust the per-instance rule cache (#1371).

        Intended for admin-edit endpoints that mutate ``rule_definitions``
        and want the next evaluation to see the change immediately,
        without waiting for the TTL. Safe to call on a cold instance
        (no-op).
        """
        if self._rules_cache is not None:
            logger.info(
                "rules_engine_cache_invalidated",
                extra={"cached_rule_count": len(self._rules_cache)},
            )
        self._rules_cache = None
        self._rules_cache_loaded_at = None

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
        import time as _time
        self._rules_cache_loaded_at = _time.monotonic()
        logger.info(
            "rules_engine_cache_loaded",
            extra={"rule_count": len(rules), "ttl_seconds": self._cache_ttl_seconds},
        )
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
            # Use cache if still fresh (#1371). An empty list is a valid
            # cached state — a tenant with zero seeded rules should not
            # re-hit the DB every call — so freshness is the gate, not
            # non-None. Stale cache is transparently reloaded.
            if self._is_cache_fresh():
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

        # #1365 — pre-fetch related events ONCE per event when any relational
        # rule will run. Previously each relational evaluator hit the database
        # with the same (tlc, tenant_id, event_id) triple, producing N copies
        # of an identical SELECT per event (N = number of relational rules).
        related_events_cache = self._prefetch_related_events(
            event_data, applicable_rules, tenant_id
        )

        for rule in applicable_rules:
            result = self._evaluate_single_rule(
                event_data, rule,
                tenant_id=tenant_id,
                related_events=related_events_cache,
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

    def persist_summary(
        self,
        summary: EvaluationSummary,
        *,
        tenant_id: str,
        event_id: Optional[str] = None,
    ) -> None:
        """Persist a pre-computed ``EvaluationSummary`` without re-evaluating.

        Public wrapper around the same persistence path used by
        ``evaluate_event(persist=True)`` — exposed so callers that have already
        run the rules can write the resulting rows once instead of evaluating
        twice.

        Use case: ingestion paths that pre-evaluate rules with ``persist=False``
        to make a reject decision before primary store, then need to write
        the eval rows to ``fsma.rule_evaluations`` after the primary commit.
        Without this method the post-commit block had to re-call
        ``evaluate_event(persist=True)``, doubling rules-engine work on the
        hot path under ``RULES_ENGINE_ENFORCE=cte_only|all``.

        Args:
            summary: Pre-computed ``EvaluationSummary``. Empty / no-verdict
                summaries are accepted and produce no DB writes (the
                underlying helper short-circuits on empty results).
            tenant_id: REQUIRED — written to every row and to the eval-error
                marker on failure. Must come from the authenticated context,
                NEVER from the summary or the event payload (#1344 invariant).
            event_id: The canonical event ID the rows reference. Defaults to
                ``summary.event_id`` when not supplied — convenient for the
                common case where the summary was returned by
                ``evaluate_event`` against this engine.

        Returns:
            None. On DB failure the inner savepoint rolls back and the
            ``traceability_events`` row is marked with ``evaluation_error``;
            the exception is swallowed so callers don't observe a partial
            persistence state. Mirrors the exact behavior of
            ``_persist_evaluations``.
        """
        resolved_event_id = event_id or summary.event_id
        if not resolved_event_id:
            # No event_id available — refuse rather than write rows with an
            # empty FK that the rules-eval queries can't join back. Better
            # to surface the misuse than silently lose results.
            raise ValueError(
                "persist_summary requires an event_id (either as kwarg or on "
                "summary.event_id)"
            )
        self._persist_evaluations(tenant_id, resolved_event_id, summary.results)

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

            # #1365 — pre-fetch once per event (not per rule).
            related_events_cache = self._prefetch_related_events(
                event_data, applicable, tenant_id
            )

            for rule in applicable:
                result = self._evaluate_single_rule(
                    event_data, rule,
                    tenant_id=tenant_id,
                    related_events=related_events_cache,
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

    def _prefetch_related_events(
        self,
        event_data: Dict[str, Any],
        applicable_rules: List[RuleDefinition],
        tenant_id: Optional[str],
    ) -> Optional[List[Dict[str, Any]]]:
        """Pre-fetch the per-event related-events list once (#1365).

        Relational evaluators (``temporal_order``, ``identity_consistency``,
        ``mass_balance``) each previously called ``fetch_related_events``
        with identical arguments — one SELECT per (event, rule) tuple.
        For an event with 3 relational rules applicable, that's 3 copies
        of the same query. This helper fetches once per event and forwards
        the result into each evaluator via a kwarg.

        Returns ``None`` — causing evaluators to fall back to per-call
        fetch — when any of the following hold:

        * no ``tenant_id`` (evaluator would error anyway at dispatch)
        * no ``session`` (engine configuration error — evaluator errors)
        * event has no ``traceability_lot_code`` (evaluator would skip)
        * no applicable rule is relational (no waste to avoid)
        * the pre-fetch itself raises — log and defer to per-evaluator
          fetch rather than aborting the whole evaluation

        Callers that pass ``None`` preserve the pre-#1365 semantics.
        """
        if not tenant_id or self.session is None:
            return None
        tlc = event_data.get("traceability_lot_code", "")
        if not tlc:
            return None
        if not any(
            (rule.evaluation_logic or {}).get("type") in RELATIONAL_EVALUATORS
            for rule in applicable_rules
        ):
            return None
        event_id = event_data.get("event_id", "")
        try:
            return fetch_related_events(
                self.session, tlc, tenant_id, str(event_id) if event_id else None
            )
        except Exception as e:
            # A failed pre-fetch must not kill the evaluation — the
            # per-evaluator fallback will re-attempt and be caught by
            # ``_evaluate_single_rule``'s own try/except so the failure
            # is counted as an `error` result, not a crash.
            logger.warning(
                "rules_engine_prefetch_failed",
                extra={
                    "event_id": event_id,
                    "tlc": tlc,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "note": "falling back to per-evaluator fetch (#1365)",
                },
            )
            return None

    def _evaluate_single_rule(
        self,
        event_data: Dict[str, Any],
        rule: RuleDefinition,
        *,
        tenant_id: Optional[str] = None,
        related_events: Optional[List[Dict[str, Any]]] = None,
    ) -> RuleEvaluationResult:
        """Evaluate a single rule against a single event.

        tenant_id is only required for relational evaluators (#1344). If a
        relational rule is dispatched without tenant_id, it is treated as
        an error (not a silent skip) so missing context is never treated
        as compliant.

        ``related_events`` (#1365) is the engine-pre-fetched per-event cache
        that is forwarded to relational evaluators to avoid N redundant
        database queries per event (one per relational rule). Stateless
        evaluators ignore it. ``None`` means "no cache available" — each
        relational evaluator will self-fetch, preserving old behavior.
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
                    related_events=related_events,
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
        """Persist evaluation results to database.

        All rows for a single event are written in one executemany-style
        INSERT wrapped in an explicit savepoint (#1372). On failure the
        savepoint is rolled back and the event is marked with an error flag
        so the caller does not silently lose the failure signal.
        """
        if not results:
            return

        insert_params = [
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
            }
            for r in results
        ]

        insert_stmt = text(
            "INSERT INTO fsma.rule_evaluations ("
            "    evaluation_id, tenant_id, event_id,"
            "    rule_id, rule_version, result,"
            "    why_failed, evidence_fields_inspected, confidence"
            ") VALUES ("
            "    :eval_id, :tenant_id, :event_id,"
            "    :rule_id, :rule_version, :result,"
            "    :why_failed, CAST(:evidence AS jsonb), :confidence"
            ")"
        )

        savepoint = self.session.begin_nested()
        try:
            self.session.execute(insert_stmt, insert_params)
        except Exception as e:
            savepoint.rollback()
            logger.error(
                "evaluation_persist_failed",
                extra={"event_id": event_id, "error": str(e)},
            )
            # Mark the event so operators can see it needs re-evaluation.
            try:
                self.session.execute(
                    text(
                        "UPDATE fsma.traceability_events"
                        " SET evaluation_error = :error_message,"
                        "     evaluated_at = NOW()"
                        " WHERE tenant_id = :tenant_id AND event_id = :event_id"
                    ),
                    {
                        "tenant_id": tenant_id,
                        "event_id": event_id,
                        "error_message": str(e),
                    },
                )
            except Exception as mark_err:
                logger.error(
                    "evaluation_persist_marker_failed",
                    extra={"event_id": event_id, "error": str(mark_err)},
                )

    _BATCH_CHUNK_SIZE: int = 100

    def _batch_persist_evaluations(
        self,
        tenant_id: str,
        results: List[tuple],  # (event_id, RuleEvaluationResult)
    ) -> None:
        """Batch persist evaluation results in chunks of _BATCH_CHUNK_SIZE.

        Each chunk is written as a single ``INSERT INTO ... VALUES (...)``
        (one round-trip per chunk) and wrapped in its own savepoint (#1372).
        On failure the savepoint is rolled back, an ``evaluation_batch_failed``
        event is logged with chunk metadata, and processing continues with the
        next chunk — a single bad chunk never aborts the rest of the batch.
        """
        if not results:
            return

        from sqlalchemy.exc import SQLAlchemyError

        chunk_size = self._BATCH_CHUNK_SIZE
        for chunk_start in range(0, len(results), chunk_size):
            chunk = results[chunk_start : chunk_start + chunk_size]
            chunk_index = chunk_start // chunk_size
            chunk_end = chunk_start + len(chunk) - 1

            value_dicts = [
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
                }
                for event_id, r in chunk
            ]

            insert_stmt = text(
                "INSERT INTO fsma.rule_evaluations ("
                "    evaluation_id, tenant_id, event_id,"
                "    rule_id, rule_version, result,"
                "    why_failed, evidence_fields_inspected, confidence"
                ") VALUES ("
                "    :eval_id, :tenant_id, :event_id,"
                "    :rule_id, :rule_version, :result,"
                "    :why_failed, CAST(:evidence AS jsonb), :confidence"
                ")"
            )

            savepoint = self.session.begin_nested()
            try:
                self.session.execute(insert_stmt, value_dicts)
            except (SQLAlchemyError, Exception) as e:
                savepoint.rollback()
                logger.error(
                    "evaluation_batch_failed",
                    extra={
                        "tenant_id": tenant_id,
                        "chunk_index": chunk_index,
                        "chunk_start": chunk_start,
                        "chunk_end": chunk_end,
                        "chunk_size": len(chunk),
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )
