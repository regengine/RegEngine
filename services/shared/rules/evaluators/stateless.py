"""
Stateless rule evaluators — 3-arg functions (event_data, logic, rule).

These evaluators check field presence and format on a single event
without querying the database.
"""

import re
from typing import Any, Dict, Optional, Tuple

from shared.fsma_validation import verify_gs1_check_digit
from shared.rules.types import RuleDefinition, RuleEvaluationResult
from shared.rules.uom import resolve_temperature_reading
from shared.rules.utils import get_nested_value


def evaluate_field_presence(
    event_data: Dict[str, Any],
    logic: Dict[str, Any],
    rule: RuleDefinition,
) -> RuleEvaluationResult:
    """Evaluate whether a required field is present and non-empty."""
    field_path = logic.get("field", "")
    value = get_nested_value(event_data, field_path)

    is_present = value is not None and (not isinstance(value, str) or value.strip() != "")

    evidence = [
        {
            "field": field_path,
            "value": str(value)[:200] if value is not None else None,
            "expected": "not_empty",
            "actual_present": is_present,
        }
    ]

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

    evidence = [
        {
            "field": field_path,
            "value": str(value)[:200] if value else None,
            "expected_pattern": pattern,
        }
    ]

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
            rule_id=rule.rule_id,
            rule_version=rule.rule_version,
            rule_title=rule.title,
            severity=rule.severity,
            result="pass",
            evidence_fields_inspected=evidence,
            citation_reference=rule.citation_reference,
            category=rule.category,
        )

    return RuleEvaluationResult(
        rule_id=rule.rule_id,
        rule_version=rule.rule_version,
        rule_title=rule.title,
        severity=rule.severity,
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
    """Evaluate presence across several fields.

    ``params.require`` selects the mode:
      - ``"any"`` (default) — at least one field present (OR logic)
      - ``"all"`` — every field present (AND logic), for rules whose
        title/failure text promises multiple KDEs (#3041)
    """
    params = logic.get("params", {})
    fields = params.get("fields", [])
    require_all = params.get("require") == "all"
    evidence = []
    present_flags = []
    missing_fields = []

    for fp in fields:
        value = get_nested_value(event_data, fp)
        is_present = value is not None and (not isinstance(value, str) or value.strip() != "")
        evidence.append(
            {
                "field": fp,
                "value": str(value)[:200] if value is not None else None,
                "present": is_present,
            }
        )
        present_flags.append(is_present)
        if not is_present:
            missing_fields.append(fp)

    passed = all(present_flags) if require_all else any(present_flags)

    if passed:
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

    # In require-all mode name only the missing fields so the operator
    # knows exactly what to supply; in any-of mode name every alternate.
    failed_fields = missing_fields if require_all else fields
    field_names = ", ".join(f.split(".")[-1].replace("_", " ") for f in failed_fields)
    why_failed = rule.failure_reason_template.format(
        field_name=field_names,
        field_path=", ".join(failed_fields),
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
        root = get_nested_value(event_data, root_path) if root_path else event_data
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

    evidence = [
        {
            "field": evidence_field,
            "value": value,
            "expected_min": min_v,
            "expected_max": max_v,
            "unit": unit_label,
            "note": note,
        }
    ]

    if value is None:
        if params.get("missing_result") == "skip":
            return RuleEvaluationResult(
                rule_id=rule.rule_id,
                rule_version=rule.rule_version,
                rule_title=rule.title,
                severity=rule.severity,
                result="skip",
                evidence_fields_inspected=evidence,
                citation_reference=rule.citation_reference,
                category=rule.category,
            )
        # Missing / non-numeric ⇒ FAIL. Otherwise a blank field fail-opens
        # the cold-chain audit (see issue #1364).
        field_label = (evidence_field or "value").split(".")[-1].replace("_", " ")
        why_failed = (
            rule.failure_reason_template.format(
                field_name=field_label,
                field_path=evidence_field or "",
                citation=rule.citation_reference or "FSMA 204",
                event_type=event_data.get("event_type", "unknown"),
                min=min_v,
                max=max_v,
                value="missing",
                unit=unit_label,
            )
            if rule.failure_reason_template
            else (f"{field_label} missing — required for {rule.citation_reference or 'FSMA 204'} numeric-range check")
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

    below_min = min_v is not None and value < float(min_v)
    above_max = max_v is not None and value > float(max_v)

    if not below_min and not above_max:
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

    # Build a direction-specific why_failed so remediation is actionable.
    field_label = (evidence_field or "value").split(".")[-1].replace("_", " ")
    if below_min and above_max:
        direction = f"outside [{min_v}, {max_v}] {unit_label}"
    elif below_min:
        direction = f"below minimum {min_v} {unit_label}"
    else:
        direction = f"above maximum {max_v} {unit_label}"

    why_failed = (
        rule.failure_reason_template.format(
            field_name=field_label,
            field_path=evidence_field or "",
            citation=rule.citation_reference or "FSMA 204",
            event_type=event_data.get("event_type", "unknown"),
            min=min_v,
            max=max_v,
            value=f"{value:.2f}",
            unit=unit_label,
        )
        if rule.failure_reason_template
        else (f"{field_label} = {value:.2f} {unit_label} is {direction} ({rule.citation_reference or 'FSMA 204'})")
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


def evaluate_gs1_check_digit(
    event_data: Dict[str, Any],
    logic: Dict[str, Any],
    rule: RuleDefinition,
) -> RuleEvaluationResult:
    """Verify a GS1 identifier's check digit when one is provided (#3041).

    Semantics (if-present):
      - field missing/empty        → skip (presence is another rule's job)
      - value contains non-digits  → skip (a location *description*, not a GLN)
      - all digits                 → must be exactly 13 digits with a valid
                                     GS1 mod-10 check digit, else fail

    The old seed used ``field_format`` with a regex that accepted any 13
    digits — the check digit the rule promised was never verified.
    """
    field_path = logic.get("field", "")
    value = get_nested_value(event_data, field_path)
    raw = str(value).strip() if value is not None else ""

    evidence = [
        {
            "field": field_path,
            "value": raw[:200] if raw else None,
            "expected": "13-digit GS1 identifier with valid check digit",
        }
    ]

    if not raw or not raw.isdigit():
        evidence[0]["note"] = "no numeric identifier provided — check digit not applicable"
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_version=rule.rule_version,
            rule_title=rule.title,
            severity=rule.severity,
            result="skip",
            evidence_fields_inspected=evidence,
            citation_reference=rule.citation_reference,
            category=rule.category,
        )

    valid = len(raw) == 13 and verify_gs1_check_digit(raw)
    evidence[0]["check_digit_valid"] = valid

    if valid:
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

    reason = "wrong length" if len(raw) != 13 else "invalid GS1 check digit"
    return RuleEvaluationResult(
        rule_id=rule.rule_id,
        rule_version=rule.rule_version,
        rule_title=rule.title,
        severity=rule.severity,
        result="fail",
        why_failed=(
            f"{field_path.split('.')[-1]} value '{raw[:50]}' is not a valid GS1 identifier "
            f"({reason}) — {rule.citation_reference or 'GS1 General Specifications'}"
        ),
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
    # #3041 — real GS1 check-digit verification for provided GLNs.
    "gs1_check_digit": evaluate_gs1_check_digit,
}
