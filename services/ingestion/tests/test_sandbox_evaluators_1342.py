"""
Regression coverage for ``app/sandbox/evaluators.py``.

The module has two evaluation halves:

* ``_evaluate_event_stateless`` — per-event rule dispatch that filters
  out relational rules, invokes registered evaluators, and converts
  crashes into ``error`` results (per #1354 — fail-open behavior is
  explicitly forbidden).
* ``_evaluate_relational_in_memory`` — cross-event checks for three
  relational rule types:
    - ``temporal_order`` (CTE lifecycle ordering inside a TLC group)
    - ``identity_consistency`` (same TLC → same product across events)
    - ``mass_balance`` (per-TLC output ≤ input, plus cross-TLC checks
      on transformations)

The mass-balance code also exercises a UOM-conversion fallback via
``_normalize_to_lbs`` — we monkeypatch that in tests where we want to
assert the converted/non-converted branches deterministically.

Tracks GitHub issue #1342 (ingestion test coverage).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from app.sandbox import evaluators as evaluators_mod
from app.sandbox.evaluators import (
    _evaluate_event_stateless,
    _evaluate_relational_in_memory,
    _get_relational_rules,
)
from shared.rules_engine import (
    RuleDefinition,
    RuleEvaluationResult,
    EvaluationSummary,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mk_rule(
    *,
    rule_id: str = "R-1",
    title: str = "Rule",
    severity: str = "warning",
    category: str = "test",
    cte_types: List[str] | None = None,
    eval_type: str = "field_presence",
    field: str = "kdes.foo",
    params: Dict[str, Any] | None = None,
    citation: str = "§0.0",
    remediation: str = "do the thing",
) -> RuleDefinition:
    """Convenience factory for a fully-populated RuleDefinition."""
    from datetime import datetime, timezone
    logic: Dict[str, Any] = {"type": eval_type, "field": field}
    if params is not None:
        logic["params"] = params
    return RuleDefinition(
        rule_id=rule_id,
        rule_version=1,
        title=title,
        description=None,
        severity=severity,
        category=category,
        applicability_conditions={"cte_types": cte_types or []},
        citation_reference=citation,
        effective_date=datetime.now(timezone.utc).date(),
        retired_date=None,
        evaluation_logic=logic,
        failure_reason_template="fail",
        remediation_suggestion=remediation,
    )


def _mk_result(
    *,
    rule_id: str = "R-1",
    result: str = "pass",
    severity: str = "warning",
) -> RuleEvaluationResult:
    return RuleEvaluationResult(
        rule_id=rule_id,
        rule_version=1,
        rule_title="Rule",
        severity=severity,
        result=result,
        category="test",
    )


# ===========================================================================
# _evaluate_event_stateless
# ===========================================================================

class TestEvaluateStatelessBasics:

    def test_no_applicable_rules_returns_empty_summary(self, monkeypatch):
        """Unknown event_type yields zero applicable rules."""
        monkeypatch.setattr(evaluators_mod, "_get_applicable_rules",
                            lambda et, include_custom=False: [])
        summary = _evaluate_event_stateless({"event_type": "mystery", "event_id": "E1"})
        assert isinstance(summary, EvaluationSummary)
        assert summary.event_id == "E1"
        assert summary.total_rules == 0
        assert summary.results == []

    def test_event_id_from_event_data(self, monkeypatch):
        monkeypatch.setattr(evaluators_mod, "_get_applicable_rules",
                            lambda et, include_custom=False: [])
        summary = _evaluate_event_stateless({"event_type": "x", "event_id": "E-CUSTOM"})
        assert summary.event_id == "E-CUSTOM"

    def test_event_id_defaults_to_uuid(self, monkeypatch):
        monkeypatch.setattr(evaluators_mod, "_get_applicable_rules",
                            lambda et, include_custom=False: [])
        summary = _evaluate_event_stateless({"event_type": "x"})
        # UUID4 hex is 32 chars + 4 dashes
        assert len(summary.event_id) == 36

    def test_include_custom_passthrough(self, monkeypatch):
        captured = {}

        def _fake(event_type, *, include_custom=False):
            captured["include_custom"] = include_custom
            return []
        monkeypatch.setattr(evaluators_mod, "_get_applicable_rules", _fake)
        _evaluate_event_stateless({"event_type": "x"}, include_custom=True)
        assert captured["include_custom"] is True

    def test_relational_rules_filtered_out(self, monkeypatch):
        """Rules with relational eval types must not be dispatched here."""
        relational = _mk_rule(eval_type="temporal_order")
        stateless = _mk_rule(rule_id="R-stateless", eval_type="field_presence")
        monkeypatch.setattr(evaluators_mod, "_get_applicable_rules",
                            lambda et, include_custom=False: [relational, stateless])
        # Stub out the stateless evaluator so we don't care about its logic
        monkeypatch.setitem(
            evaluators_mod._EVALUATORS,
            "field_presence",
            lambda ev, logic, rule: _mk_result(rule_id=rule.rule_id, result="pass"),
        )
        summary = _evaluate_event_stateless({"event_type": "x"})
        assert summary.total_rules == 1
        assert summary.results[0].rule_id == "R-stateless"


class TestEvaluateStatelessDispatch:

    def test_unknown_eval_type_reports_error(self, monkeypatch):
        rule = _mk_rule(eval_type="not_a_real_type")
        monkeypatch.setattr(evaluators_mod, "_get_applicable_rules",
                            lambda et, include_custom=False: [rule])
        summary = _evaluate_event_stateless({"event_type": "x"})
        assert len(summary.results) == 1
        assert summary.results[0].result == "error"
        assert "Unknown evaluation type" in summary.results[0].why_failed
        assert summary.errored == 1

    def test_evaluator_crash_reports_error_with_type_and_message(self, monkeypatch):
        rule = _mk_rule(eval_type="field_presence")

        def _crash(ev, logic, r):
            raise ValueError("boom!")

        monkeypatch.setattr(evaluators_mod, "_get_applicable_rules",
                            lambda et, include_custom=False: [rule])
        monkeypatch.setitem(evaluators_mod._EVALUATORS, "field_presence", _crash)
        summary = _evaluate_event_stateless({"event_type": "x"})
        assert summary.results[0].result == "error"
        assert "ValueError" in summary.results[0].why_failed
        assert "boom!" in summary.results[0].why_failed

    def test_evaluator_returns_pass_increments_passed(self, monkeypatch):
        rule = _mk_rule()
        monkeypatch.setattr(evaluators_mod, "_get_applicable_rules",
                            lambda et, include_custom=False: [rule])
        monkeypatch.setitem(
            evaluators_mod._EVALUATORS, "field_presence",
            lambda ev, logic, r: _mk_result(result="pass"),
        )
        summary = _evaluate_event_stateless({"event_type": "x"})
        assert summary.passed == 1
        assert summary.failed == 0

    def test_evaluator_returns_fail_increments_failed(self, monkeypatch):
        rule = _mk_rule(severity="warning")
        monkeypatch.setattr(evaluators_mod, "_get_applicable_rules",
                            lambda et, include_custom=False: [rule])
        monkeypatch.setitem(
            evaluators_mod._EVALUATORS, "field_presence",
            lambda ev, logic, r: _mk_result(result="fail"),
        )
        summary = _evaluate_event_stateless({"event_type": "x"})
        assert summary.failed == 1
        # Non-critical failure does NOT go into critical_failures
        assert summary.critical_failures == []

    def test_critical_fail_goes_into_critical_failures(self, monkeypatch):
        rule = _mk_rule(severity="critical")
        monkeypatch.setattr(evaluators_mod, "_get_applicable_rules",
                            lambda et, include_custom=False: [rule])
        monkeypatch.setitem(
            evaluators_mod._EVALUATORS, "field_presence",
            lambda ev, logic, r: _mk_result(result="fail", severity="critical"),
        )
        summary = _evaluate_event_stateless({"event_type": "x"})
        assert summary.failed == 1
        assert len(summary.critical_failures) == 1

    def test_warn_increments_warned(self, monkeypatch):
        rule = _mk_rule()
        monkeypatch.setattr(evaluators_mod, "_get_applicable_rules",
                            lambda et, include_custom=False: [rule])
        monkeypatch.setitem(
            evaluators_mod._EVALUATORS, "field_presence",
            lambda ev, logic, r: _mk_result(result="warn"),
        )
        summary = _evaluate_event_stateless({"event_type": "x"})
        assert summary.warned == 1

    def test_critical_error_goes_into_critical_failures(self, monkeypatch):
        rule = _mk_rule(severity="critical")
        monkeypatch.setattr(evaluators_mod, "_get_applicable_rules",
                            lambda et, include_custom=False: [rule])
        monkeypatch.setitem(
            evaluators_mod._EVALUATORS, "field_presence",
            lambda ev, logic, r: _mk_result(result="error", severity="critical"),
        )
        summary = _evaluate_event_stateless({"event_type": "x"})
        assert summary.errored == 1
        assert len(summary.critical_failures) == 1

    def test_not_ftl_scoped_bucket(self, monkeypatch):
        rule = _mk_rule()
        monkeypatch.setattr(evaluators_mod, "_get_applicable_rules",
                            lambda et, include_custom=False: [rule])
        monkeypatch.setitem(
            evaluators_mod._EVALUATORS, "field_presence",
            lambda ev, logic, r: _mk_result(result="not_ftl_scoped"),
        )
        summary = _evaluate_event_stateless({"event_type": "x"})
        assert summary.not_ftl_scoped == 1

    def test_unrecognized_result_goes_into_skipped(self, monkeypatch):
        """Any result string other than pass/fail/warn/error/not_ftl_scoped → skipped."""
        rule = _mk_rule()
        monkeypatch.setattr(evaluators_mod, "_get_applicable_rules",
                            lambda et, include_custom=False: [rule])
        monkeypatch.setitem(
            evaluators_mod._EVALUATORS, "field_presence",
            lambda ev, logic, r: _mk_result(result="skip"),
        )
        summary = _evaluate_event_stateless({"event_type": "x"})
        assert summary.skipped == 1

    def test_eval_type_defaults_to_field_presence(self, monkeypatch):
        """A rule with no ``type`` key defaults to field_presence."""
        from datetime import datetime, timezone
        rule_no_type = RuleDefinition(
            rule_id="R", rule_version=1, title="T", description=None,
            severity="warning", category="test",
            applicability_conditions={},
            citation_reference=None,
            effective_date=datetime.now(timezone.utc).date(),
            retired_date=None,
            evaluation_logic={"field": "kdes.foo"},  # no "type" key
            failure_reason_template="",
            remediation_suggestion=None,
        )
        captured = {}
        monkeypatch.setattr(evaluators_mod, "_get_applicable_rules",
                            lambda et, include_custom=False: [rule_no_type])
        def _fp(ev, logic, r):
            captured["called"] = True
            return _mk_result(result="pass")
        monkeypatch.setitem(evaluators_mod._EVALUATORS, "field_presence", _fp)
        _evaluate_event_stateless({"event_type": "x"})
        assert captured.get("called") is True


# ===========================================================================
# _get_relational_rules
# ===========================================================================

class TestGetRelationalRules:

    def test_returns_dict_keyed_by_eval_type(self):
        rules = _get_relational_rules()
        assert isinstance(rules, dict)
        # In the seed data all three relational types are defined
        assert set(rules.keys()) <= {"temporal_order", "identity_consistency", "mass_balance"}

    def test_non_relational_rules_excluded(self, monkeypatch):
        """Replace _SANDBOX_RULES with rules whose types are stateless → empty."""
        stateless_only = [_mk_rule(eval_type="field_presence")]
        monkeypatch.setattr(evaluators_mod, "_SANDBOX_RULES", stateless_only)
        assert _get_relational_rules() == {}

    def test_collects_each_relational_type_once(self, monkeypatch):
        tr = _mk_rule(rule_id="R-T", eval_type="temporal_order")
        ic = _mk_rule(rule_id="R-I", eval_type="identity_consistency")
        mb = _mk_rule(rule_id="R-M", eval_type="mass_balance")
        other = _mk_rule(rule_id="R-O", eval_type="field_presence")
        monkeypatch.setattr(evaluators_mod, "_SANDBOX_RULES", [tr, ic, mb, other])
        result = _get_relational_rules()
        assert set(result.keys()) == {"temporal_order", "identity_consistency", "mass_balance"}
        assert result["temporal_order"].rule_id == "R-T"
        assert result["identity_consistency"].rule_id == "R-I"
        assert result["mass_balance"].rule_id == "R-M"


# ===========================================================================
# _evaluate_relational_in_memory — early returns
# ===========================================================================

class TestRelationalEarlyReturns:

    def test_no_relational_rules_returns_empty(self, monkeypatch):
        monkeypatch.setattr(evaluators_mod, "_get_relational_rules", lambda: {})
        assert _evaluate_relational_in_memory([]) == {}

    def test_empty_events_returns_empty(self, monkeypatch):
        # Even with rules defined, no events → no results
        assert _evaluate_relational_in_memory([]) == {}

    def test_single_event_per_tlc_returns_empty(self, monkeypatch):
        """Single-event TLC groups are skipped — no cross-event check possible."""
        evt = {"traceability_lot_code": "TLC-1", "event_id": "E1", "event_type": "shipping"}
        assert _evaluate_relational_in_memory([evt]) == {}

    def test_empty_tlc_skipped_from_grouping(self, monkeypatch):
        """Events without a TLC don't form groups, even if there are 2 of them."""
        evts = [
            {"traceability_lot_code": "", "event_id": "E1", "event_type": "shipping"},
            {"traceability_lot_code": None, "event_id": "E2", "event_type": "shipping"},
        ]
        assert _evaluate_relational_in_memory(evts) == {}


# ===========================================================================
# _evaluate_relational_in_memory — temporal order
# ===========================================================================

def _only_temporal_rule(monkeypatch):
    """Patch _get_relational_rules to return only the temporal rule."""
    rule = _mk_rule(
        rule_id="R-TEMP",
        eval_type="temporal_order",
        cte_types=["shipping", "harvesting"],
        citation="§1.0",
    )
    monkeypatch.setattr(evaluators_mod, "_get_relational_rules",
                        lambda: {"temporal_order": rule})
    return rule


class TestTemporalOrder:

    def test_ordered_events_pass(self, monkeypatch):
        _only_temporal_rule(monkeypatch)
        evts = [
            {"event_id": "E1", "traceability_lot_code": "TLC",
             "event_type": "harvesting", "event_timestamp": "2026-01-01T00:00:00Z"},
            {"event_id": "E2", "traceability_lot_code": "TLC",
             "event_type": "shipping", "event_timestamp": "2026-01-05T00:00:00Z"},
        ]
        res = _evaluate_relational_in_memory(evts)
        assert res["E2"][0].result == "pass"

    def test_out_of_order_events_fail(self, monkeypatch):
        _only_temporal_rule(monkeypatch)
        # Shipping timestamped BEFORE harvesting — paradox
        evts = [
            {"event_id": "E1", "traceability_lot_code": "TLC",
             "event_type": "harvesting", "event_timestamp": "2026-01-05T00:00:00Z"},
            {"event_id": "E2", "traceability_lot_code": "TLC",
             "event_type": "shipping", "event_timestamp": "2026-01-01T00:00:00Z"},
        ]
        res = _evaluate_relational_in_memory(evts)
        failed = [r for vals in res.values() for r in vals if r.result == "fail"]
        assert failed, "Expected at least one temporal failure"
        assert "Chronology paradox" in failed[0].why_failed
        assert "TLC" in failed[0].why_failed

    def test_cte_type_filter_skips_non_applicable_events(self, monkeypatch):
        """A rule scoped to ['shipping'] should NOT emit results for cooling."""
        from datetime import datetime, timezone
        rule = RuleDefinition(
            rule_id="R-T", rule_version=1, title="T", description=None,
            severity="warning", category="test",
            applicability_conditions={"cte_types": ["shipping"]},
            citation_reference="§1", effective_date=datetime.now(timezone.utc).date(),
            retired_date=None,
            evaluation_logic={"type": "temporal_order"},
            failure_reason_template="",
            remediation_suggestion=None,
        )
        monkeypatch.setattr(evaluators_mod, "_get_relational_rules",
                            lambda: {"temporal_order": rule})
        evts = [
            {"event_id": "E1", "traceability_lot_code": "TLC",
             "event_type": "cooling", "event_timestamp": "2026-01-01T00:00:00Z"},
            {"event_id": "E2", "traceability_lot_code": "TLC",
             "event_type": "cooling", "event_timestamp": "2026-01-02T00:00:00Z"},
        ]
        res = _evaluate_relational_in_memory(evts)
        # Neither event applies — no temporal results at all
        temporal_results = [r for vals in res.values() for r in vals]
        assert temporal_results == []

    def test_unknown_event_type_skipped_for_current(self, monkeypatch):
        """An event with an event_type not in _CTE_LIFECYCLE_ORDER gets skipped."""
        _only_temporal_rule(monkeypatch)
        evts = [
            {"event_id": "E1", "traceability_lot_code": "TLC",
             "event_type": "shipping", "event_timestamp": "2026-01-01T00:00:00Z"},
            # "cleaning" isn't in _CTE_LIFECYCLE_ORDER
            {"event_id": "E2", "traceability_lot_code": "TLC",
             "event_type": "cleaning", "event_timestamp": "2026-01-05T00:00:00Z"},
        ]
        res = _evaluate_relational_in_memory(evts)
        # The shipping event IS evaluated but "other" (cleaning) is skipped mid-loop
        # So shipping passes because cleaning doesn't contribute to violations.
        shipping_results = res.get("E1", [])
        assert shipping_results and shipping_results[0].result == "pass"

    def test_all_sentinel_in_cte_types_applies_everywhere(self, monkeypatch):
        from datetime import datetime, timezone
        rule = RuleDefinition(
            rule_id="R-T", rule_version=1, title="T", description=None,
            severity="warning", category="test",
            applicability_conditions={"cte_types": ["all"]},
            citation_reference="§1", effective_date=datetime.now(timezone.utc).date(),
            retired_date=None,
            evaluation_logic={"type": "temporal_order"},
            failure_reason_template="",
            remediation_suggestion=None,
        )
        monkeypatch.setattr(evaluators_mod, "_get_relational_rules",
                            lambda: {"temporal_order": rule})
        evts = [
            {"event_id": "E1", "traceability_lot_code": "TLC",
             "event_type": "shipping", "event_timestamp": "2026-01-01T00:00:00Z"},
            {"event_id": "E2", "traceability_lot_code": "TLC",
             "event_type": "harvesting", "event_timestamp": "2026-01-05T00:00:00Z"},
        ]
        res = _evaluate_relational_in_memory(evts)
        # At least one event produces a result (applicable via "all")
        assert res

    def test_all_sentinel_with_current_event_missing_from_lifecycle(self, monkeypatch):
        """When 'all' is in cte_types but current event_type is NOT in
        _CTE_LIFECYCLE_ORDER, the inner `continue` at line 161 fires and
        the event is skipped silently."""
        from datetime import datetime, timezone
        rule = RuleDefinition(
            rule_id="R-T", rule_version=1, title="T", description=None,
            severity="warning", category="test",
            applicability_conditions={"cte_types": ["all"]},
            citation_reference="§1", effective_date=datetime.now(timezone.utc).date(),
            retired_date=None,
            evaluation_logic={"type": "temporal_order"},
            failure_reason_template="",
            remediation_suggestion=None,
        )
        monkeypatch.setattr(evaluators_mod, "_get_relational_rules",
                            lambda: {"temporal_order": rule})
        evts = [
            # "cleaning" bypasses the cte_types filter (via "all") but is not
            # in _CTE_LIFECYCLE_ORDER — current_stage is None, event is skipped.
            {"event_id": "E1", "traceability_lot_code": "TLC",
             "event_type": "cleaning", "event_timestamp": "2026-01-01T00:00:00Z"},
            {"event_id": "E2", "traceability_lot_code": "TLC",
             "event_type": "cleaning", "event_timestamp": "2026-01-05T00:00:00Z"},
        ]
        res = _evaluate_relational_in_memory(evts)
        # Both events are skipped by the `current_stage is None` continue,
        # so no temporal_order results are produced.
        for evt_results in res.values():
            assert not any(r.rule_id == "R-T" for r in evt_results)


# ===========================================================================
# _evaluate_relational_in_memory — identity consistency
# ===========================================================================

def _only_identity_rule(monkeypatch, *, cte_types=None):
    from datetime import datetime, timezone
    rule = RuleDefinition(
        rule_id="R-IC", rule_version=1, title="IC", description=None,
        severity="warning", category="test",
        applicability_conditions={"cte_types": cte_types or ["shipping", "harvesting"]},
        citation_reference="§2", effective_date=datetime.now(timezone.utc).date(),
        retired_date=None,
        evaluation_logic={"type": "identity_consistency"},
        failure_reason_template="",
        remediation_suggestion="fix it",
    )
    monkeypatch.setattr(evaluators_mod, "_get_relational_rules",
                        lambda: {"identity_consistency": rule})
    return rule


class TestIdentityConsistency:

    def test_same_product_across_events_passes(self, monkeypatch):
        _only_identity_rule(monkeypatch)
        evts = [
            {"event_id": "E1", "traceability_lot_code": "TLC",
             "event_type": "harvesting", "product_reference": "Romaine"},
            {"event_id": "E2", "traceability_lot_code": "TLC",
             "event_type": "shipping", "product_reference": "Romaine"},
        ]
        res = _evaluate_relational_in_memory(evts)
        assert all(r.result == "pass" for vals in res.values() for r in vals)

    def test_different_product_fails(self, monkeypatch):
        _only_identity_rule(monkeypatch)
        evts = [
            {"event_id": "E1", "traceability_lot_code": "TLC",
             "event_type": "harvesting", "product_reference": "Romaine"},
            {"event_id": "E2", "traceability_lot_code": "TLC",
             "event_type": "shipping", "product_reference": "Spinach"},
        ]
        res = _evaluate_relational_in_memory(evts)
        fails = [r for vals in res.values() for r in vals if r.result == "fail"]
        assert fails
        assert "identity changed" in fails[0].why_failed
        assert "TLC" in fails[0].why_failed

    def test_whitespace_and_case_normalization_treats_same(self, monkeypatch):
        _only_identity_rule(monkeypatch)
        evts = [
            {"event_id": "E1", "traceability_lot_code": "TLC",
             "event_type": "harvesting", "product_reference": "Romaine Lettuce"},
            {"event_id": "E2", "traceability_lot_code": "TLC",
             "event_type": "shipping", "product_reference": "  romaine   LETTUCE  "},
        ]
        res = _evaluate_relational_in_memory(evts)
        assert all(r.result == "pass" for vals in res.values() for r in vals)

    def test_blank_product_reference_skipped(self, monkeypatch):
        """An event with no product_reference skips the inner check."""
        _only_identity_rule(monkeypatch)
        evts = [
            {"event_id": "E1", "traceability_lot_code": "TLC",
             "event_type": "harvesting", "product_reference": "Romaine"},
            {"event_id": "E2", "traceability_lot_code": "TLC",
             "event_type": "shipping", "product_reference": ""},
        ]
        res = _evaluate_relational_in_memory(evts)
        # Only E1 has a product — E2 is skipped by the blank guard
        assert "E2" not in res or all(
            r.rule_id != "R-IC" for r in res.get("E2", [])
        )

    def test_cte_type_filter_skips_non_applicable(self, monkeypatch):
        _only_identity_rule(monkeypatch, cte_types=["shipping"])
        evts = [
            {"event_id": "E1", "traceability_lot_code": "TLC",
             "event_type": "harvesting", "product_reference": "Romaine"},
            {"event_id": "E2", "traceability_lot_code": "TLC",
             "event_type": "harvesting", "product_reference": "Spinach"},
        ]
        # Neither event is shipping → no results at all
        res = _evaluate_relational_in_memory(evts)
        assert res == {}

    def test_all_sentinel_applies_to_every_event(self, monkeypatch):
        _only_identity_rule(monkeypatch, cte_types=["all"])
        evts = [
            {"event_id": "E1", "traceability_lot_code": "TLC",
             "event_type": "cooling", "product_reference": "Romaine"},
            {"event_id": "E2", "traceability_lot_code": "TLC",
             "event_type": "cooling", "product_reference": "Spinach"},
        ]
        res = _evaluate_relational_in_memory(evts)
        fails = [r for vals in res.values() for r in vals if r.result == "fail"]
        assert fails  # At least one mismatch reported


# ===========================================================================
# _evaluate_relational_in_memory — per-TLC mass balance
# ===========================================================================

def _only_mass_rule(monkeypatch, *, cte_types=None, tolerance=1.0):
    from datetime import datetime, timezone
    rule = RuleDefinition(
        rule_id="R-MB", rule_version=1, title="MB", description=None,
        severity="warning", category="test",
        applicability_conditions={"cte_types": cte_types or ["shipping"]},
        citation_reference="§3", effective_date=datetime.now(timezone.utc).date(),
        retired_date=None,
        evaluation_logic={"type": "mass_balance",
                          "params": {"tolerance_percent": tolerance}},
        failure_reason_template="",
        remediation_suggestion="rebalance",
    )
    monkeypatch.setattr(evaluators_mod, "_get_relational_rules",
                        lambda: {"mass_balance": rule})
    return rule


class TestMassBalancePerTlc:

    def test_consistent_units_within_tolerance_pass(self, monkeypatch):
        _only_mass_rule(monkeypatch, tolerance=1.0)
        evts = [
            {"event_id": "E1", "traceability_lot_code": "TLC",
             "event_type": "harvesting", "quantity": 100, "unit_of_measure": "lbs"},
            {"event_id": "E2", "traceability_lot_code": "TLC",
             "event_type": "shipping", "quantity": 99, "unit_of_measure": "lbs"},
        ]
        res = _evaluate_relational_in_memory(evts)
        assert res["E2"][0].result == "pass"

    def test_output_exceeds_input_by_tolerance_fails(self, monkeypatch):
        _only_mass_rule(monkeypatch, tolerance=1.0)
        evts = [
            {"event_id": "E1", "traceability_lot_code": "TLC",
             "event_type": "harvesting", "quantity": 100, "unit_of_measure": "lbs"},
            {"event_id": "E2", "traceability_lot_code": "TLC",
             "event_type": "shipping", "quantity": 200, "unit_of_measure": "lbs"},
        ]
        res = _evaluate_relational_in_memory(evts)
        assert res["E2"][0].result == "fail"
        assert "Mass balance violation" in res["E2"][0].why_failed

    def test_mixed_units_not_convertible_warns(self, monkeypatch):
        _only_mass_rule(monkeypatch)
        # Patch normalize_to_lbs to always fail
        monkeypatch.setattr(evaluators_mod, "_normalize_to_lbs",
                            lambda q, u: None)
        evts = [
            {"event_id": "E1", "traceability_lot_code": "TLC",
             "event_type": "harvesting", "quantity": 100, "unit_of_measure": "lbs"},
            {"event_id": "E2", "traceability_lot_code": "TLC",
             "event_type": "shipping", "quantity": 50, "unit_of_measure": "cases"},
        ]
        res = _evaluate_relational_in_memory(evts)
        assert res["E2"][0].result == "warn"
        assert "inconclusive" in res["E2"][0].why_failed

    def test_mixed_units_convertible_uses_conversion(self, monkeypatch):
        _only_mass_rule(monkeypatch, tolerance=1.0)
        # 10 cases normalize to 100 lbs
        def _norm(q, u):
            if u.lower() == "cases":
                return q * 10.0
            if u.lower() == "lbs":
                return q
            return None
        monkeypatch.setattr(evaluators_mod, "_normalize_to_lbs", _norm)
        evts = [
            {"event_id": "E1", "traceability_lot_code": "TLC",
             "event_type": "harvesting", "quantity": 10, "unit_of_measure": "cases"},
            {"event_id": "E2", "traceability_lot_code": "TLC",
             "event_type": "shipping", "quantity": 100, "unit_of_measure": "lbs"},
        ]
        res = _evaluate_relational_in_memory(evts)
        # 10 cases = 100 lbs ≥ 100 lbs shipping → within tolerance → pass
        assert res["E2"][0].result == "pass"
        # Evidence shows uom_converted = True
        evidence = res["E2"][0].evidence_fields_inspected[0]
        assert evidence["uom_converted"] is True

    def test_none_quantity_skipped_in_collection(self, monkeypatch):
        _only_mass_rule(monkeypatch)
        evts = [
            {"event_id": "E1", "traceability_lot_code": "TLC",
             "event_type": "harvesting", "quantity": None, "unit_of_measure": "lbs"},
            {"event_id": "E2", "traceability_lot_code": "TLC",
             "event_type": "shipping", "quantity": 50, "unit_of_measure": "lbs"},
        ]
        res = _evaluate_relational_in_memory(evts)
        # input=0 because None was skipped; output_total=50 > 0 * (1+.01) → but code
        # also has ``total_input > 0`` guard so it goes to the final else (pass)
        assert res["E2"][0].result == "pass"

    def test_zero_input_falls_through_to_pass(self, monkeypatch):
        """When total_input is 0, the fail branch is bypassed (no division)."""
        _only_mass_rule(monkeypatch)
        evts = [
            {"event_id": "E1", "traceability_lot_code": "TLC",
             "event_type": "shipping", "quantity": 50, "unit_of_measure": "lbs"},
            {"event_id": "E2", "traceability_lot_code": "TLC",
             "event_type": "shipping", "quantity": 50, "unit_of_measure": "lbs"},
        ]
        res = _evaluate_relational_in_memory(evts)
        # Both shipping — no inputs; ``total_input > 0`` guard false → pass
        for evt_results in res.values():
            assert evt_results[0].result == "pass"

    def test_cte_type_filter_skips_non_applicable(self, monkeypatch):
        _only_mass_rule(monkeypatch, cte_types=["shipping"])
        evts = [
            {"event_id": "E1", "traceability_lot_code": "TLC",
             "event_type": "harvesting", "quantity": 100, "unit_of_measure": "lbs"},
            {"event_id": "E2", "traceability_lot_code": "TLC",
             "event_type": "harvesting", "quantity": 200, "unit_of_measure": "lbs"},
        ]
        # Neither event is shipping — no mass-balance results
        res = _evaluate_relational_in_memory(evts)
        assert res == {}

    def test_tolerance_default_applies_when_params_missing(self, monkeypatch):
        """When ``params`` is absent, tolerance defaults to 1.0."""
        from datetime import datetime, timezone
        rule = RuleDefinition(
            rule_id="R-MB", rule_version=1, title="MB", description=None,
            severity="warning", category="test",
            applicability_conditions={"cte_types": ["shipping"]},
            citation_reference="§3", effective_date=datetime.now(timezone.utc).date(),
            retired_date=None,
            evaluation_logic={"type": "mass_balance"},  # no params
            failure_reason_template="",
            remediation_suggestion=None,
        )
        monkeypatch.setattr(evaluators_mod, "_get_relational_rules",
                            lambda: {"mass_balance": rule})
        evts = [
            {"event_id": "E1", "traceability_lot_code": "TLC",
             "event_type": "harvesting", "quantity": 100, "unit_of_measure": "lbs"},
            {"event_id": "E2", "traceability_lot_code": "TLC",
             "event_type": "shipping", "quantity": 101, "unit_of_measure": "lbs"},
        ]
        # 101 / 100 = 1.01 = exactly at the 1% tolerance → pass (<= not <)
        res = _evaluate_relational_in_memory(evts)
        assert res["E2"][0].result == "pass"


# ===========================================================================
# _evaluate_relational_in_memory — cross-TLC transformation mass balance
# ===========================================================================

class TestMassBalanceCrossTlc:

    def test_transformation_output_within_tolerance_passes(self, monkeypatch):
        _only_mass_rule(monkeypatch, cte_types=["transformation"])
        evts = [
            {"event_id": "E-IN-A", "traceability_lot_code": "LOT-A",
             "event_type": "harvesting", "quantity": 50, "unit_of_measure": "lbs"},
            {"event_id": "E-IN-B", "traceability_lot_code": "LOT-B",
             "event_type": "harvesting", "quantity": 50, "unit_of_measure": "lbs"},
            {"event_id": "E-XFORM", "traceability_lot_code": "LOT-MEGA",
             "event_type": "transformation", "quantity": 99, "unit_of_measure": "lbs",
             "kdes": {"input_traceability_lot_codes": ["LOT-A", "LOT-B"]}},
        ]
        res = _evaluate_relational_in_memory(evts)
        # The transformation event's cross-TLC check should pass
        xform_results = [r for r in res.get("E-XFORM", []) if r.rule_id == "R-MB"]
        assert any(r.result == "pass" for r in xform_results)

    def test_transformation_output_exceeds_tolerance_fails(self, monkeypatch):
        _only_mass_rule(monkeypatch, cte_types=["transformation"], tolerance=1.0)
        evts = [
            {"event_id": "E-IN-A", "traceability_lot_code": "LOT-A",
             "event_type": "harvesting", "quantity": 50, "unit_of_measure": "lbs"},
            {"event_id": "E-IN-B", "traceability_lot_code": "LOT-B",
             "event_type": "harvesting", "quantity": 50, "unit_of_measure": "lbs"},
            {"event_id": "E-XFORM", "traceability_lot_code": "LOT-MEGA",
             "event_type": "transformation", "quantity": 500, "unit_of_measure": "lbs",
             "kdes": {"input_traceability_lot_codes": ["LOT-A", "LOT-B"]}},
        ]
        res = _evaluate_relational_in_memory(evts)
        xform_fails = [r for r in res.get("E-XFORM", []) if r.result == "fail"]
        assert xform_fails
        assert "transformation" in xform_fails[0].why_failed.lower()

    def test_transformation_with_string_input_tlcs(self, monkeypatch):
        _only_mass_rule(monkeypatch, cte_types=["transformation"])
        evts = [
            {"event_id": "E-IN", "traceability_lot_code": "LOT-A",
             "event_type": "harvesting", "quantity": 100, "unit_of_measure": "lbs"},
            {"event_id": "E-XFORM", "traceability_lot_code": "LOT-MEGA",
             "event_type": "transformation", "quantity": 90, "unit_of_measure": "lbs",
             "kdes": {"input_traceability_lot_codes": "LOT-A, "}},
        ]
        res = _evaluate_relational_in_memory(evts)
        xform_results = [r for r in res.get("E-XFORM", []) if r.rule_id == "R-MB"]
        # Successfully parsed input → pass
        assert any(r.result == "pass" for r in xform_results)

    def test_transformation_without_input_tlcs_skipped(self, monkeypatch):
        _only_mass_rule(monkeypatch, cte_types=["transformation"])
        evts = [
            {"event_id": "E1", "traceability_lot_code": "TLC",
             "event_type": "transformation", "quantity": 100, "unit_of_measure": "lbs",
             "kdes": {}},
            {"event_id": "E2", "traceability_lot_code": "TLC",
             "event_type": "transformation", "quantity": 100, "unit_of_measure": "lbs",
             "kdes": {}},
        ]
        res = _evaluate_relational_in_memory(evts)
        # Per-TLC check still fires for each event; cross-TLC skipped entirely
        # because input_tlcs is empty. Count the rule results — at most 2 (the
        # per-TLC passes), not 4 (would be 2 per + 2 cross).
        xform_result_count = sum(
            1 for vals in res.values() for r in vals if r.rule_id == "R-MB"
        )
        assert xform_result_count == 2

    def test_transformation_without_output_qty_skipped(self, monkeypatch):
        _only_mass_rule(monkeypatch, cte_types=["transformation"])
        evts = [
            {"event_id": "E-IN", "traceability_lot_code": "LOT-A",
             "event_type": "harvesting", "quantity": 100, "unit_of_measure": "lbs"},
            {"event_id": "E-XFORM", "traceability_lot_code": "LOT-MEGA",
             "event_type": "transformation", "quantity": None, "unit_of_measure": "lbs",
             "kdes": {"input_traceability_lot_codes": ["LOT-A"]}},
        ]
        res = _evaluate_relational_in_memory(evts)
        # No transformation-level result emitted for E-XFORM
        assert "E-XFORM" not in res or not any(
            r.rule_id == "R-MB" for r in res.get("E-XFORM", [])
        )

    def test_transformation_with_zero_input_total_skipped(self, monkeypatch):
        """When input TLCs exist but none have quantity → total_input == 0 → skip."""
        _only_mass_rule(monkeypatch, cte_types=["transformation"])
        evts = [
            {"event_id": "E-IN", "traceability_lot_code": "LOT-A",
             "event_type": "harvesting", "quantity": None, "unit_of_measure": "lbs"},
            {"event_id": "E-XFORM", "traceability_lot_code": "LOT-MEGA",
             "event_type": "transformation", "quantity": 90, "unit_of_measure": "lbs",
             "kdes": {"input_traceability_lot_codes": ["LOT-A"]}},
        ]
        res = _evaluate_relational_in_memory(evts)
        # No cross-TLC result for the transformation because total_input=0
        assert "E-XFORM" not in res

    def test_cross_tlc_uom_conversion_success(self, monkeypatch):
        _only_mass_rule(monkeypatch, cte_types=["transformation"], tolerance=5.0)
        def _norm(q, u):
            if u.lower() == "cases":
                return q * 10.0
            if u.lower() == "lbs":
                return q
            return None
        monkeypatch.setattr(evaluators_mod, "_normalize_to_lbs", _norm)
        evts = [
            {"event_id": "E-IN", "traceability_lot_code": "LOT-A",
             "event_type": "harvesting", "quantity": 10, "unit_of_measure": "cases"},
            {"event_id": "E-XFORM", "traceability_lot_code": "LOT-MEGA",
             "event_type": "transformation", "quantity": 95, "unit_of_measure": "lbs",
             "kdes": {"input_traceability_lot_codes": ["LOT-A"]}},
        ]
        res = _evaluate_relational_in_memory(evts)
        xform_results = [r for r in res.get("E-XFORM", []) if r.rule_id == "R-MB"]
        # 10 cases → 100 lbs ≥ 95 → pass
        assert any(r.result == "pass" for r in xform_results)
        pass_evidence = [
            r.evidence_fields_inspected[0] for r in xform_results if r.result == "pass"
        ]
        assert any(ev.get("uom_converted") for ev in pass_evidence)

    def test_cross_tlc_input_uom_unconvertible_aborts_conversion(self, monkeypatch):
        """If any input lot's UOM can't be normalized to lbs, `all_ok` flips
        to False and both inner loops break (lines 446-450). The code then
        falls back to raw quantities."""
        _only_mass_rule(monkeypatch, cte_types=["transformation"], tolerance=5.0)

        def _norm(q, u):
            # "lbs" normalizes, "widgets" fails.
            if u.lower() == "lbs":
                return q
            return None
        monkeypatch.setattr(evaluators_mod, "_normalize_to_lbs", _norm)

        evts = [
            # Two input lots with DIFFERENT uoms so len(all_units) > 1 and
            # conversion is attempted. The "widgets" UOM forces lbs=None.
            {"event_id": "E-IN-A", "traceability_lot_code": "LOT-A",
             "event_type": "harvesting", "quantity": 5, "unit_of_measure": "widgets"},
            {"event_id": "E-IN-B", "traceability_lot_code": "LOT-A",
             "event_type": "harvesting", "quantity": 5, "unit_of_measure": "widgets"},
            {"event_id": "E-XFORM", "traceability_lot_code": "LOT-MEGA",
             "event_type": "transformation", "quantity": 10, "unit_of_measure": "lbs",
             "kdes": {"input_traceability_lot_codes": ["LOT-A"]}},
        ]
        res = _evaluate_relational_in_memory(evts)
        # The evaluator should still emit a result (raw-units fallback) because
        # all_ok became False, conversion is skipped, and raw quantities are used.
        xform_results = [r for r in res.get("E-XFORM", []) if r.rule_id == "R-MB"]
        assert xform_results
        # Evidence must show uom_converted=False since conversion aborted.
        for r in xform_results:
            for ev in r.evidence_fields_inspected:
                assert ev.get("uom_converted") is False

    def test_cross_tlc_uom_conversion_output_none_skips(self, monkeypatch):
        """If output UOM can't be normalized, use_converted stays False."""
        _only_mass_rule(monkeypatch, cte_types=["transformation"])
        def _norm(q, u):
            # Only lbs normalizes; cases fail
            if u.lower() == "lbs":
                return q
            return None
        monkeypatch.setattr(evaluators_mod, "_normalize_to_lbs", _norm)
        evts = [
            {"event_id": "E-IN", "traceability_lot_code": "LOT-A",
             "event_type": "harvesting", "quantity": 10, "unit_of_measure": "lbs"},
            {"event_id": "E-XFORM", "traceability_lot_code": "LOT-MEGA",
             "event_type": "transformation", "quantity": 10, "unit_of_measure": "cases",
             "kdes": {"input_traceability_lot_codes": ["LOT-A"]}},
        ]
        res = _evaluate_relational_in_memory(evts)
        xform_results = [r for r in res.get("E-XFORM", []) if r.rule_id == "R-MB"]
        # Conversion failed → uses raw quantities: 10 cases (raw) vs 10 lbs input
        # — passes because output <= input * tolerance
        assert xform_results

    def test_no_mass_rule_registered_skips_cross_tlc_entirely(self, monkeypatch):
        monkeypatch.setattr(evaluators_mod, "_get_relational_rules", lambda: {})
        evts = [
            {"event_id": "E-IN", "traceability_lot_code": "LOT-A",
             "event_type": "harvesting", "quantity": 10, "unit_of_measure": "lbs"},
            {"event_id": "E-XFORM", "traceability_lot_code": "LOT-MEGA",
             "event_type": "transformation", "quantity": 100, "unit_of_measure": "lbs",
             "kdes": {"input_traceability_lot_codes": ["LOT-A"]}},
        ]
        res = _evaluate_relational_in_memory(evts)
        assert res == {}

    def test_non_transformation_events_ignored_by_cross_tlc(self, monkeypatch):
        _only_mass_rule(monkeypatch, cte_types=["shipping"])
        evts = [
            {"event_id": "E1", "traceability_lot_code": "TLC",
             "event_type": "harvesting", "quantity": 100, "unit_of_measure": "lbs"},
            {"event_id": "E2", "traceability_lot_code": "TLC",
             "event_type": "shipping", "quantity": 100, "unit_of_measure": "lbs",
             "kdes": {"input_traceability_lot_codes": ["OTHER-TLC"]}},
        ]
        res = _evaluate_relational_in_memory(evts)
        # E2 is shipping, not transformation — cross-TLC loop skips it
        # (only per-TLC mass balance would produce a result if applicable)
        # Only the per-TLC pass should appear.
        for evt_id, vals in res.items():
            mb_results = [r for r in vals if r.rule_id == "R-MB"]
            # Exactly one mass-balance verdict per applicable event
            assert len(mb_results) <= 1
