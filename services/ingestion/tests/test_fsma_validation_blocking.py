"""Regression tests for #1239 — FSMA validation failure must block persistence.

Default strict mode (``FSMA_STRICT_MODE`` unset) refuses to persist an
event whose normalized form fails ``FSMAEvent`` validation — returns
HTTP 422. Advisory mode (``FSMA_STRICT_MODE=false``) still persists
but marks the row ``fsma_validation_status=failed`` with an error-
severity alert so FDA exports can filter it.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.epcis import persistence as persist_mod


# ---------------------------------------------------------------------------
# _fsma_strict_mode default
# ---------------------------------------------------------------------------


def test_strict_mode_on_by_default(monkeypatch):
    """FSMA_STRICT_MODE unset => strict."""
    monkeypatch.delenv("FSMA_STRICT_MODE", raising=False)
    assert persist_mod._fsma_strict_mode() is True


def test_strict_mode_off_when_explicitly_false(monkeypatch):
    monkeypatch.setenv("FSMA_STRICT_MODE", "false")
    assert persist_mod._fsma_strict_mode() is False

    monkeypatch.setenv("FSMA_STRICT_MODE", "0")
    assert persist_mod._fsma_strict_mode() is False


def test_strict_mode_various_truthy_values(monkeypatch):
    for value in ("1", "true", "yes", "on", "strict", "TRUE"):
        monkeypatch.setenv("FSMA_STRICT_MODE", value)
        assert persist_mod._fsma_strict_mode() is True, (
            f"FSMA_STRICT_MODE={value!r} should enable strict mode"
        )


# ---------------------------------------------------------------------------
# Fallback (in-memory) path blocks on FSMA failure in strict mode
# ---------------------------------------------------------------------------


TEST_TENANT_A = "tenant-a-00000000-0000-0000-0000-000000000001"
TEST_TENANT_B = "tenant-b-00000000-0000-0000-0000-000000000002"

# bizStep that maps under the new #1153 CTE map.
_SHIPPING_BIZSTEP = "urn:epcglobal:cbv:bizstep:shipping"


def _base_event(tlc: str, hour: int) -> dict:
    """EPCIS event that passes #1153 bizStep mapping. Quantity is required
    by #1249 — tests that set ``_validate_as_fsma_event`` to None still need
    to clear the quantity gate, so callers supply an explicit quantityList.
    """
    return {
        "type": "ObjectEvent",
        "eventTime": f"2026-04-17T{hour:02d}:00:00Z",
        "action": "OBSERVE",
        "bizStep": _SHIPPING_BIZSTEP,
        "epcList": ["urn:epc:id:sgtin:0614141.107346.2017"],
        "ilmd": {"fsma:traceabilityLotCode": tlc},
        "extension": {"quantityList": [{"quantity": 5.0, "uom": "KGM"}]},
    }


def test_fallback_persistence_raises_422_on_validation_failure(monkeypatch):
    """#1239: fallback path must raise 422, not silently store."""
    # Force strict mode (default).
    monkeypatch.delenv("FSMA_STRICT_MODE", raising=False)
    # Clear any leftover state.
    persist_mod._epcis_store.clear()
    persist_mod._epcis_idempotency_index.clear()

    event = _base_event("TLC-001", 12)

    # Force the FSMAEvent validator to return None (failure).
    with patch.object(persist_mod, "_validate_as_fsma_event", return_value=None):
        with pytest.raises(HTTPException) as exc:
            persist_mod._ingest_single_event_fallback(TEST_TENANT_A, event)

    assert exc.value.status_code == 422
    # #1148: store is tenant-scoped. An empty outer dict or an empty
    # tenant partition both satisfy "nothing was persisted".
    tenant_store = persist_mod._epcis_store.get(TEST_TENANT_A, {})
    assert len(tenant_store) == 0, "Tenant partition must remain empty on rejection"


def test_fallback_persistence_allows_event_when_strict_mode_off(monkeypatch):
    """Advisory mode: event is stored but marked failed."""
    monkeypatch.setenv("FSMA_STRICT_MODE", "false")
    persist_mod._epcis_store.clear()
    persist_mod._epcis_idempotency_index.clear()

    event = _base_event("TLC-002", 13)

    with patch.object(persist_mod, "_validate_as_fsma_event", return_value=None):
        payload, status = persist_mod._ingest_single_event_fallback(TEST_TENANT_A, event)

    assert status == 201
    tenant_store = persist_mod._epcis_store[TEST_TENANT_A]
    assert len(tenant_store) == 1
    # The stored record is explicitly marked as failed for downstream
    # FDA export filtering.
    stored = list(tenant_store.values())[0]
    assert stored["normalized_cte"]["fsma_validation_status"] == "failed"
    assert stored["tenant_id"] == TEST_TENANT_A
    # Alert severity must be "error" so dashboards can catch it.
    fsma_alerts = [a for a in stored["alerts"] if a["alert_type"] == "fsma_validation"]
    assert fsma_alerts, "An fsma_validation alert must be emitted"
    assert fsma_alerts[0]["severity"] == "error"


def test_fallback_persistence_passes_through_valid_event(monkeypatch):
    """Validation passing => event persists with status=passed."""
    monkeypatch.delenv("FSMA_STRICT_MODE", raising=False)
    persist_mod._epcis_store.clear()
    persist_mod._epcis_idempotency_index.clear()

    event = _base_event("TLC-003", 14)

    # Valid -> return any truthy dict
    with patch.object(
        persist_mod, "_validate_as_fsma_event", return_value={"ok": True}
    ):
        payload, status = persist_mod._ingest_single_event_fallback(TEST_TENANT_A, event)

    assert status == 201
    stored = list(persist_mod._epcis_store[TEST_TENANT_A].values())[0]
    assert stored["normalized_cte"]["fsma_validation_status"] == "passed"


# ---------------------------------------------------------------------------
# #1148 — fallback store must be tenant-scoped (no cross-tenant leak)
# ---------------------------------------------------------------------------


def test_fallback_store_tenant_isolation(monkeypatch):
    """Two tenants hitting the fallback must not see each other's events."""
    monkeypatch.delenv("FSMA_STRICT_MODE", raising=False)
    persist_mod._epcis_store.clear()
    persist_mod._epcis_idempotency_index.clear()

    event_a = _base_event("TLC-A", 10)
    event_b = _base_event("TLC-B", 11)

    with patch.object(
        persist_mod, "_validate_as_fsma_event", return_value={"ok": True}
    ):
        payload_a, _ = persist_mod._ingest_single_event_fallback(TEST_TENANT_A, event_a)
        payload_b, _ = persist_mod._ingest_single_event_fallback(TEST_TENANT_B, event_b)

    store_a = persist_mod._epcis_store[TEST_TENANT_A]
    store_b = persist_mod._epcis_store[TEST_TENANT_B]
    assert len(store_a) == 1
    assert len(store_b) == 1
    # Event ids must not appear in the other tenant's partition.
    assert payload_a["cte_id"] not in store_b
    assert payload_b["cte_id"] not in store_a
    # TLCs are tenant-local.
    assert list(store_a.values())[0]["normalized_cte"]["tlc"] == "TLC-A"
    assert list(store_b.values())[0]["normalized_cte"]["tlc"] == "TLC-B"


def test_fallback_store_per_tenant_fifo_cap(monkeypatch):
    """Per-tenant cap must evict FIFO; other tenants unaffected."""
    monkeypatch.delenv("FSMA_STRICT_MODE", raising=False)
    monkeypatch.setattr(persist_mod, "_EPCIS_FALLBACK_CAP_PER_TENANT", 3)
    persist_mod._epcis_store.clear()
    persist_mod._epcis_idempotency_index.clear()

    with patch.object(
        persist_mod, "_validate_as_fsma_event", return_value={"ok": True}
    ):
        for i in range(5):
            event = _base_event(f"TLC-A-{i}", 1 + i)
            persist_mod._ingest_single_event_fallback(TEST_TENANT_A, event)
        # Other tenant stays untouched.
        persist_mod._ingest_single_event_fallback(
            TEST_TENANT_B, _base_event("TLC-B", 8)
        )

    store_a = persist_mod._epcis_store[TEST_TENANT_A]
    store_b = persist_mod._epcis_store[TEST_TENANT_B]
    assert len(store_a) == 3, "Cap should evict oldest entries"
    assert len(store_b) == 1, "Cap is per-tenant, not global"
    # The oldest two (TLC-A-0, TLC-A-1) should be gone.
    tlcs_a = {rec["normalized_cte"]["tlc"] for rec in store_a.values()}
    assert tlcs_a == {"TLC-A-2", "TLC-A-3", "TLC-A-4"}
