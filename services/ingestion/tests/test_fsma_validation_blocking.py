"""Data-free checks for strict mode and malformed EPCIS rejection."""

import pytest
from app.epcis import persistence as persist_mod
from fastapi import HTTPException


def test_strict_mode_on_by_default(monkeypatch):
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
        assert persist_mod._fsma_strict_mode() is True


def test_empty_event_is_rejected_without_persistence():
    persist_mod._epcis_store.clear()
    persist_mod._epcis_idempotency_index.clear()

    with pytest.raises(HTTPException) as exc:
        persist_mod._ingest_single_event_fallback("", {})

    assert exc.value.status_code == 400
    assert persist_mod._epcis_store == {}
    assert persist_mod._epcis_idempotency_index == {}
