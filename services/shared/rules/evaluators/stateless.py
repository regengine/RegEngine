"""
Stateless rule evaluators — 3-arg functions (event_data, logic, rule).

These evaluators check field presence and format on a single event
without querying the database.
"""

import re
from typing import Any, Dict, Optional, Tuple

from shared.rules.types import RuleDefinition, RuleEvaluationResult
from shared.rules.utils import get_nested_value
from shared.rules.uom import resolve_temperature_reading


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


def _coerce_float(value: Any) -> Optional[float]:
    """Best-effort coercion of a field value to float, returns None on failure."""
    if value is None:
        return None
    if isinstance(value, bool):
        # bool is a subclass of int — refuse it explicitly so a True/False
        # flag doesn't silently become 1.0/0.0 and slip past the range check.
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_numeric_value(
    event_data: Dict[str, Any],
    logic: Dict[str, Any],
) -> Tuple[Optional[float], Optional[str], Optional[str]]:
    """Resolve the numeric value to evaluate for ``numeric_range``.

    Returns ``(value, evidence_field, note)`` where:
      - ``value`` is the canonicalized number (None ⇒ nothing parseable)
      - ``evidence_field`` is the dotted path or KDE key the value came from
      - ``note`` is a human-readable qualifier ("converted from °F", etc.)

    The evaluator supports three layouts under ``logic.params``:

    1. ``source: "temperature"`` — delegate to :func:`resolve_temperature_reading`
       against ``kdes`` (default) or the event root. Value is returned in °C.
    2. A plain ``field: "<dotted.path>"`` — fetch and coerce to float. No unit
       translation; the caller is expected to name a field whose scale is
       known (e.g. ``kdes.cooling_duration_hours``).
    3. Neither ⇒ ``(None, None, None)``.
    """
    params = logic.get("params", {}) or {}
    source = params.get("source")

    if source == "temperature":
        # Pull from ``kdes`` by default — that is where FSMA 204 KDEs live.
        root_path = params.get("root", "kdes")
        root = (
            get_nested_value(event_data, root_path)
            if root_path
            else event_data
        )
        if not isinstance(root, dict):
            return None, root_path, None
        resolved = resolve_temperature_reading(root)
        if resolved is None:
            return None, root_path, None
        value_c, source_key = resolved
        note = f"normalized to °C from kdes.{source_key}"
        return value_c, f"{root_path}.{source_key}" if root_path else source_key, note

    field_path = logic.get("field") or params.get("field")
    if field_path:
        raw = get_nested_value(event_data, field_path)
        return _coerce_float(raw), field_path, None

    return None, None, None


def evaluate_numeric_range(
    event_data: Dict[str, Any],
    logic: Dict[str, Any],
    rule: RuleDefinition,
) -> RuleEvaluationResult:
    """Evaluate that a numeric reading falls within an inclusive [min, max] range.

    ``logic.params`` shape::

        {
          "source": "temperature",        # optional; omit for plain field
          "root":   "kdes",               # optional; only with source=temperature
          "min":    0.0,                  # optional (no lower bound if omitted)
          "max":    5.0,                  # optional (no upper bound if omitted)
          "unit":   "C"                   # optional; label only, for evidence/why
        }

    The fix for #1364 is twofold: (1) a missing field produces a FAIL, not a
    SKIP — silently passing when operators leave temperature blank would
    defeat the purpose of the rule. (2) ``source=temperature`` routes
    through :func:`resolve_temperature_reading` so °F and °C inputs are
    normalized before comparison.
    """
    params = logic.get("params", {}) or {}
    min_v = params.get("min")
    max_v = params.get("max")
    unit_label = params.get("unit") or "C"

    value, evidence_field, note = _resolve_numeric_value(event_data, logic)

    evidence = [{
        "field": evidence_field,
        "value": value,
        "expected_min": min_v,
        "expected_max": max_v,
        "unit": unit_label,
        "note": note,
    }]

    if value is None:
        # Missing / non-numeric ⇒ FAIL. Otherwise a blank field fail-opens
        # the cold-chain audit (see issue #1364).
        field_label = (evidence_field or "value").split(".")[-1].replace("_", " ")
        why_failed = rule.failure_reason_template.format(
            field_name=field_label,
            field_path=evidence_field or "",
            citation=rule.citation_reference or "FSMA 204",
            event_type=event_data.get("event_type", "unknown"),
            min=min_v,
            max=max_v,
            value="missing",
            unit=unit_label,
        ) if rule.failure_reason_template else (
            f"{field_label} missing — required for {rule.citation_reference or 'FSMA 204'} numeric-range check"
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

    below_min = min_v is not None and value < float(min_v)
    above_max = max_v is not None and value > float(max_v)

    if not below_min and not above_max:
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="pass", evidence_fields_inspected=evidence,
            citation_reference=rule.citation_reference,
            category=rule.category,
        )

    # Build a direction-specific why_failed so remediation is actionable.
    field_label = (evidence_field or "value").split(".")[-1].replace("_", " ")
    if below_min and above_max:
        direction = f"outside [{min_v}, {max_v}] {unit_label}"
    elif below_min:
        direction = f"below minimum {min_v} {unit_label}"
    else:
        direction = f"above maximum {max_v} {unit_label}"

    why_failed = rule.failure_reason_template.format(
        field_name=field_label,
        field_path=evidence_field or "",
        citation=rule.citation_reference or "FSMA 204",
        event_type=event_data.get("event_type", "unknown"),
        min=min_v,
        max=max_v,
        value=f"{value:.2f}",
        unit=unit_label,
    ) if rule.failure_reason_template else (
        f"{field_label} = {value:.2f} {unit_label} is {direction} "
        f"({rule.citation_reference or 'FSMA 204'})"
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
EVALUATORS = {
    "field_presence": evaluate_field_presence,
    "field_format": evaluate_field_format,
    "multi_field_presence": evaluate_multi_field_presence,
    # #1364 — numeric-range validation (e.g. COOLING temperature threshold).
    "numeric_range": evaluate_numeric_range,
}
