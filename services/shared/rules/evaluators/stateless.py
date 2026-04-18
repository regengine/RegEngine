"""
Stateless rule evaluators — 3-arg functions (event_data, logic, rule).

These evaluators check field presence and format on a single event
without querying the database.
"""

from typing import Any, Dict

from shared.rules.types import RuleDefinition, RuleEvaluationResult
from shared.rules.utils import get_nested_value
from shared.rules.identifiers import is_valid_gln, is_valid_gtin
from shared.rules.safe_regex import (
    INVALID_PATTERN,
    TIMEOUT,
    safe_match,
)
from shared.rules.uom import UnitConversionError, convert_temperature


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

    # #1356 — rule patterns come from a user-writable JSON column
    # (rule_definitions.evaluation_logic). A malicious or accidentally
    # pathological pattern must NOT hang a worker thread. safe_match
    # enforces: RE2 if available, catastrophic-shape rejection otherwise,
    # and a 100ms wall-clock budget.
    outcome = safe_match(pattern, str(value), timeout_ms=100)
    evidence[0]["matches_pattern"] = outcome.is_match()
    evidence[0]["regex_outcome"] = outcome.status

    if outcome.is_match():
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="pass", evidence_fields_inspected=evidence,
            citation_reference=rule.citation_reference, category=rule.category,
        )

    # #1356 — TIMEOUT / INVALID_PATTERN must fail-closed with a distinct
    # reason so downstream tooling can alert on DoS-bait rules without
    # confusing them with a legitimate format mismatch. The rule ITSELF
    # is broken — a regulatory stamp cannot rest on a rule that does not
    # evaluate deterministically.
    if outcome.status in (TIMEOUT, INVALID_PATTERN):
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="error",
            why_failed=(
                f"Rule '{rule.title}' regex could not be evaluated safely: "
                f"{outcome.status}"
                + (f" ({outcome.detail})" if outcome.detail else "")
            ),
            evidence_fields_inspected=evidence,
            citation_reference=rule.citation_reference,
            remediation_suggestion=(
                "Rewrite the rule pattern to avoid nested quantifiers "
                "(e.g. (a+)+), or install the `re2` Python binding for "
                "a linear-time regex backend."
            ),
            category=rule.category,
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


def evaluate_temperature_threshold(
    event_data: Dict[str, Any],
    logic: Dict[str, Any],
    rule: RuleDefinition,
) -> RuleEvaluationResult:
    """Validate a recorded temperature against a max/min threshold (#1364).

    Before this evaluator existed, the COOLING CTE rule only checked that
    ``kdes.cooling_date`` was present; it never looked at whether the
    recorded temperature was within the FDA's 41°F (5°C) cold-chain
    limit (21 CFR §1.1330(b)(6)).

    Logic configuration (``evaluation_logic.params``)::

        temperature_field   str  (required) dot-path to the numeric temp,
                                 e.g. "kdes.cooling_temperature"
        temperature_unit_field str (optional) dot-path to the unit
                                 string ("C" / "F" / "K"); defaults to
                                 params.default_unit.
        default_unit        str  (optional, default "F") unit used when
                                 the event omits a unit field.
        max_temperature     num  (optional) maximum allowed temperature
        min_temperature     num  (optional) minimum allowed temperature
        threshold_unit      str  (optional, default "F") unit for the
                                 max/min values in the rule definition.

    Missing temperature value → fail (temperature is a mandatory KDE
    when this rule is configured). Unknown unit → error (rule cannot
    evaluate). Value outside the [min, max] band → fail.
    """
    params = logic.get("params", {}) or {}
    temp_field = params.get("temperature_field")
    unit_field = params.get("temperature_unit_field")
    default_unit = str(params.get("default_unit", "F"))
    max_temp = params.get("max_temperature")
    min_temp = params.get("min_temperature")
    threshold_unit = str(params.get("threshold_unit", "F"))

    if not temp_field:
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="error",
            why_failed=(
                f"Rule '{rule.title}' (temperature_threshold) missing "
                "required params.temperature_field"
            ),
            category=rule.category,
        )

    raw_value = get_nested_value(event_data, temp_field)
    raw_unit = (
        get_nested_value(event_data, unit_field) if unit_field else None
    ) or default_unit

    if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="fail",
            why_failed=(
                f"Event missing required temperature field "
                f"'{temp_field}' ({rule.citation_reference or 'FSMA 204'})."
            ),
            evidence_fields_inspected=[{
                "temperature_field": temp_field,
                "value": None,
            }],
            citation_reference=rule.citation_reference,
            remediation_suggestion=rule.remediation_suggestion,
            category=rule.category,
        )

    try:
        value_num = float(raw_value)
    except (TypeError, ValueError):
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="fail",
            why_failed=(
                f"Temperature value {raw_value!r} is not numeric "
                f"({rule.citation_reference or 'FSMA 204'})."
            ),
            evidence_fields_inspected=[{
                "temperature_field": temp_field,
                "value": raw_value,
            }],
            citation_reference=rule.citation_reference,
            category=rule.category,
        )

    evidence = [{
        "temperature_field": temp_field,
        "recorded_value": value_num,
        "recorded_unit": raw_unit,
        "threshold_unit": threshold_unit,
        "max_temperature": max_temp,
        "min_temperature": min_temp,
    }]

    # Normalize the recorded value AND the thresholds to Celsius so we
    # don't compare apples (F) to oranges (C).
    try:
        recorded_c = convert_temperature(value_num, str(raw_unit), "C")
        max_c = (
            convert_temperature(float(max_temp), threshold_unit, "C")
            if max_temp is not None else None
        )
        min_c = (
            convert_temperature(float(min_temp), threshold_unit, "C")
            if min_temp is not None else None
        )
    except UnitConversionError as exc:
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="error",
            why_failed=(
                f"Rule '{rule.title}' could not interpret temperature unit: "
                f"{exc.reason}"
            ),
            evidence_fields_inspected=evidence,
            category=rule.category,
        )

    evidence[0]["recorded_value_c"] = recorded_c
    if max_c is not None:
        evidence[0]["max_temperature_c"] = max_c
    if min_c is not None:
        evidence[0]["min_temperature_c"] = min_c

    over_max = max_c is not None and recorded_c > max_c
    under_min = min_c is not None and recorded_c < min_c
    if over_max or under_min:
        bound = "above maximum" if over_max else "below minimum"
        threshold_display = f"{max_temp}°{threshold_unit}" if over_max else f"{min_temp}°{threshold_unit}"
        why = (
            f"Recorded temperature {value_num}°{raw_unit} ({recorded_c:.1f}°C) "
            f"is {bound} threshold of {threshold_display} for this CTE "
            f"({rule.citation_reference or 'FSMA 204'})."
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
        result="pass", evidence_fields_inspected=evidence,
        citation_reference=rule.citation_reference, category=rule.category,
    )


def evaluate_all_field_presence(
    event_data: Dict[str, Any],
    logic: Dict[str, Any],
    rule: RuleDefinition,
) -> RuleEvaluationResult:
    """Evaluate that EVERY listed field is present and non-empty (AND logic).

    Companion to ``multi_field_presence`` (which uses OR logic). Required
    for rules that name more than one KDE — e.g. #1358's
    "Quantity AND Unit of Measure Required" rule, which previously only
    checked quantity and let unit_of_measure slip past. Fail-closed: if
    ANY field is missing, the rule fails and the list of missing fields
    is included in ``why_failed`` so tenants know exactly what to add.
    """
    fields = logic.get("params", {}).get("fields", [])
    if not fields:
        # An empty all-of list would vacuously pass — treat that as a
        # misconfigured rule rather than a silent green stamp.
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="error",
            why_failed=(
                f"Rule '{rule.title}' uses all_field_presence with no fields "
                "configured — rule is misconfigured."
            ),
            category=rule.category,
        )

    evidence = []
    missing = []

    for fp in fields:
        value = get_nested_value(event_data, fp)
        is_present = value is not None and (
            not isinstance(value, str) or value.strip() != ""
        )
        evidence.append({
            "field": fp,
            "value": str(value)[:200] if value is not None else None,
            "present": is_present,
        })
        if not is_present:
            missing.append(fp)

    if not missing:
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="pass", evidence_fields_inspected=evidence,
            citation_reference=rule.citation_reference, category=rule.category,
        )

    missing_names = ", ".join(
        fp.split(".")[-1].replace("_", " ") for fp in missing
    )
    try:
        why_failed = rule.failure_reason_template.format(
            field_name=missing_names,
            field_path=", ".join(missing),
            citation=rule.citation_reference or "FSMA 204",
            event_type=event_data.get("event_type", "unknown"),
        )
    except KeyError:
        # Template didn't expect a placeholder we tried to fill — fall
        # back to a deterministic reason so the rule still produces a
        # usable why_failed.
        why_failed = (
            f"Event missing required field(s): {missing_names} "
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


def evaluate_gs1_identifier(
    event_data: Dict[str, Any],
    logic: Dict[str, Any],
    rule: RuleDefinition,
) -> RuleEvaluationResult:
    """Validate a GS1 identifier (GLN or GTIN) with a proper mod-10 check.

    The legacy ``field_format`` path validated GLNs with a regex
    ``^\\d{13}$|^[^0-9].*$|^$`` that passed empty strings and any
    non-numeric value (#1357). This evaluator enforces:

      - exactly 13 (GLN) or 8/12/13/14 (GTIN) numeric digits,
      - a matching GS1 mod-10 check digit.

    Presence semantics are controlled via ``params.condition``:

        required         — field MUST be present AND valid (default).
        required_if_present — missing field is a pass; if present, must be valid.

    Identifier kind is selected via ``params.kind`` (``"gln"`` | ``"gtin"``).
    Default is ``"gln"`` to match existing rule definitions.
    """
    field_path = logic.get("field", "")
    params = logic.get("params", {}) or {}
    kind = str(params.get("kind", "gln")).lower()
    condition = str(params.get("condition", "required")).lower()
    value = get_nested_value(event_data, field_path)

    evidence = [{
        "field": field_path,
        "value": str(value)[:200] if value is not None else None,
        "expected_identifier": kind,
        "condition": condition,
    }]

    # Presence gate. required_if_present treats missing as a pass; the
    # "field must be present" constraint belongs in a separate
    # field_presence rule so the two concerns don't tangle.
    is_missing = value is None or (isinstance(value, str) and value.strip() == "")
    if is_missing:
        if condition == "required_if_present":
            evidence[0]["check"] = "absent_ok"
            return RuleEvaluationResult(
                rule_id=rule.rule_id, rule_version=rule.rule_version,
                rule_title=rule.title, severity=rule.severity,
                result="pass", evidence_fields_inspected=evidence,
                citation_reference=rule.citation_reference, category=rule.category,
            )
        # required — missing is a fail.
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="fail",
            why_failed=rule.failure_reason_template.format(
                field_name=field_path.split(".")[-1],
                field_path=field_path,
                citation=rule.citation_reference or "GS1 General Specifications §3.4.2",
                event_type=event_data.get("event_type", "unknown"),
            ),
            evidence_fields_inspected=evidence,
            citation_reference=rule.citation_reference,
            remediation_suggestion=rule.remediation_suggestion,
            category=rule.category,
        )

    validator = is_valid_gln if kind == "gln" else is_valid_gtin
    valid = validator(str(value))
    evidence[0]["valid"] = valid

    if valid:
        return RuleEvaluationResult(
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            rule_title=rule.title, severity=rule.severity,
            result="pass", evidence_fields_inspected=evidence,
            citation_reference=rule.citation_reference, category=rule.category,
        )

    # Identify the specific reason for the fail message — "not 13 digits"
    # vs "check digit mismatch" is useful for tenants debugging bad data.
    s = str(value)
    expected_len = 13 if kind == "gln" else "8/12/13/14"
    if kind == "gln":
        length_ok = len(s) == 13
    else:
        length_ok = len(s) in {8, 12, 13, 14}
    if not s.isdigit():
        reason_detail = "value is not numeric"
    elif not length_ok:
        reason_detail = f"expected {expected_len} digits, got {len(s)}"
    else:
        reason_detail = "check digit mismatch"

    return RuleEvaluationResult(
        rule_id=rule.rule_id, rule_version=rule.rule_version,
        rule_title=rule.title, severity=rule.severity,
        result="fail",
        why_failed=(
            f"{field_path.split('.')[-1]} value '{s[:50]}' is not a valid "
            f"{kind.upper()} — {reason_detail} "
            f"({rule.citation_reference or 'GS1 General Specifications §3.4.2'})."
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
    "all_field_presence": evaluate_all_field_presence,
    "gs1_identifier": evaluate_gs1_identifier,
    "temperature_threshold": evaluate_temperature_threshold,
}
