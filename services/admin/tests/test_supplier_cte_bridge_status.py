"""Bridge-status surfacing for ``app/supplier_cte_service.py``.

Audit finding: supplier-to-canonical bridge failures were logged and the
supplier write committed anyway, so a 200 response could hide a missing
canonical row (invisible to FDA export and compliance scoring).

The bridge now returns ``"bridged" | "skipped" | "failed"``,
``_persist_supplier_cte_event`` propagates that status as a third tuple
item, and the write response carries it as ``canonical_bridge_status``.

These tests fail on the old code (the bridge returned ``None`` and
``_persist_supplier_cte_event`` returned a 2-tuple) and pass on the new.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_SERVICE_DIR = Path(__file__).resolve().parent.parent
_SERVICES_DIR = _SERVICE_DIR.parent
for _p in (_SERVICE_DIR, _SERVICES_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import app.supplier_cte_service as cte_service  # noqa: E402
from app.supplier_cte_service import (  # noqa: E402
    _bridge_to_canonical,
    _persist_supplier_cte_event,
)

TENANT_ID = uuid.UUID("00000000-0000-0000-0000-00000000b1d9")


class _RecordingStore:
    instances: list["_RecordingStore"] = []

    def __init__(self, session, dual_write: bool = True):
        self.persisted: list = []
        _RecordingStore.instances.append(self)

    def persist_event(self, canonical_event):
        self.persisted.append(canonical_event)
        return None


@pytest.fixture
def reset_recording_store():
    _RecordingStore.instances = []
    yield
    _RecordingStore.instances = []


def _patch_store(monkeypatch: pytest.MonkeyPatch, store_cls):
    import shared.canonical_persistence as cp_mod
    import shared.canonical_persistence.writer as cp_writer

    monkeypatch.setattr(cp_mod, "CanonicalEventStore", store_cls)
    monkeypatch.setattr(cp_writer, "CanonicalEventStore", store_cls)


def _mk_event(cte_type="shipping"):
    event = MagicMock()
    event.id = uuid.UUID("00000000-0000-0000-0000-000000000b01")
    event.cte_type = cte_type
    event.event_time = datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc)
    return event


def _mk_facility():
    facility = MagicMock()
    facility.id = uuid.UUID("00000000-0000-0000-0000-000000000b02")
    del facility.gln
    return facility


class TestBridgeReturnValues:
    def test_success_returns_bridged(self, monkeypatch, reset_recording_store):
        _patch_store(monkeypatch, _RecordingStore)
        status = _bridge_to_canonical(
            db=MagicMock(),
            tenant_id=TENANT_ID,
            event=_mk_event(),
            facility=_mk_facility(),
            tlc_code="TLC-BRIDGE-001",
            kde_data={"product_description": "Spinach", "quantity": 10, "unit_of_measure": "cases"},
        )
        assert status == "bridged"
        assert len(_RecordingStore.instances[0].persisted) == 1

    def test_missing_kdes_returns_skipped(self, monkeypatch, reset_recording_store):
        _patch_store(monkeypatch, _RecordingStore)
        status = _bridge_to_canonical(
            db=MagicMock(),
            tenant_id=TENANT_ID,
            event=_mk_event(),
            facility=_mk_facility(),
            tlc_code="TLC-BRIDGE-002",
            kde_data={"product_description": "Spinach"},
        )
        assert status == "skipped"
        assert _RecordingStore.instances == []

    def test_store_failure_returns_failed(self, monkeypatch, reset_recording_store):
        class _ExplodingStore:
            def __init__(self, *_args, **_kwargs):
                raise RuntimeError("canonical pipeline offline")

        _patch_store(monkeypatch, _ExplodingStore)
        status = _bridge_to_canonical(
            db=MagicMock(),
            tenant_id=TENANT_ID,
            event=_mk_event(),
            facility=_mk_facility(),
            tlc_code="TLC-BRIDGE-003",
            kde_data={"quantity": 5, "unit_of_measure": "cases"},
        )
        assert status == "failed"


def _mk_session_with_empty_chain():
    """Mock session: no existing lot, tenant exists, no previous event."""
    session = MagicMock()
    lot_result = MagicMock()
    lot_result.scalar_one_or_none.return_value = None
    lock_result = MagicMock()
    lock_result.scalar_one_or_none.return_value = TENANT_ID
    prev_result = MagicMock()
    prev_result.scalar_one_or_none.return_value = None
    session.execute.side_effect = [lot_result, lock_result, prev_result]
    return session


def _mk_user_and_facility():
    user = MagicMock()
    user.id = uuid.UUID("00000000-0000-0000-0000-000000000b03")
    facility = MagicMock()
    facility.id = uuid.UUID("00000000-0000-0000-0000-000000000b04")
    return user, facility


class TestPersistPropagatesBridgeStatus:
    @pytest.mark.parametrize("bridge_status", ["bridged", "skipped", "failed"])
    def test_persist_returns_bridge_status(self, monkeypatch, bridge_status):
        """``_persist_supplier_cte_event`` must surface the bridge outcome
        as a third tuple item so callers cannot commit silently."""
        monkeypatch.setattr(cte_service, "_bridge_to_canonical", lambda *_args, **_kwargs: bridge_status)
        user, facility = _mk_user_and_facility()
        event, lot, status = _persist_supplier_cte_event(
            _mk_session_with_empty_chain(),
            tenant_id=TENANT_ID,
            current_user=user,
            facility=facility,
            cte_type="shipping",
            tlc_code="TLC-BRIDGE-010",
            event_time=datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc),
            kde_data={"quantity": 7, "unit_of_measure": "cases"},
            obligation_ids=[],
        )
        assert status == bridge_status
        assert event is not None
        assert lot is not None
