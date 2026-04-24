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
    # Class var so test cases can set the summary returned by evaluate_event.
    summary_to_return: Any = None

    def __init__(self, db_session: Any) -> None:
        self.db_session = db_session

    def evaluate_event(self, event_data: dict, persist: bool, tenant_id: str) -> Any:
        return _FakeEngine.summary_to_return


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
