"""
Tests for the Versioned Rules Engine.

Validates:
1. Rule evaluation logic (field_presence, field_format, multi_field_presence)
2. Applicability filtering by CTE type
3. Human-readable failure messages
4. Evidence field inspection
5. Rule seed data integrity
"""

import pytest

from shared.rules_engine import (
    RuleDefinition,
    RuleEvaluationResult,
    EvaluationSummary,
    _evaluate_field_presence,
    _evaluate_field_format,
    _evaluate_multi_field_presence,
    FSMA_RULE_SEEDS,
    RulesEngine,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_rule(**overrides) -> RuleDefinition:
    """Create a test rule definition."""
    defaults = {
        "rule_id": "test-rule-001",
        "rule_version": 1,
        "title": "Test Rule",
        "description": "A test rule",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["receiving"]},
        "citation_reference": "21 CFR §1.1345(b)(7)",
        "effective_date": "2026-01-01",
        "retired_date": None,
        "evaluation_logic": {
            "type": "field_presence",
            "field": "kdes.tlc_source_reference",
        },
        "failure_reason_template": "Missing {field_name} required by {citation}",
        "remediation_suggestion": "Request the TLC source reference from supplier",
    }
    defaults.update(overrides)
    return RuleDefinition(**defaults)


def _make_event(**overrides) -> dict:
    """Create a test canonical event data dict."""
    defaults = {
        "event_id": "evt-001",
        "event_type": "receiving",
        "traceability_lot_code": "TLC-001",
        "product_reference": "Romaine Lettuce",
        "quantity": 500.0,
        "unit_of_measure": "cases",
        "from_facility_reference": "0061414100001",
        "to_facility_reference": "0061414100002",
        "kdes": {
            "receive_date": "2026-03-25",
            "reference_document": "BOL-001",
            "tlc_source_reference": "0061414100003",
            "immediate_previous_source": "Fresh Farms LLC",
        },
    }
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# Field Presence Evaluation
# ---------------------------------------------------------------------------

class TestFieldPresence:
    def test_field_present_passes(self):
        rule = _make_rule(evaluation_logic={"type": "field_presence", "field": "kdes.receive_date"})
        event = _make_event()
        result = _evaluate_field_presence(event, rule.evaluation_logic, rule)
        assert result.result == "pass"

    def test_field_missing_fails(self):
        rule = _make_rule(evaluation_logic={"type": "field_presence", "field": "kdes.missing_field"})
        event = _make_event()
        result = _evaluate_field_presence(event, rule.evaluation_logic, rule)
        assert result.result == "fail"
        assert result.why_failed is not None
        assert "missing field" in result.why_failed.lower() or "Missing" in result.why_failed

    def test_empty_string_fails(self):
        rule = _make_rule(evaluation_logic={"type": "field_presence", "field": "kdes.empty_kde"})
        event = _make_event(kdes={"empty_kde": "   "})
        result = _evaluate_field_presence(event, rule.evaluation_logic, rule)
        assert result.result == "fail"

    def test_nested_field_access(self):
        rule = _make_rule(evaluation_logic={"type": "field_presence", "field": "kdes.tlc_source_reference"})
        event = _make_event()
        result = _evaluate_field_presence(event, rule.evaluation_logic, rule)
        assert result.result == "pass"
        assert len(result.evidence_fields_inspected) == 1
        assert result.evidence_fields_inspected[0]["field"] == "kdes.tlc_source_reference"

    def test_top_level_field(self):
        rule = _make_rule(evaluation_logic={"type": "field_presence", "field": "product_reference"})
        event = _make_event()
        result = _evaluate_field_presence(event, rule.evaluation_logic, rule)
        assert result.result == "pass"

    def test_failure_includes_citation(self):
        rule = _make_rule(
            evaluation_logic={"type": "field_presence", "field": "kdes.missing"},
            citation_reference="21 CFR §1.1345(b)(7)",
        )
        event = _make_event()
        result = _evaluate_field_presence(event, rule.evaluation_logic, rule)
        assert result.citation_reference == "21 CFR §1.1345(b)(7)"

    def test_failure_includes_remediation(self):
        rule = _make_rule(
            evaluation_logic={"type": "field_presence", "field": "kdes.missing"},
            remediation_suggestion="Contact your supplier",
        )
        event = _make_event()
        result = _evaluate_field_presence(event, rule.evaluation_logic, rule)
        assert result.remediation_suggestion == "Contact your supplier"


# ---------------------------------------------------------------------------
# Multi-Field Presence Evaluation
# ---------------------------------------------------------------------------

class TestMultiFieldPresence:
    def test_at_least_one_present_passes(self):
        rule = _make_rule(evaluation_logic={
            "type": "multi_field_presence",
            "field": "kdes.tlc_source_reference",
            "params": {"fields": ["kdes.tlc_source_reference", "kdes.tlc_source_gln"]},
        })
        event = _make_event()
        result = _evaluate_multi_field_presence(event, rule.evaluation_logic, rule)
        assert result.result == "pass"

    def test_all_missing_fails(self):
        rule = _make_rule(evaluation_logic={
            "type": "multi_field_presence",
            "field": "kdes.missing",
            "params": {"fields": ["kdes.field_a", "kdes.field_b", "kdes.field_c"]},
        })
        event = _make_event()
        result = _evaluate_multi_field_presence(event, rule.evaluation_logic, rule)
        assert result.result == "fail"
        assert len(result.evidence_fields_inspected) == 3

    def test_evidence_shows_all_checked_fields(self):
        rule = _make_rule(evaluation_logic={
            "type": "multi_field_presence",
            "params": {"fields": ["kdes.receive_date", "kdes.missing"]},
        })
        event = _make_event()
        result = _evaluate_multi_field_presence(event, rule.evaluation_logic, rule)
        assert result.result == "pass"
        assert len(result.evidence_fields_inspected) == 2
        # First field present, second missing
        assert result.evidence_fields_inspected[0]["present"] is True
        assert result.evidence_fields_inspected[1]["present"] is False


# ---------------------------------------------------------------------------
# Field Format Evaluation
# ---------------------------------------------------------------------------

class TestFieldFormat:
    def test_matching_format_passes(self):
        rule = _make_rule(evaluation_logic={
            "type": "field_format",
            "field": "from_facility_reference",
            "params": {"pattern": r"^\d{13}$"},
        })
        event = _make_event(from_facility_reference="0061414100001")
        result = _evaluate_field_format(event, rule.evaluation_logic, rule)
        assert result.result == "pass"

    def test_non_matching_format_fails(self):
        rule = _make_rule(evaluation_logic={
            "type": "field_format",
            "field": "from_facility_reference",
            "params": {"pattern": r"^\d{13}$"},
        })
        event = _make_event(from_facility_reference="not-a-gln")
        result = _evaluate_field_format(event, rule.evaluation_logic, rule)
        assert result.result == "fail"

    def test_missing_field_fails_format_check(self):
        rule = _make_rule(evaluation_logic={
            "type": "field_format",
            "field": "kdes.missing_field",
            "params": {"pattern": r".*"},
        })
        event = _make_event()
        result = _evaluate_field_format(event, rule.evaluation_logic, rule)
        assert result.result == "fail"


# ---------------------------------------------------------------------------
# Rule Applicability
# ---------------------------------------------------------------------------

class TestRuleApplicability:
    def test_rules_filter_by_cte_type(self):
        rules = [
            _make_rule(title="Receiving Rule", applicability_conditions={"cte_types": ["receiving"]}),
            _make_rule(title="Shipping Rule", applicability_conditions={"cte_types": ["shipping"]}),
            _make_rule(title="Universal Rule", applicability_conditions={"cte_types": []}),
        ]
        # This tests the static method without DB
        engine = RulesEngine.__new__(RulesEngine)
        engine._rules_cache = rules

        receiving_rules = engine.get_applicable_rules("receiving", rules)
        assert len(receiving_rules) == 2  # Receiving Rule + Universal Rule

        shipping_rules = engine.get_applicable_rules("shipping", rules)
        assert len(shipping_rules) == 2  # Shipping Rule + Universal Rule

    def test_empty_cte_types_means_all(self):
        rule = _make_rule(applicability_conditions={"cte_types": []})
        engine = RulesEngine.__new__(RulesEngine)
        engine._rules_cache = [rule]

        for cte in ["receiving", "shipping", "harvesting", "transformation"]:
            applicable = engine.get_applicable_rules(cte, [rule])
            assert len(applicable) == 1


# ---------------------------------------------------------------------------
# Seed Data Integrity
# ---------------------------------------------------------------------------

class TestRuleSeedData:
    def test_seed_count(self):
        assert len(FSMA_RULE_SEEDS) == 28

    def test_all_seeds_have_required_fields(self):
        required = {"title", "severity", "category", "evaluation_logic", "failure_reason_template"}
        for seed in FSMA_RULE_SEEDS:
            for field in required:
                assert field in seed, f"Seed '{seed.get('title', 'unknown')}' missing '{field}'"

    def test_all_seeds_have_citations(self):
        for seed in FSMA_RULE_SEEDS:
            # All rules should cite a CFR section or GS1 spec
            citation = seed.get("citation_reference", "")
            assert citation, f"Seed '{seed['title']}' missing citation_reference"

    def test_all_seeds_have_remediation(self):
        for seed in FSMA_RULE_SEEDS:
            remediation = seed.get("remediation_suggestion", "")
            assert remediation, f"Seed '{seed['title']}' missing remediation_suggestion"

    def test_severity_distribution(self):
        severities = [s["severity"] for s in FSMA_RULE_SEEDS]
        assert "critical" in severities
        assert "warning" in severities

    def test_category_coverage(self):
        categories = {s["category"] for s in FSMA_RULE_SEEDS}
        assert "kde_presence" in categories
        assert "source_reference" in categories
        assert "lot_linkage" in categories

    def test_failure_templates_use_placeholders(self):
        for seed in FSMA_RULE_SEEDS:
            template = seed["failure_reason_template"]
            # Templates should have at least one placeholder
            assert "{" in template, f"Template for '{seed['title']}' has no placeholders"


# ---------------------------------------------------------------------------
# Evaluation Summary
# ---------------------------------------------------------------------------

class TestEvaluationSummary:
    def test_compliant_when_no_failures(self):
        summary = EvaluationSummary(passed=5, failed=0, warned=1)
        assert summary.compliant is True

    def test_non_compliant_when_failures(self):
        summary = EvaluationSummary(passed=3, failed=2, warned=1)
        assert summary.compliant is False
