"""Regression tests for #1364 — ``numeric_range`` rule evaluator.

Before this fix the stateless evaluator dispatch table had only three
entries (field_presence, field_format, multi_field_presence). The
COOLING CTE seed could check that a temperature reading was *present*
but never that it was *at or below the cold-chain threshold* — a cooling
event with ``cooling_temperature=80`` (°F) passed compliance despite
being clearly out of spec.

The fix adds ``evaluate_numeric_range`` with a unit-aware comparison
path. These tests lock the behavior so future refactors don't
reintroduce silent fail-open paths.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict

import pytest

from shared.rules.evaluators.stateless import (
    EVALUATORS,
    evaluate_numeric_range,
)
from shared.rules.types import RuleDefinition, RuleEvaluationResult


# ---------------------------------------------------------------------------
# Rule factory — a RuleDefinition is a dataclass, not a Pydantic model.
# We build one with the defaults relevant to the evaluator under test.
# ---------------------------------------------------------------------------


def _rule(
    *,
    logic: Dict[str, Any],
    title: str = "Cooling: Achieved Temperature",
    severity: str = "critical",
    citation: str = "21 CFR \u00a71.1330(b)(5)",
    template: str = (
        "{field_name} value {value} is outside the allowed range "
        "(min={min}, max={max}) per {citation}"
    ),
) -> RuleDefinition:
    return RuleDefinition(
        rule_id="rule-temp-1",
        rule_version=1,
        title=title,
        description=None,
        severity=severity,
        category="kde_threshold",
        applicability_conditions={"cte_types": ["cooling"], "ftl_scope": ["ALL"]},
        citation_reference=citation,
        effective_date=date(2026, 1, 1),
        retired_date=None,
        evaluation_logic=logic,
        failure_reason_template=template,
        remediation_suggestion="Re-verify the reading and record its unit",
    )


def _event(**kdes) -> Dict[str, Any]:
    return {
        "event_type": "cooling",
        "traceability_lot_code": "TLC-1",
        "kdes": kdes,
    }


# ---------------------------------------------------------------------------
# Dispatch — the evaluator is registered under "numeric_range".
# ---------------------------------------------------------------------------


class TestDispatchRegistration_Issue1364:
    def test_numeric_range_registered(self):
        assert "numeric_range" in EVALUATORS
        assert EVALUATORS["numeric_range"] is evaluate_numeric_range

    def test_existing_evaluators_still_registered(self):
        # The additive change must not shadow the existing three.
        assert "field_presence" in EVALUATORS
        assert "field_format" in EVALUATORS
        assert "multi_field_presence" in EVALUATORS


# ---------------------------------------------------------------------------
# Basic in-range / out-of-range logic (no unit normalization).
# ---------------------------------------------------------------------------


class TestBasicNumericRange_Issue1364:
    def test_value_within_range_passes(self):
        logic = {
            "type": "numeric_range",
            "field": "kdes.ph",
            "params": {"min": 4.0, "max": 4.6},
        }
        rule = _rule(logic=logic, title="pH acidification gate")
        result = evaluate_numeric_range(_event(ph=4.3), logic, rule)
        assert result.result == "pass"

    def test_value_above_max_fails(self):
        logic = {
            "type": "numeric_range",
            "field": "kdes.ph",
            "params": {"min": 4.0, "max": 4.6},
        }
        result = evaluate_numeric_range(_event(ph=5.0), logic, _rule(logic=logic))
        assert result.result == "fail"
        assert "5.0" in (result.why_failed or "")

    def test_value_below_min_fails(self):
        logic = {
            "type": "numeric_range",
            "field": "kdes.ph",
            "params": {"min": 4.0, "max": 4.6},
        }
        result = evaluate_numeric_range(_event(ph=3.0), logic, _rule(logic=logic))
        assert result.result == "fail"

    def test_inclusive_on_both_bounds(self):
        """min/max must be inclusive — 5.0 °C at a 5.0 °C ceiling passes."""
        logic = {"type": "numeric_range", "field": "kdes.x", "params": {"min": 1.0, "max": 5.0}}
        rule = _rule(logic=logic)
        assert evaluate_numeric_range(_event(x=1.0), logic, rule).result == "pass"
        assert evaluate_numeric_range(_event(x=5.0), logic, rule).result == "pass"
        # Just beyond either bound must fail.
        assert evaluate_numeric_range(_event(x=0.999), logic, rule).result == "fail"
        assert evaluate_numeric_range(_event(x=5.001), logic, rule).result == "fail"

    def test_only_max_specified_acts_as_ceiling(self):
        logic = {"type": "numeric_range", "field": "kdes.x", "params": {"max": 5.0}}
        rule = _rule(logic=logic)
        assert evaluate_numeric_range(_event(x=-1000), logic, rule).result == "pass"
        assert evaluate_numeric_range(_event(x=5.0), logic, rule).result == "pass"
        assert evaluate_numeric_range(_event(x=5.001), logic, rule).result == "fail"

    def test_only_min_specified_acts_as_floor(self):
        logic = {"type": "numeric_range", "field": "kdes.x", "params": {"min": 0.0}}
        rule = _rule(logic=logic)
        assert evaluate_numeric_range(_event(x=0.0), logic, rule).result == "pass"
        assert evaluate_numeric_range(_event(x=-0.001), logic, rule).result == "fail"


# ---------------------------------------------------------------------------
# Missing / non-numeric field handling.
# ---------------------------------------------------------------------------


class TestMissingOrBadFieldValue_Issue1364:
    def test_missing_field_fails_not_skips(self):
        """A numeric_range rule exists because the value is *required*
        in range. Silently skipping when the field is absent would
        fail-open on the most common regression (KDE simply not emitted)."""
        logic = {"type": "numeric_range", "field": "kdes.temperature", "params": {"max": 5}}
        result = evaluate_numeric_range(_event(), logic, _rule(logic=logic))
        assert result.result == "fail"

    @pytest.mark.parametrize("bad", ["not-a-number", True, False, [], {}])
    def test_non_numeric_field_value_fails(self, bad):
        logic = {"type": "numeric_range", "field": "kdes.x", "params": {"max": 5}}
        result = evaluate_numeric_range(_event(x=bad), logic, _rule(logic=logic))
        assert result.result == "fail"

    def test_numeric_string_value_is_coerced(self):
        # Ingestion pipelines sometimes deliver numbers as JSON strings
        # ("5.0" not 5.0). Accepting clean float-parseable strings
        # avoids a spurious fail on perfectly valid data.
        logic = {"type": "numeric_range", "field": "kdes.x", "params": {"max": 5}}
        rule = _rule(logic=logic)
        assert evaluate_numeric_range(_event(x="4.8"), logic, rule).result == "pass"
        assert evaluate_numeric_range(_event(x="6.0"), logic, rule).result == "fail"


# ---------------------------------------------------------------------------
# Rule-author misconfiguration.
# ---------------------------------------------------------------------------


class TestMisconfiguredRule_Issue1364:
    def test_neither_min_nor_max_is_error(self):
        """A rule with no bounds can't evaluate anything. Surface it
        as ``error`` (counts against compliance per #1354) rather than
        passing silently."""
        logic = {"type": "numeric_range", "field": "kdes.x", "params": {}}
        result = evaluate_numeric_range(_event(x=5), logic, _rule(logic=logic))
        assert result.result == "error"
        assert "min" in (result.why_failed or "").lower()

    def test_unknown_canonical_unit_is_error(self):
        """A numeric_range rule declaring ``unit=\"kelvin\"`` is a
        rule-author error — the engine doesn't know how to normalize
        non-temperature units. Fail closed so the miscategorization
        surfaces instead of lurking."""
        logic = {
            "type": "numeric_range",
            "field": "kdes.x",
            "params": {"max": 5, "unit": "kelvin", "unit_field": "kdes.x_unit"},
        }
        rule = _rule(logic=logic)
        result = evaluate_numeric_range(
            _event(x=5, x_unit="kelvin"), logic, rule
        )
        assert result.result == "error"


# ---------------------------------------------------------------------------
# Temperature-aware path — the heart of #1364.
# ---------------------------------------------------------------------------


class TestTemperatureAwareNormalization_Issue1364:
    def test_fahrenheit_reading_normalized_to_celsius(self):
        """Rule expresses max in °C; event carries reading in °F.
        The evaluator must convert before comparing."""
        logic = {
            "type": "numeric_range",
            "field": "kdes.cooling_temperature",
            "params": {"max": 5, "unit": "celsius", "unit_field": "kdes.cooling_temperature_unit"},
        }
        rule = _rule(logic=logic)
        # 41 °F == 5 °C — right at the ceiling, must pass.
        result = evaluate_numeric_range(
            _event(cooling_temperature=41.0, cooling_temperature_unit="F"),
            logic,
            rule,
        )
        assert result.result == "pass"

    def test_fahrenheit_above_ceiling_fails(self):
        logic = {
            "type": "numeric_range",
            "field": "kdes.cooling_temperature",
            "params": {"max": 5, "unit": "celsius", "unit_field": "kdes.cooling_temperature_unit"},
        }
        rule = _rule(logic=logic)
        # 80 °F ≈ 26.7 °C — well above the 5 °C cold-chain ceiling.
        # Pre-fix, presence-only rule passed this event.
        result = evaluate_numeric_range(
            _event(cooling_temperature=80.0, cooling_temperature_unit="°F"),
            logic,
            rule,
        )
        assert result.result == "fail"

    def test_celsius_reading_passes_through(self):
        logic = {
            "type": "numeric_range",
            "field": "kdes.cooling_temperature",
            "params": {"max": 5, "unit": "celsius", "unit_field": "kdes.cooling_temperature_unit"},
        }
        result = evaluate_numeric_range(
            _event(cooling_temperature=3.5, cooling_temperature_unit="C"),
            logic,
            _rule(logic=logic),
        )
        assert result.result == "pass"

    def test_missing_unit_fails_not_assumed_celsius_when_no_assumed_unit(self):
        """Without an ``assumed_unit`` fallback, a reading with no
        unit must fail closed — otherwise a raw "70" arriving from a
        Fahrenheit-only feed would silently pass as 70 °C."""
        logic = {
            "type": "numeric_range",
            "field": "kdes.cooling_temperature",
            "params": {"max": 5, "unit": "celsius", "unit_field": "kdes.cooling_temperature_unit"},
        }
        result = evaluate_numeric_range(
            _event(cooling_temperature=70.0),  # no unit KDE
            logic,
            _rule(logic=logic),
        )
        assert result.result == "fail"
        assert "unit" in (result.why_failed or "").lower()

    def test_assumed_unit_applies_when_unit_absent(self):
        """A rule can opt into a default unit for legacy feeds. Then
        a raw number is treated as °C (strict-but-not-fail-closed)."""
        logic = {
            "type": "numeric_range",
            "field": "kdes.cooling_temperature",
            "params": {
                "max": 5,
                "unit": "celsius",
                "unit_field": "kdes.cooling_temperature_unit",
                "assumed_unit": "celsius",
            },
        }
        # No unit KDE, but assumed_unit="celsius" — so 4.0 is 4 °C.
        result = evaluate_numeric_range(
            _event(cooling_temperature=4.0),
            logic,
            _rule(logic=logic),
        )
        assert result.result == "pass"

    def test_unknown_unit_token_fails(self):
        """A reading tagged "kelvin" can't be normalized into the
        rule's Celsius range — fail closed and say so."""
        logic = {
            "type": "numeric_range",
            "field": "kdes.cooling_temperature",
            "params": {"max": 5, "unit": "celsius", "unit_field": "kdes.cooling_temperature_unit"},
        }
        result = evaluate_numeric_range(
            _event(cooling_temperature=278.15, cooling_temperature_unit="kelvin"),
            logic,
            _rule(logic=logic),
        )
        assert result.result == "fail"


# ---------------------------------------------------------------------------
# Result shape — callers rely on citation/category/severity being set.
# ---------------------------------------------------------------------------


class TestResultShape_Issue1364:
    def test_result_preserves_rule_metadata(self):
        logic = {
            "type": "numeric_range",
            "field": "kdes.x",
            "params": {"max": 5},
        }
        rule = _rule(logic=logic, severity="critical", citation="21 CFR \u00a71.1330(b)(5)")
        result = evaluate_numeric_range(_event(x=6), logic, rule)
        assert result.severity == "critical"
        assert result.citation_reference == "21 CFR \u00a71.1330(b)(5)"
        assert result.category == "kde_threshold"
        assert result.rule_title == "Cooling: Achieved Temperature"

    def test_evidence_includes_field_and_bounds(self):
        logic = {
            "type": "numeric_range",
            "field": "kdes.cooling_temperature",
            "params": {"max": 5, "unit": "celsius", "unit_field": "kdes.cooling_temperature_unit"},
        }
        result = evaluate_numeric_range(
            _event(cooling_temperature=80.0, cooling_temperature_unit="F"),
            logic,
            _rule(logic=logic),
        )
        assert result.evidence_fields_inspected
        ev = result.evidence_fields_inspected[0]
        assert ev["field"] == "kdes.cooling_temperature"
        assert ev["max"] == 5
        assert ev["unit_expected"] == "celsius"
        assert ev["unit_actual"] == "F"
        # Normalized value should be recorded so ops can audit the
        # conversion without re-running the rule.
        assert "normalized_value" in ev
