"""EPCIS persistence rules-enforcement gate (Phase 0 #1d).

Verifies that ``_persist_prepared_event_in_session`` honors
``RULES_ENGINE_ENFORCE`` by raising HTTPException(422) when the pre-eval
gate decides to reject, and that the primary CTE write is skipped in
that case so the caller's ``db_session.rollback()`` is clean.

The test reuses the hermetic fakes already established by
``test_epcis_persistence_1342.py`` (CTEPersistence, RulesEngine,
CanonicalEventStore, normalize_epcis_event — all swapped at the module
level so the lazy imports inside the function under test pick them up).
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from services.shared.rules.types import EvaluationSummary, RuleEvaluationResult


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class _FakeCTEPersistence:
    last_called = False
    last_instance = None

    def __init__(self, db_session: Any) -> None:
        _FakeCTEPersistence.last_instance = self
        self.db_session = db_session

    def store_event(self, **kwargs: Any) -> Any:
        _FakeCTEPersistence.last_called = True
        result = MagicMock()
        result.event_id = "ev-1"
        result.sha256_hash = "sha-1"
        result.chain_hash = "chain-1"
        result.idempotent = False
        return result


class _FakeCanonicalEventStore:
    def __init__(self, db_session: Any, dual_write: bool = False, skip_chain_write: bool = False) -> None:
        self.db_session = db_session

    def set_tenant_context(self, tenant_id: str) -> None:
        pass

    def persist_event(self, canonical: Any) -> None:
        pass


class _FakeEngine:
    # Class vars so test cases can read counts after the function under test
    # has finished running its threaded canonical block (the daemon thread
    # is joined on the main thread before the function returns, so all
    # call-count assertions are deterministic).
    summary_to_return: Any = None
    evaluate_event_call_count: int = 0
    evaluate_event_persist_true_count: int = 0
    persist_summary_calls: list = []

    def __init__(self, db_session: Any) -> None:
        self.db_session = db_session

    def evaluate_event(self, event_data: dict, persist: bool, tenant_id: str) -> Any:
        _FakeEngine.evaluate_event_call_count += 1
        if persist:
            _FakeEngine.evaluate_event_persist_true_count += 1
        return _FakeEngine.summary_to_return

    def persist_summary(self, summary: Any, *, tenant_id: str, event_id=None) -> None:
        _FakeEngine.persist_summary_calls.append({
            "summary": summary,
            "tenant_id": tenant_id,
            "event_id": event_id,
        })


def _fake_normalize_epcis_event(event: Any, tenant_id: str) -> Any:
    class _Canonical:
        event_id = "canonical-id"
        event_type = MagicMock(value="OBJECT_EVENT")
        traceability_lot_code = "TLC-X"
        product_reference = "prod-r"
        quantity = 1.0
        unit_of_measure = "CS"
        from_facility_reference = None
        to_facility_reference = None
        from_entity_reference = None
        to_entity_reference = None
        kdes: dict[str, Any] = {}

    return _Canonical()


@pytest.fixture(autouse=True)
def _install_fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wire the hermetic fakes at the module level so lazy imports pick them up."""
    _FakeCTEPersistence.last_called = False
    _FakeCTEPersistence.last_instance = None
    _FakeEngine.summary_to_return = None
    _FakeEngine.evaluate_event_call_count = 0
    _FakeEngine.evaluate_event_persist_true_count = 0
    _FakeEngine.persist_summary_calls = []

    import shared.cte_persistence as _cte_mod
    import shared.canonical_event as _canon_mod
    import shared.canonical_persistence as _store_mod
    import shared.rules_engine as _rules_mod

    monkeypatch.setattr(_cte_mod, "CTEPersistence", _FakeCTEPersistence)
    monkeypatch.setattr(_canon_mod, "normalize_epcis_event", _fake_normalize_epcis_event)
    monkeypatch.setattr(_store_mod, "CanonicalEventStore", _FakeCanonicalEventStore)
    monkeypatch.setattr(_rules_mod, "RulesEngine", _FakeEngine)


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
        result="fail", why_failed="non-critical",
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


def _make_prepared() -> dict:
    """Minimal prepared-event dict matching _prepare_event_for_persistence output."""
    return {
        "event": {"eventID": "urn:uuid:test"},
        "idempotency_key": "idem-1",
        "normalized": {
            "event_type": "receiving",
            "tlc": "TLC-X",
            "epcis_event_type": "OBJECT_EVENT",
            "epcis_action": "ADD",
            "epcis_biz_step": "receiving",
            "quantity": 1.0,
            "unit_of_measure": "CS",
            "location_id": "urn:epc:id:sgln:0012345.00001.0",
            "event_time": "2026-01-01T00:00:00Z",
        },
        "kdes": {},
        "alerts": [],
        "kde_map": {"fsma_validation_status": "passed"},
        "quantity_value": 1.0,
        "event_time": "2026-01-01T00:00:00Z",
    }


# ---------------------------------------------------------------------------
# OFF mode — pre-eval is short-circuited, primary store still called
# ---------------------------------------------------------------------------

class TestEnforceOff:
    @pytest.fixture(autouse=True)
    def _off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "off")

    def test_critical_failure_does_not_reject(self) -> None:
        """OFF mode: even a summary full of critical failures lets the
        event through. The pre-eval gate short-circuits entirely —
        evaluate_event should not even be called by the pre-eval path
        (the existing threaded canonical block is a separate caller
        and may still invoke it later, which is fine)."""
        _FakeEngine.summary_to_return = _critical_summary()
        from app.epcis import persistence as persistence_mod
        payload, status = persistence_mod._persist_prepared_event_in_session(
            db_session=MagicMock(), tenant_id="t-1", prepared=_make_prepared(),
        )
        assert status in (200, 201)
        assert _FakeCTEPersistence.last_called is True


# ---------------------------------------------------------------------------
# CTE_ONLY mode — critical failure → 422, store_event NOT called
# ---------------------------------------------------------------------------

class TestEnforceCteOnly:
    @pytest.fixture(autouse=True)
    def _cte_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "cte_only")

    def test_critical_failure_raises_422(self) -> None:
        _FakeEngine.summary_to_return = _critical_summary()
        from app.epcis import persistence as persistence_mod
        with pytest.raises(HTTPException) as exc_info:
            persistence_mod._persist_prepared_event_in_session(
                db_session=MagicMock(), tenant_id="t-1", prepared=_make_prepared(),
            )
        assert exc_info.value.status_code == 422
        detail = exc_info.value.detail
        assert detail["error"] == "rule_violation"
        assert "CTE_REQ_HARVEST_DATE" in detail["reason"]
        assert "harvest_date missing" in detail["reason"]
        assert detail["tenant_id"] == "t-1"
        # Primary store never called — pre-eval gate intercepted.
        assert _FakeCTEPersistence.last_called is False

    def test_warning_only_accepts(self) -> None:
        _FakeEngine.summary_to_return = _warning_only_summary()
        from app.epcis import persistence as persistence_mod
        payload, status = persistence_mod._persist_prepared_event_in_session(
            db_session=MagicMock(), tenant_id="t-1", prepared=_make_prepared(),
        )
        assert status in (200, 201)
        assert _FakeCTEPersistence.last_called is True

    def test_no_verdict_accepts(self) -> None:
        """Non-FTL / no_rules_loaded → compliant=None → must never reject.
        Blocking here would break ingestion for tenants without seeded
        rules and for non-FTL products."""
        _FakeEngine.summary_to_return = _no_verdict_summary()
        from app.epcis import persistence as persistence_mod
        payload, status = persistence_mod._persist_prepared_event_in_session(
            db_session=MagicMock(), tenant_id="t-1", prepared=_make_prepared(),
        )
        assert status in (200, 201)
        assert _FakeCTEPersistence.last_called is True

    def test_compliant_accepts(self) -> None:
        _FakeEngine.summary_to_return = _compliant_summary()
        from app.epcis import persistence as persistence_mod
        payload, status = persistence_mod._persist_prepared_event_in_session(
            db_session=MagicMock(), tenant_id="t-1", prepared=_make_prepared(),
        )
        assert status in (200, 201)
        assert _FakeCTEPersistence.last_called is True

    def test_canonical_error_accepts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """If normalize_epcis_event raises, pre-eval treats as no-verdict
        and the event is accepted. Preserves best-effort semantics for
        transient canonical bugs."""
        _FakeEngine.summary_to_return = _critical_summary()  # would reject if eval ran

        def _raise(event: Any, tenant_id: str) -> Any:
            raise RuntimeError("canonical broken")

        import shared.canonical_event as _canon_mod
        monkeypatch.setattr(_canon_mod, "normalize_epcis_event", _raise)

        from app.epcis import persistence as persistence_mod
        payload, status = persistence_mod._persist_prepared_event_in_session(
            db_session=MagicMock(), tenant_id="t-1", prepared=_make_prepared(),
        )
        assert status in (200, 201)
        assert _FakeCTEPersistence.last_called is True


# ---------------------------------------------------------------------------
# ALL mode
# ---------------------------------------------------------------------------

class TestEnforceAll:
    @pytest.fixture(autouse=True)
    def _all(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "all")

    def test_warning_only_rejects_under_all(self) -> None:
        """ALL mode is stricter than CTE_ONLY: warning-severity failures
        ALSO reject."""
        _FakeEngine.summary_to_return = _warning_only_summary()
        from app.epcis import persistence as persistence_mod
        with pytest.raises(HTTPException) as exc_info:
            persistence_mod._persist_prepared_event_in_session(
                db_session=MagicMock(), tenant_id="t-1", prepared=_make_prepared(),
            )
        assert exc_info.value.status_code == 422
        assert "R_WARN" in exc_info.value.detail["reason"]
        assert _FakeCTEPersistence.last_called is False

    def test_compliant_accepts(self) -> None:
        _FakeEngine.summary_to_return = _compliant_summary()
        from app.epcis import persistence as persistence_mod
        payload, status = persistence_mod._persist_prepared_event_in_session(
            db_session=MagicMock(), tenant_id="t-1", prepared=_make_prepared(),
        )
        assert status in (200, 201)
        assert _FakeCTEPersistence.last_called is True


# ---------------------------------------------------------------------------
# Threaded post-commit block — uses pre-computed summary instead of
# re-evaluating. This is the actual fix for the double-eval regression.
# ---------------------------------------------------------------------------

class TestThreadedBlockReusesPreComputedSummary:
    """Under enforcement, the post-commit threaded canonical block must
    persist the pre-computed summary via ``RulesEngine.persist_summary``
    instead of re-running ``evaluate_event(persist=True)``. Otherwise
    every accepted event under enforcement pays for two full rule
    evaluations on the hot path.

    The threaded block uses ``threading.Thread.join(timeout=...)`` on the
    main thread, so by the time the function under test returns, the
    daemon thread has either finished or timed out — call counts on
    class-var counters are deterministic.
    """

    @pytest.fixture(autouse=True)
    def _cte_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "cte_only")

    def test_compliant_uses_persist_summary_not_reevaluate(self) -> None:
        """Compliant event under enforcement → pre-eval runs (1 evaluate
        call, persist=False) → primary store → threaded block calls
        persist_summary, NOT evaluate_event again.

        Expected counts:
          - evaluate_event total: 1 (pre-eval only)
          - evaluate_event persist=True: 0 (the fix — no re-evaluation)
          - persist_summary calls: 1 (threaded block uses pre-computed)
        """
        _FakeEngine.summary_to_return = _compliant_summary()
        from app.epcis import persistence as persistence_mod
        payload, status = persistence_mod._persist_prepared_event_in_session(
            db_session=MagicMock(), tenant_id="t-1", prepared=_make_prepared(),
        )
        assert status in (200, 201)
        assert _FakeEngine.evaluate_event_call_count == 1, (
            f"expected 1 evaluate_event call (pre-eval only), "
            f"got {_FakeEngine.evaluate_event_call_count} — re-eval regression"
        )
        assert _FakeEngine.evaluate_event_persist_true_count == 0, (
            f"threaded block should NOT call evaluate_event(persist=True) "
            f"when a pre-computed summary is available; called "
            f"{_FakeEngine.evaluate_event_persist_true_count} times"
        )
        assert len(_FakeEngine.persist_summary_calls) == 1, (
            f"expected 1 persist_summary call, "
            f"got {len(_FakeEngine.persist_summary_calls)}"
        )

    def test_warning_only_uses_persist_summary_not_reevaluate(self) -> None:
        """Warning-only failure under cte_only mode → accept + threaded
        block uses persist_summary. Same single-eval pattern as compliant."""
        _FakeEngine.summary_to_return = _warning_only_summary()
        from app.epcis import persistence as persistence_mod
        payload, status = persistence_mod._persist_prepared_event_in_session(
            db_session=MagicMock(), tenant_id="t-1", prepared=_make_prepared(),
        )
        assert status in (200, 201)
        assert _FakeEngine.evaluate_event_persist_true_count == 0
        assert len(_FakeEngine.persist_summary_calls) == 1

    def test_persist_summary_anchors_on_threaded_canonical_event_id(self) -> None:
        """persist_summary must be called with the threaded block's
        canonical event_id — the rows must reference the canonical event
        we actually persisted, not the pre-eval throwaway. Both calls
        to ``normalize_epcis_event`` produce the same fake event_id in
        this test, so we can only assert non-empty here; the contract
        under real ``normalize_epcis_event`` (which mints UUIDs) is
        enforced by the implementation passing
        ``event_id=str(_canonical.event_id)`` from the threaded block.
        """
        _FakeEngine.summary_to_return = _compliant_summary()
        from app.epcis import persistence as persistence_mod
        persistence_mod._persist_prepared_event_in_session(
            db_session=MagicMock(), tenant_id="t-1", prepared=_make_prepared(),
        )
        assert len(_FakeEngine.persist_summary_calls) == 1
        call = _FakeEngine.persist_summary_calls[0]
        assert call["event_id"] is not None
        assert call["event_id"] != ""
        assert call["tenant_id"] == "t-1"


class TestThreadedBlockFallbackWhenNoPreComputedSummary:
    """When pre-eval is skipped (OFF mode) or returns a no-verdict / errored
    summary, the threaded block must fall back to the pre-Phase-0 behavior
    of ``evaluate_event(persist=True)``. This branch is the default
    production path while ``RULES_ENGINE_ENFORCE=off``, so it must remain
    bit-for-bit identical to the prior implementation."""

    def test_off_mode_falls_back_to_evaluate_event(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """OFF mode short-circuits pre-eval (returns summary=None), so the
        threaded block re-evaluates with persist=True. Single eval total."""
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "off")
        _FakeEngine.summary_to_return = _compliant_summary()
        from app.epcis import persistence as persistence_mod
        payload, status = persistence_mod._persist_prepared_event_in_session(
            db_session=MagicMock(), tenant_id="t-1", prepared=_make_prepared(),
        )
        assert status in (200, 201)
        # Pre-eval skipped (OFF short-circuit), threaded block evaluated once.
        assert _FakeEngine.evaluate_event_call_count == 1
        assert _FakeEngine.evaluate_event_persist_true_count == 1
        assert len(_FakeEngine.persist_summary_calls) == 0, (
            "OFF mode must NOT call persist_summary — no pre-computed "
            "summary exists, so the fallback branch handles persistence "
            "via evaluate_event(persist=True)"
        )

    def test_no_verdict_summary_falls_back_to_evaluate_event(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """no_verdict_reason summary has empty .results — persist_summary
        would be a no-op against it. Threaded block falls through to
        evaluate_event so the eval rows actually get written."""
        monkeypatch.setenv("RULES_ENGINE_ENFORCE", "cte_only")
        _FakeEngine.summary_to_return = _no_verdict_summary()
        from app.epcis import persistence as persistence_mod
        payload, status = persistence_mod._persist_prepared_event_in_session(
            db_session=MagicMock(), tenant_id="t-1", prepared=_make_prepared(),
        )
        assert status in (200, 201)
        # Pre-eval ran (1 call) + threaded block re-evaluated to write rows.
        assert _FakeEngine.evaluate_event_call_count == 2
        assert _FakeEngine.evaluate_event_persist_true_count == 1
        assert len(_FakeEngine.persist_summary_calls) == 0
