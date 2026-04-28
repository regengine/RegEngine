"""Unit tests for ``_persist_canonical_and_eval`` (PR 4 of double-eval fix).

Closes the closure-level integration gap flagged in PR #1926. The
threaded ``_do_canonical_write`` closure inside ``ingest_events`` cannot
be called in isolation, but its body now lives in the module-level
``_persist_canonical_and_eval`` helper that takes the same inputs as
explicit parameters. These tests pin the routing contract:

  - pre-computed summary present + has results → ``persist_summary``
  - pre-computed summary None / empty results → ``evaluate_event(persist=True)``
  - non-compliant verdict (in either branch) → exception-queue creation
  - compliant verdict → no exception-queue creation
  - canonical persist runs in both branches

The fakes track call counts on class vars so the assertions are
deterministic — no FastAPI DI surface, no TestClient, no threading.
"""
from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from services.ingestion.app import webhook_router_v2 as wrv2
from services.shared.rules.types import EvaluationSummary, RuleEvaluationResult


# ---------------------------------------------------------------------------
# Fakes — class vars track calls so assertions don't need MagicMock spec.
# ---------------------------------------------------------------------------

class _FakeCanonicalEventStore:
    persist_call_count: int = 0
    persist_args: list = []

    def __init__(self, db_session: Any, dual_write: bool = False, skip_chain_write: bool = False) -> None:
        self.db_session = db_session

    def persist_event(self, canonical: Any) -> None:
        _FakeCanonicalEventStore.persist_call_count += 1
        _FakeCanonicalEventStore.persist_args.append(canonical)


class _FakeEngine:
    """Records every call to evaluate_event and persist_summary so tests
    can assert exact routing under each mode/summary combination."""
    summary_to_return: Any = None
    evaluate_event_persist_true_calls: list = []
    evaluate_event_persist_false_calls: list = []
    persist_summary_calls: list = []

    def __init__(self, db_session: Any) -> None:
        self.db_session = db_session

    def evaluate_event(self, event_data: dict, persist: bool, tenant_id: str) -> Any:
        bucket = (
            _FakeEngine.evaluate_event_persist_true_calls
            if persist
            else _FakeEngine.evaluate_event_persist_false_calls
        )
        bucket.append({"event_data": event_data, "tenant_id": tenant_id})
        return _FakeEngine.summary_to_return

    def persist_summary(self, summary: Any, *, tenant_id: str, event_id=None) -> None:
        _FakeEngine.persist_summary_calls.append({
            "summary": summary,
            "tenant_id": tenant_id,
            "event_id": event_id,
        })


class _FakeExceptionQueueService:
    create_calls: list = []

    def __init__(self, db_session: Any) -> None:
        self.db_session = db_session

    def create_exceptions_from_evaluation(self, tenant_id: str, summary: Any) -> None:
        _FakeExceptionQueueService.create_calls.append({
            "tenant_id": tenant_id,
            "summary": summary,
        })


def _fake_normalize_webhook_event(event: Any, tenant_id: str, **_: Any) -> Any:
    """Stub that returns a fresh canonical with a per-call unique event_id.

    The real ``normalize_webhook_event`` mints a UUID per call. Our tests
    don't need true UUIDs, but they DO need the event_id to be non-empty
    so the ``persist_summary`` event_id assertion is meaningful.
    """
    return SimpleNamespace(
        event_id="canonical-uuid-fresh",
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _install(monkeypatch: pytest.MonkeyPatch) -> None:
    # Reset class-var trackers between tests.
    _FakeCanonicalEventStore.persist_call_count = 0
    _FakeCanonicalEventStore.persist_args = []
    _FakeEngine.summary_to_return = None
    _FakeEngine.evaluate_event_persist_true_calls = []
    _FakeEngine.evaluate_event_persist_false_calls = []
    _FakeEngine.persist_summary_calls = []
    _FakeExceptionQueueService.create_calls = []

    # Stub at the module level so the helper's lazy ``from shared.X import Y``
    # imports pick up the fakes.
    cps_mod = ModuleType("shared.canonical_persistence")
    cps_mod.CanonicalEventStore = _FakeCanonicalEventStore
    monkeypatch.setitem(sys.modules, "shared.canonical_persistence", cps_mod)

    re_mod = ModuleType("shared.rules_engine")
    re_mod.RulesEngine = _FakeEngine
    monkeypatch.setitem(sys.modules, "shared.rules_engine", re_mod)

    eq_mod = ModuleType("shared.exception_queue")
    eq_mod.ExceptionQueueService = _FakeExceptionQueueService
    monkeypatch.setitem(sys.modules, "shared.exception_queue", eq_mod)

    monkeypatch.setattr(wrv2, "normalize_webhook_event", _fake_normalize_webhook_event)


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


def _critical_summary() -> EvaluationSummary:
    crit = RuleEvaluationResult(
        rule_id="CTE_REQ_HARVEST_DATE", severity="critical",
        result="fail", why_failed="harvest_date missing",
    )
    return EvaluationSummary(
        total_rules=1, failed=1, results=[crit], critical_failures=[crit],
        event_id="from-pre-eval",
    )


def _warning_only_summary() -> EvaluationSummary:
    warn = RuleEvaluationResult(
        rule_id="R_WARN", severity="warning",
        result="fail", why_failed="non-critical",
    )
    return EvaluationSummary(
        total_rules=1, failed=1, results=[warn], critical_failures=[],
        event_id="from-pre-eval",
    )


def _no_verdict_summary() -> EvaluationSummary:
    return EvaluationSummary(
        total_rules=0, no_verdict_reason="no_rules_loaded",
        event_id="from-pre-eval",
    )


def _compliant_summary() -> EvaluationSummary:
    return EvaluationSummary(
        total_rules=1, passed=1,
        results=[RuleEvaluationResult(rule_id="R_OK", severity="info", result="pass")],
        event_id="from-pre-eval",
    )


# ---------------------------------------------------------------------------
# Fast path: pre-computed summary present → persist_summary, no re-eval
# ---------------------------------------------------------------------------

class TestFastPathUsingPreComputedSummary:

    def test_compliant_summary_uses_persist_summary(self, _make_event):
        precomputed = _compliant_summary()
        wrv2._persist_canonical_and_eval(
            db_session=MagicMock(), event=_make_event, tenant_id="t-1",
            precomputed_summary=precomputed,
        )
        # Canonical persisted exactly once.
        assert _FakeCanonicalEventStore.persist_call_count == 1
        # persist_summary called once with the pre-computed summary.
        assert len(_FakeEngine.persist_summary_calls) == 1
        call = _FakeEngine.persist_summary_calls[0]
        assert call["summary"] is precomputed
        assert call["tenant_id"] == "t-1"
        # event_id MUST be the freshly-persisted canonical's event_id,
        # NOT the pre-eval canonical's event_id (``from-pre-eval``).
        assert call["event_id"] == "canonical-uuid-fresh"
        # No re-evaluation.
        assert _FakeEngine.evaluate_event_persist_true_calls == []
        assert _FakeEngine.evaluate_event_persist_false_calls == []
        # Compliant → no exception-queue write.
        assert _FakeExceptionQueueService.create_calls == []

    def test_warning_only_summary_uses_persist_summary_and_creates_exceptions(self, _make_event):
        """Warning-only failure → persist_summary fast path AND
        exception-queue creation (because ``compliant=False`` for any
        non-empty failure set, regardless of severity)."""
        precomputed = _warning_only_summary()
        wrv2._persist_canonical_and_eval(
            db_session=MagicMock(), event=_make_event, tenant_id="t-1",
            precomputed_summary=precomputed,
        )
        assert len(_FakeEngine.persist_summary_calls) == 1
        assert _FakeEngine.evaluate_event_persist_true_calls == []
        # Exception queue gets a row.
        assert len(_FakeExceptionQueueService.create_calls) == 1
        assert _FakeExceptionQueueService.create_calls[0]["tenant_id"] == "t-1"
        assert _FakeExceptionQueueService.create_calls[0]["summary"] is precomputed

    def test_critical_summary_uses_persist_summary_and_creates_exceptions(self, _make_event):
        """Edge case: a critical-failure summary that somehow reaches the
        persist helper (caller didn't reject — would only happen if the
        caller is OFF mode but pre-eval returned a populated summary
        anyway, e.g. a config flip mid-request). Persist + exception-queue."""
        precomputed = _critical_summary()
        wrv2._persist_canonical_and_eval(
            db_session=MagicMock(), event=_make_event, tenant_id="t-1",
            precomputed_summary=precomputed,
        )
        assert len(_FakeEngine.persist_summary_calls) == 1
        assert _FakeEngine.evaluate_event_persist_true_calls == []
        assert len(_FakeExceptionQueueService.create_calls) == 1


# ---------------------------------------------------------------------------
# Fallback path: no pre-computed summary OR empty results
# ---------------------------------------------------------------------------

class TestFallbackPathUsesEvaluateEvent:

    def test_summary_none_falls_back_to_evaluate_event(self, _make_event):
        """OFF mode (or pre-eval errored) → caller passes None →
        ``evaluate_event(persist=True)`` runs, persist_summary doesn't.
        This branch is the default production path while
        ``RULES_ENGINE_ENFORCE=off`` and MUST remain bit-for-bit
        identical to pre-Phase-0 behavior."""
        _FakeEngine.summary_to_return = _compliant_summary()
        wrv2._persist_canonical_and_eval(
            db_session=MagicMock(), event=_make_event, tenant_id="t-1",
            precomputed_summary=None,
        )
        # Canonical persisted.
        assert _FakeCanonicalEventStore.persist_call_count == 1
        # evaluate_event called once with persist=True.
        assert len(_FakeEngine.evaluate_event_persist_true_calls) == 1
        ev_call = _FakeEngine.evaluate_event_persist_true_calls[0]
        assert ev_call["tenant_id"] == "t-1"
        # event_data anchored on the freshly-persisted canonical event_id.
        assert ev_call["event_data"]["event_id"] == "canonical-uuid-fresh"
        # No persist_summary, no exception queue (compliant).
        assert _FakeEngine.persist_summary_calls == []
        assert _FakeExceptionQueueService.create_calls == []

    def test_no_verdict_summary_falls_back_to_evaluate_event(self, _make_event):
        """Pre-eval ran but produced a no-verdict summary (no rules loaded
        / non-FTL). ``.results`` is empty → ``persist_summary`` would be
        a no-op → fall back to ``evaluate_event(persist=True)`` so the
        eval rows still get written (the threaded block is the only
        path that writes them)."""
        _FakeEngine.summary_to_return = _no_verdict_summary()
        precomputed = _no_verdict_summary()  # same shape
        wrv2._persist_canonical_and_eval(
            db_session=MagicMock(), event=_make_event, tenant_id="t-1",
            precomputed_summary=precomputed,
        )
        # Falls through to evaluate_event because results is empty.
        assert len(_FakeEngine.evaluate_event_persist_true_calls) == 1
        assert _FakeEngine.persist_summary_calls == []

    def test_fallback_path_creates_exceptions_on_non_compliant(self, _make_event):
        """Fallback's ``evaluate_event(persist=True)`` returns a
        non-compliant summary → exception-queue creation still fires.
        Same behavior as the fast path, just routed through evaluate."""
        _FakeEngine.summary_to_return = _warning_only_summary()
        wrv2._persist_canonical_and_eval(
            db_session=MagicMock(), event=_make_event, tenant_id="t-1",
            precomputed_summary=None,
        )
        assert len(_FakeEngine.evaluate_event_persist_true_calls) == 1
        assert len(_FakeExceptionQueueService.create_calls) == 1


# ---------------------------------------------------------------------------
# Invariants common to both paths
# ---------------------------------------------------------------------------

class TestCommonInvariants:

    def test_canonical_always_persisted(self, _make_event):
        """Canonical event is persisted in BOTH paths — the dual-write
        contract (#1335) doesn't depend on which rules-eval branch ran."""
        # Fast path
        _FakeEngine.summary_to_return = _compliant_summary()  # for fallback consumers
        wrv2._persist_canonical_and_eval(
            db_session=MagicMock(), event=_make_event, tenant_id="t-1",
            precomputed_summary=_compliant_summary(),
        )
        assert _FakeCanonicalEventStore.persist_call_count == 1

        # Fallback path
        _FakeCanonicalEventStore.persist_call_count = 0
        wrv2._persist_canonical_and_eval(
            db_session=MagicMock(), event=_make_event, tenant_id="t-1",
            precomputed_summary=None,
        )
        assert _FakeCanonicalEventStore.persist_call_count == 1

    def test_persist_summary_anchored_on_threaded_canonical_id_not_pre_eval_id(self, _make_event):
        """Critical contract: persist_summary writes rows against the
        canonical event_id WE just persisted, not the pre-eval canonical's
        event_id. ``normalize_webhook_event`` mints a fresh ID per call,
        so the pre-eval canonical's ID is a throwaway. If we wrote rows
        against it, they'd reference a canonical event that isn't in the
        database."""
        precomputed = _compliant_summary()
        # Mark the pre-eval canonical with a sentinel ID to detect a
        # programming error where the helper writes rows against it.
        precomputed.event_id = "PRE_EVAL_SENTINEL_DO_NOT_USE"
        wrv2._persist_canonical_and_eval(
            db_session=MagicMock(), event=_make_event, tenant_id="t-1",
            precomputed_summary=precomputed,
        )
        call = _FakeEngine.persist_summary_calls[0]
        assert call["event_id"] == "canonical-uuid-fresh"
        assert call["event_id"] != "PRE_EVAL_SENTINEL_DO_NOT_USE"
