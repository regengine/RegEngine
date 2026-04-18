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


def test_fallback_persistence_raises_422_on_validation_failure(monkeypatch):
    """#1239: fallback path must raise 422, not silently store."""
    # Force strict mode (default).
    monkeypatch.delenv("FSMA_STRICT_MODE", raising=False)
    # Clear any leftover state.
    persist_mod._epcis_store.clear()
    persist_mod._epcis_idempotency_index.clear()

    event = {
        "type": "ObjectEvent",
        "eventTime": "2026-04-17T12:00:00Z",
        "action": "OBSERVE",
        "bizStep": "shipping",
        "epcList": ["urn:epc:id:sgtin:0614141.107346.2017"],
        "ilmd": {"fsma:traceabilityLotCode": "TLC-001"},
    }

    # Force the FSMAEvent validator to return None (failure).
    with patch.object(persist_mod, "_validate_as_fsma_event", return_value=None):
        with pytest.raises(HTTPException) as exc:
            persist_mod._ingest_single_event_fallback(event)

    assert exc.value.status_code == 422
    assert persist_mod._epcis_store == {}, "Store must remain empty on rejection"
    assert persist_mod._epcis_idempotency_index == {}


def test_fallback_persistence_allows_event_when_strict_mode_off(monkeypatch):
    """Advisory mode: event is stored but marked failed."""
    monkeypatch.setenv("FSMA_STRICT_MODE", "false")
    persist_mod._epcis_store.clear()
    persist_mod._epcis_idempotency_index.clear()

    event = {
        "type": "ObjectEvent",
        "eventTime": "2026-04-17T13:00:00Z",
        "action": "OBSERVE",
        "bizStep": "shipping",
        "epcList": ["urn:epc:id:sgtin:0614141.107346.2017"],
        "ilmd": {"fsma:traceabilityLotCode": "TLC-002"},
    }

    with patch.object(persist_mod, "_validate_as_fsma_event", return_value=None):
        payload, status = persist_mod._ingest_single_event_fallback(event)

    assert status == 201
    assert len(persist_mod._epcis_store) == 1
    # The stored record is explicitly marked as failed for downstream
    # FDA export filtering.
    stored = list(persist_mod._epcis_store.values())[0]
    assert stored["normalized_cte"]["fsma_validation_status"] == "failed"
    # Alert severity must be "error" so dashboards can catch it.
    fsma_alerts = [a for a in stored["alerts"] if a["alert_type"] == "fsma_validation"]
    assert fsma_alerts, "An fsma_validation alert must be emitted"
    assert fsma_alerts[0]["severity"] == "error"


def test_fallback_persistence_passes_through_valid_event(monkeypatch):
    """Validation passing => event persists with status=passed."""
    monkeypatch.delenv("FSMA_STRICT_MODE", raising=False)
    persist_mod._epcis_store.clear()
    persist_mod._epcis_idempotency_index.clear()

    event = {
        "type": "ObjectEvent",
        "eventTime": "2026-04-17T14:00:00Z",
        "action": "OBSERVE",
        "bizStep": "shipping",
        "epcList": ["urn:epc:id:sgtin:0614141.107346.2017"],
        "ilmd": {"fsma:traceabilityLotCode": "TLC-003"},
    }

    # Valid -> return any truthy dict
    with patch.object(
        persist_mod, "_validate_as_fsma_event", return_value={"ok": True}
    ):
        payload, status = persist_mod._ingest_single_event_fallback(event)

    assert status == 201
    stored = list(persist_mod._epcis_store.values())[0]
    assert stored["normalized_cte"]["fsma_validation_status"] == "passed"
