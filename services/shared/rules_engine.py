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
from datetime import date, datetime
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


# Evaluator dispatch — stateless (3-arg: event_data, logic, rule)
_EVALUATORS = {
    "field_presence": _evaluate_field_presence,
    "field_format": _evaluate_field_format,
    "multi_field_presence": _evaluate_multi_field_presence,
}


# ---------------------------------------------------------------------------
# Relational Evaluators — cross-event validation (4-arg: + session)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Unit of Measure Conversion Table
# ---------------------------------------------------------------------------
# Converts common food industry units to a canonical base unit (lbs).
# Used by mass balance to compare quantities across different UOMs.

_UOM_TO_LBS: Dict[str, float] = {
    # Weight (already in lbs)
    "lbs": 1.0,
    "lb": 1.0,
    "pound": 1.0,
    "pounds": 1.0,
    # Kilograms
    "kg": 2.20462,
    "kgs": 2.20462,
    "kilogram": 2.20462,
    "kilograms": 2.20462,
    # Ounces
    "oz": 0.0625,
    "ounce": 0.0625,
    "ounces": 0.0625,
    # Tons
    "ton": 2000.0,
    "tons": 2000.0,
    "short_ton": 2000.0,
    "metric_ton": 2204.62,
    "mt": 2204.62,
    # Produce containers (industry standard approximations)
    "case": 24.0,
    "cases": 24.0,
    "cs": 24.0,
    "carton": 24.0,
    "cartons": 24.0,
    "bin": 800.0,
    "bins": 800.0,
    "pallet": 2000.0,
    "pallets": 2000.0,
    "crate": 40.0,
    "crates": 40.0,
    "box": 24.0,
    "boxes": 24.0,
    "bag": 5.0,
    "bags": 5.0,
    "bunch": 1.5,
    "bunches": 1.5,
    "head": 2.0,
    "heads": 2.0,
    "each": 1.0,
    "ea": 1.0,
    "unit": 1.0,
    "units": 1.0,
    "piece": 1.0,
    "pieces": 1.0,
    "pc": 1.0,
    "pcs": 1.0,
}


def _normalize_to_lbs(quantity: float, uom: str) -> Optional[float]:
    """Convert a quantity to lbs using the UOM lookup table.

    Returns None if the UOM is not recognized.
    """
    uom_key = uom.lower().strip().rstrip(".")
    factor = _UOM_TO_LBS.get(uom_key)
    if factor is None:
        return None
    return quantity * factor


# CTE lifecycle ordering per FSMA 204 supply chain flow
_CTE_LIFECYCLE_ORDER = {
    "harvesting": 0,
    "cooling": 1,
    "initial_packing": 2,
    "first_land_based_receiving": 3,
    "transformation": 4,
    "shipping": 5,
    "receiving": 6,
}


def _fetch_related_events(
    session: Session,
    traceability_lot_code: str,
    tenant_id: str,
    exclude_event_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Fetch all ACTIVE events for the same TLC + tenant.

    Returns list of dicts with event_id, event_type, event_timestamp,
    product_reference, quantity, unit_of_measure.
    """
    query = text("""
        SELECT event_id, event_type, event_timestamp,
               product_reference, quantity, unit_of_measure
        FROM fsma.traceability_events
        WHERE traceability_lot_code = :tlc
          AND tenant_id = :tenant_id
          AND status = 'active'
          AND (:exclude_id IS NULL OR event_id != CAST(:exclude_id AS uuid))
        ORDER BY event_timestamp ASC
    """)
    rows = session.execute(query, {
        "tlc": traceability_lot_code,
        "tenant_id": tenant_id,
        "exclude_id": exclude_event_id,
    }).fetchall()

    return [
        {
            "event_id": str(r[0]),
            "event_type": r[1],
            "event_timestamp": r[2],
            "product_reference": r[3],
            "quantity": float(r[4]) if r[4] is not None else None,
            "unit_of_measure": r[5],
        }
        for r in rows
    ]


def _evaluate_temporal_order(
    event_data: Dict[str, Any],
    logic: Dict[str, Any],
    rule: RuleDefinition,
    session: Session,
) -> RuleEvaluationResult:
    """Detect chronology paradoxes — e.g. shipping before harvesting."""
    tlc = event_data.get("traceability_lot_code", "")
    tenant_id = event_data.get("tenant_id", "")
    event_id = event_data.get("event_id", "")

    if not tlc or not tenant_id:
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="skip", why_failed="Missing TLC or tenant_id for temporal check",
            category=rule.category,
        )

    related = _fetch_related_events(session, tlc, str(tenant_id), str(event_id))
    if not related:
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="pass", category=rule.category,
            evidence_fields_inspected=[{"note": "No related events for TLC", "tlc": tlc}],
        )

    # Build timeline: current event + related events
    current_type = event_data.get("event_type", "")
    current_ts = event_data.get("event_timestamp")
    if isinstance(current_ts, str):
        current_ts = datetime.fromisoformat(current_ts.replace("Z", "+00:00"))

    current_stage = _CTE_LIFECYCLE_ORDER.get(current_type)
    if current_stage is None:
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="skip", why_failed=f"Unknown CTE type: {current_type}",
            category=rule.category,
        )

    # Check each related event for chronology violations
    violations = []
    for evt in related:
        other_type = evt["event_type"]
        other_stage = _CTE_LIFECYCLE_ORDER.get(other_type)
        if other_stage is None:
            continue

        other_ts = evt["event_timestamp"]
        if isinstance(other_ts, str):
            other_ts = datetime.fromisoformat(other_ts.replace("Z", "+00:00"))

        # Lifecycle-earlier stage should have an earlier-or-equal timestamp
        if other_stage < current_stage and other_ts > current_ts:
            violations.append({
                "earlier_stage": other_type,
                "earlier_timestamp": str(other_ts),
                "later_stage": current_type,
                "later_timestamp": str(current_ts),
                "event_id": evt["event_id"],
            })
        elif other_stage > current_stage and other_ts < current_ts:
            violations.append({
                "earlier_stage": current_type,
                "earlier_timestamp": str(current_ts),
                "later_stage": other_type,
                "later_timestamp": str(other_ts),
                "event_id": evt["event_id"],
            })

    if violations:
        v = violations[0]
        why = (
            f"Chronology paradox for TLC '{tlc}': {v['later_stage']} "
            f"(at {v['later_timestamp']}) occurs before {v['earlier_stage']} "
            f"(at {v['earlier_timestamp']}). "
            f"CTE events must follow the supply chain lifecycle order "
            f"({rule.citation_reference or '21 CFR §1.1310'})."
        )
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="fail", why_failed=why,
            evidence_fields_inspected=violations,
            citation_reference=rule.citation_reference,
            remediation_suggestion=rule.remediation_suggestion,
            category=rule.category,
        )

    return RuleEvaluationResult(
        rule_id=rule.rule_id, rule_version=rule.rule_version,
        rule_title=rule.title, severity=rule.severity,
        result="pass", category=rule.category,
        evidence_fields_inspected=[{
            "tlc": tlc, "events_checked": len(related),
            "current_stage": current_type,
        }],
    )


def _evaluate_identity_consistency(
    event_data: Dict[str, Any],
    logic: Dict[str, Any],
    rule: RuleDefinition,
    session: Session,
) -> RuleEvaluationResult:
    """Detect product identity drift — same TLC changing product mid-chain."""
    tlc = event_data.get("traceability_lot_code", "")
    tenant_id = event_data.get("tenant_id", "")
    event_id = event_data.get("event_id", "")
    current_product = event_data.get("product_reference")

    if not current_product or not tlc or not tenant_id:
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="skip",
            why_failed="Missing product_reference, TLC, or tenant_id for identity check",
            category=rule.category,
        )

    related = _fetch_related_events(session, tlc, str(tenant_id), str(event_id))
    if not related:
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="pass", category=rule.category,
            evidence_fields_inspected=[{"note": "No related events for TLC", "tlc": tlc}],
        )

    normalized_current = " ".join(current_product.strip().lower().split())
    mismatches = []

    for evt in related:
        other_product = evt.get("product_reference")
        if not other_product:
            continue
        normalized_other = " ".join(other_product.strip().lower().split())
        if normalized_other != normalized_current:
            mismatches.append({
                "event_id": evt["event_id"],
                "event_type": evt["event_type"],
                "product_reference": other_product,
                "current_product": current_product,
            })

    if mismatches:
        m = mismatches[0]
        why = (
            f"Product identity changed for TLC '{tlc}': "
            f"'{m['product_reference']}' (at {m['event_type']}) vs "
            f"'{current_product}' (current event). "
            f"The same TLC must refer to the same product throughout the supply chain "
            f"({rule.citation_reference or '21 CFR §1.1310(a)'})."
        )
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="fail", why_failed=why,
            evidence_fields_inspected=mismatches,
            citation_reference=rule.citation_reference,
            remediation_suggestion=rule.remediation_suggestion,
            category=rule.category,
        )

    return RuleEvaluationResult(
        rule_id=rule.rule_id, rule_version=rule.rule_version,
        rule_title=rule.title, severity=rule.severity,
        result="pass", category=rule.category,
        evidence_fields_inspected=[{
            "tlc": tlc, "events_checked": len(related),
            "product": current_product,
        }],
    )


def _evaluate_mass_balance(
    event_data: Dict[str, Any],
    logic: Dict[str, Any],
    rule: RuleDefinition,
    session: Session,
) -> RuleEvaluationResult:
    """Detect mass balance violations — output exceeding input for same TLC."""
    tlc = event_data.get("traceability_lot_code", "")
    tenant_id = event_data.get("tenant_id", "")
    event_id = event_data.get("event_id", "")
    current_quantity = event_data.get("quantity")
    current_uom = event_data.get("unit_of_measure", "")
    current_type = event_data.get("event_type", "")

    if not tlc or not tenant_id or current_quantity is None:
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="skip",
            why_failed="Missing TLC, tenant_id, or quantity for mass balance check",
            category=rule.category,
        )

    related = _fetch_related_events(session, tlc, str(tenant_id), str(event_id))
    if not related:
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="pass", category=rule.category,
            evidence_fields_inspected=[{"note": "No related events for TLC", "tlc": tlc}],
        )

    tolerance_percent = logic.get("params", {}).get("tolerance_percent", 1.0)

    # Classify event types
    input_types = {"harvesting", "receiving", "first_land_based_receiving"}
    output_types = {"shipping"}

    total_input = 0.0
    total_output = 0.0
    units_seen = set()
    use_converted = False  # True if we successfully converted all to lbs

    # Collect all (qty, uom, event_type) tuples
    all_entries = [(float(current_quantity), current_uom, current_type)]
    if current_uom:
        units_seen.add(current_uom.lower().strip())

    for evt in related:
        evt_qty = evt.get("quantity")
        evt_uom = evt.get("unit_of_measure", "")
        if evt_qty is None:
            continue
        if evt_uom:
            units_seen.add(evt_uom.lower().strip())
        all_entries.append((float(evt_qty), evt_uom, evt["event_type"]))

    # Try UOM conversion if units differ
    if len(units_seen) > 1:
        converted_entries = []
        all_convertible = True
        for qty, uom, etype in all_entries:
            lbs = _normalize_to_lbs(qty, uom) if uom else None
            if lbs is None:
                all_convertible = False
                break
            converted_entries.append((lbs, etype))

        if all_convertible:
            use_converted = True
            for lbs, etype in converted_entries:
                if etype in input_types:
                    total_input += lbs
                elif etype in output_types:
                    total_output += lbs
        # else: fall through to mixed-unit warning below

    if not use_converted:
        # Same-unit path or unconvertible mixed units
        for qty, uom, etype in all_entries:
            if etype in input_types:
                total_input += qty
            elif etype in output_types:
                total_output += qty

    evidence = [{
        "tlc": tlc,
        "total_input": total_input,
        "total_output": total_output,
        "tolerance_percent": tolerance_percent,
        "units_seen": list(units_seen),
        "events_checked": len(related) + 1,
        "uom_converted": use_converted,
    }]

    # Mixed units that couldn't be converted — warn
    if len(units_seen) > 1 and not use_converted:
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="warn",
            why_failed=(
                f"Mass balance check inconclusive for TLC '{tlc}': "
                f"mixed units of measure detected ({', '.join(sorted(units_seen))}) "
                f"and not all could be converted. "
                f"Cannot reliably compare input ({total_input}) vs output ({total_output})."
            ),
            evidence_fields_inspected=evidence,
            citation_reference=rule.citation_reference,
            category=rule.category,
        )

    # No input events yet — can't validate
    if total_input == 0 and total_output > 0:
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="warn",
            why_failed=(
                f"Mass balance check for TLC '{tlc}': "
                f"output quantity ({total_output}) recorded but no input events found. "
                f"Input events (harvesting/receiving) may not yet be recorded."
            ),
            evidence_fields_inspected=evidence,
            citation_reference=rule.citation_reference,
            category=rule.category,
        )

    # Check: output must not exceed input + tolerance
    max_allowed = total_input * (1 + tolerance_percent / 100)
    if total_output > max_allowed:
        why = (
            f"Mass balance violation for TLC '{tlc}': "
            f"total output ({total_output}) exceeds total input ({total_input}) "
            f"by more than {tolerance_percent}% tolerance "
            f"(max allowed: {max_allowed:.2f}). "
            f"({rule.citation_reference or '21 CFR §1.1310'})."
        )
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="fail", why_failed=why,
            evidence_fields_inspected=evidence,
            citation_reference=rule.citation_reference,
            remediation_suggestion=rule.remediation_suggestion,
            category=rule.category,
        )

    return RuleEvaluationResult(
        rule_id=rule.rule_id, rule_version=rule.rule_version,
        rule_title=rule.title, severity=rule.severity,
        result="pass", category=rule.category,
        evidence_fields_inspected=evidence,
    )


# Relational evaluator dispatch — 4-arg (event_data, logic, rule, session)
_RELATIONAL_EVALUATORS = {
    "temporal_order": _evaluate_temporal_order,
    "identity_consistency": _evaluate_identity_consistency,
    "mass_balance": _evaluate_mass_balance,
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
            elif result.result in ("skip", "error"):
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

        # Try stateless evaluators first
        evaluator = _EVALUATORS.get(eval_type)
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

        # Try relational evaluators (require DB session)
        relational_evaluator = _RELATIONAL_EVALUATORS.get(eval_type)
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
    # --- Relational Rules (cross-event validation) ---
    {
        "title": "Temporal Order: CTE Chronology Must Be Causal",
        "description": "CTE events for the same TLC must follow supply chain lifecycle order — harvesting before cooling before packing before shipping before receiving",
        "severity": "critical",
        "category": "temporal_ordering",
        "applicability_conditions": {"cte_types": ["shipping", "receiving", "transformation", "initial_packing", "cooling"]},
        "citation_reference": "21 CFR §1.1310",
        "evaluation_logic": {"type": "temporal_order"},
        "failure_reason_template": "Chronology paradox: {event_type} event timestamp violates supply chain lifecycle order for this TLC ({citation})",
        "remediation_suggestion": "Verify event timestamps — a later-stage CTE cannot occur before an earlier-stage CTE for the same traceability lot code",
    },
    {
        "title": "Identity Consistency: Product Must Not Change for Same TLC",
        "description": "The product description must remain consistent across all CTEs for the same traceability lot code (excluding transformation, which legitimately creates new products)",
        "severity": "warning",
        "category": "lot_linkage",
        "applicability_conditions": {"cte_types": ["harvesting", "cooling", "initial_packing", "first_land_based_receiving", "shipping", "receiving"]},
        "citation_reference": "21 CFR §1.1310(a)",
        "evaluation_logic": {"type": "identity_consistency"},
        "failure_reason_template": "Product identity changed for TLC: {event_type} event has a different product than prior events ({citation})",
        "remediation_suggestion": "Verify the product description matches across all events for this traceability lot code. If the product was legitimately transformed, use a transformation event",
    },
    {
        "title": "Mass Balance: Output Cannot Exceed Input for Same TLC",
        "description": "Total shipped/output quantity for a TLC cannot exceed total received/input quantity (within tolerance)",
        "severity": "critical",
        "category": "quantity_consistency",
        "applicability_conditions": {"cte_types": ["shipping", "transformation"]},
        "citation_reference": "21 CFR §1.1310",
        "evaluation_logic": {
            "type": "mass_balance",
            "params": {"tolerance_percent": 1.0},
        },
        "failure_reason_template": "Mass balance violation: output quantity exceeds input quantity for this TLC ({citation})",
        "remediation_suggestion": "Verify quantities — you cannot ship more than was received/harvested for the same traceability lot code. Check for data entry errors or missing input events",
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
                    CAST(:applicability AS jsonb), :citation,
                    CAST(:logic AS jsonb), :failure_template,
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
                VALUES (:rule_id, 'created', CAST(:values AS jsonb), 'system_seed')
            """),
            {
                "rule_id": rule_id,
                "values": json.dumps({"title": rule_data["title"], "severity": rule_data["severity"]}),
            },
        )

        inserted += 1

    logger.info("rule_definitions_seeded", extra={"inserted": inserted, "total_seeds": len(FSMA_RULE_SEEDS)})
    return inserted
