"""
Unit tests for the Rules Engine — business logic only, no database.

Tests cover:
    - RuleDefinition / RuleEvaluationResult / EvaluationSummary dataclasses
    - _get_nested_value helper
    - _evaluate_field_presence evaluator
    - _evaluate_field_format evaluator
    - _evaluate_multi_field_presence evaluator
    - RulesEngine.evaluate_event (batch evaluation against mock rules)
    - Critical failure detection and severity ordering
    - why_failed explanation generation
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from services.shared.rules_engine import (
    EvaluationSummary,
    RuleDefinition,
    RuleEvaluationResult,
    RulesEngine,
    _evaluate_field_format,
    _evaluate_field_presence,
    _evaluate_multi_field_presence,
    _get_nested_value,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_rule(**overrides) -> RuleDefinition:
    """Factory for a RuleDefinition with sensible defaults."""
    defaults = dict(
        rule_id="rule-001",
        rule_version=1,
        title="Test Rule",
        description="A unit-test rule",
        severity="critical",
        category="kde_presence",
        applicability_conditions={"cte_types": ["receiving"]},
        citation_reference="21 CFR §1.1345(b)(7)",
        effective_date=date(2026, 1, 1),
        retired_date=None,
        evaluation_logic={"type": "field_presence", "field": "kdes.tlc_source_reference"},
        failure_reason_template=(
            "Missing {field_name} at {field_path} per {citation} for {event_type} event"
        ),
        remediation_suggestion="Request the data from your supplier",
    )
    defaults.update(overrides)
    return RuleDefinition(**defaults)


def _make_event(**overrides) -> dict:
    """Factory for a canonical event dict."""
    defaults = {
        "event_id": "evt-001",
        "event_type": "receiving",
        "kdes": {
            "tlc_source_reference": "REF-123",
            "harvest_date": "2026-01-10",
        },
    }
    defaults.update(overrides)
    return defaults


@pytest.fixture
def mock_session():
    return MagicMock()


# ---------------------------------------------------------------------------
# 1. Dataclass Construction & Validation
# ---------------------------------------------------------------------------

class TestDataclasses:
    def test_rule_definition_creation(self):
        rule = _make_rule()
        assert rule.rule_id == "rule-001"
        assert rule.severity == "critical"
        assert rule.retired_date is None

    def test_evaluation_result_defaults(self):
        r = RuleEvaluationResult()
        assert r.result == "pass"
        assert r.why_failed is None
        assert r.confidence == 1.0
        assert r.severity == "warning"
        assert isinstance(r.evidence_fields_inspected, list)
        assert r.evaluation_id  # UUID auto-generated

    def test_evaluation_summary_compliant_when_no_failures(self):
        s = EvaluationSummary(event_id="e1", total_rules=2, passed=2)
        assert s.compliant is True

    def test_evaluation_summary_not_compliant_when_failures(self):
        s = EvaluationSummary(event_id="e1", total_rules=2, passed=1, failed=1)
        assert s.compliant is False


# ---------------------------------------------------------------------------
# 2. _get_nested_value
# ---------------------------------------------------------------------------

class TestGetNestedValue:
    def test_flat_key(self):
        assert _get_nested_value({"a": 1}, "a") == 1

    def test_nested_key(self):
        data = {"kdes": {"harvest_date": "2026-01-10"}}
        assert _get_nested_value(data, "kdes.harvest_date") == "2026-01-10"

    def test_deeply_nested(self):
        data = {"a": {"b": {"c": 42}}}
        assert _get_nested_value(data, "a.b.c") == 42

    def test_missing_key_returns_none(self):
        assert _get_nested_value({"a": 1}, "b") is None

    def test_missing_nested_key_returns_none(self):
        assert _get_nested_value({"a": {"b": 1}}, "a.c") is None

    def test_non_dict_intermediate_returns_none(self):
        assert _get_nested_value({"a": "string"}, "a.b") is None

    def test_empty_string_value(self):
        assert _get_nested_value({"a": ""}, "a") == ""


# ---------------------------------------------------------------------------
# 3. _evaluate_field_presence
# ---------------------------------------------------------------------------

class TestEvaluateFieldPresence:
    def test_present_field_passes(self):
        rule = _make_rule()
        event = _make_event()
        result = _evaluate_field_presence(
            event, rule.evaluation_logic, rule
        )
        assert result.result == "pass"
        assert result.rule_id == "rule-001"
        assert result.why_failed is None

    def test_missing_field_fails(self):
        rule = _make_rule()
        event = _make_event(kdes={})  # no tlc_source_reference
        result = _evaluate_field_presence(
            event, rule.evaluation_logic, rule
        )
        assert result.result == "fail"
        assert result.why_failed is not None
        assert "tlc source reference" in result.why_failed

    def test_empty_string_field_fails(self):
        rule = _make_rule()
        event = _make_event(kdes={"tlc_source_reference": "   "})
        result = _evaluate_field_presence(
            event, rule.evaluation_logic, rule
        )
        assert result.result == "fail"

    def test_none_field_fails(self):
        rule = _make_rule()
        event = _make_event(kdes={"tlc_source_reference": None})
        result = _evaluate_field_presence(
            event, rule.evaluation_logic, rule
        )
        assert result.result == "fail"

    def test_numeric_field_passes(self):
        rule = _make_rule(evaluation_logic={"type": "field_presence", "field": "kdes.quantity"})
        event = _make_event(kdes={"quantity": 0})  # 0 is non-None
        result = _evaluate_field_presence(
            event, rule.evaluation_logic, rule
        )
        assert result.result == "pass"

    def test_evidence_fields_populated(self):
        rule = _make_rule()
        event = _make_event()
        result = _evaluate_field_presence(
            event, rule.evaluation_logic, rule
        )
        assert len(result.evidence_fields_inspected) == 1
        evidence = result.evidence_fields_inspected[0]
        assert evidence["field"] == "kdes.tlc_source_reference"
        assert evidence["actual_present"] is True

    def test_why_failed_includes_citation(self):
        rule = _make_rule()
        event = _make_event(kdes={})
        result = _evaluate_field_presence(
            event, rule.evaluation_logic, rule
        )
        assert "21 CFR" in result.why_failed

    def test_remediation_suggestion_set_on_failure(self):
        rule = _make_rule()
        event = _make_event(kdes={})
        result = _evaluate_field_presence(
            event, rule.evaluation_logic, rule
        )
        assert result.remediation_suggestion == "Request the data from your supplier"


# ---------------------------------------------------------------------------
# 4. _evaluate_field_format
# ---------------------------------------------------------------------------

class TestEvaluateFieldFormat:
    def test_matching_format_passes(self):
        rule = _make_rule(
            evaluation_logic={
                "type": "field_format",
                "field": "kdes.harvest_date",
                "params": {"pattern": r"\d{4}-\d{2}-\d{2}"},
            },
        )
        event = _make_event()
        result = _evaluate_field_format(event, rule.evaluation_logic, rule)
        assert result.result == "pass"

    def test_non_matching_format_fails(self):
        rule = _make_rule(
            evaluation_logic={
                "type": "field_format",
                "field": "kdes.harvest_date",
                "params": {"pattern": r"^\d{8}$"},  # requires YYYYMMDD
            },
        )
        event = _make_event()
        result = _evaluate_field_format(event, rule.evaluation_logic, rule)
        assert result.result == "fail"
        assert "does not match required format" in result.why_failed

    def test_missing_field_fails(self):
        rule = _make_rule(
            evaluation_logic={
                "type": "field_format",
                "field": "kdes.nonexistent",
                "params": {"pattern": r".*"},
            },
        )
        event = _make_event()
        result = _evaluate_field_format(event, rule.evaluation_logic, rule)
        assert result.result == "fail"

    def test_empty_string_fails(self):
        rule = _make_rule(
            evaluation_logic={
                "type": "field_format",
                "field": "kdes.harvest_date",
                "params": {"pattern": r"\d{4}-\d{2}-\d{2}"},
            },
        )
        event = _make_event(kdes={"harvest_date": ""})
        result = _evaluate_field_format(event, rule.evaluation_logic, rule)
        assert result.result == "fail"

    def test_evidence_includes_pattern(self):
        rule = _make_rule(
            evaluation_logic={
                "type": "field_format",
                "field": "kdes.harvest_date",
                "params": {"pattern": r"\d{4}-\d{2}-\d{2}"},
            },
        )
        event = _make_event()
        result = _evaluate_field_format(event, rule.evaluation_logic, rule)
        evidence = result.evidence_fields_inspected[0]
        assert evidence["expected_pattern"] == r"\d{4}-\d{2}-\d{2}"


# ---------------------------------------------------------------------------
# 5. _evaluate_multi_field_presence
# ---------------------------------------------------------------------------

class TestEvaluateMultiFieldPresence:
    def test_one_of_many_present_passes(self):
        rule = _make_rule(
            evaluation_logic={
                "type": "multi_field_presence",
                "field": "kdes.tlc_source_reference",
                "params": {
                    "fields": [
                        "kdes.tlc_source_reference",
                        "kdes.supplier_reference",
                    ],
                },
            },
        )
        event = _make_event()
        result = _evaluate_multi_field_presence(event, rule.evaluation_logic, rule)
        assert result.result == "pass"

    def test_all_missing_fails(self):
        rule = _make_rule(
            evaluation_logic={
                "type": "multi_field_presence",
                "field": "kdes.tlc_source_reference",
                "params": {
                    "fields": [
                        "kdes.supplier_reference",
                        "kdes.vendor_code",
                    ],
                },
            },
        )
        event = _make_event()
        result = _evaluate_multi_field_presence(event, rule.evaluation_logic, rule)
        assert result.result == "fail"
        assert result.why_failed is not None

    def test_evidence_records_all_fields(self):
        rule = _make_rule(
            evaluation_logic={
                "type": "multi_field_presence",
                "field": "kdes",
                "params": {
                    "fields": [
                        "kdes.tlc_source_reference",
                        "kdes.missing_field",
                    ],
                },
            },
        )
        event = _make_event()
        result = _evaluate_multi_field_presence(event, rule.evaluation_logic, rule)
        assert len(result.evidence_fields_inspected) == 2
        assert result.evidence_fields_inspected[0]["present"] is True
        assert result.evidence_fields_inspected[1]["present"] is False


# ---------------------------------------------------------------------------
# 6. RulesEngine.evaluate_event (integrated, mock DB)
# ---------------------------------------------------------------------------

class TestRulesEngineEvaluateEvent:
    def _engine_with_rules(self, rules, mock_session):
        engine = RulesEngine(mock_session)
        engine._rules_cache = rules
        return engine

    def test_evaluate_event_passes_all(self, mock_session):
        rules = [_make_rule()]
        engine = self._engine_with_rules(rules, mock_session)
        event = _make_event()

        summary = engine.evaluate_event(event, persist=False)
        assert summary.total_rules == 1
        assert summary.passed == 1
        assert summary.failed == 0
        assert summary.compliant is True

    def test_evaluate_event_detects_failure(self, mock_session):
        rules = [_make_rule()]
        engine = self._engine_with_rules(rules, mock_session)
        event = _make_event(kdes={})

        summary = engine.evaluate_event(event, persist=False)
        assert summary.failed == 1
        assert summary.compliant is False

    def test_critical_failures_tracked(self, mock_session):
        rules = [_make_rule(severity="critical")]
        engine = self._engine_with_rules(rules, mock_session)
        event = _make_event(kdes={})

        summary = engine.evaluate_event(event, persist=False)
        assert len(summary.critical_failures) == 1
        assert summary.critical_failures[0].severity == "critical"

    def test_non_critical_failure_not_in_critical_list(self, mock_session):
        rules = [_make_rule(severity="warning")]
        engine = self._engine_with_rules(rules, mock_session)
        event = _make_event(kdes={})

        summary = engine.evaluate_event(event, persist=False)
        assert summary.failed == 1
        assert len(summary.critical_failures) == 0

    def test_unknown_evaluator_type_skips(self, mock_session):
        rules = [_make_rule(evaluation_logic={"type": "custom_check_v99"})]
        engine = self._engine_with_rules(rules, mock_session)
        event = _make_event()

        summary = engine.evaluate_event(event, persist=False)
        assert summary.skipped == 1
        assert "Unknown evaluation type" in summary.results[0].why_failed

    def test_evaluator_exception_skips(self, mock_session):
        rules = [_make_rule(
            evaluation_logic={"type": "field_presence", "field": "kdes.x"},
            # Template that will fail because of bad format key
            failure_reason_template="{nonexistent_key}",
        )]
        engine = self._engine_with_rules(rules, mock_session)
        event = _make_event(kdes={})

        summary = engine.evaluate_event(event, persist=False)
        # Should be skipped (caught exception), not crash
        assert summary.skipped == 1
        assert "Evaluation error" in summary.results[0].why_failed

    def test_multiple_rules_evaluated(self, mock_session):
        rules = [
            _make_rule(rule_id="r1"),
            _make_rule(rule_id="r2", evaluation_logic={
                "type": "field_presence", "field": "kdes.harvest_date",
            }),
        ]
        engine = self._engine_with_rules(rules, mock_session)
        event = _make_event()

        summary = engine.evaluate_event(event, persist=False)
        assert summary.total_rules == 2
        assert summary.passed == 2


# ---------------------------------------------------------------------------
# 7. Applicability Filtering
# ---------------------------------------------------------------------------

class TestGetApplicableRules:
    def test_filter_by_cte_type(self, mock_session):
        rules = [
            _make_rule(rule_id="r1", applicability_conditions={"cte_types": ["receiving"]}),
            _make_rule(rule_id="r2", applicability_conditions={"cte_types": ["shipping"]}),
        ]
        engine = RulesEngine(mock_session)
        applicable = engine.get_applicable_rules("receiving", rules)
        assert len(applicable) == 1
        assert applicable[0].rule_id == "r1"

    def test_empty_cte_types_matches_all(self, mock_session):
        rules = [_make_rule(applicability_conditions={"cte_types": []})]
        engine = RulesEngine(mock_session)
        applicable = engine.get_applicable_rules("any_event_type", rules)
        assert len(applicable) == 1

    def test_all_keyword_matches_all(self, mock_session):
        rules = [_make_rule(applicability_conditions={"cte_types": ["all"]})]
        engine = RulesEngine(mock_session)
        applicable = engine.get_applicable_rules("shipping", rules)
        assert len(applicable) == 1


# ---------------------------------------------------------------------------
# 8. Batch Evaluation
# ---------------------------------------------------------------------------

class TestBatchEvaluation:
    def test_batch_evaluates_multiple_events(self, mock_session):
        rules = [_make_rule()]
        engine = RulesEngine(mock_session)
        engine._rules_cache = rules

        events = [
            _make_event(event_id="e1"),
            _make_event(event_id="e2", kdes={}),
        ]

        # Mock load_active_rules to return cached rules
        engine.load_active_rules = MagicMock(return_value=rules)

        summaries = engine.evaluate_events_batch(events, tenant_id="t1", persist=False)
        assert len(summaries) == 2
        assert summaries[0].passed == 1  # e1 passes
        assert summaries[1].failed == 1  # e2 fails


# ---------------------------------------------------------------------------
# 9. Severity Ordering
# ---------------------------------------------------------------------------

class TestSeverityOrdering:
    def test_critical_before_warning(self):
        """Verify that severity can be used for sorting/prioritization."""
        severity_order = {"critical": 0, "warning": 1, "info": 2}

        results = [
            RuleEvaluationResult(severity="warning", result="fail"),
            RuleEvaluationResult(severity="critical", result="fail"),
            RuleEvaluationResult(severity="info", result="fail"),
        ]

        sorted_results = sorted(results, key=lambda r: severity_order.get(r.severity, 99))
        assert sorted_results[0].severity == "critical"
        assert sorted_results[1].severity == "warning"
        assert sorted_results[2].severity == "info"


# ---------------------------------------------------------------------------
# 10. why_failed Explanation Quality
# ---------------------------------------------------------------------------

class TestWhyFailedExplanation:
    def test_why_failed_contains_field_name(self):
        rule = _make_rule()
        event = _make_event(kdes={})
        result = _evaluate_field_presence(event, rule.evaluation_logic, rule)
        assert "tlc source reference" in result.why_failed

    def test_why_failed_contains_event_type(self):
        rule = _make_rule()
        event = _make_event(kdes={}, event_type="shipping")
        result = _evaluate_field_presence(event, rule.evaluation_logic, rule)
        assert "shipping" in result.why_failed

    def test_format_why_failed_shows_value(self):
        rule = _make_rule(
            evaluation_logic={
                "type": "field_format",
                "field": "kdes.harvest_date",
                "params": {"pattern": r"^\d{8}$"},
            },
        )
        event = _make_event()  # harvest_date = "2026-01-10"
        result = _evaluate_field_format(event, rule.evaluation_logic, rule)
        assert "2026-01-10" in result.why_failed
