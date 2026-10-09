"""Focused fallback/pure-helper coverage for ``app/epcis/persistence.py``.

Complements the broader ``test_epcis_persistence_1342`` suite with a
small hermetic file: pure helpers, the unsupported-CTE gate, tenant
isolation of the in-memory fallback store, and the idempotent fallback
ingest path with validation collaborators stubbed. No database, no
network.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app.epcis import persistence as persistence_mod  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_state() -> Any:
    persistence_mod._epcis_store.clear()
    persistence_mod._epcis_idempotency_index.clear()
    yield
    persistence_mod._epcis_store.clear()
    persistence_mod._epcis_idempotency_index.clear()


class TestSafeIso:
    def test_naive_datetime_assumes_utc(self) -> None:
        result = persistence_mod._safe_iso(datetime(2026, 5, 1, 12, 0, 0))
        assert result.endswith("+00:00")

    def test_aware_datetime_converts_to_utc(self) -> None:
        eastern = timezone(timedelta(hours=-5))
        result = persistence_mod._safe_iso(datetime(2026, 5, 1, 12, 0, 0, tzinfo=eastern))
        assert "17:00" in result
        assert result.endswith("+00:00")

    def test_string_passes_through(self) -> None:
        assert persistence_mod._safe_iso("2026-05-01T12:00:00Z") == "2026-05-01T12:00:00Z"

    def test_unexpected_type_falls_back_to_now(self) -> None:
        result = persistence_mod._safe_iso(None)
        assert "T" in result


class TestBuildKdeMap:
    def test_maps_product_and_locations(self) -> None:
        kde_map = persistence_mod._build_kde_map(
            {"type": "ObjectEvent"},
            {
                "product_id": "sku-1",
                "source_location_id": "0614141000012",
                "dest_location_id": "0614141000029",
            },
            "idem-1",
        )
        assert kde_map["product_id"] == "sku-1"
        assert kde_map["ship_from_gln"] == "0614141000012"
        assert kde_map["ship_to_gln"] == "0614141000029"
        assert kde_map["epcis_idempotency_key"] == "idem-1"
        assert kde_map["epcis_document_json"] == '{"type":"ObjectEvent"}'

    def test_omits_missing_keys(self) -> None:
        kde_map = persistence_mod._build_kde_map({"type": "ObjectEvent"}, {}, "idem-2")
        assert "product_id" not in kde_map
        assert "ship_from_gln" not in kde_map
        assert "ship_to_gln" not in kde_map


class TestParseEpcisDocument:
    def test_round_trips_stored_json(self) -> None:
        result = persistence_mod._parse_epcis_document({"epcis_document_json": '{"type":"ObjectEvent"}'}, {})
        assert result["type"] == "ObjectEvent"

    def test_invalid_json_synthesizes_from_normalized(self) -> None:
        result = persistence_mod._parse_epcis_document(
            {"epcis_document_json": "{broken"},
            {"epcis_event_type": "ObjectEvent", "lot_code": "LOT-9"},
        )
        assert result["type"] == "ObjectEvent"
        assert result["action"] == "OBSERVE"
        assert result["ilmd"]["cbvmda:lotNumber"] == "LOT-9"

    def test_transformation_event_carries_no_action(self) -> None:
        result = persistence_mod._parse_epcis_document({}, {"epcis_event_type": "TransformationEvent"})
        assert result["type"] == "TransformationEvent"
        assert "action" not in result


class TestUnsupportedCteType:
    def test_known_cte_returns_none(self) -> None:
        assert persistence_mod._unsupported_cte_type_error("shipping") is None

    def test_unknown_cte_returns_sorted_allowed_list(self) -> None:
        detail = persistence_mod._unsupported_cte_type_error("growing")
        assert detail is not None
        assert detail["error"] == "unsupported_cte_type"
        assert detail["allowed"] == sorted(detail["allowed"])
        assert "shipping" in detail["allowed"]


class TestFallbackStore:
    def test_tenants_are_isolated(self) -> None:
        persistence_mod._fallback_store_put("tenant-a", "evt-1", {"v": 1})
        assert "evt-1" not in persistence_mod._fallback_store_for("tenant-b")
        assert persistence_mod._fallback_store_for("tenant-a")["evt-1"] == {"v": 1}

    def test_fifo_eviction_when_over_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(persistence_mod, "_EPCIS_FALLBACK_CAP_PER_TENANT", 2)
        persistence_mod._fallback_store_put("t", "a", {})
        persistence_mod._fallback_store_put("t", "b", {})
        persistence_mod._fallback_store_put("t", "c", {})
        assert list(persistence_mod._fallback_store_for("t").keys()) == ["b", "c"]

    def test_idempotency_index_is_per_tenant(self) -> None:
        persistence_mod._fallback_idempotency_put("tenant-a", "key-1", "evt-1")
        assert persistence_mod._fallback_idempotency_for("tenant-b").get("key-1") is None
        assert persistence_mod._fallback_idempotency_for("tenant-a")["key-1"] == "evt-1"


class TestEnvFlags:
    def test_batch_transactional_defaults_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("EPCIS_BATCH_TRANSACTIONAL", raising=False)
        assert persistence_mod._batch_transactional() is True

    def test_batch_transactional_false_variant(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EPCIS_BATCH_TRANSACTIONAL", "false")
        assert persistence_mod._batch_transactional() is False

    def test_fallback_explicit_override_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALLOW_EPCIS_IN_MEMORY_FALLBACK", "true")
        assert persistence_mod._allow_in_memory_fallback() is True

    def test_strict_mode_prefers_new_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("STRICT_FSMA_VALIDATION", "false")
        monkeypatch.setenv("FSMA_STRICT_MODE", "true")
        assert persistence_mod._fsma_strict_mode() is False


def _stub_validation(monkeypatch: pytest.MonkeyPatch, fsma_ok: bool = True) -> None:
    monkeypatch.setattr(persistence_mod, "_validate_epcis", lambda event: [])
    monkeypatch.setattr(persistence_mod, "_event_idempotency_key", lambda event: "idem-key")
    monkeypatch.setattr(
        persistence_mod,
        "_normalize_epcis_to_cte",
        lambda event: {
            "tlc": "TLC-1",
            "event_time": "2026-01-01T00:00:00+00:00",
            "validation_status": "valid",
        },
    )
    monkeypatch.setattr(persistence_mod, "_extract_kdes", lambda event: [])
    monkeypatch.setattr(persistence_mod, "_compliance_alerts", lambda n, k: [])
    monkeypatch.setattr(persistence_mod, "_enforce_mandatory_gln_check_digits", lambda n: None)
    monkeypatch.setattr(persistence_mod, "_validate_epcis_glns", lambda n: [])
    monkeypatch.setattr(persistence_mod, "_validate_as_fsma_event", lambda n, t: fsma_ok)
    monkeypatch.setattr(persistence_mod, "_kde_completeness", lambda kdes: 1.0)


class TestIngestSingleEventFallback:
    def test_second_ingest_is_idempotent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_validation(monkeypatch)
        payload, status = persistence_mod._ingest_single_event_fallback("t", {"type": "ObjectEvent"})
        assert status == 201
        assert payload["idempotent"] is False

        payload2, status2 = persistence_mod._ingest_single_event_fallback("t", {"type": "ObjectEvent"})
        assert status2 == 200
        assert payload2["idempotent"] is True
        assert payload2["cte_id"] == payload["cte_id"]

    def test_idempotency_does_not_leak_across_tenants(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_validation(monkeypatch)
        payload_a, _ = persistence_mod._ingest_single_event_fallback("tenant-a", {"type": "ObjectEvent"})
        payload_b, status_b = persistence_mod._ingest_single_event_fallback("tenant-b", {"type": "ObjectEvent"})
        assert status_b == 201
        assert payload_b["cte_id"] != payload_a["cte_id"]

    def test_structural_validation_error_raises_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(persistence_mod, "_validate_epcis", lambda event: ["bad event"])
        with pytest.raises(HTTPException) as exc_info:
            persistence_mod._ingest_single_event_fallback("t", {})
        assert exc_info.value.status_code == 400

    def test_strict_fsma_failure_raises_422(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_validation(monkeypatch, fsma_ok=False)
        monkeypatch.setenv("STRICT_FSMA_VALIDATION", "true")
        monkeypatch.delenv("FSMA_STRICT_MODE", raising=False)
        with pytest.raises(HTTPException) as exc_info:
            persistence_mod._ingest_single_event_fallback("t", {"type": "ObjectEvent"})
        assert exc_info.value.status_code == 422


class TestPrepareEventEdgeCases:
    def test_missing_quantity_raises_422(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(persistence_mod, "_validate_epcis", lambda event: [])
        monkeypatch.setattr(persistence_mod, "_event_idempotency_key", lambda event: "k")
        monkeypatch.setattr(
            persistence_mod,
            "_normalize_epcis_to_cte",
            lambda event: {
                "event_type": "shipping",
                "tlc": "TLC-1",
                "event_time": "2026-01-01T00:00:00+00:00",
                "quantity": None,
            },
        )
        monkeypatch.setattr(persistence_mod, "_extract_kdes", lambda event: [])
        monkeypatch.setattr(persistence_mod, "_compliance_alerts", lambda n, k: [])
        monkeypatch.setattr(persistence_mod, "_enforce_mandatory_gln_check_digits", lambda n: None)
        monkeypatch.setattr(persistence_mod, "_validate_epcis_glns", lambda n: [])
        monkeypatch.setattr(persistence_mod, "_build_kde_map", lambda e, n, k: {"fsma_validation_status": "passed"})
        monkeypatch.setattr(persistence_mod, "_validate_as_fsma_event", lambda n, t: True)
        with pytest.raises(HTTPException) as exc_info:
            persistence_mod._prepare_event_for_persistence("t", {"type": "ObjectEvent"})
        assert exc_info.value.status_code == 422

    def test_unsupported_cte_type_raises_422(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(persistence_mod, "_validate_epcis", lambda event: [])
        monkeypatch.setattr(persistence_mod, "_event_idempotency_key", lambda event: "k")
        monkeypatch.setattr(persistence_mod, "_normalize_epcis_to_cte", lambda event: {"event_type": "growing"})
        with pytest.raises(HTTPException) as exc_info:
            persistence_mod._prepare_event_for_persistence("t", {"type": "ObjectEvent"})
        assert exc_info.value.status_code == 422

    def test_dispatcher_maps_unvalidated_value_error_to_422(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom(tenant_id: str, event: dict) -> Any:
            raise ValueError("E_EPCIS_UNVALIDATED")

        monkeypatch.setattr(persistence_mod, "_ingest_single_event_db", _boom)
        with pytest.raises(HTTPException) as exc_info:
            persistence_mod._ingest_single_event("t", {"type": "ObjectEvent"})
        assert exc_info.value.status_code == 422

    def test_dispatcher_returns_503_when_no_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom(tenant_id: str, event: dict) -> Any:
            raise RuntimeError("db down")

        monkeypatch.setattr(persistence_mod, "_ingest_single_event_db", _boom)
        monkeypatch.setattr(persistence_mod, "_allow_in_memory_fallback", lambda: False)
        with pytest.raises(HTTPException) as exc_info:
            persistence_mod._ingest_single_event("t", {"type": "ObjectEvent"})
        assert exc_info.value.status_code == 503

    def test_list_events_returns_empty_on_no_rows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sess = MagicMock()
        sess.execute.return_value.fetchall.return_value = []
        monkeypatch.setattr(persistence_mod, "get_db_safe", lambda: sess)
        assert persistence_mod._list_events_from_db("t", None, None, None) == []
        sess.close.assert_called_once()
