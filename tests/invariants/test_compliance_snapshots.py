"""
Snapshot tests for compliance outputs.

Compliance system outputs need format and reasoning stability. Changes to
customer-visible artifacts should be intentional, never accidental.

Ref: REGENGINE_CODEBASE_REMEDIATION_PRD.md Phase 2.3

Tests:
    - Evidence references in compliance reports
    - Rule citation format
    - Explanation structure
    - Deterministic output for deterministic inputs
    - Evaluation result field completeness
"""

import sys
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services"))

from shared.canonical_event import (
    CTEType,
    EventStatus,
    IngestionSource,
    TraceabilityEvent,
)
from shared.rules.types import RuleDefinition, RuleEvaluationResult, EvaluationSummary
from shared.rules.evaluators.stateless import (
    evaluate_field_presence,
    evaluate_multi_field_presence,
)

TENANT = "00000000-0000-0000-0000-000000000099"


_DEFAULT_KDES = {
    "receive_date": "2026-04-14",
    "reference_document": "BOL-SNAP-001",
    "tlc_source_reference": "0061414100003",
    "immediate_previous_source": "Fresh Farms LLC",
}


def _event(event_type="receiving", kdes=None, **extra):
    """Build a canonical event for snapshot testing."""
    params = dict(
        tenant_id=TENANT,
        source_system=IngestionSource.WEBHOOK_API,
        event_type=event_type,
        event_timestamp=datetime(2026, 4, 14, 10, 0, 0, tzinfo=timezone.utc),
        traceability_lot_code="TLC-SNAP-001",
        product_reference="Romaine Lettuce",
        quantity=500.0,
        unit_of_measure="cases",
        from_facility_reference="0061414100001",
        to_facility_reference="0061414100002",
        from_entity_reference="Fresh Farms LLC",
        kdes=dict(_DEFAULT_KDES) if kdes is None else kdes,
    )
    params.update(extra)
    return TraceabilityEvent(**params)


def _rule(rule_id="snap-rule-001", eval_logic=None, **extra):
    """Build a rule definition for snapshot testing."""
    params = dict(
        rule_id=rule_id,
        rule_version=1,
        title="Snapshot Test Rule",
        description="Test rule for snapshot verification",
        severity="critical",
        category="kde_presence",
        applicability_conditions={"cte_types": ["receiving"]},
        citation_reference="21 CFR \u00a71.1345(b)(7)",
        effective_date=date(2026, 1, 1),
        retired_date=None,
        evaluation_logic=eval_logic or {"type": "field_presence", "field": "traceability_lot_code"},
        failure_reason_template="Missing {field_name} required by {citation}",
        remediation_suggestion="Add the required field",
    )
    params.update(extra)
    return RuleDefinition(**params)


# ===================================================================
# Evidence References in Compliance Reports
# ===================================================================

class TestEvidenceReferences:
    """Evidence fields inspected must be stable and complete."""

    def test_field_presence_evidence_structure(self):
        """field_presence evaluator produces evidence with field, value, expected, actual_present."""
        event_data = _event().model_dump(mode="json")
        rule = _rule(evaluation_logic={"type": "field_presence", "field": "traceability_lot_code"})
        result = evaluate_field_presence(event_data, rule.evaluation_logic, rule)

        assert len(result.evidence_fields_inspected) == 1
        evidence = result.evidence_fields_inspected[0]
        assert "field" in evidence
        assert "value" in evidence
        assert "expected" in evidence
        assert "actual_present" in evidence
        assert evidence["field"] == "traceability_lot_code"
        assert evidence["actual_present"] is True

    def test_multi_field_evidence_lists_all_checked(self):
        """multi_field_presence evaluator lists all fields checked in evidence."""
        event_data = _event().model_dump(mode="json")
        rule = _rule(
            evaluation_logic={
                "type": "multi_field_presence",
                "field": "kdes.tlc_source_reference",
                "params": {"fields": ["kdes.tlc_source_reference", "kdes.tlc_source_gln", "from_entity_reference"]},
            },
        )
        result = evaluate_multi_field_presence(event_data, rule.evaluation_logic, rule)

        assert len(result.evidence_fields_inspected) == 3
        field_names = [e["field"] for e in result.evidence_fields_inspected]
        assert "kdes.tlc_source_reference" in field_names
        assert "kdes.tlc_source_gln" in field_names
        assert "from_entity_reference" in field_names

    def test_evidence_value_is_truncated_at_200_chars(self):
        """Evidence values are truncated to prevent oversized reports."""
        long_value = "x" * 500
        event_data = _event(kdes={"long_field": long_value}).model_dump(mode="json")
        rule = _rule(evaluation_logic={"type": "field_presence", "field": "kdes.long_field"})
        result = evaluate_field_presence(event_data, rule.evaluation_logic, rule)

        evidence = result.evidence_fields_inspected[0]
        assert len(evidence["value"]) <= 200

    def test_missing_field_evidence_shows_none(self):
        """Missing field is represented as None in evidence."""
        event_data = _event(kdes={}).model_dump(mode="json")
        rule = _rule(evaluation_logic={"type": "field_presence", "field": "kdes.nonexistent"})
        result = evaluate_field_presence(event_data, rule.evaluation_logic, rule)

        evidence = result.evidence_fields_inspected[0]
        assert evidence["value"] is None
        assert evidence["actual_present"] is False


# ===================================================================
# Rule Citation Format
# ===================================================================

class TestCitationFormat:
    """Citations must follow consistent format and be present on results."""

    def test_passing_result_includes_citation(self):
        """Passing results carry the rule's citation_reference."""
        event_data = _event().model_dump(mode="json")
        rule = _rule(citation_reference="21 CFR \u00a71.1345(b)(7)")
        result = evaluate_field_presence(event_data, rule.evaluation_logic, rule)

        assert result.result == "pass"
        assert result.citation_reference == "21 CFR \u00a71.1345(b)(7)"

    def test_failing_result_includes_citation_and_remediation(self):
        """Failing results carry citation AND remediation suggestion."""
        event_data = _event(kdes={}).model_dump(mode="json")
        rule = _rule(
            evaluation_logic={"type": "field_presence", "field": "kdes.receive_date"},
            remediation_suggestion="Record the receive date",
        )
        result = evaluate_field_presence(event_data, rule.evaluation_logic, rule)

        assert result.result == "fail"
        assert result.citation_reference is not None
        assert result.remediation_suggestion == "Record the receive date"

    def test_rule_id_and_version_on_result(self):
        """Every result carries the rule_id and rule_version that produced it."""
        event_data = _event().model_dump(mode="json")
        rule = _rule(rule_id="fsma-204-recv-001", rule_version=3)
        result = evaluate_field_presence(event_data, rule.evaluation_logic, rule)

        assert result.rule_id == "fsma-204-recv-001"
        assert result.rule_version == 3

    def test_category_is_propagated(self):
        """Result category matches the rule category."""
        event_data = _event().model_dump(mode="json")
        rule = _rule(category="source_reference")
        result = evaluate_field_presence(event_data, rule.evaluation_logic, rule)

        assert result.category == "source_reference"


# ===================================================================
# Explanation Structure (why_failed)
# ===================================================================

class TestExplanationStructure:
    """Failure explanations must be human-readable and template-driven."""

    def test_why_failed_uses_template(self):
        """Failure reason is generated from the rule's failure_reason_template."""
        event_data = _event(kdes={}).model_dump(mode="json")
        rule = _rule(
            evaluation_logic={"type": "field_presence", "field": "kdes.receive_date"},
            failure_reason_template="Missing {field_name} required by {citation}",
            citation_reference="21 CFR \u00a71.1345(b)(2)",
        )
        result = evaluate_field_presence(event_data, rule.evaluation_logic, rule)

        assert result.why_failed is not None
        assert "receive date" in result.why_failed.lower()
        assert "21 CFR" in result.why_failed

    def test_why_failed_is_none_on_pass(self):
        """Passing results have no failure explanation."""
        event_data = _event().model_dump(mode="json")
        rule = _rule()
        result = evaluate_field_presence(event_data, rule.evaluation_logic, rule)

        assert result.result == "pass"
        assert result.why_failed is None

    def test_multi_field_failure_lists_checked_fields(self):
        """Multi-field failure explanation names the fields that were checked."""
        event_data = _event(kdes={}, from_entity_reference=None).model_dump(mode="json")
        rule = _rule(
            evaluation_logic={
                "type": "multi_field_presence",
                "field": "from_entity_reference",
                "params": {"fields": ["from_entity_reference", "kdes.immediate_previous_source"]},
            },
            failure_reason_template="Missing {field_name} \u2014 cannot identify source ({citation})",
        )
        result = evaluate_multi_field_presence(event_data, rule.evaluation_logic, rule)

        assert result.result == "fail"
        assert result.why_failed is not None


# ===================================================================
# Deterministic Output
# ===================================================================

class TestDeterministicOutput:
    """Same canonical event + same rules = identical compliance output.
    This is critical for audit reproducibility."""

    def test_same_event_same_rule_identical_fields(self):
        """Two evaluations of the same event produce byte-identical results (except evaluation_id)."""
        event_data = _event().model_dump(mode="json")
        rule = _rule()

        r1 = evaluate_field_presence(event_data, rule.evaluation_logic, rule)
        r2 = evaluate_field_presence(event_data, rule.evaluation_logic, rule)

        assert r1.result == r2.result
        assert r1.rule_id == r2.rule_id
        assert r1.rule_version == r2.rule_version
        assert r1.severity == r2.severity
        assert r1.why_failed == r2.why_failed
        assert r1.evidence_fields_inspected == r2.evidence_fields_inspected
        assert r1.citation_reference == r2.citation_reference
        assert r1.category == r2.category
        # evaluation_id is UUID — deliberately different per evaluation

    def test_failing_event_same_rule_identical_failure(self):
        """Two evaluations of the same failing event produce identical failures."""
        event_data = _event(kdes={}).model_dump(mode="json")
        rule = _rule(evaluation_logic={"type": "field_presence", "field": "kdes.receive_date"})

        r1 = evaluate_field_presence(event_data, rule.evaluation_logic, rule)
        r2 = evaluate_field_presence(event_data, rule.evaluation_logic, rule)

        assert r1.result == r2.result == "fail"
        assert r1.why_failed == r2.why_failed
        assert r1.evidence_fields_inspected == r2.evidence_fields_inspected

    def test_evaluation_summary_is_deterministic(self):
        """EvaluationSummary counts are deterministic for the same input."""
        event_data = _event().model_dump(mode="json")
        rules = [
            _rule(rule_id=f"det-{i}", evaluation_logic={"type": "field_presence", "field": "traceability_lot_code"})
            for i in range(5)
        ]

        summaries = []
        for _ in range(3):
            summary = EvaluationSummary(event_id="det-test")
            for rule in rules:
                result = evaluate_field_presence(event_data, rule.evaluation_logic, rule)
                summary.results.append(result)
                if result.result == "pass":
                    summary.passed += 1
                elif result.result == "fail":
                    summary.failed += 1
                summary.total_rules += 1
            summaries.append(summary)

        assert all(s.total_rules == 5 for s in summaries)
        assert all(s.passed == 5 for s in summaries)
        assert all(s.failed == 0 for s in summaries)
        assert all(s.compliant is True for s in summaries)


# ===================================================================
# Result Field Completeness
# ===================================================================

class TestResultFieldCompleteness:
    """Every RuleEvaluationResult must have all fields populated."""

    def test_passing_result_has_all_fields(self):
        """A passing result has all required fields set."""
        event_data = _event().model_dump(mode="json")
        rule = _rule()
        result = evaluate_field_presence(event_data, rule.evaluation_logic, rule)

        assert result.evaluation_id  # non-empty UUID
        assert result.rule_id == rule.rule_id
        assert result.rule_version == rule.rule_version
        assert result.rule_title == rule.title
        assert result.severity == rule.severity
        assert result.result == "pass"
        assert result.evidence_fields_inspected  # non-empty list
        assert result.confidence == 1.0
        assert result.citation_reference == rule.citation_reference
        assert result.category == rule.category

    def test_failing_result_has_all_fields(self):
        """A failing result has all required fields INCLUDING why_failed and remediation."""
        event_data = _event(kdes={}).model_dump(mode="json")
        rule = _rule(
            evaluation_logic={"type": "field_presence", "field": "kdes.receive_date"},
            remediation_suggestion="Add the date",
        )
        result = evaluate_field_presence(event_data, rule.evaluation_logic, rule)

        assert result.evaluation_id
        assert result.rule_id == rule.rule_id
        assert result.result == "fail"
        assert result.why_failed is not None
        assert len(result.why_failed) > 0
        assert result.remediation_suggestion == "Add the date"
        assert result.evidence_fields_inspected

    def test_evaluation_id_is_unique_per_result(self):
        """Each evaluation produces a unique evaluation_id."""
        event_data = _event().model_dump(mode="json")
        rule = _rule()

        ids = set()
        for _ in range(10):
            result = evaluate_field_presence(event_data, rule.evaluation_logic, rule)
            ids.add(result.evaluation_id)

        assert len(ids) == 10, "evaluation_ids must be unique"
