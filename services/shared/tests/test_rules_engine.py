"""Focused unit tests for ``shared.rules.engine.RulesEngine``.

Covers the main public behavior with a stubbed DB session (no network,
no live database): rule filtering, single-event evaluation, the tri-state
no-verdict branches, fail-closed error handling, tenant isolation for
relational rules, batch/summary guards, and the rule cache.
"""

from __future__ import annotations

import time
from datetime import date
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest
from shared.rules.engine import RulesEngine
from shared.rules.types import EvaluationSummary, RuleDefinition, RuleEvaluationResult


def _rule(
    rule_id: str = "rule-1",
    *,
    eval_type: str = "field_presence",
    logic: Dict[str, Any] | None = None,
    conditions: Dict[str, Any] | None = None,
    severity: str = "critical",
    category: str = "kde_presence",
    field: str = "kdes.lot_code",
) -> RuleDefinition:
    base_logic: Dict[str, Any] = {"type": eval_type, "field": field}
    if logic:
        base_logic.update(logic)
    return RuleDefinition(
        rule_id=rule_id,
        rule_version=1,
        title=f"Rule {rule_id}",
        description="test rule",
        severity=severity,
        category=category,
        applicability_conditions=conditions if conditions is not None else {},
        citation_reference="21 CFR 1.1310",
        effective_date=date(2024, 1, 1),
        retired_date=None,
        evaluation_logic=base_logic,
        failure_reason_template="Missing {field_name} ({field_path}) for {event_type}: {citation}",
        remediation_suggestion="Supply the field.",
    )


def _ftl_event(**overrides: Any) -> Dict[str, Any]:
    event: Dict[str, Any] = {
        "event_id": "evt-1",
        "event_type": "shipping",
        "kdes": {"lot_code": "LOT-1", "ftl_covered": True},
    }
    event.update(overrides)
    return event


def _engine_with_rules(rules: List[RuleDefinition]) -> RulesEngine:
    """Engine whose rule load returns ``rules`` without touching a database."""
    engine = RulesEngine(MagicMock())
    engine.load_active_rules = lambda: rules  # type: ignore[method-assign]
    return engine


# ---------------------------------------------------------------------------
# get_applicable_rules
# ---------------------------------------------------------------------------


class TestGetApplicableRules:
    def test_cte_match_applies_to_ftl_event(self):
        engine = RulesEngine(MagicMock())
        rule = _rule(conditions={"cte_types": ["shipping"]})
        out = engine.get_applicable_rules("shipping", [rule], event_ftl_category=None, event_is_ftl=True)
        assert out == [rule]

    def test_cte_mismatch_excluded(self):
        engine = RulesEngine(MagicMock())
        rule = _rule(conditions={"cte_types": ["harvesting"]})
        out = engine.get_applicable_rules("shipping", [rule], event_ftl_category=None, event_is_ftl=True)
        assert out == []

    def test_cte_all_matches_any_event(self):
        engine = RulesEngine(MagicMock())
        rule = _rule(conditions={"cte_types": ["all"]})
        out = engine.get_applicable_rules("receiving", [rule], event_ftl_category=None, event_is_ftl=True)
        assert out == [rule]

    def test_default_ftl_rule_skipped_for_non_ftl_event(self):
        engine = RulesEngine(MagicMock())
        rule = _rule(conditions={"cte_types": ["shipping"]})
        out = engine.get_applicable_rules("shipping", [rule], event_ftl_category=None, event_is_ftl=False)
        assert out == []

    def test_non_ftl_scope_fires_for_non_ftl_and_unknown(self):
        engine = RulesEngine(MagicMock())
        rule = _rule(conditions={"cte_types": ["shipping"], "ftl_scope": ["NON_FTL"]})
        assert engine.get_applicable_rules("shipping", [rule], event_ftl_category=None, event_is_ftl=False) == [rule]
        assert engine.get_applicable_rules("shipping", [rule], event_ftl_category=None, event_is_ftl=None) == [rule]
        assert engine.get_applicable_rules("shipping", [rule], event_ftl_category=None, event_is_ftl=True) == []

    def test_any_scope_fires_regardless_of_ftl_status(self):
        engine = RulesEngine(MagicMock())
        rule = _rule(conditions={"cte_types": ["shipping"], "ftl_scope": ["ANY"]})
        for status in (True, False, None):
            out = engine.get_applicable_rules("shipping", [rule], event_ftl_category=None, event_is_ftl=status)
            assert out == [rule]

    def test_unknown_ftl_returns_only_non_ftl_scoped_rules(self):
        engine = RulesEngine(MagicMock())
        ftl_rule = _rule("ftl", conditions={"cte_types": ["shipping"]})
        meta_rule = _rule("meta", conditions={"cte_types": ["shipping"], "ftl_scope": ["NON_FTL"]})
        out = engine.get_applicable_rules("shipping", [ftl_rule, meta_rule], event_ftl_category=None, event_is_ftl=None)
        assert out == [meta_rule]

    def test_ftl_category_scope_filters(self):
        engine = RulesEngine(MagicMock())
        rule = _rule(conditions={"cte_types": ["shipping"], "ftl_scope": ["leafy greens"]})
        match = engine.get_applicable_rules("shipping", [rule], event_ftl_category="leafy greens", event_is_ftl=True)
        assert match == [rule]
        mismatch = engine.get_applicable_rules("shipping", [rule], event_ftl_category="finfish", event_is_ftl=True)
        assert mismatch == []


# ---------------------------------------------------------------------------
# evaluate_event
# ---------------------------------------------------------------------------


class TestEvaluateEvent:
    def test_passing_stateless_rule_is_compliant(self):
        engine = _engine_with_rules([_rule(conditions={"cte_types": ["shipping"]})])
        summary = engine.evaluate_event(_ftl_event(), persist=False, tenant_id="tenant-a")
        assert summary.total_rules == 1
        assert summary.passed == 1
        assert summary.failed == 0
        assert summary.compliant is True

    def test_failing_stateless_rule_is_not_compliant(self):
        engine = _engine_with_rules([_rule(conditions={"cte_types": ["shipping"]}, field="kdes.missing_field")])
        summary = engine.evaluate_event(_ftl_event(), persist=False, tenant_id="tenant-a")
        assert summary.failed == 1
        assert summary.compliant is False

    def test_operational_warning_fail_becomes_warn(self):
        engine = _engine_with_rules(
            [
                _rule(
                    conditions={"cte_types": ["shipping"]},
                    field="kdes.missing_field",
                    severity="warning",
                    category="operational_quality",
                )
            ]
        )
        summary = engine.evaluate_event(_ftl_event(), persist=False, tenant_id="tenant-a")
        assert summary.warned == 1
        assert summary.failed == 0
        assert summary.results[0].result == "warn"
        assert summary.compliant is True

    def test_non_ftl_event_has_no_verdict(self):
        engine = _engine_with_rules([_rule(conditions={"cte_types": ["shipping"]})])
        event = _ftl_event(kdes={"lot_code": "LOT-1", "ftl_covered": False})
        summary = engine.evaluate_event(event, persist=False, tenant_id="tenant-a")
        assert summary.no_verdict_reason == "not_ftl_scoped"
        assert summary.compliant is None

    def test_non_ftl_meta_rule_pass_still_has_no_verdict(self):
        engine = _engine_with_rules(
            [
                _rule(
                    conditions={"cte_types": ["shipping"], "ftl_scope": ["NON_FTL"]},
                    logic={"type": "field_presence", "field": "kdes.lot_code"},
                )
            ]
        )
        event = _ftl_event(kdes={"lot_code": "LOT-1", "ftl_covered": False})
        summary = engine.evaluate_event(event, persist=False, tenant_id="tenant-a")
        assert summary.passed == 1
        assert summary.no_verdict_reason == "not_ftl_scoped"
        assert summary.compliant is None

    def test_missing_ftl_hint_has_no_verdict(self):
        engine = _engine_with_rules([])
        summary = engine.evaluate_event(
            {"event_id": "evt-x", "event_type": "shipping", "kdes": {}},
            persist=False,
            tenant_id="tenant-a",
        )
        assert summary.no_verdict_reason == "ftl_classification_missing"
        assert summary.compliant is None

    def test_empty_rule_set_has_no_verdict(self):
        engine = _engine_with_rules([])
        summary = engine.evaluate_event(_ftl_event(), persist=False, tenant_id="tenant-a")
        assert summary.total_rules == 0
        assert summary.compliant is None

    def test_unknown_eval_type_is_error_not_skip(self):
        engine = _engine_with_rules([_rule(eval_type="no_such_evaluator", conditions={"cte_types": ["shipping"]})])
        summary = engine.evaluate_event(_ftl_event(), persist=False, tenant_id="tenant-a")
        assert summary.errored == 1
        assert summary.results[0].result == "error"
        assert summary.compliant is False

    def test_crashing_stateless_evaluator_is_error(self, monkeypatch):
        from shared.rules.evaluators import stateless as stateless_mod

        def _boom(event_data, logic, rule):
            raise RuntimeError("boom")

        monkeypatch.setitem(stateless_mod.EVALUATORS, "field_presence", _boom)
        engine = _engine_with_rules([_rule(conditions={"cte_types": ["shipping"]})])
        summary = engine.evaluate_event(_ftl_event(), persist=False, tenant_id="tenant-a")
        assert summary.errored == 1
        assert summary.results[0].result == "error"
        assert "boom" in (summary.results[0].why_failed or "")
        assert summary.compliant is False

    def test_relational_rule_without_tenant_is_error(self):
        engine = _engine_with_rules(
            [
                _rule(
                    eval_type="temporal_order", conditions={"cte_types": ["shipping"]}, logic={"type": "temporal_order"}
                )
            ]
        )
        event = _ftl_event(traceability_lot_code="TLC-1")
        summary = engine.evaluate_event(event, persist=False, tenant_id=None)
        assert summary.errored == 1
        assert summary.results[0].result == "error"
        assert summary.compliant is False

    def test_relational_evaluator_gets_caller_tenant_not_payload(self, monkeypatch):
        from shared.rules.evaluators import relational as relational_mod

        seen: Dict[str, Any] = {}

        def _stub(event_data, logic, rule, session, *, tenant_id=None, related_events=None):
            seen["tenant_id"] = tenant_id
            seen["payload_tenant"] = event_data.get("tenant_id")
            return RuleEvaluationResult(
                rule_id=rule.rule_id,
                rule_version=rule.rule_version,
                rule_title=rule.title,
                severity=rule.severity,
                result="pass",
                category=rule.category,
            )

        monkeypatch.setitem(relational_mod.RELATIONAL_EVALUATORS, "temporal_order", _stub)
        engine = _engine_with_rules(
            [
                _rule(
                    eval_type="temporal_order", conditions={"cte_types": ["shipping"]}, logic={"type": "temporal_order"}
                )
            ]
        )
        event = _ftl_event(traceability_lot_code="TLC-1", tenant_id="tenant-forged")
        summary = engine.evaluate_event(event, persist=False, tenant_id="tenant-real")
        assert summary.passed == 1
        assert seen["tenant_id"] == "tenant-real"
        assert seen["payload_tenant"] == "tenant-forged"


# ---------------------------------------------------------------------------
# Guards, tally, cache, loading
# ---------------------------------------------------------------------------


class TestGuardsAndHelpers:
    def test_batch_requires_tenant(self):
        engine = RulesEngine(MagicMock())
        with pytest.raises(ValueError):
            engine.evaluate_events_batch([_ftl_event()], tenant_id="", persist=False)

    def test_persist_summary_requires_event_id(self):
        engine = RulesEngine(MagicMock())
        with pytest.raises(ValueError):
            engine.persist_summary(EvaluationSummary(event_id=""), tenant_id="tenant-a")

    def test_batch_evaluates_each_event(self):
        rules = [_rule(conditions={"cte_types": ["shipping"]})]
        engine = RulesEngine(MagicMock())
        engine.load_active_rules = lambda: rules  # type: ignore[method-assign]
        summaries = engine.evaluate_events_batch(
            [_ftl_event(event_id="e1"), _ftl_event(event_id="e2")], tenant_id="tenant-a", persist=False
        )
        assert [s.event_id for s in summaries] == ["e1", "e2"]
        assert all(s.compliant is True for s in summaries)

    def test_tally_counts_error_and_critical(self):
        summary = EvaluationSummary(event_id="e", total_rules=2)
        RulesEngine._tally_result(
            summary,
            RuleEvaluationResult(
                rule_id="r1",
                rule_version=1,
                rule_title="t",
                severity="critical",
                result="error",
                category="kde_presence",
            ),
        )
        RulesEngine._tally_result(
            summary,
            RuleEvaluationResult(
                rule_id="r2", rule_version=1, rule_title="t", severity="warning", result="skip", category="kde_presence"
            ),
        )
        assert summary.errored == 1
        assert summary.skipped == 1
        assert len(summary.critical_failures) == 1
        assert summary.compliant is False

    def test_cache_ttl_zero_always_reloads(self):
        session = MagicMock()
        session.execute.return_value.fetchall.return_value = []
        engine = RulesEngine(session, cache_ttl_seconds=0)
        engine.load_active_rules()
        assert engine._is_cache_fresh() is False

    def test_cache_fresh_then_invalidated(self):
        session = MagicMock()
        session.execute.return_value.fetchall.return_value = []
        engine = RulesEngine(session, cache_ttl_seconds=60)
        engine.load_active_rules()
        assert engine._is_cache_fresh() is True
        engine.invalidate_cache()
        assert engine._is_cache_fresh() is False

    def test_cache_expires_after_ttl(self, monkeypatch):
        session = MagicMock()
        session.execute.return_value.fetchall.return_value = []
        engine = RulesEngine(session, cache_ttl_seconds=60)
        engine.load_active_rules()
        monkeypatch.setattr(time, "monotonic", lambda: (engine._rules_cache_loaded_at or 0) + 61)
        assert engine._is_cache_fresh() is False

    def test_load_active_rules_parses_json_strings(self):
        import json

        session = MagicMock()
        session.execute.return_value.fetchall.return_value = [
            (
                "r1",
                2,
                "Title",
                "desc",
                "critical",
                "kde_presence",
                json.dumps({"cte_types": ["shipping"]}),
                "cite",
                date(2024, 1, 1),
                None,
                json.dumps({"type": "field_presence", "field": "kdes.lot_code"}),
                "Missing {field_name}",
                "Fix it.",
            ),
        ]
        engine = RulesEngine(session)
        rules = engine.load_active_rules()
        assert len(rules) == 1
        assert rules[0].rule_id == "r1"
        assert rules[0].rule_version == 2
        assert rules[0].applicability_conditions == {"cte_types": ["shipping"]}
        assert rules[0].evaluation_logic["field"] == "kdes.lot_code"
