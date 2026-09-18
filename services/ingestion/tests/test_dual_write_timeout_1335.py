"""Regression tests for the EPCIS canonical dual-write — #2499 and #2534.

History: the canonical write to ``fsma.traceability_events`` (plus its
rule evaluation) used to run in a ``daemon=True`` worker thread joined
with a 5 s timeout (``CANONICAL_DUAL_WRITE_TIMEOUT_S``). Issue #1335
introduced that fan-out so a slow canonical DB path could not block the
EPCIS ingest response. Two defects followed:

* #2499 (P0) — the worker issued SQL on the SAME caller-managed
  ``db_session`` the request thread then committed. A SQLAlchemy Session
  and its psycopg connection are not thread-safe, so on the timeout path
  (worker still alive) the main thread's commit raced the worker's
  ``execute()`` on one connection.
* #2534 (P2) — any worker exception was downgraded to a
  ``logger.warning("epcis_canonical_write_skipped")`` and the event was
  still reported persisted (HTTP 201) even though the canonical row and
  its rule rows silently never landed.

Fix: the canonical write now runs SYNCHRONOUSLY on the request thread,
inside the same transaction the caller commits. One connection used
sequentially (no cross-thread sharing → #2499 closed); a failure poisons
the session and propagates so the caller rolls back and the client sees a
5xx instead of a false 201 (→ #2534 closed).

These tests drive the real ``_persist_prepared_event_in_session`` with
hermetic fakes swapped at the module level (same pattern as
``test_epcis_persistence_enforcement.py``), so they need no live DB.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Hermetic fakes — swapped onto the already-loaded real modules so the
# lazy imports inside the function under test resolve to them.
# ---------------------------------------------------------------------------


class _FakeCTEPersistence:
    def __init__(self, db_session: Any) -> None:
        self.db_session = db_session

    def store_event(self, **kwargs: Any) -> Any:
        result = MagicMock()
        result.event_id = "ev-1"
        result.sha256_hash = "sha-1"
        result.chain_hash = "chain-1"
        result.idempotent = False
        return result


class _FakeCanonicalEventStore:
    # Records the thread that executed persist_event so a test can assert
    # the canonical write ran on the SAME (request) thread — i.e. it is
    # not fanned out to a worker (#2499).
    persist_thread_name: str | None = None

    def __init__(self, db_session: Any, dual_write: bool = False, skip_chain_write: bool = False) -> None:
        self.db_session = db_session
        # #2499: the EPCIS path must NOT dual-write or grow the chain via
        # the canonical store (the legacy CTE write owns the chain here).
        assert dual_write is False
        assert skip_chain_write is True

    def set_tenant_context(self, tenant_id: str) -> None:
        pass

    def persist_event(self, canonical: Any) -> None:
        import threading

        _FakeCanonicalEventStore.persist_thread_name = threading.current_thread().name


class _FakeEngine:
    def __init__(self, db_session: Any) -> None:
        self.db_session = db_session

    def evaluate_event(self, event_data: dict, persist: bool, tenant_id: str) -> Any:
        return None

    def persist_summary(self, summary: Any, *, tenant_id: str, event_id=None) -> None:
        pass


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
    _FakeCanonicalEventStore.persist_thread_name = None

    import shared.canonical_event as _canon_mod
    import shared.canonical_persistence as _store_mod
    import shared.cte_persistence as _cte_mod
    import shared.rules_engine as _rules_mod

    monkeypatch.setattr(_cte_mod, "CTEPersistence", _FakeCTEPersistence)
    monkeypatch.setattr(_canon_mod, "normalize_epcis_event", _fake_normalize_epcis_event)
    monkeypatch.setattr(_store_mod, "CanonicalEventStore", _FakeCanonicalEventStore)
    monkeypatch.setattr(_rules_mod, "RulesEngine", _FakeEngine)
    # OFF mode: skip the pre-eval gate so these tests exercise the
    # canonical-write block directly on the default production path.
    monkeypatch.setenv("RULES_ENGINE_ENFORCE", "off")


def _make_prepared() -> dict:
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
# #2499 — canonical write runs on the request thread, not a worker.
# ---------------------------------------------------------------------------


class TestCanonicalWriteIsSynchronous_Issue2499:
    def test_persist_event_runs_on_caller_thread(self) -> None:
        """The canonical write must execute on the same thread that calls
        ``_persist_prepared_event_in_session`` — proving there is no
        daemon worker sharing the session/connection with the committing
        main thread."""
        import threading

        from services.ingestion.app.epcis import persistence as persistence_mod

        payload, status = persistence_mod._persist_prepared_event_in_session(
            db_session=MagicMock(),
            tenant_id="t-1",
            prepared=_make_prepared(),
        )
        assert status == 201
        assert _FakeCanonicalEventStore.persist_thread_name == threading.current_thread().name, (
            "canonical write must run synchronously on the request thread "
            "(no fan-out to a daemon worker sharing the DB session)"
        )

    def test_idempotent_result_skips_canonical_write(self) -> None:
        """Idempotent legacy result → canonical block is not entered."""

        class _IdempotentCTE(_FakeCTEPersistence):
            def store_event(self, **kwargs: Any) -> Any:
                result = MagicMock()
                result.event_id = "ev-1"
                result.idempotent = True
                return result

        import shared.cte_persistence as _cte_mod

        _cte_mod.CTEPersistence = _IdempotentCTE  # type: ignore[attr-defined]
        try:
            from services.ingestion.app.epcis import persistence as persistence_mod

            payload, status = persistence_mod._persist_prepared_event_in_session(
                db_session=MagicMock(),
                tenant_id="t-1",
                prepared=_make_prepared(),
            )
            assert status == 200
            assert _FakeCanonicalEventStore.persist_thread_name is None
        finally:
            _cte_mod.CTEPersistence = _FakeCTEPersistence  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# #2534 — a canonical-write failure propagates (no silent 201 drop).
# ---------------------------------------------------------------------------


class TestCanonicalWriteFailLoud_Issue2534:
    def test_normalize_failure_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A pre-SQL ``ValueError`` from ``normalize_epcis_event`` must
        propagate, not be downgraded to a warning while the event is
        reported persisted (HTTP 201)."""
        import shared.canonical_event as _canon_mod

        def _boom(event: Any, tenant_id: str) -> Any:
            raise ValueError("bad timestamp")

        monkeypatch.setattr(_canon_mod, "normalize_epcis_event", _boom)

        from services.ingestion.app.epcis import persistence as persistence_mod

        with pytest.raises(ValueError, match="bad timestamp"):
            persistence_mod._persist_prepared_event_in_session(
                db_session=MagicMock(),
                tenant_id="t-1",
                prepared=_make_prepared(),
            )

    def test_persist_event_failure_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A failure inside ``CanonicalEventStore.persist_event`` must
        propagate so the caller rolls back the shared transaction."""

        class _FailingStore(_FakeCanonicalEventStore):
            def persist_event(self, canonical: Any) -> None:
                raise RuntimeError("canonical insert failed")

        import shared.canonical_persistence as _store_mod

        monkeypatch.setattr(_store_mod, "CanonicalEventStore", _FailingStore)

        from services.ingestion.app.epcis import persistence as persistence_mod

        with pytest.raises(RuntimeError, match="canonical insert failed"):
            persistence_mod._persist_prepared_event_in_session(
                db_session=MagicMock(),
                tenant_id="t-1",
                prepared=_make_prepared(),
            )

    def test_single_event_db_rolls_back_on_canonical_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """End-to-end: a canonical failure on the own-session wrapper
        must trigger ``rollback()`` (no commit, no false 201)."""
        import shared.canonical_event as _canon_mod

        def _boom(event: Any, tenant_id: str) -> Any:
            raise RuntimeError("canon dead")

        monkeypatch.setattr(_canon_mod, "normalize_epcis_event", _boom)

        sess = MagicMock()
        from services.ingestion.app.epcis import persistence as persistence_mod

        monkeypatch.setattr(persistence_mod, "get_db_safe", lambda: sess)
        # Skip the real EPCIS validation/normalization pipeline — we want
        # the failure to originate in the synchronous canonical write
        # inside _persist_prepared_event_in_session, not in pre-DB checks.
        monkeypatch.setattr(
            persistence_mod,
            "_prepare_event_for_persistence",
            lambda tenant_id, event: _make_prepared(),
        )

        with pytest.raises(RuntimeError, match="canon dead"):
            persistence_mod._ingest_single_event_db("t-1", {"eventID": "urn:uuid:test"})

        sess.rollback.assert_called_once()
        sess.commit.assert_not_called()
        sess.close.assert_called_once()
