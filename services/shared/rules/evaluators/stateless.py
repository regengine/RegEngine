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
    "gs1_identifier": evaluate_gs1_identifier,
}
