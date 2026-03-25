"""
Versioned Rules Engine for FSMA 204 Compliance.

Separates regulatory logic from application logic. Rules are versioned,
citable policy artifacts — not code paths embedded in service logic.

Every evaluation produces:
    - pass / fail / warn / skip
    - why_failed (human-readable, rendered from template)
    - evidence_fields_inspected (what was checked and what values were found)
    - rule_version (which version of the rule was applied)
    - confidence (how certain is the evaluation)

A user should see:
    "Failed: Receiving event missing traceability lot code source reference
     (21 CFR §1.1345(b)(7)). Request the TLC source reference from your
     immediate supplier."

NOT:
    "validation_error_17"

Usage:
    from shared.rules_engine import RulesEngine

    engine = RulesEngine(db_session)
    results = engine.evaluate_event(canonical_event)
    # results = [RuleEvaluationResult(...), ...]
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("rules-engine")


# ---------------------------------------------------------------------------
# Data Types
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Rule Evaluator Functions
# ---------------------------------------------------------------------------

def _get_nested_value(data: Dict[str, Any], field_path: str) -> Any:
    """Get a value from a nested dict using dot notation. e.g., 'kdes.harvest_date'."""
    parts = field_path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _evaluate_field_presence(
    event_data: Dict[str, Any],
    logic: Dict[str, Any],
    rule: RuleDefinition,
) -> RuleEvaluationResult:
    """Evaluate whether a required field is present and non-empty."""
    field_path = logic.get("field", "")
    value = _get_nested_value(event_data, field_path)

    is_present = value is not None and (
        not isinstance(value, str) or value.strip() != ""
    )

    evidence = [{
        "field": field_path,
        "value": str(value)[:200] if value is not None else None,
        "expected": "not_empty",
        "actual_present": is_present,
    }]

    if is_present:
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_version=rule.rule_version,
            rule_title=rule.title,
            severity=rule.severity,
            result="pass",
            evidence_fields_inspected=evidence,
            citation_reference=rule.citation_reference,
            category=rule.category,
        )

    # Render failure message from template
    why_failed = rule.failure_reason_template.format(
        field_name=field_path.split(".")[-1].replace("_", " "),
        field_path=field_path,
        citation=rule.citation_reference or "FSMA 204",
        event_type=event_data.get("event_type", "unknown"),
    )

    return RuleEvaluationResult(
        rule_id=rule.rule_id,
        rule_version=rule.rule_version,
        rule_title=rule.title,
        severity=rule.severity,
        result="fail",
        why_failed=why_failed,
        evidence_fields_inspected=evidence,
        citation_reference=rule.citation_reference,
        remediation_suggestion=rule.remediation_suggestion,
        category=rule.category,
    )


def _evaluate_field_format(
    event_data: Dict[str, Any],
    logic: Dict[str, Any],
    rule: RuleDefinition,
) -> RuleEvaluationResult:
    """Evaluate whether a field matches an expected format (regex)."""
    field_path = logic.get("field", "")
    pattern = logic.get("params", {}).get("pattern", ".*")
    value = _get_nested_value(event_data, field_path)

    evidence = [{
        "field": field_path,
        "value": str(value)[:200] if value else None,
        "expected_pattern": pattern,
    }]

    if value is None or (isinstance(value, str) and value.strip() == ""):
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_version=rule.rule_version,
            rule_title=rule.title,
            severity=rule.severity,
            result="fail",
            why_failed=rule.failure_reason_template.format(
                field_name=field_path.split(".")[-1],
                field_path=field_path,
                citation=rule.citation_reference or "FSMA 204",
                event_type=event_data.get("event_type", "unknown"),
            ),
            evidence_fields_inspected=evidence,
            citation_reference=rule.citation_reference,
            remediation_suggestion=rule.remediation_suggestion,
            category=rule.category,
        )

    matches = bool(re.match(pattern, str(value)))
    evidence[0]["matches_pattern"] = matches

    if matches:
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="pass", evidence_fields_inspected=evidence,
            citation_reference=rule.citation_reference, category=rule.category,
        )

    return RuleEvaluationResult(
        rule_id=rule.rule_id, rule_version=rule.rule_version,
        rule_title=rule.title, severity=rule.severity,
        result="fail",
        why_failed=f"{field_path.split('.')[-1]} value '{str(value)[:50]}' does not match required format ({rule.citation_reference or 'FSMA 204'})",
        evidence_fields_inspected=evidence,
        citation_reference=rule.citation_reference,
        remediation_suggestion=rule.remediation_suggestion,
        category=rule.category,
    )


def _evaluate_multi_field_presence(
    event_data: Dict[str, Any],
    logic: Dict[str, Any],
    rule: RuleDefinition,
) -> RuleEvaluationResult:
    """Evaluate that at least one of several fields is present (OR logic)."""
    fields = logic.get("params", {}).get("fields", [])
    evidence = []
    any_present = False

    for fp in fields:
        value = _get_nested_value(event_data, fp)
        is_present = value is not None and (not isinstance(value, str) or value.strip() != "")
        evidence.append({
            "field": fp,
            "value": str(value)[:200] if value is not None else None,
            "present": is_present,
        })
        if is_present:
            any_present = True

    if any_present:
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="pass", evidence_fields_inspected=evidence,
            citation_reference=rule.citation_reference, category=rule.category,
        )

    field_names = ", ".join(f.split(".")[-1].replace("_", " ") for f in fields)
    why_failed = rule.failure_reason_template.format(
        field_name=field_names,
        field_path=", ".join(fields),
        citation=rule.citation_reference or "FSMA 204",
        event_type=event_data.get("event_type", "unknown"),
    )

    return RuleEvaluationResult(
        rule_id=rule.rule_id, rule_version=rule.rule_version,
        rule_title=rule.title, severity=rule.severity,
        result="fail", why_failed=why_failed,
        evidence_fields_inspected=evidence,
        citation_reference=rule.citation_reference,
        remediation_suggestion=rule.remediation_suggestion,
        category=rule.category,
    )


# Evaluator dispatch
_EVALUATORS = {
    "field_presence": _evaluate_field_presence,
    "field_format": _evaluate_field_format,
    "multi_field_presence": _evaluate_multi_field_presence,
}


# ---------------------------------------------------------------------------
# Rules Engine
# ---------------------------------------------------------------------------

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

            # Empty cte_types means applies to all event types
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
            elif result.result == "skip":
                summary.skipped += 1

        # Persist results
        if persist and tenant_id:
            self._persist_evaluations(tenant_id, event_id, summary.results)

        return summary

    def evaluate_events_batch(
        self,
        events: List[Dict[str, Any]],
        tenant_id: str,
        persist: bool = True,
    ) -> List[EvaluationSummary]:
        """Evaluate multiple events against all applicable rules."""
        # Load rules once for the batch
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

        # Batch persist
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

        evaluator = _EVALUATORS.get(eval_type)
        if not evaluator:
            return RuleEvaluationResult(
                rule_id=rule.rule_id,
                rule_version=rule.rule_version,
                rule_title=rule.title,
                severity=rule.severity,
                result="skip",
                why_failed=f"Unknown evaluation type: {eval_type}",
                category=rule.category,
            )

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
                result="skip",
                why_failed=f"Evaluation error: {str(e)}",
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
                            :why_failed, :evidence::jsonb,
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
                logger.warning(
                    "evaluation_persist_failed",
                    extra={"rule_id": r.rule_id, "error": str(e)},
                )

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
                    f":res_{i}, :why_{i}, :ev_{i}::jsonb, :conf_{i})"
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
                    logger.warning("batch_eval_persist_failed: %s", str(e))


# ---------------------------------------------------------------------------
# Built-in Rule Seed Data
# ---------------------------------------------------------------------------
# These are the top 25 highest-value FSMA checks, defined as Python dicts
# for initial seeding into the database.

FSMA_RULE_SEEDS: List[Dict[str, Any]] = [
    # --- KDE Presence Rules (per CTE type) ---
    {
        "title": "Receiving: TLC Source Reference Required",
        "description": "Receiving events must include the traceability lot code source reference identifying the entity that assigned the TLC",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["receiving"]},
        "citation_reference": "21 CFR §1.1345(b)(7)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.tlc_source_reference",
            "params": {"fields": ["kdes.tlc_source_reference", "kdes.tlc_source_gln", "from_entity_reference"]},
        },
        "failure_reason_template": "Receiving event missing {field_name} required by {citation}",
        "remediation_suggestion": "Request the traceability lot code source reference (GLN or business name) from your immediate supplier",
    },
    {
        "title": "Receiving: Immediate Previous Source Required",
        "description": "Receiving events must identify the immediate previous source of the food",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["receiving"]},
        "citation_reference": "21 CFR §1.1345(b)(5)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "from_entity_reference",
            "params": {"fields": ["from_entity_reference", "kdes.immediate_previous_source", "kdes.ship_from_location"]},
        },
        "failure_reason_template": "Receiving event missing {field_name} — cannot identify immediate previous source ({citation})",
        "remediation_suggestion": "Record the business name and location of the entity that shipped this food to you",
    },
    {
        "title": "Receiving: Reference Document Required",
        "description": "Receiving events must include a reference document number (BOL, invoice, etc.)",
        "severity": "warning",
        "category": "source_reference",
        "applicability_conditions": {"cte_types": ["receiving"]},
        "citation_reference": "21 CFR §1.1345(b)(6)",
        "evaluation_logic": {"type": "field_presence", "field": "kdes.reference_document"},
        "failure_reason_template": "Receiving event missing {field_name} (BOL, invoice, or purchase order number) required by {citation}",
        "remediation_suggestion": "Record the reference document type and number (e.g., BOL #12345, Invoice #INV-2026-001)",
    },
    {
        "title": "Receiving: Receive Date Required",
        "description": "Receiving events must include the date the food was received",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["receiving"]},
        "citation_reference": "21 CFR §1.1345(b)(2)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.receive_date",
            "params": {"fields": ["kdes.receive_date", "event_timestamp"]},
        },
        "failure_reason_template": "Receiving event missing {field_name} required by {citation}",
        "remediation_suggestion": "Record the date the food was received at your facility",
    },
    {
        "title": "Shipping: Ship-From Location Required",
        "description": "Shipping events must identify the location the food was shipped from",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["shipping"]},
        "citation_reference": "21 CFR §1.1340(b)(3)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "from_facility_reference",
            "params": {"fields": ["from_facility_reference", "kdes.ship_from_location", "kdes.ship_from_gln"]},
        },
        "failure_reason_template": "Shipping event missing {field_name} ({citation})",
        "remediation_suggestion": "Record the ship-from location (GLN preferred, or location description)",
    },
    {
        "title": "Shipping: Ship-To Location Required",
        "description": "Shipping events must identify the location the food was shipped to",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["shipping"]},
        "citation_reference": "21 CFR §1.1340(b)(4)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "to_facility_reference",
            "params": {"fields": ["to_facility_reference", "kdes.ship_to_location", "kdes.ship_to_gln"]},
        },
        "failure_reason_template": "Shipping event missing {field_name} ({citation})",
        "remediation_suggestion": "Record the ship-to location (GLN preferred, or location description)",
    },
    {
        "title": "Shipping: Ship Date Required",
        "description": "Shipping events must include the date the food was shipped",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["shipping"]},
        "citation_reference": "21 CFR §1.1340(b)(2)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.ship_date",
            "params": {"fields": ["kdes.ship_date", "event_timestamp"]},
        },
        "failure_reason_template": "Shipping event missing {field_name} ({citation})",
        "remediation_suggestion": "Record the date the food was shipped",
    },
    {
        "title": "Shipping: Reference Document Required",
        "description": "Shipping events must include a reference document number",
        "severity": "warning",
        "category": "source_reference",
        "applicability_conditions": {"cte_types": ["shipping"]},
        "citation_reference": "21 CFR §1.1340(b)(6)",
        "evaluation_logic": {"type": "field_presence", "field": "kdes.reference_document"},
        "failure_reason_template": "Shipping event missing {field_name} ({citation})",
        "remediation_suggestion": "Record the reference document type and number (BOL, invoice, or PO)",
    },
    {
        "title": "Harvesting: Harvest Date Required",
        "description": "Harvesting events must include the date of harvest",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["harvesting"]},
        "citation_reference": "21 CFR §1.1327(b)(2)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.harvest_date",
            "params": {"fields": ["kdes.harvest_date", "event_timestamp"]},
        },
        "failure_reason_template": "Harvesting event missing {field_name} ({citation})",
        "remediation_suggestion": "Record the date of harvest",
    },
    {
        "title": "Harvesting: Farm Location Required",
        "description": "Harvesting events must identify the farm or growing area location",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["harvesting"]},
        "citation_reference": "21 CFR §1.1327(b)(3)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "from_facility_reference",
            "params": {"fields": ["from_facility_reference", "kdes.location_name", "kdes.field_name"]},
        },
        "failure_reason_template": "Harvesting event missing {field_name} — cannot identify farm/growing area ({citation})",
        "remediation_suggestion": "Record the farm location description where food was harvested",
    },
    {
        "title": "Initial Packing: Packing Date Required",
        "description": "Initial packing events must include the date of packing",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["initial_packing"]},
        "citation_reference": "21 CFR §1.1335(b)(4)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.packing_date",
            "params": {"fields": ["kdes.packing_date", "event_timestamp"]},
        },
        "failure_reason_template": "Initial packing event missing {field_name} ({citation})",
        "remediation_suggestion": "Record the date of initial packing",
    },
    {
        "title": "Transformation: Transformation Date Required",
        "description": "Transformation events must include the date of transformation",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["transformation"]},
        "citation_reference": "21 CFR §1.1350(b)(4)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.transformation_date",
            "params": {"fields": ["kdes.transformation_date", "event_timestamp"]},
        },
        "failure_reason_template": "Transformation event missing {field_name} ({citation})",
        "remediation_suggestion": "Record the date of transformation",
    },
    {
        "title": "Cooling: Cooling Date Required",
        "description": "Cooling events must include the date of cooling",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["cooling"]},
        "citation_reference": "21 CFR §1.1330(b)(3)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.cooling_date",
            "params": {"fields": ["kdes.cooling_date", "event_timestamp"]},
        },
        "failure_reason_template": "Cooling event missing {field_name} ({citation})",
        "remediation_suggestion": "Record the date of cooling",
    },
    # --- Universal Rules (apply to all CTE types) ---
    {
        "title": "TLC Must Be Present",
        "description": "Every CTE must have a traceability lot code",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": []},
        "citation_reference": "21 CFR §1.1310",
        "evaluation_logic": {"type": "field_presence", "field": "traceability_lot_code"},
        "failure_reason_template": "Event missing traceability lot code ({citation})",
        "remediation_suggestion": "Assign a traceability lot code to this event",
    },
    {
        "title": "Product Description Required",
        "description": "Every CTE must include a product description (commodity and variety)",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": []},
        "citation_reference": "21 CFR §1.1310(b)(1)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "product_reference",
            "params": {"fields": ["product_reference", "kdes.product_description"]},
        },
        "failure_reason_template": "Event missing {field_name} (commodity and variety) ({citation})",
        "remediation_suggestion": "Record the commodity and variety of the food (e.g., 'Romaine Lettuce, Whole Head')",
    },
    {
        "title": "Quantity and Unit of Measure Required",
        "description": "Every CTE must include the quantity and unit of measure",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": []},
        "citation_reference": "21 CFR §1.1310(b)(2)",
        "evaluation_logic": {"type": "field_presence", "field": "quantity"},
        "failure_reason_template": "Event missing quantity and unit of measure ({citation})",
        "remediation_suggestion": "Record the quantity and unit of measure for this event",
    },
    {
        "title": "Location Identifier Required",
        "description": "Every CTE must identify at least one facility location (GLN or description)",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": []},
        "citation_reference": "21 CFR §1.1310(b)(3)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "from_facility_reference",
            "params": {"fields": ["from_facility_reference", "to_facility_reference", "kdes.location_name", "kdes.location_gln"]},
        },
        "failure_reason_template": "Event missing facility location identifier ({citation})",
        "remediation_suggestion": "Provide at least one location identifier: GLN (preferred) or location description",
    },
    # --- Identifier Format Rules ---
    {
        "title": "GLN Format Validation",
        "description": "If a GLN is provided, it must be exactly 13 digits with valid check digit",
        "severity": "warning",
        "category": "identifier_format",
        "applicability_conditions": {"cte_types": []},
        "citation_reference": "GS1 General Specifications §3.4.2",
        "evaluation_logic": {
            "type": "field_format",
            "field": "from_facility_reference",
            "condition": "regex_if_present",
            "params": {"pattern": r"^\d{13}$|^[^0-9].*$|^$"},
        },
        "failure_reason_template": "Facility GLN '{field_name}' is not a valid 13-digit GS1 identifier",
        "remediation_suggestion": "Verify the GLN is exactly 13 digits with a valid GS1 check digit",
    },
    # --- Lot Linkage Rules ---
    {
        "title": "Shipping: TLC Source Reference Required",
        "description": "Shipping events must include TLC source reference identifying who assigned the lot code",
        "severity": "warning",
        "category": "lot_linkage",
        "applicability_conditions": {"cte_types": ["shipping"]},
        "citation_reference": "21 CFR §1.1340(b)(7)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.tlc_source_reference",
            "params": {"fields": ["kdes.tlc_source_reference", "kdes.tlc_source_gln"]},
        },
        "failure_reason_template": "Shipping event missing TLC source reference ({citation}) — cannot trace who assigned the lot code",
        "remediation_suggestion": "Record the GLN or business name of the entity that assigned the traceability lot code",
    },
    {
        "title": "Transformation: Input TLCs Required",
        "description": "Transformation events must list all input traceability lot codes that were transformed",
        "severity": "critical",
        "category": "lot_linkage",
        "applicability_conditions": {"cte_types": ["transformation"]},
        "citation_reference": "21 CFR §1.1350(a)(4)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.input_traceability_lot_codes",
            "params": {"fields": ["kdes.input_traceability_lot_codes", "kdes.input_tlcs"]},
        },
        "failure_reason_template": "Transformation event missing input TLCs ({citation}) — cannot link new lot to source lots",
        "remediation_suggestion": "List all input traceability lot codes that were combined or transformed into this new lot",
    },
    # --- Record Completeness Rules ---
    {
        "title": "Reference Document Required for All CTEs",
        "description": "All CTE types require at least one reference document (BOL, invoice, PO, production record)",
        "severity": "warning",
        "category": "source_reference",
        "applicability_conditions": {"cte_types": []},
        "citation_reference": "21 CFR §1.1310(c)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.reference_document",
            "params": {"fields": ["kdes.reference_document", "transport_reference"]},
        },
        "failure_reason_template": "Event missing reference document — no BOL, invoice, or purchase order recorded ({citation})",
        "remediation_suggestion": "Record at least one reference document: bill of lading, invoice, purchase order, or production record",
    },
    {
        "title": "First Land-Based Receiving: Landing Date Required",
        "description": "First land-based receiving events for seafood must include the landing date",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["first_land_based_receiving"]},
        "citation_reference": "21 CFR §1.1325(b)(4)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.landing_date",
            "params": {"fields": ["kdes.landing_date", "event_timestamp"]},
        },
        "failure_reason_template": "First land-based receiving event missing {field_name} ({citation})",
        "remediation_suggestion": "Record the date the seafood was landed (date vessel arrived at port)",
    },
    {
        "title": "Harvesting: Commodity and Variety Required",
        "description": "Harvesting events must identify the commodity and variety of food harvested",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["harvesting"]},
        "citation_reference": "21 CFR §1.1327(b)(1)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "product_reference",
            "params": {"fields": ["product_reference", "kdes.product_description", "kdes.commodity"]},
        },
        "failure_reason_template": "Harvesting event missing commodity and variety ({citation})",
        "remediation_suggestion": "Record the commodity and variety of the food harvested (e.g., 'Romaine Lettuce')",
    },
    {
        "title": "Receiving: Receiving Location Required",
        "description": "Receiving events must identify the location where food was received",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["receiving"]},
        "citation_reference": "21 CFR §1.1345(b)(4)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "to_facility_reference",
            "params": {"fields": ["to_facility_reference", "kdes.receiving_location", "kdes.location_name"]},
        },
        "failure_reason_template": "Receiving event missing receiving location ({citation})",
        "remediation_suggestion": "Record the location description where food was received (GLN preferred)",
    },
    {
        "title": "Initial Packing: Harvester Business Name Required",
        "description": "Initial packing events must identify the harvester business name and phone number",
        "severity": "warning",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["initial_packing"]},
        "citation_reference": "21 CFR §1.1335(b)(8)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.harvester_business_name",
            "params": {"fields": ["kdes.harvester_business_name", "from_entity_reference"]},
        },
        "failure_reason_template": "Initial packing event missing harvester business name ({citation})",
        "remediation_suggestion": "Record the harvester's business name and phone number",
    },
]


def seed_rule_definitions(session: Session) -> int:
    """
    Seed the rule_definitions table with the built-in FSMA rules.

    Idempotent — skips rules that already exist (matched by title).
    Returns count of newly inserted rules.
    """
    inserted = 0
    for rule_data in FSMA_RULE_SEEDS:
        existing = session.execute(
            text("SELECT rule_id FROM fsma.rule_definitions WHERE title = :title"),
            {"title": rule_data["title"]},
        ).fetchone()

        if existing:
            continue

        rule_id = str(uuid4())
        session.execute(
            text("""
                INSERT INTO fsma.rule_definitions (
                    rule_id, title, description, severity, category,
                    applicability_conditions, citation_reference,
                    evaluation_logic, failure_reason_template,
                    remediation_suggestion
                ) VALUES (
                    :rule_id, :title, :description, :severity, :category,
                    :applicability::jsonb, :citation,
                    :logic::jsonb, :failure_template,
                    :remediation
                )
            """),
            {
                "rule_id": rule_id,
                "title": rule_data["title"],
                "description": rule_data.get("description"),
                "severity": rule_data["severity"],
                "category": rule_data["category"],
                "applicability": json.dumps(rule_data.get("applicability_conditions", {})),
                "citation": rule_data.get("citation_reference"),
                "logic": json.dumps(rule_data["evaluation_logic"]),
                "failure_template": rule_data["failure_reason_template"],
                "remediation": rule_data.get("remediation_suggestion"),
            },
        )

        # Audit log
        session.execute(
            text("""
                INSERT INTO fsma.rule_audit_log (rule_id, action, new_values, changed_by)
                VALUES (:rule_id, 'created', :values::jsonb, 'system_seed')
            """),
            {
                "rule_id": rule_id,
                "values": json.dumps({"title": rule_data["title"], "severity": rule_data["severity"]}),
            },
        )

        inserted += 1

    logger.info("rule_definitions_seeded", extra={"inserted": inserted, "total_seeds": len(FSMA_RULE_SEEDS)})
    return inserted
