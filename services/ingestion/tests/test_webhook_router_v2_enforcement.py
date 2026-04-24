"""Unit tests for the ``_rules_preeval_reject`` helper and its wiring into
``webhook_router_v2`` (Phase 0 #1c).

The full ``ingest_events`` route in this module has a large FastAPI-DI
surface (principal, auth, db_session, request-lifecycle hooks) that the
co-located ``test_webhook_router_v2_1342.py`` file mocks at scale but has
~22 pre-existing solo-failing tests unrelated to this change (excluded
from the xdist signal job in #1902). These tests focus on the narrowly
testable unit — the helper — and document the expected end-to-end
behavior via small docstrings on each case.

Coverage:
  - Helper returns (False, None) when ``RULES_ENGINE_ENFORCE`` is off
  - Helper returns (True, reason) in cte_only mode when critical_failures
    is non-empty
  - Helper returns (False, None) in cte_only mode for warning-only fails
  - Helper returns (False, None) for no-verdict summaries
  - Helper swallows canonical/eval errors and returns (False, None)
    (preserves best-effort semantics for tenants without seeded rules)
  - Helper returns (True, reason) in ``all`` mode on warning-only fails
"""
from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest

from services.ingestion.app import webhook_router_v2 as wrv2
from services.shared.rules.types import EvaluationSummary, RuleEvaluationResult


# ---------------------------------------------------------------------------
# Summary factories
# ---------------------------------------------------------------------------

def _critical_summary() -> EvaluationSummary:
    crit = RuleEvaluationResult(
        rule_id="CTE_REQ_HARVEST_DATE", severity="critical",
        result="fail", why_failed="harvest_date missing",
    )
    return EvaluationSummary(
        total_rules=1, failed=1, results=[crit], critical_failures=[crit],
    )


def _warning_only_summary() -> EvaluationSummary:
    warn = RuleEvaluationResult(
        rule_id="R_WARN", severity="warning",
        result="fail", why_failed="non-critical warning",
    )
    return EvaluationSummary(
        total_rules=1, failed=1, results=[warn], critical_failures=[],
    )


def _no_verdict_summary() -> EvaluationSummary:
    return EvaluationSummary(total_rules=0, no_verdict_reason="no_rules_loaded")


def _compliant_summary() -> EvaluationSummary:
    return EvaluationSummary(
        total_rules=1, passed=1,
        results=[RuleEvaluationResult(rule_id="R_OK", severity="info", result="pass")],
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def _make_event():
    return SimpleNamespace(
        cte_type=SimpleNamespace(value="harvesting"),
        traceability_lot_code="TLC-1",
        product_description="Tomatoes",
        quantity=1.0,
        unit_of_measure="kg",
        timestamp="2026-01-01T00:00:00Z",
        location_gln=None,
        location_name="Farm",
        kdes={},
    )


def _install(monkeypatch, *, summary: EvaluationSummary, canonical_raises=None):
    """Stub normalize_webhook_event + RulesEngine to return the given summary."""
    def _normalize(event, tenant_id):
        if canonical_raises is not None:
            raise canonical_raises
        return SimpleNamespace(
            event_id="cev-1",
            event_type=SimpleNamespace(value=event.cte_type.value),
            traceability_lot_code=event.traceability_lot_code,
            product_reference=None,
            quantity=event.quantity,
            unit_of_measure=event.unit_of_measure,
            from_facility_reference=None,
            to_facility_reference=None,
            from_entity_reference=None,
            to_entity_reference=None,
            kdes=event.kdes,
        )
    monkeypatch.setattr(wrv2, "normalize_webhook_event", _normalize)

    class _FakeEngine:
        def __init__(self, db_session):
            pass
        def evaluate_event(self, event_data, persist, tenant_id):
            # Pre-eval path MUST pass persist=False
            assert persist is False, "preeval should not persist eval rows"
            return summary

    re_mod = ModuleType("shared.rules_engine")
    re_mod.RulesEngine = _FakeEngine
    monkeypatch.setitem(sys.modules, "shared.rules_engine", re_mod)


@pytest.fixture(autouse=True)
def _silence_logger(monkeypatch):
    class _Silent:
        def info(self, *a, **k): pass
        def warning(self, *a, **k): pass
        def error(self, *a, **k): pass
        def debug(self, *a, **k): pass
    monkeypatch.setattr(wrv2, "logger", _Silent())


# ---------------------------------------------------------------------------
# OFF mode
# ---------------------------------------------------------------------------

class TestPreEvalOff:

    @pytest.fixture(autouse=True)
    def _off(self, monkeypatch):
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "off")

    def test_critical_failure_does_not_reject(self, monkeypatch, _make_event):
        _install(monkeypatch, summary=_critical_summary())
        reject, reason = wrv2._rules_preeval_reject(_make_event, db_session=None, tenant_id="t")
        assert reject is False
        assert reason is None


# ---------------------------------------------------------------------------
# CTE_ONLY mode
# ---------------------------------------------------------------------------

class TestPreEvalCteOnly:

    @pytest.fixture(autouse=True)
    def _cte_only(self, monkeypatch):
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "cte_only")

    def test_critical_failure_rejects_with_rule_id_in_reason(self, monkeypatch, _make_event):
        _install(monkeypatch, summary=_critical_summary())
        reject, reason = wrv2._rules_preeval_reject(_make_event, db_session=None, tenant_id="t")
        assert reject is True
        assert "CTE_REQ_HARVEST_DATE" in reason
        assert "harvest_date missing" in reason

    def test_warning_only_does_not_reject(self, monkeypatch, _make_event):
        _install(monkeypatch, summary=_warning_only_summary())
        reject, reason = wrv2._rules_preeval_reject(_make_event, db_session=None, tenant_id="t")
        assert reject is False
        assert reason is None

    def test_no_verdict_does_not_reject(self, monkeypatch, _make_event):
        """no_rules_loaded / non-FTL → compliant=None → must never reject.
        Blocking here would break ingestion for every tenant without
        seeded rules or non-FTL products."""
        _install(monkeypatch, summary=_no_verdict_summary())
        reject, reason = wrv2._rules_preeval_reject(_make_event, db_session=None, tenant_id="t")
        assert reject is False
        assert reason is None

    def test_compliant_does_not_reject(self, monkeypatch, _make_event):
        _install(monkeypatch, summary=_compliant_summary())
        reject, _ = wrv2._rules_preeval_reject(_make_event, db_session=None, tenant_id="t")
        assert reject is False

    def test_canonical_error_does_not_reject(self, monkeypatch, _make_event):
        """A canonical-normalization crash must never reject the event.
        Treating it as no-verdict preserves the pre-refactor best-effort
        behavior for every tenant when the canonical module has a
        transient bug."""
        _install(
            monkeypatch,
            summary=_critical_summary(),  # would reject if eval ran
            canonical_raises=RuntimeError("canonical broken"),
        )
        reject, reason = wrv2._rules_preeval_reject(_make_event, db_session=None, tenant_id="t")
        assert reject is False
        assert reason is None


# ---------------------------------------------------------------------------
# ALL mode
# ---------------------------------------------------------------------------

class TestPreEvalAll:

    @pytest.fixture(autouse=True)
    def _all(self, monkeypatch):
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "all")

    def test_warning_only_rejects_under_all(self, monkeypatch, _make_event):
        """ALL mode is stricter than CTE_ONLY: warning-severity fails
        ALSO reject."""
        _install(monkeypatch, summary=_warning_only_summary())
        reject, reason = wrv2._rules_preeval_reject(_make_event, db_session=None, tenant_id="t")
        assert reject is True
        assert "R_WARN" in reason

    def test_compliant_still_accepts(self, monkeypatch, _make_event):
        _install(monkeypatch, summary=_compliant_summary())
        reject, _ = wrv2._rules_preeval_reject(_make_event, db_session=None, tenant_id="t")
        assert reject is False

    def test_no_verdict_still_accepts(self, monkeypatch, _make_event):
        _install(monkeypatch, summary=_no_verdict_summary())
        reject, _ = wrv2._rules_preeval_reject(_make_event, db_session=None, tenant_id="t")
        assert reject is False
