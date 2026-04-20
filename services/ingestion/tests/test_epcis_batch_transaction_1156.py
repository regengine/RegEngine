"""Regression coverage for #1156 — EPCIS batch ingest atomicity.

Scenario under test: a 3-event batch where the 2nd event fails during
the DB-write phase. After rollback, NONE of the three events must be
visible in the CTE store. This protects downstream graph/compliance
readers from seeing a partially-committed supply chain.

Also covers the ``EPCIS_BATCH_TRANSACTIONAL`` env var: default (unset)
is treated as transactional; ``false`` switches the router's batch
endpoints to legacy partial-success semantics.

Issue: #1156
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))


import importlib

from app.epcis import persistence as persistence_mod  # noqa: E402

# NB: ``from app.epcis import router as router_mod`` resolves to the
# APIRouter instance (router = APIRouter(...) shadows the module name
# when the package re-exports). Use importlib to grab the real module.
router_mod = importlib.import_module("app.epcis.router")


# ── Shared fixtures ────────────────────────────────────────────────────────


_VALID_EPCIS_TEMPLATE = {
    "@context": [],
    "type": "ObjectEvent",
    "eventTime": "2026-02-28T09:30:00-05:00",
    "eventTimeZoneOffset": "-05:00",
    "action": "OBSERVE",
    "bizStep": "urn:epcglobal:cbv:bizstep:receiving",
    "bizLocation": {"id": "urn:epc:id:sgln:0614141.00002.0"},
    "ilmd": {
        "cbvmda:lotNumber": "ROM-0042",
        "fsma:traceabilityLotCode": "00012345678901-ROM0042",
    },
    "extension": {
        "quantityList": [
            {
                "epcClass": "urn:epc:class:lgtin:0614141.107346.ROM0042",
                "quantity": 10.0,
                "uom": "CS",
            },
        ],
    },
}


def _make_event(lot: str) -> dict:
    """Return a deep-copied EPCIS event with a distinct lot (so idempotency keys differ)."""
    import copy

    evt = copy.deepcopy(_VALID_EPCIS_TEMPLATE)
    evt["ilmd"] = {
        "cbvmda:lotNumber": lot,
        "fsma:traceabilityLotCode": f"00012345678901-{lot}",
    }
    evt["extension"]["quantityList"][0]["epcClass"] = (
        f"urn:epc:class:lgtin:0614141.107346.{lot}"
    )
    return evt


class _FakeStoreResult:
    def __init__(self, event_id: str, idempotent: bool = False) -> None:
        self.event_id = event_id
        self.idempotent = idempotent


class _RecordingCTEPersistence:
    """Fake CTEPersistence that records every ``store_event`` call.

    Simulates a mid-batch DB failure: ``fail_on_lot`` is the lot number
    that should raise RuntimeError when encountered. All prior calls
    recorded in ``stored_events`` represent rows that WOULD be committed
    — but the outer atomic transaction must roll them back so the
    persistence layer ends up with no survivors.
    """

    stored_events: list[str] = []
    fail_on_lot: str | None = None

    def __init__(self, db_session: Any) -> None:
        self.db_session = db_session

    def store_event(self, **kwargs: Any) -> _FakeStoreResult:
        # The lot code is carried through the kde map as lotNumber.
        kdes = kwargs.get("kdes") or {}
        lot = kdes.get("lotNumber") or kwargs.get("traceability_lot_code", "")
        if _RecordingCTEPersistence.fail_on_lot and _RecordingCTEPersistence.fail_on_lot in lot:
            raise RuntimeError(f"simulated DB write failure for lot={lot}")
        event_id = f"cte-{lot}"
        _RecordingCTEPersistence.stored_events.append(event_id)
        return _FakeStoreResult(event_id=event_id, idempotent=False)


class _FakeCanonicalEventStore:
    def __init__(self, db_session: Any, dual_write: bool = False, skip_chain_write: bool = False) -> None:
        pass

    def set_tenant_context(self, tenant_id: str) -> None:
        pass

    def persist_event(self, canonical: Any) -> None:
        pass


class _FakeRulesEngine:
    def __init__(self, db_session: Any) -> None:
        pass

    def evaluate_event(self, event_data: dict, persist: bool, tenant_id: str) -> None:
        pass


def _fake_normalize_epcis_event(event: dict, tenant_id: str) -> Any:
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
def _reset_and_install_fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    import shared.cte_persistence as _cte_mod
    import shared.canonical_event as _canon_mod
    import shared.canonical_persistence as _store_mod
    import shared.rules_engine as _rules_mod

    _RecordingCTEPersistence.stored_events = []
    _RecordingCTEPersistence.fail_on_lot = None

    monkeypatch.setattr(_cte_mod, "CTEPersistence", _RecordingCTEPersistence)
    monkeypatch.setattr(_canon_mod, "normalize_epcis_event", _fake_normalize_epcis_event)
    monkeypatch.setattr(_store_mod, "CanonicalEventStore", _FakeCanonicalEventStore)
    monkeypatch.setattr(_rules_mod, "RulesEngine", _FakeRulesEngine)


# ── The core #1156 regression ──────────────────────────────────────────────


class TestBatchAtomicityOnMidBatchDbFailure:
    """3-event batch, 2nd fails DB write — expect 0 survivors + WARN log."""

    def test_none_of_three_events_persist_when_second_fails(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        session = MagicMock()
        monkeypatch.setattr(persistence_mod, "get_db_safe", lambda: session)

        # Arrange: lot B fails mid-batch.
        _RecordingCTEPersistence.fail_on_lot = "LOT-B"

        events = [_make_event("LOT-A"), _make_event("LOT-B"), _make_event("LOT-C")]

        with caplog.at_level("WARNING", logger="epcis-ingestion"):
            with pytest.raises(HTTPException) as exc_info:
                persistence_mod._ingest_batch_events_db_atomic("tenant-1156", events)

        # Rollback path: 400 with atomic marker + offending index.
        assert exc_info.value.status_code == 400
        detail = exc_info.value.detail
        assert detail["error"] == "batch_persistence_failed"
        assert detail["mode"] == "atomic"
        # The 2nd event (index 1) is the one that blew up.
        assert detail["failed_index"] == 1

        # Session lifecycle: rollback + close. Commit MUST NOT have fired.
        session.rollback.assert_called_once()
        session.close.assert_called_once()
        session.commit.assert_not_called()

        # WARN log mentions the offending index and the tenant.
        warn_messages = [r.message for r in caplog.records if r.levelname == "WARNING"]
        assert any(
            "epcis_batch_rollback" in m and "failed_index=1" in m and "tenant-1156" in m
            for m in warn_messages
        ), f"missing structured rollback warning; got: {warn_messages}"

    def test_happy_path_commits_once_for_three_good_events(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session = MagicMock()
        monkeypatch.setattr(persistence_mod, "get_db_safe", lambda: session)

        events = [_make_event("LOT-X"), _make_event("LOT-Y"), _make_event("LOT-Z")]
        results = persistence_mod._ingest_batch_events_db_atomic("tenant-1156", events)

        assert len(results) == 3
        for payload, status in results:
            assert status == 201
        session.commit.assert_called_once()
        session.rollback.assert_not_called()
        # All three events made it to the fake store_event (pre-commit).
        assert len(_RecordingCTEPersistence.stored_events) == 3


# ── EPCIS_BATCH_TRANSACTIONAL env gate ─────────────────────────────────────


class TestBatchTransactionalEnvGate:
    def test_default_unset_is_atomic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("EPCIS_BATCH_TRANSACTIONAL", raising=False)
        assert persistence_mod._batch_transactional() is True

    @pytest.mark.parametrize("val", ["1", "true", "yes", "on", "atomic"])
    def test_truthy_variants_are_atomic(
        self, monkeypatch: pytest.MonkeyPatch, val: str
    ) -> None:
        monkeypatch.setenv("EPCIS_BATCH_TRANSACTIONAL", val)
        assert persistence_mod._batch_transactional() is True

    @pytest.mark.parametrize("val", ["0", "false", "no", "off", "partial"])
    def test_falsy_variants_opt_out(
        self, monkeypatch: pytest.MonkeyPatch, val: str
    ) -> None:
        monkeypatch.setenv("EPCIS_BATCH_TRANSACTIONAL", val)
        assert persistence_mod._batch_transactional() is False


# ── Router mode-default resolution ─────────────────────────────────────────


class TestRouterModeDefaultsRespectEnvGate:
    """``mode`` query param absent → router resolves via ``_batch_transactional``."""

    def test_no_mode_with_env_true_dispatches_to_atomic(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = {"atomic": 0, "partial": 0}

        def _fake_atomic(tenant: str, events: list[dict]) -> list:
            calls["atomic"] += 1
            return [({"status": 201, "cte_id": "x"}, 201) for _ in events]

        def _fake_single(tenant: str, event: dict):
            calls["partial"] += 1
            return ({"status": 201, "cte_id": "x"}, 201)

        monkeypatch.setattr(router_mod, "_ingest_batch_events_db_atomic", _fake_atomic)
        monkeypatch.setattr(router_mod, "_ingest_single_event", _fake_single)
        monkeypatch.setattr(router_mod, "_batch_transactional", lambda: True)
        monkeypatch.setattr(
            router_mod, "_resolve_authenticated_tenant",
            lambda request, x, y: "tenant-router",
        )

        import asyncio

        body = router_mod.BatchIngestRequest(events=[_make_event("LOT-1")])
        fake_request = MagicMock()
        resp = asyncio.run(
            router_mod.ingest_epcis_batch(
                request=fake_request, body=body, mode=None,
                x_tenant_id="tenant-router", x_regengine_api_key="k", _=None,
            )
        )
        assert resp.status_code == 201
        assert calls == {"atomic": 1, "partial": 0}

    def test_no_mode_with_env_false_dispatches_to_partial(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = {"atomic": 0, "partial": 0}

        def _fake_atomic(tenant: str, events: list[dict]) -> list:
            calls["atomic"] += 1
            return [({"status": 201, "cte_id": "x"}, 201) for _ in events]

        def _fake_single(tenant: str, event: dict):
            calls["partial"] += 1
            return ({"status": 201, "cte_id": "x"}, 201)

        monkeypatch.setattr(router_mod, "_ingest_batch_events_db_atomic", _fake_atomic)
        monkeypatch.setattr(router_mod, "_ingest_single_event", _fake_single)
        monkeypatch.setattr(router_mod, "_batch_transactional", lambda: False)
        monkeypatch.setattr(
            router_mod, "_resolve_authenticated_tenant",
            lambda request, x, y: "tenant-router",
        )

        import asyncio

        body = router_mod.BatchIngestRequest(events=[_make_event("LOT-2")])
        fake_request = MagicMock()
        resp = asyncio.run(
            router_mod.ingest_epcis_batch(
                request=fake_request, body=body, mode=None,
                x_tenant_id="tenant-router", x_regengine_api_key="k", _=None,
            )
        )
        assert resp.status_code == 201
        assert calls == {"atomic": 0, "partial": 1}
