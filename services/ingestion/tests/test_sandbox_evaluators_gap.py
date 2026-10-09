"""Focused coverage for ``app/sandbox/evaluators.py``.

Covers the two public entry points: per-event stateless dispatch
(``_evaluate_event_stateless``) and cross-event in-memory relational
checks (``_evaluate_relational_in_memory``), including edge and error
cases. Pure in-memory, no network or external services.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from app.sandbox import evaluators as evaluators_mod
from app.sandbox.evaluators import (
    _evaluate_event_stateless,
    _evaluate_relational_in_memory,
)
from shared.rules_engine import RuleDefinition, RuleEvaluationResult


def _mk_rule(
    *,
    rule_id: str = "R-1",
    severity: str = "warning",
    category: str = "test",
    cte_types: List[str] | None = None,
    eval_type: str = "field_presence",
) -> RuleDefinition:
    logic: Dict[str, Any] = {"type": eval_type, "field": "kdes.foo"}
    return RuleDefinition(
        rule_id=rule_id,
        rule_version=1,
        title="Rule",
        description=None,
        severity=severity,
        category=category,
        applicability_conditions={"cte_types": cte_types or []},
        citation_reference="SR 1.0",
        effective_date=datetime.now(timezone.utc).date(),
        retired_date=None,
        evaluation_logic=logic,
        failure_reason_template="fail",
        remediation_suggestion="fix it",
    )


def _mk_result(
    *,
    rule_id: str = "R-1",
    result: str = "pass",
    severity: str = "warning",
    category: str = "test",
) -> RuleEvaluationResult:
    return RuleEvaluationResult(
        rule_id=rule_id,
        rule_version=1,
        rule_title="Rule",
        severity=severity,
        result=result,
        category=category,
    )


def _relational_rule(eval_type: str, rule_id: str) -> RuleDefinition:
    return _mk_rule(
        rule_id=rule_id,
        eval_type=eval_type,
        cte_types=["harvesting", "shipping"],
    )


class TestStatelessDispatch:
    def test_unknown_eval_type_is_error(self, monkeypatch):
        rule = _mk_rule(eval_type="not_a_real_type")
        monkeypatch.setattr(evaluators_mod, "_get_applicable_rules", lambda et, include_custom=False: [rule])
        summary = _evaluate_event_stateless({"event_type": "x", "event_id": "E1"})
        assert summary.total_rules == 1
        assert summary.results[0].result == "error"
        assert "Unknown evaluation type" in summary.results[0].why_failed
        assert summary.errored == 1

    def test_evaluator_crash_is_error_not_skip(self, monkeypatch):
        rule = _mk_rule(eval_type="field_presence")

        def _crash(event, logic, rule_def):
            raise ValueError("boom")

        monkeypatch.setattr(evaluators_mod, "_get_applicable_rules", lambda et, include_custom=False: [rule])
        monkeypatch.setitem(evaluators_mod._EVALUATORS, "field_presence", _crash)
        summary = _evaluate_event_stateless({"event_type": "x", "event_id": "E1"})
        assert summary.results[0].result == "error"
        assert "ValueError" in summary.results[0].why_failed
        assert summary.errored == 1
        assert summary.results[0].result != "skip"

    def test_relational_rules_excluded_from_stateless(self, monkeypatch):
        relational = _mk_rule(rule_id="R-rel", eval_type="temporal_order")
        stateless = _mk_rule(rule_id="R-ok", eval_type="field_presence")
        monkeypatch.setattr(
            evaluators_mod,
            "_get_applicable_rules",
            lambda et, include_custom=False: [relational, stateless],
        )
        monkeypatch.setitem(
            evaluators_mod._EVALUATORS,
            "field_presence",
            lambda ev, logic, r: _mk_result(rule_id=r.rule_id, result="pass"),
        )
        summary = _evaluate_event_stateless({"event_type": "x", "event_id": "E1"})
        assert summary.total_rules == 1
        assert [r.rule_id for r in summary.results] == ["R-ok"]
        assert summary.passed == 1


class TestRelationalInMemory:
    def test_single_event_group_returns_empty(self):
        evt = {
            "event_id": "E1",
            "traceability_lot_code": "TLC-1",
            "event_type": "shipping",
        }
        assert _evaluate_relational_in_memory([evt]) == {}

    def test_ordered_events_pass(self, monkeypatch):
        rule = _relational_rule("temporal_order", "R-TEMP")
        monkeypatch.setattr(evaluators_mod, "_get_relational_rules", lambda: {"temporal_order": rule})
        evts = [
            {
                "event_id": "E1",
                "traceability_lot_code": "TLC",
                "event_type": "harvesting",
                "event_timestamp": "2026-01-01T00:00:00Z",
            },
            {
                "event_id": "E2",
                "traceability_lot_code": "TLC",
                "event_type": "shipping",
                "event_timestamp": "2026-01-05T00:00:00Z",
            },
        ]
        res = _evaluate_relational_in_memory(evts)
        assert res["E2"][0].result == "pass"

    def test_out_of_order_events_fail(self, monkeypatch):
        rule = _relational_rule("temporal_order", "R-TEMP")
        monkeypatch.setattr(evaluators_mod, "_get_relational_rules", lambda: {"temporal_order": rule})
        evts = [
            {
                "event_id": "E1",
                "traceability_lot_code": "TLC",
                "event_type": "harvesting",
                "event_timestamp": "2026-01-05T00:00:00Z",
            },
            {
                "event_id": "E2",
                "traceability_lot_code": "TLC",
                "event_type": "shipping",
                "event_timestamp": "2026-01-01T00:00:00Z",
            },
        ]
        res = _evaluate_relational_in_memory(evts)
        failed = [r for vals in res.values() for r in vals if r.result == "fail"]
        assert failed, "expected at least one temporal failure"
        assert "Chronology paradox" in failed[0].why_failed

    def test_identity_mismatch_fails(self, monkeypatch):
        rule = _relational_rule("identity_consistency", "R-ID")
        monkeypatch.setattr(evaluators_mod, "_get_relational_rules", lambda: {"identity_consistency": rule})
        evts = [
            {
                "event_id": "E1",
                "traceability_lot_code": "TLC",
                "event_type": "harvesting",
                "product_reference": "Fresh Spinach",
            },
            {
                "event_id": "E2",
                "traceability_lot_code": "TLC",
                "event_type": "shipping",
                "product_reference": "Frozen Peas",
            },
        ]
        res = _evaluate_relational_in_memory(evts)
        failed = [r for vals in res.values() for r in vals if r.result == "fail"]
        assert failed, "expected at least one identity failure"
        assert "Product identity changed" in failed[0].why_failed
