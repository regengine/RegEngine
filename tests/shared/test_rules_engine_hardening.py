"""
Regression tests for rules-engine correctness hardening.

Each test targets a specific regulatory-correctness bug that could
falsely stamp a non-compliant record as FSMA 204 compliant.

Issues covered:
    #1203 — /validate endpoint is orphaned (covered by its removal — see
            services/compliance/app/routes.py and the frontend hook).
    #1344 — relational evaluators trusted event-payload tenant_id.
    #1346 — non-FTL foods received a compliance stamp.
    #1347 — empty rule set silently reported compliant=True.
    #1354 — evaluator errors were counted as 'skipped', not 'failed'.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from shared.rules.types import (
    EvaluationSummary,
    RuleDefinition,
    RuleEvaluationResult,
)
from shared.rules.engine import RulesEngine
from shared.rules.evaluators.relational import evaluate_identity_consistency
from shared.rules.ftl import is_ftl_food, get_ftl_category


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_rule(**overrides) -> RuleDefinition:
    defaults = dict(
        rule_id="rule-under-test",
        rule_version=1,
        title="Test Rule",
        description="A rule for the hardening tests",
        severity="critical",
        category="kde_presence",
        applicability_conditions={"cte_types": ["receiving"], "ftl_scope": ["ALL"]},
        citation_reference="21 CFR §1.1310",
        effective_date=date(2026, 1, 1),
        retired_date=None,
        evaluation_logic={"type": "field_presence", "field": "kdes.tlc_source_reference"},
        failure_reason_template="Missing {field_name} per {citation}",
        remediation_suggestion="Supply the field",
    )
    defaults.update(overrides)
    return RuleDefinition(**defaults)


def _make_event(**overrides) -> Dict[str, Any]:
    """FTL-covered receiving event with the required field present."""
    defaults = {
        "event_id": "evt-1",
        "event_type": "receiving",
        "traceability_lot_code": "TLC-1",
        "product_reference": "Romaine Lettuce",
        "quantity": 100.0,
        "unit_of_measure": "cases",
        # FTL hint — signals this product IS on the FTL.
        "ftl_covered": True,
        "ftl_category": "Leafy Greens",
        "kdes": {
            "tlc_source_reference": "0061414100003",
        },
    }
    defaults.update(overrides)
    return defaults


def _engine_with_rules(rules: List[RuleDefinition], session=None) -> RulesEngine:
    engine = RulesEngine.__new__(RulesEngine)
    engine.session = session
    engine._rules_cache = rules
    return engine


# ===========================================================================
# #1347 — empty rule set must NOT report compliant=True
# ===========================================================================


class TestIssue1347EmptyRuleSet:
    def test_empty_rule_set_no_verdict(self):
        """An empty ruleset must return compliant=None, not True."""
        engine = _engine_with_rules([])
        event = _make_event()
        summary = engine.evaluate_event(event, persist=False, tenant_id="t1")
        assert summary.total_rules == 0
        assert summary.compliant is None
        assert summary.no_verdict_reason == "no_rules_loaded"

    def test_summary_compliant_tri_state(self):
        """EvaluationSummary.compliant is Optional[bool], not bool."""
        empty = EvaluationSummary(event_id="e1")
        assert empty.compliant is None

        ran = EvaluationSummary(event_id="e1", total_rules=3, passed=3)
        assert ran.compliant is True

        failed = EvaluationSummary(event_id="e1", total_rules=3, passed=2, failed=1)
        assert failed.compliant is False

    def test_all_rules_retired_is_no_verdict(self):
        """A tenant whose rules were all retired gets no verdict."""
        # Simulated by an engine that loads an empty rule set.
        engine = _engine_with_rules([])
        event = _make_event()
        summary = engine.evaluate_event(event, persist=False, tenant_id="t1")
        assert summary.compliant is None

    def test_no_verdict_reason_explicit(self):
        """The no_verdict_reason field must be set to a debuggable string."""
        engine = _engine_with_rules([])
        event = _make_event()
        summary = engine.evaluate_event(event, persist=False, tenant_id="t1")
        assert summary.no_verdict_reason in {
            "no_rules_loaded",
            "not_ftl_scoped",
            "ftl_classification_missing",
        }


# ===========================================================================
# #1354 — evaluator errors must count as FAILED, not skipped
# ===========================================================================


class TestIssue1354EvaluatorErrors:
    def test_evaluator_exception_counted_as_errored(self):
        """When an evaluator raises, the summary must mark compliant=False."""
        engine = _engine_with_rules([_make_rule()])
        # Pass a non-dict event to force an exception inside the evaluator
        # (get_nested_value will bail gracefully, so we need a stronger
        # failure — patch the evaluator to crash).
        import shared.rules.engine as engine_module

        broken_rule = _make_rule(
            evaluation_logic={"type": "field_presence", "field": "kdes.tlc_source_reference"},
        )
        engine._rules_cache = [broken_rule]

        def _boom(*a, **kw):
            raise RuntimeError("synthetic evaluator crash")

        engine_module.EVALUATORS["field_presence_broken"] = _boom
        broken_rule.evaluation_logic["type"] = "field_presence_broken"

        try:
            summary = engine.evaluate_event(_make_event(), persist=False, tenant_id="t1")
        finally:
            del engine_module.EVALUATORS["field_presence_broken"]

        assert summary.errored == 1
        assert summary.passed == 0
        assert summary.failed == 0
        # The crash must produce a non-compliant verdict.
        assert summary.compliant is False
        assert summary.results[0].result == "error"

    def test_unknown_eval_type_counted_as_errored(self):
        """An unknown eval_type (e.g. JSON typo) must fail, not silently skip."""
        rule = _make_rule(evaluation_logic={"type": "nonexistent_eval_v999"})
        engine = _engine_with_rules([rule])
        summary = engine.evaluate_event(_make_event(), persist=False, tenant_id="t1")

        assert summary.errored == 1
        assert summary.compliant is False
        assert "Unknown evaluation type" in (summary.results[0].why_failed or "")

    def test_errored_counts_toward_critical_failures(self):
        """Critical-severity evaluator errors surface as critical_failures."""
        rule = _make_rule(
            severity="critical",
            evaluation_logic={"type": "nonexistent_eval_v999"},
        )
        engine = _engine_with_rules([rule])
        summary = engine.evaluate_event(_make_event(), persist=False, tenant_id="t1")
        assert len(summary.critical_failures) == 1
        assert summary.critical_failures[0].result == "error"


# ===========================================================================
# #1346 — non-FTL foods MUST NOT receive a compliance stamp
# ===========================================================================


class TestIssue1346FTLScoping:
    def test_non_ftl_food_no_verdict(self):
        """A product explicitly not on the FTL must not get compliant=True."""
        rules = [_make_rule()]
        engine = _engine_with_rules(rules)
        event = _make_event(ftl_covered=False)
        event.pop("ftl_category", None)

        summary = engine.evaluate_event(event, persist=False, tenant_id="t1")
        assert summary.compliant is None
        assert summary.no_verdict_reason == "not_ftl_scoped"

    def test_non_ftl_category_skipped(self):
        """An event with a non-FTL category string is not FTL."""
        rules = [_make_rule()]
        engine = _engine_with_rules(rules)
        event = _make_event()
        event.pop("ftl_covered", None)
        event["ftl_category"] = "Canned Goods"  # not on the FTL

        summary = engine.evaluate_event(event, persist=False, tenant_id="t1")
        assert summary.compliant is None
        assert summary.no_verdict_reason == "not_ftl_scoped"

    def test_missing_ftl_classification_no_verdict(self):
        """An event with no FTL hint must not be stamped compliant."""
        rules = [_make_rule()]
        engine = _engine_with_rules(rules)
        event = _make_event()
        for k in ("ftl_covered", "ftl_category"):
            event.pop(k, None)

        summary = engine.evaluate_event(event, persist=False, tenant_id="t1")
        # The FTL meta-rule is not in this tiny rule set, so nothing applies
        # and the engine reports ftl_classification_missing explicitly.
        assert summary.compliant is None
        assert summary.no_verdict_reason == "ftl_classification_missing"

    def test_ftl_food_still_evaluates_normally(self):
        """Regression — FTL foods continue to receive normal compliance verdicts."""
        rules = [_make_rule()]
        engine = _engine_with_rules(rules)
        event = _make_event()  # ftl_covered=True, ftl_category=Leafy Greens

        summary = engine.evaluate_event(event, persist=False, tenant_id="t1")
        assert summary.compliant is True
        assert summary.total_rules == 1

    def test_ftl_scope_filters_by_category(self):
        """A rule scoped to ["Leafy Greens"] must not apply to "Soft Cheeses"."""
        leafy_rule = _make_rule(
            title="Leafy-only",
            applicability_conditions={
                "cte_types": ["receiving"],
                "ftl_scope": ["Leafy Greens"],
            },
        )
        cheese_rule = _make_rule(
            title="Cheese-only",
            applicability_conditions={
                "cte_types": ["receiving"],
                "ftl_scope": ["Soft Cheeses"],
            },
        )
        engine = _engine_with_rules([leafy_rule, cheese_rule])
        event = _make_event(ftl_category="Leafy Greens")

        applicable = engine.get_applicable_rules(
            "receiving",
            event_ftl_category=get_ftl_category(event),
            event_is_ftl=is_ftl_food(event),
        )
        titles = {r.title for r in applicable}
        assert "Leafy-only" in titles
        assert "Cheese-only" not in titles

    def test_ftl_helpers(self):
        """The ftl helpers correctly classify events."""
        assert is_ftl_food({"ftl_covered": True}) is True
        assert is_ftl_food({"ftl_covered": False}) is False
        assert is_ftl_food({"ftl_category": "Leafy Greens"}) is True
        assert is_ftl_food({"ftl_category": "Canned Goods"}) is False
        assert is_ftl_food({}) is None
        assert get_ftl_category({"ftl_category": "leafy greens"}) == "leafy greens"
        assert get_ftl_category({"ftl_category": "Canned Goods"}) is None


# ===========================================================================
# #1344 — relational evaluators must trust ONLY authenticated tenant_id
# ===========================================================================


class TestIssue1344TenantIsolation:
    def _make_session_capturing_tenant(self) -> MagicMock:
        """A mock session that records the tenant_id from executed queries."""
        captured: Dict[str, Any] = {}

        def _execute(query, params=None):
            if params and "tenant_id" in params:
                captured["tenant_id"] = params["tenant_id"]
            result = MagicMock()
            result.fetchall.return_value = []
            result.fetchone.return_value = None
            return result

        session = MagicMock()
        session.execute.side_effect = _execute
        session._captured = captured  # type: ignore[attr-defined]
        return session

    def test_relational_evaluator_ignores_payload_tenant_id(self):
        """A forged event.tenant_id must NOT be used for DB lookup."""
        session = self._make_session_capturing_tenant()
        rule = _make_rule(
            evaluation_logic={"type": "identity_consistency"},
            category="lot_linkage",
        )
        event_data = _make_event()
        event_data["tenant_id"] = "ATTACKER-TENANT"  # forged!

        result = evaluate_identity_consistency(
            event_data, rule.evaluation_logic, rule, session,
            tenant_id="VICTIM-TENANT",  # authenticated kwarg
        )

        # The DB lookup must have used the kwarg tenant, not the payload.
        assert session._captured.get("tenant_id") == "VICTIM-TENANT"
        # And the evaluator must not have crashed.
        assert result.result in {"pass", "fail", "skip"}

    def test_kwarg_wins_when_payload_mismatches(self):
        """The kwarg tenant_id always wins over a divergent payload value."""
        session = self._make_session_capturing_tenant()
        rule = _make_rule(evaluation_logic={"type": "identity_consistency"})
        event_data = _make_event()
        event_data["tenant_id"] = "TENANT-ATTACKER"

        evaluate_identity_consistency(
            event_data, rule.evaluation_logic, rule, session,
            tenant_id="TENANT-REAL",
        )
        assert session._captured["tenant_id"] == "TENANT-REAL"

    def test_engine_rejects_relational_rule_without_tenant(self):
        """A relational rule with no tenant kwarg must ERROR, not skip."""
        session = self._make_session_capturing_tenant()
        rule = _make_rule(evaluation_logic={"type": "identity_consistency"})
        engine = _engine_with_rules([rule], session=session)
        event = _make_event()

        # No tenant_id passed — relational rule must not run against
        # an implicit payload tenant.
        summary = engine.evaluate_event(event, persist=False, tenant_id=None)
        # Exactly one rule, it errored.
        assert summary.errored == 1
        assert summary.compliant is False
        # DB was NOT touched (no cross-tenant leak).
        assert "tenant_id" not in session._captured

    def test_batch_requires_tenant_id(self):
        """evaluate_events_batch must refuse to run without a tenant context."""
        engine = _engine_with_rules([_make_rule()])
        with pytest.raises(ValueError, match="tenant_id"):
            engine.evaluate_events_batch([_make_event()], tenant_id="", persist=False)


# ===========================================================================
# #1203 — orphaned /validate endpoint is removed
# ===========================================================================


class TestIssue1203ValidateEndpointRemoval:
    def test_validate_route_removed_from_compliance_service(self):
        """The orphaned /validate route must no longer be registered."""
        from services.compliance.main import app as compliance_app

        routes = {getattr(r, "path", None) for r in compliance_app.routes}
        assert "/validate" not in routes, (
            "Orphaned /validate endpoint resurfaced — see #1203. "
            "If you are wiring it into ingestion, do that first."
        )

    def test_validate_not_in_compliance_root_listing(self):
        """The root JSON must not advertise /validate as a key endpoint."""
        from fastapi.testclient import TestClient
        from services.compliance.main import app as compliance_app

        with TestClient(compliance_app) as client:
            resp = client.get("/")
        assert resp.status_code == 200
        key_endpoints = resp.json().get("key_endpoints", {})
        assert "validate" not in key_endpoints
