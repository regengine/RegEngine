"""Webhook-compat rules enforcement wire-up tests (Phase 0 #1b).

Verifies that ``RULES_ENGINE_ENFORCE={off,cte_only,all}`` drives the
accept/reject decision on ingested events, and that a rejection rolls
back the primary CTE savepoint so the event is not persisted.

Complements ``test_webhook_compat_1342.py`` (which tests the
OFF-mode / current behavior) — the stubs in that file return
``SimpleNamespace(compliant=bool)`` which doesn't carry
``critical_failures``. These tests install a stub that returns a real
``EvaluationSummary`` so the enforcement helper has something to
decide on.
"""
from __future__ import annotations

import asyncio
import sys
from types import ModuleType, SimpleNamespace

import pytest

# Test-path boilerplate mirrors test_webhook_compat_1342.py.
from services.ingestion.app import webhook_compat as wc

from services.shared.rules.types import EvaluationSummary, RuleEvaluationResult


# ---------------------------------------------------------------------------
# Minimal fakes (copy of the bits we need from test_webhook_compat_1342)
# ---------------------------------------------------------------------------

class _FakeSavepoint:
    def __init__(self, recorder, name):
        self.recorder = recorder
        self.name = name
        self.committed = False
        self.rolled_back = False

    def commit(self):
        self.committed = True
        self.recorder.append(("commit", self.name))

    def rollback(self):
        self.rolled_back = True
        self.recorder.append(("rollback", self.name))


class _FakeSession:
    def __init__(self):
        self.actions: list[tuple] = []
        self.savepoints: list[_FakeSavepoint] = []
        self.commit_count = 0
        self.rollback_count = 0

    def begin_nested(self):
        name = f"sp-{len(self.savepoints)}"
        sp = _FakeSavepoint(self.actions, name)
        self.savepoints.append(sp)
        return sp

    def commit(self):
        self.commit_count += 1
        self.actions.append(("session_commit",))

    def rollback(self):
        self.rollback_count += 1
        self.actions.append(("session_rollback",))


class _FakePersistence:
    def __init__(self, db_session):
        self.db_session = db_session
        self.store_calls: list[dict] = []
        self.store_result = SimpleNamespace(
            event_id="ev-1", sha256_hash="sha-1", chain_hash="chain-1"
        )

    def store_event(self, **kwargs):
        self.store_calls.append(kwargs)
        return self.store_result


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


def _make_payload(events, tenant_id="t-enforce"):
    return SimpleNamespace(tenant_id=tenant_id, source="manual", events=events)


def _install(monkeypatch, *, summary: EvaluationSummary, canonical_raises=None):
    sess = _FakeSession()
    persist = _FakePersistence(sess)
    cap: dict = {
        "exc_queue_calls": [],
        "publish_graph_calls": [],
        "rules_evaluate_calls": [],
    }

    monkeypatch.setattr(wc, "_verify_api_key_sync", lambda x_regengine_api_key: None)
    monkeypatch.setattr(wc, "_check_rate_limit", lambda tenant_id: None)
    monkeypatch.setattr(wc, "_validate_event_kdes", lambda e: [])
    monkeypatch.setattr(wc, "_generate_alerts", lambda e: [])
    monkeypatch.setattr(
        wc, "_publish_graph_sync",
        lambda eid, e, t: cap["publish_graph_calls"].append((eid, t)),
    )

    def _db_gen_factory():
        def _gen():
            yield sess
        return _gen()
    monkeypatch.setattr(wc, "_get_db_session", _db_gen_factory)

    tv_mod = ModuleType("app.tenant_validation")
    tv_mod.validate_tenant_id = lambda tid: None
    monkeypatch.setitem(sys.modules, "app.tenant_validation", tv_mod)

    cp_mod = ModuleType("shared.cte_persistence")
    cp_mod.CTEPersistence = lambda db_session: persist
    monkeypatch.setitem(sys.modules, "shared.cte_persistence", cp_mod)

    ce_mod = ModuleType("shared.canonical_event")
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
    ce_mod.normalize_webhook_event = _normalize
    monkeypatch.setitem(sys.modules, "shared.canonical_event", ce_mod)

    cps_mod = ModuleType("shared.canonical_persistence")
    class _FakeCanonicalStore:
        def __init__(self, db_session, dual_write):
            pass
        def persist_event(self, canonical):
            pass
    cps_mod.CanonicalEventStore = _FakeCanonicalStore
    monkeypatch.setitem(sys.modules, "shared.canonical_persistence", cps_mod)

    re_mod = ModuleType("shared.rules_engine")
    class _FakeEngine:
        def __init__(self, db_session):
            pass
        def evaluate_event(self, event_data, persist, tenant_id):
            cap["rules_evaluate_calls"].append(tenant_id)
            return summary
    re_mod.RulesEngine = _FakeEngine
    monkeypatch.setitem(sys.modules, "shared.rules_engine", re_mod)

    eq_mod = ModuleType("shared.exception_queue")
    class _FakeExceptionQueue:
        def __init__(self, db_session):
            pass
        def create_exceptions_from_evaluation(self, tenant_id, summary):
            cap["exc_queue_calls"].append(tenant_id)
    eq_mod.ExceptionQueueService = _FakeExceptionQueue
    monkeypatch.setitem(sys.modules, "shared.exception_queue", eq_mod)

    return sess, persist, cap


@pytest.fixture(autouse=True)
def _silence_logger(monkeypatch):
    class _Silent:
        def info(self, *a, **k): pass
        def warning(self, *a, **k): pass
        def error(self, *a, **k): pass
        def debug(self, *a, **k): pass
    monkeypatch.setattr(wc, "logger", _Silent())


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
# OFF mode — no behavior change
# ---------------------------------------------------------------------------

class TestEnforceOff:

    @pytest.fixture(autouse=True)
    def _off(self, monkeypatch):
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "off")

    def test_critical_failure_does_not_reject(self, monkeypatch):
        sess, persist, cap = _install(monkeypatch, summary=_critical_summary())
        resp = asyncio.run(wc.ingest_events(
            payload=_make_payload([_make_event()]),
            x_regengine_api_key="k",
        ))
        assert resp.accepted == 1 and resp.rejected == 0
        assert resp.events[0].status == "accepted"
        # Primary savepoint committed; canonical savepoint committed
        assert ("commit", "sp-0") in sess.actions
        # Exception queue still fires for compliant=False (unchanged)
        assert cap["exc_queue_calls"] == ["t-enforce"]


# ---------------------------------------------------------------------------
# CTE_ONLY mode — rejects on critical_failures
# ---------------------------------------------------------------------------

class TestEnforceCteOnly:

    @pytest.fixture(autouse=True)
    def _cte_only(self, monkeypatch):
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "cte_only")

    def test_critical_failure_rejects_event_and_rolls_back(self, monkeypatch):
        sess, persist, cap = _install(monkeypatch, summary=_critical_summary())
        resp = asyncio.run(wc.ingest_events(
            payload=_make_payload([_make_event()]),
            x_regengine_api_key="k",
        ))
        assert resp.accepted == 0 and resp.rejected == 1
        assert resp.events[0].status == "rejected"
        assert "rule_violation" in resp.events[0].errors[0]
        assert "CTE_REQ_HARVEST_DATE" in resp.events[0].errors[0]
        # Primary savepoint rolled back (not committed)
        assert ("rollback", "sp-0") in sess.actions
        assert ("commit", "sp-0") not in sess.actions
        # store_event was called (required to produce a store_result for the
        # rejected path), but the savepoint rollback unwinds that write.
        assert len(persist.store_calls) == 1
        # No publish_graph_sync on rejected events
        assert cap["publish_graph_calls"] == []
        # No exception-queue fire on reject — exception queue is for
        # non-blocking failures on ACCEPTED events, not for rejects.
        assert cap["exc_queue_calls"] == []

    def test_warning_only_failure_does_not_reject(self, monkeypatch):
        """Warnings are non-critical: the event accepts, but a row lands
        in the exception queue for tenant visibility."""
        sess, persist, cap = _install(monkeypatch, summary=_warning_only_summary())
        resp = asyncio.run(wc.ingest_events(
            payload=_make_payload([_make_event()]),
            x_regengine_api_key="k",
        ))
        assert resp.accepted == 1 and resp.rejected == 0
        assert resp.events[0].status == "accepted"
        assert ("commit", "sp-0") in sess.actions
        assert cap["exc_queue_calls"] == ["t-enforce"]

    def test_no_verdict_never_rejects(self, monkeypatch):
        """Non-FTL / no_rules_loaded → compliant=None → must accept."""
        sess, persist, cap = _install(monkeypatch, summary=_no_verdict_summary())
        resp = asyncio.run(wc.ingest_events(
            payload=_make_payload([_make_event()]),
            x_regengine_api_key="k",
        ))
        assert resp.accepted == 1 and resp.rejected == 0
        assert resp.events[0].status == "accepted"

    def test_compliant_accepts_without_exception_queue(self, monkeypatch):
        sess, persist, cap = _install(monkeypatch, summary=_compliant_summary())
        resp = asyncio.run(wc.ingest_events(
            payload=_make_payload([_make_event()]),
            x_regengine_api_key="k",
        ))
        assert resp.accepted == 1
        assert cap["exc_queue_calls"] == []

    def test_canonical_error_does_not_block_accept_under_enforce(self, monkeypatch):
        """If canonical normalization crashes, summary is None and the
        enforcement check is skipped — primary event still commits.
        Preserves the prior best-effort semantics so a canonical-module
        regression can't take down ingestion for every tenant."""
        sess, persist, cap = _install(
            monkeypatch,
            summary=_critical_summary(),  # would reject if it ran
            canonical_raises=RuntimeError("canonical broken"),
        )
        resp = asyncio.run(wc.ingest_events(
            payload=_make_payload([_make_event()]),
            x_regengine_api_key="k",
        ))
        assert resp.accepted == 1 and resp.rejected == 0
        # Canonical savepoint rolled back; primary savepoint committed
        assert ("commit", "sp-0") in sess.actions


# ---------------------------------------------------------------------------
# ALL mode — rejects on any compliant=False
# ---------------------------------------------------------------------------

class TestEnforceAll:

    @pytest.fixture(autouse=True)
    def _all(self, monkeypatch):
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "all")

    def test_warning_only_failure_rejects_under_all(self, monkeypatch):
        """ALL mode is stricter than CTE_ONLY: warning-severity failures
        ALSO reject."""
        sess, persist, cap = _install(monkeypatch, summary=_warning_only_summary())
        resp = asyncio.run(wc.ingest_events(
            payload=_make_payload([_make_event()]),
            x_regengine_api_key="k",
        ))
        assert resp.accepted == 0 and resp.rejected == 1
        assert resp.events[0].status == "rejected"
        assert "R_WARN" in resp.events[0].errors[0]
        assert ("rollback", "sp-0") in sess.actions

    def test_compliant_still_accepts_in_all_mode(self, monkeypatch):
        sess, _, _ = _install(monkeypatch, summary=_compliant_summary())
        resp = asyncio.run(wc.ingest_events(
            payload=_make_payload([_make_event()]),
            x_regengine_api_key="k",
        ))
        assert resp.accepted == 1
        assert ("commit", "sp-0") in sess.actions
