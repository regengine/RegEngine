"""
Stateless rule evaluators — 3-arg functions (event_data, logic, rule).

These evaluators check field presence and format on a single event
without querying the database.
"""

import re
from typing import Any, Dict, Optional

from shared.rules.types import RuleDefinition, RuleEvaluationResult
from shared.rules.utils import get_nested_value
from shared.rules.uom import normalize_temperature_to_celsius


def evaluate_field_presence(
    event_data: Dict[str, Any],
    logic: Dict[str, Any],
    rule: RuleDefinition,
) -> RuleEvaluationResult:
    """Evaluate whether a required field is present and non-empty."""
    field_path = logic.get("field", "")
    value = get_nested_value(event_data, field_path)

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


def evaluate_field_format(
    event_data: Dict[str, Any],
    logic: Dict[str, Any],
    rule: RuleDefinition,
) -> RuleEvaluationResult:
    """Evaluate whether a field matches an expected format (regex)."""
    field_path = logic.get("field", "")
    pattern = logic.get("params", {}).get("pattern", ".*")
    value = get_nested_value(event_data, field_path)

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


def evaluate_multi_field_presence(
    event_data: Dict[str, Any],
    logic: Dict[str, Any],
    rule: RuleDefinition,
) -> RuleEvaluationResult:
    """Evaluate that at least one of several fields is present (OR logic)."""
    fields = logic.get("params", {}).get("fields", [])
    evidence = []
    any_present = False

    for fp in fields:
        value = get_nested_value(event_data, fp)
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


def _coerce_numeric(value: Any) -> Optional[float]:
    """Best-effort numeric coercion for rule evaluation.

    Accepts int/float directly, and strings that parse cleanly via
    ``float(...)``. Rejects booleans (because ``isinstance(True, int)``
    is True in Python and ``True == 1.0`` would silently pass a
    numeric_range rule). Returns ``None`` for anything else.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except (TypeError, ValueError):
            return None
    return None


def evaluate_numeric_range(
    event_data: Dict[str, Any],
    logic: Dict[str, Any],
    rule: RuleDefinition,
) -> RuleEvaluationResult:
    """Evaluate that a numeric field falls within ``[min, max]`` (inclusive).

    Logic schema
    ------------
    ``{
        "type": "numeric_range",
        "field": "kdes.temperature",     # required
        "params": {
            "min": 0,                    # optional; one of min/max required
            "max": 5,
            "unit": "celsius",           # optional; if set, the stored value
                                         # is first normalized via uom helpers
                                         # (currently only temperature is
                                         # unit-aware).
            "unit_field": "kdes.temperature_unit"   # optional; dot path to
                                                    # a sibling KDE carrying
                                                    # the reading's unit
                                                    # (typical shape in
                                                    # ingestion payloads)
        }
    }``

    Design notes
    ------------
    * **Missing field == fail** (not skip). A rule author writes a
      numeric_range rule because the value is *required* and must land
      in range; silently skipping would fail-open on the most common
      miscategorization (field simply absent).
    * **Unrecognized unit == fail** rather than pass. A reading in
      "kelvin" or "rankine" is outside our conversion table; treating
      it as compliant would defeat the threshold. The failure reason
      names the offending unit so the operator can fix the ingest.
    * **params.unit defaults to celsius** when absent — the rule author
      signals the range is unit-aware by providing ``unit_field`` or an
      explicit ``unit`` on each KDE. Without either, the numeric value
      is compared as-is (back-compat for non-temperature ranges like
      pH, moisture %, etc.).
    """
    field_path = logic.get("field", "")
    params = logic.get("params", {}) or {}
    min_value = params.get("min")
    max_value = params.get("max")
    canonical_unit = params.get("unit")
    unit_field = params.get("unit_field")

    # Allow rule authors to express either bound alone — e.g. "temp
    # must be <= 5°C" without a lower bound.
    if min_value is None and max_value is None:
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_version=rule.rule_version,
            rule_title=rule.title,
            severity=rule.severity,
            result="error",
            why_failed=(
                f"numeric_range rule '{rule.title}' has neither params.min "
                f"nor params.max — rule is unusable as configured"
            ),
            citation_reference=rule.citation_reference,
            category=rule.category,
        )

    raw_value = get_nested_value(event_data, field_path)
    numeric = _coerce_numeric(raw_value)

    evidence: Dict[str, Any] = {
        "field": field_path,
        "value": str(raw_value)[:200] if raw_value is not None else None,
        "min": min_value,
        "max": max_value,
        "unit_expected": canonical_unit,
    }

    if numeric is None:
        evidence["actual_present"] = False
        # Templates for numeric_range rules commonly reference
        # ``{value}``/``{min}``/``{max}`` — fall back to a descriptive
        # default when a placeholder isn't satisfiable here (field is
        # absent, so ``value`` may not exist).
        try:
            why_failed = rule.failure_reason_template.format(
                field_name=field_path.split(".")[-1].replace("_", " "),
                field_path=field_path,
                citation=rule.citation_reference or "FSMA 204",
                event_type=event_data.get("event_type", "unknown"),
                value=raw_value,
                min=min_value,
                max=max_value,
                unit=canonical_unit or "",
            )
        except (KeyError, IndexError):
            why_failed = (
                f"{field_path} is required by "
                f"{rule.citation_reference or 'FSMA 204'} "
                f"but was missing or not numeric"
            )
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_version=rule.rule_version,
            rule_title=rule.title,
            severity=rule.severity,
            result="fail",
            why_failed=why_failed,
            evidence_fields_inspected=[evidence],
            citation_reference=rule.citation_reference,
            remediation_suggestion=rule.remediation_suggestion,
            category=rule.category,
        )

    compare_value = numeric

    # Temperature-aware path: when the rule expresses its range in
    # Celsius (or Fahrenheit), pull the unit off the event and
    # normalize before comparing.
    if canonical_unit is not None:
        unit_token = None
        if unit_field:
            unit_token = get_nested_value(event_data, unit_field)
        if unit_token is None:
            unit_token = params.get("assumed_unit")

        if unit_token is None:
            # Unit is ambiguous. Fail rather than silently comparing
            # "70" as Celsius when it was actually Fahrenheit.
            evidence["unit_actual"] = None
            return RuleEvaluationResult(
                rule_id=rule.rule_id,
                rule_version=rule.rule_version,
                rule_title=rule.title,
                severity=rule.severity,
                result="fail",
                why_failed=(
                    f"{field_path} reading is missing its unit — cannot "
                    f"compare against {canonical_unit} range "
                    f"({rule.citation_reference or 'FSMA 204'})"
                ),
                evidence_fields_inspected=[evidence],
                citation_reference=rule.citation_reference,
                remediation_suggestion=(
                    rule.remediation_suggestion
                    or f"Record the unit (°F or °C) alongside {field_path}"
                ),
                category=rule.category,
            )

        evidence["unit_actual"] = str(unit_token)[:40]
        canonical_lower = str(canonical_unit).strip().lower()
        if canonical_lower in {"celsius", "c", "°c"}:
            normalized = normalize_temperature_to_celsius(numeric, str(unit_token))
        elif canonical_lower in {"fahrenheit", "f", "°f"}:
            celsius = normalize_temperature_to_celsius(numeric, str(unit_token))
            # Round-trip to the rule's canonical unit.
            normalized = (celsius * 9.0 / 5.0) + 32.0 if celsius is not None else None
        else:
            # Unknown canonical unit (not a temperature) — rule author
            # error; fail closed rather than guess.
            return RuleEvaluationResult(
                rule_id=rule.rule_id,
                rule_version=rule.rule_version,
                rule_title=rule.title,
                severity=rule.severity,
                result="error",
                why_failed=(
                    f"numeric_range rule '{rule.title}' declares unit="
                    f"{canonical_unit!r} which is not a supported "
                    f"temperature unit"
                ),
                evidence_fields_inspected=[evidence],
                citation_reference=rule.citation_reference,
                category=rule.category,
            )

        if normalized is None:
            return RuleEvaluationResult(
                rule_id=rule.rule_id,
                rule_version=rule.rule_version,
                rule_title=rule.title,
                severity=rule.severity,
                result="fail",
                why_failed=(
                    f"{field_path} unit {unit_token!r} is not a recognized "
                    f"temperature unit — cannot convert to {canonical_unit} "
                    f"({rule.citation_reference or 'FSMA 204'})"
                ),
                evidence_fields_inspected=[evidence],
                citation_reference=rule.citation_reference,
                remediation_suggestion=(
                    rule.remediation_suggestion
                    or "Record the temperature unit as °F or °C"
                ),
                category=rule.category,
            )
        compare_value = normalized
        evidence["normalized_value"] = compare_value

    below = min_value is not None and compare_value < float(min_value)
    above = max_value is not None and compare_value > float(max_value)

    if not below and not above:
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_version=rule.rule_version,
            rule_title=rule.title,
            severity=rule.severity,
            result="pass",
            evidence_fields_inspected=[evidence],
            citation_reference=rule.citation_reference,
            category=rule.category,
        )

    # Failure reason: prefer the rule's template so citations are
    # consistent, but fall back to a descriptive default when the
    # template is a simple presence phrase.
    direction = "below min" if below else "above max"
    default_reason = (
        f"{field_path} value {compare_value} is {direction} "
        f"(min={min_value}, max={max_value}"
        + (f", unit={canonical_unit}" if canonical_unit else "")
        + f") per {rule.citation_reference or 'FSMA 204'}"
    )
    try:
        why_failed = rule.failure_reason_template.format(
            field_name=field_path.split(".")[-1].replace("_", " "),
            field_path=field_path,
            citation=rule.citation_reference or "FSMA 204",
            event_type=event_data.get("event_type", "unknown"),
            value=compare_value,
            min=min_value,
            max=max_value,
            unit=canonical_unit or "",
        )
    except (KeyError, IndexError):
        why_failed = default_reason

    return RuleEvaluationResult(
        rule_id=rule.rule_id,
        rule_version=rule.rule_version,
        rule_title=rule.title,
        severity=rule.severity,
        result="fail",
        why_failed=why_failed,
        evidence_fields_inspected=[evidence],
        citation_reference=rule.citation_reference,
        remediation_suggestion=rule.remediation_suggestion,
        category=rule.category,
    )


# Evaluator dispatch — stateless (3-arg: event_data, logic, rule)
EVALUATORS = {
    "field_presence": evaluate_field_presence,
    "field_format": evaluate_field_format,
    "multi_field_presence": evaluate_multi_field_presence,
    "numeric_range": evaluate_numeric_range,
}
