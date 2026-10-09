"""Focused tests for shared.rules.evaluators.stateless.

Covers the five stateless (single-event, no-DB) evaluators and the
EVALUATORS dispatch table: field_presence, field_format,
multi_field_presence, numeric_range and gs1_check_digit.

Pure-Python; no database, no network, no external services.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict

from shared.rules.evaluators import stateless
from shared.rules.evaluators.stateless import (
    EVALUATORS,
    evaluate_field_format,
    evaluate_field_presence,
    evaluate_gs1_check_digit,
    evaluate_multi_field_presence,
    evaluate_numeric_range,
)
from shared.rules.types import RuleDefinition


def _make_rule(**overrides) -> RuleDefinition:
    defaults = dict(
        rule_id="rule-under-test",
        rule_version=1,
        title="Test Rule",
        description="A rule for the stateless evaluator tests",
        severity="critical",
        category="kde_presence",
        applicability_conditions={"cte_types": ["receiving"], "ftl_scope": ["ALL"]},
        citation_reference="21 CFR 1.1310",
        effective_date=date(2026, 1, 1),
        retired_date=None,
        evaluation_logic={},
        failure_reason_template="Missing {field_name} at {field_path} per {citation} for {event_type}",
        remediation_suggestion="Supply the field",
    )
    defaults.update(overrides)
    return RuleDefinition(**defaults)


def _make_event(**overrides) -> Dict[str, Any]:
    event = {
        "event_id": "evt-1",
        "event_type": "receiving",
        "kdes": {},
    }
    event.update(overrides)
    return event


class TestFieldPresence:
    def test_present_value_passes(self):
        event = _make_event(kdes={"lot_code": "ABC-123"})
        result = evaluate_field_presence(event, {"field": "kdes.lot_code"}, _make_rule())
        assert result.result == "pass"
        assert result.why_failed is None

    def test_missing_field_fails(self):
        event = _make_event()
        result = evaluate_field_presence(event, {"field": "kdes.lot_code"}, _make_rule())
        assert result.result == "fail"
        assert result.why_failed
        assert "lot code" in result.why_failed

    def test_zero_and_false_count_as_present(self):
        assert (
            evaluate_field_presence(_make_event(kdes={"qty": 0}), {"field": "kdes.qty"}, _make_rule()).result == "pass"
        )
        assert (
            evaluate_field_presence(_make_event(kdes={"flag": False}), {"field": "kdes.flag"}, _make_rule()).result
            == "pass"
        )

    def test_blank_string_and_empty_list_count_as_absent(self):
        assert (
            evaluate_field_presence(_make_event(kdes={"a": "   "}), {"field": "kdes.a"}, _make_rule()).result == "fail"
        )
        assert evaluate_field_presence(_make_event(kdes={"b": []}), {"field": "kdes.b"}, _make_rule()).result == "fail"


class TestFieldFormat:
    def test_matching_value_passes(self):
        event = _make_event(kdes={"lot_code": "ABC-123"})
        logic = {"field": "kdes.lot_code", "params": {"pattern": r"^[A-Z]+-\d+$"}}
        result = evaluate_field_format(event, logic, _make_rule())
        assert result.result == "pass"

    def test_mismatched_value_fails(self):
        event = _make_event(kdes={"lot_code": "not a code!!"})
        logic = {"field": "kdes.lot_code", "params": {"pattern": r"^[A-Z]+-\d+$"}}
        result = evaluate_field_format(event, logic, _make_rule())
        assert result.result == "fail"
        assert result.why_failed

    def test_missing_value_fails_not_skips(self):
        logic = {"field": "kdes.lot_code", "params": {"pattern": r"^.+$"}}
        result = evaluate_field_format(_make_event(), logic, _make_rule())
        assert result.result == "fail"


class TestMultiFieldPresence:
    def test_any_mode_passes_when_one_field_present(self):
        event = _make_event(kdes={"lot_code": "ABC"})
        logic = {"params": {"fields": ["kdes.lot_code", "kdes.po_number"]}}
        assert evaluate_multi_field_presence(event, logic, _make_rule()).result == "pass"

    def test_any_mode_fails_when_none_present(self):
        logic = {"params": {"fields": ["kdes.lot_code", "kdes.po_number"]}}
        result = evaluate_multi_field_presence(_make_event(), logic, _make_rule())
        assert result.result == "fail"
        assert result.why_failed

    def test_all_mode_requires_every_field(self):
        logic = {"params": {"fields": ["kdes.lot_code", "kdes.po_number"], "require": "all"}}
        partial = _make_event(kdes={"lot_code": "ABC"})
        result = evaluate_multi_field_presence(partial, logic, _make_rule())
        assert result.result == "fail"
        assert "po number" in (result.why_failed or "")
        full = _make_event(kdes={"lot_code": "ABC", "po_number": "PO-1"})
        assert evaluate_multi_field_presence(full, logic, _make_rule()).result == "pass"

    def test_empty_field_list_fails(self):
        result = evaluate_multi_field_presence(_make_event(), {"params": {"fields": []}}, _make_rule())
        assert result.result == "fail"


class TestNumericRange:
    def _range_logic(self, **params) -> Dict[str, Any]:
        base = {"min": 0.0, "max": 5.0, "unit": "C"}
        base.update(params)
        return {"field": "kdes.cooling_duration_hours", "params": base}

    def test_value_in_range_passes(self):
        event = _make_event(kdes={"cooling_duration_hours": 2.5})
        assert evaluate_numeric_range(event, self._range_logic(), _make_rule()).result == "pass"

    def test_value_above_max_fails_with_direction(self):
        event = _make_event(kdes={"cooling_duration_hours": 9.0})
        rule = _make_rule(failure_reason_template="")
        result = evaluate_numeric_range(event, self._range_logic(), rule)
        assert result.result == "fail"
        assert result.why_failed and "above maximum" in result.why_failed

    def test_missing_value_fails_not_skips(self):
        result = evaluate_numeric_range(_make_event(), self._range_logic(), _make_rule())
        assert result.result == "fail"

    def test_missing_value_skips_when_opted_in(self):
        result = evaluate_numeric_range(_make_event(), self._range_logic(missing_result="skip"), _make_rule())
        assert result.result == "skip"

    def test_boolean_value_is_rejected_as_non_numeric(self):
        event = _make_event(kdes={"cooling_duration_hours": True})
        result = evaluate_numeric_range(event, self._range_logic(), _make_rule())
        assert result.result == "fail"

    def test_temperature_source_normalizes_fahrenheit(self):
        event = _make_event(kdes={"temperature_fahrenheit": 41})
        logic = {"params": {"source": "temperature", "root": "kdes", "min": 0.0, "max": 5.0, "unit": "C"}}
        assert evaluate_numeric_range(event, logic, _make_rule()).result == "pass"


class TestGs1CheckDigit:
    VALID_GS1_13 = "1234567890128"

    def test_valid_identifier_passes(self):
        event = _make_event(kdes={"location_gln": self.VALID_GS1_13})
        result = evaluate_gs1_check_digit(event, {"field": "kdes.location_gln"}, _make_rule())
        assert result.result == "pass"

    def test_bad_check_digit_fails(self):
        event = _make_event(kdes={"location_gln": "1234567890123"})
        result = evaluate_gs1_check_digit(event, {"field": "kdes.location_gln"}, _make_rule())
        assert result.result == "fail"
        assert result.why_failed and "check digit" in result.why_failed

    def test_wrong_length_fails(self):
        event = _make_event(kdes={"location_gln": "12345678"})
        result = evaluate_gs1_check_digit(event, {"field": "kdes.location_gln"}, _make_rule())
        assert result.result == "fail"

    def test_missing_value_skips(self):
        result = evaluate_gs1_check_digit(_make_event(), {"field": "kdes.location_gln"}, _make_rule())
        assert result.result == "skip"

    def test_location_description_skips(self):
        event = _make_event(kdes={"location_gln": "Dock 7 warehouse"})
        result = evaluate_gs1_check_digit(event, {"field": "kdes.location_gln"}, _make_rule())
        assert result.result == "skip"


class TestEvaluatorDispatch:
    def test_all_evaluators_registered(self):
        assert set(EVALUATORS) == {
            "field_presence",
            "field_format",
            "multi_field_presence",
            "numeric_range",
            "gs1_check_digit",
        }

    def test_dispatch_matches_direct_call(self):
        event = _make_event(kdes={"lot_code": "ABC-123"})
        rule = _make_rule()
        via_table = EVALUATORS["field_presence"](event, {"field": "kdes.lot_code"}, rule)
        direct = stateless.evaluate_field_presence(event, {"field": "kdes.lot_code"}, rule)
        assert via_table.result == direct.result == "pass"
