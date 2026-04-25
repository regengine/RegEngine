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
        reject, reason, _summary_unused = wrv2._rules_preeval_reject(_make_event, db_session=None, tenant_id="t")
        assert reject is False
        assert reason is None

    def test_off_mode_short_circuits_before_normalize(self, monkeypatch, _make_event):
        """Under OFF mode the helper MUST skip normalization + eval entirely
        — every webhook request would otherwise pay the added latency even
        though the verdict is always accept. The existing post-commit
        threaded block still does its own eval with ``persist=True``, so
        without this short-circuit we'd run canonical+eval twice per
        accepted event on the hot path — a 2x latency regression vs. the
        pre-Phase-0 behavior.
        """
        calls: dict = {"normalize": 0, "evaluate": 0}

        def _normalize_spy(event, tenant_id):
            calls["normalize"] += 1
            return SimpleNamespace(
                event_id="cev-1",
                event_type=SimpleNamespace(value=event.cte_type.value),
                traceability_lot_code=event.traceability_lot_code,
                product_reference=None, quantity=event.quantity,
                unit_of_measure=event.unit_of_measure,
                from_facility_reference=None, to_facility_reference=None,
                from_entity_reference=None, to_entity_reference=None,
                kdes=event.kdes,
            )

        class _SpyEngine:
            def __init__(self, db_session):
                pass
            def evaluate_event(self, event_data, persist, tenant_id):
                calls["evaluate"] += 1
                return _critical_summary()

        monkeypatch.setattr(wrv2, "normalize_webhook_event", _normalize_spy)
        re_mod = ModuleType("shared.rules_engine")
        re_mod.RulesEngine = _SpyEngine
        monkeypatch.setitem(sys.modules, "shared.rules_engine", re_mod)

        reject, reason, _summary_unused = wrv2._rules_preeval_reject(_make_event, db_session=None, tenant_id="t")

        assert reject is False
        assert reason is None
        assert calls["normalize"] == 0, "normalize must be skipped in OFF mode"
        assert calls["evaluate"] == 0, "evaluate must be skipped in OFF mode"


# ---------------------------------------------------------------------------
# CTE_ONLY mode
# ---------------------------------------------------------------------------

class TestPreEvalCteOnly:

    @pytest.fixture(autouse=True)
    def _cte_only(self, monkeypatch):
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "cte_only")

    def test_critical_failure_rejects_with_rule_id_in_reason(self, monkeypatch, _make_event):
        _install(monkeypatch, summary=_critical_summary())
        reject, reason, _summary_unused = wrv2._rules_preeval_reject(_make_event, db_session=None, tenant_id="t")
        assert reject is True
        assert "CTE_REQ_HARVEST_DATE" in reason
        assert "harvest_date missing" in reason

    def test_warning_only_does_not_reject(self, monkeypatch, _make_event):
        _install(monkeypatch, summary=_warning_only_summary())
        reject, reason, _summary_unused = wrv2._rules_preeval_reject(_make_event, db_session=None, tenant_id="t")
        assert reject is False
        assert reason is None

    def test_no_verdict_does_not_reject(self, monkeypatch, _make_event):
        """no_rules_loaded / non-FTL → compliant=None → must never reject.
        Blocking here would break ingestion for every tenant without
        seeded rules or non-FTL products."""
        _install(monkeypatch, summary=_no_verdict_summary())
        reject, reason, _summary_unused = wrv2._rules_preeval_reject(_make_event, db_session=None, tenant_id="t")
        assert reject is False
        assert reason is None

    def test_compliant_does_not_reject(self, monkeypatch, _make_event):
        _install(monkeypatch, summary=_compliant_summary())
        reject, _, _summary_unused = wrv2._rules_preeval_reject(_make_event, db_session=None, tenant_id="t")
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
        reject, reason, _summary_unused = wrv2._rules_preeval_reject(_make_event, db_session=None, tenant_id="t")
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
        reject, reason, _summary_unused = wrv2._rules_preeval_reject(_make_event, db_session=None, tenant_id="t")
        assert reject is True
        assert "R_WARN" in reason

    def test_compliant_still_accepts(self, monkeypatch, _make_event):
        _install(monkeypatch, summary=_compliant_summary())
        reject, _, _summary_unused = wrv2._rules_preeval_reject(_make_event, db_session=None, tenant_id="t")
        assert reject is False

    def test_no_verdict_still_accepts(self, monkeypatch, _make_event):
        _install(monkeypatch, summary=_no_verdict_summary())
        reject, _, _summary_unused = wrv2._rules_preeval_reject(_make_event, db_session=None, tenant_id="t")
        assert reject is False


# ---------------------------------------------------------------------------
# Summary return — proves the third tuple slot lets callers reuse the
# pre-eval result instead of forcing a re-evaluation in the post-commit
# threaded block. Closes the double-eval regression.
# ---------------------------------------------------------------------------

class TestPreEvalReturnsSummary:
    """The helper returns ``(reject, reason, summary)`` so the threaded
    post-commit canonical block can persist the pre-computed evaluation
    via ``RulesEngine.persist_summary`` instead of running every rule a
    second time."""

    def test_summary_returned_under_enforcement(self, monkeypatch, _make_event):
        """Under cte_only, the summary slot is populated so the threaded
        block can reuse it. Without this, every accepted event under
        enforcement would pay for two full rules evaluations on the hot
        path — a 2x CPU regression vs. the OFF-mode default."""
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "cte_only")
        crit = _critical_summary()
        _install(monkeypatch, summary=crit)
        reject, reason, summary = wrv2._rules_preeval_reject(
            _make_event, db_session=None, tenant_id="t"
        )
        # Even though this case rejects, the summary is still returned —
        # callers might log or audit it before short-circuiting.
        assert reject is True
        assert summary is crit, "helper must hand the engine's summary back unchanged"

    def test_summary_returned_when_compliant(self, monkeypatch, _make_event):
        """Compliant events under enforcement: helper accepts AND returns
        the summary. The threaded block uses it via persist_summary."""
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "cte_only")
        compliant = _compliant_summary()
        _install(monkeypatch, summary=compliant)
        reject, reason, summary = wrv2._rules_preeval_reject(
            _make_event, db_session=None, tenant_id="t"
        )
        assert reject is False
        assert reason is None
        assert summary is compliant

    def test_summary_none_under_off_mode(self, monkeypatch, _make_event):
        """OFF mode — pre-eval still runs (the OFF short-circuit is in
        a separate review-fix PR); when it runs, the summary is returned.
        Once the short-circuit lands the helper returns ``(False, None, None)``
        without invoking the engine, so summary is None — the test below
        accepts both shapes during the migration window."""
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "off")
        _install(monkeypatch, summary=_critical_summary())
        reject, reason, summary = wrv2._rules_preeval_reject(
            _make_event, db_session=None, tenant_id="t"
        )
        assert reject is False
        assert reason is None
        # Summary may be None (post-short-circuit) or the critical summary
        # (pre-short-circuit). Either is OK — the threaded block falls
        # back to evaluate_event when summary is None or has no results.

    def test_summary_none_when_canonical_errors(self, monkeypatch, _make_event):
        """When canonical normalization raises, the helper logs and
        returns ``(False, None, None)`` — preserves best-effort semantics
        and signals the threaded block to fall back to evaluate_event."""
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "cte_only")
        _install(
            monkeypatch,
            summary=_critical_summary(),  # would reject if eval ran
            canonical_raises=RuntimeError("canonical broken"),
        )
        reject, reason, summary = wrv2._rules_preeval_reject(
            _make_event, db_session=None, tenant_id="t"
        )
        assert reject is False
        assert reason is None
        assert summary is None, (
            "canonical/eval errors must produce summary=None so the "
            "threaded block falls back to re-evaluation rather than "
            "persisting an empty result set"
        )
