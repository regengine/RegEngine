"""Coverage for app/integration_webhook.py — generic ERP webhook receiver.

Locks:
- _extract_nested: flat key, dotted key, non-dict intermediate → None,
  missing key → None
- _apply_mapping: all fields mapped, missing fields excluded from
  canonical, extra fields go to kdes, no-extras case has no kdes key,
  None values filtered out
- Pydantic models — FieldMapping defaults, WebhookPayload, WebhookResponse
- POST /webhook/{connector_id}: happy path, missing cte_type → error,
  missing traceability_lot_code → error, custom field_mapping honored,
  default mapping when field_mapping omitted, exception inside
  _apply_mapping caught → error recorded

Issue: #1342
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import integration_webhook as iw
from app.integration_webhook import (
    FieldMapping,
    WebhookPayload,
    WebhookResponse,
    _apply_mapping,
    _extract_nested,
    router,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client():
    return TestClient(_app())


def _valid_event(**overrides):
    """Build a canonical event with all required fields."""
    base = {
        "cte_type": "receiving",
        "traceability_lot_code": "TLC1",
        "product_description": "Tomatoes",
        "quantity": 100,
        "unit_of_measure": "LB",
        "location_name": "Distribution Center",
        "timestamp": "2026-01-01T00:00:00Z",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# _extract_nested
# ---------------------------------------------------------------------------


class TestExtractNested:
    def test_flat_key(self):
        assert _extract_nested({"a": 1, "b": 2}, "a") == 1

    def test_dotted_path(self):
        data = {"header": {"doc_date": "2026-01-01"}}
        assert _extract_nested(data, "header.doc_date") == "2026-01-01"

    def test_deep_nesting(self):
        data = {"a": {"b": {"c": "deep"}}}
        assert _extract_nested(data, "a.b.c") == "deep"

    def test_non_dict_intermediate_returns_none(self):
        """A non-dict in the middle of the path short-circuits to None."""
        data = {"a": "not-a-dict"}
        assert _extract_nested(data, "a.b") is None

    def test_missing_terminal_returns_none(self):
        data = {"a": {"b": 1}}
        assert _extract_nested(data, "a.c") is None

    def test_missing_root_returns_none(self):
        assert _extract_nested({}, "missing") is None


# ---------------------------------------------------------------------------
# _apply_mapping
# ---------------------------------------------------------------------------


class TestApplyMapping:
    def test_all_default_fields_mapped(self):
        event = _valid_event()
        mapping = FieldMapping()
        result = _apply_mapping(event, mapping)

        assert result["cte_type"] == "receiving"
        assert result["traceability_lot_code"] == "TLC1"
        assert result["product_description"] == "Tomatoes"
        assert result["quantity"] == 100
        assert result["unit_of_measure"] == "LB"
        assert result["location_name"] == "Distribution Center"
        assert result["timestamp"] == "2026-01-01T00:00:00Z"
        assert "kdes" not in result  # No extra fields

    def test_missing_source_fields_excluded_from_canonical(self):
        """Fields absent from the source event are not added to canonical."""
        event = {"cte_type": "receiving", "traceability_lot_code": "TLC1"}
        result = _apply_mapping(event, FieldMapping())

        assert result == {"cte_type": "receiving", "traceability_lot_code": "TLC1"}
        assert "product_description" not in result

    def test_extra_fields_go_to_kdes(self):
        """Fields not in the mapping are carried over as KDEs."""
        event = _valid_event(
            purchase_order="PO-123",
            internal_ref="REF-456",
        )
        result = _apply_mapping(event, FieldMapping())

        assert "kdes" in result
        assert result["kdes"] == {"purchase_order": "PO-123", "internal_ref": "REF-456"}

    def test_none_values_filtered_out(self):
        """Source fields with None value are not copied into canonical."""
        event = {
            "cte_type": "receiving",
            "traceability_lot_code": "TLC1",
            "product_description": None,  # Should be filtered
            "custom_field": None,  # Should be filtered from kdes
            "real_kde": "value",
        }
        result = _apply_mapping(event, FieldMapping())

        assert "product_description" not in result
        assert result["kdes"] == {"real_kde": "value"}
        assert "custom_field" not in result.get("kdes", {})

    def test_custom_mapping_with_nested_paths(self):
        """Custom FieldMapping with dotted source paths."""
        event = {
            "header": {"event_type": "harvesting"},
            "lot": {"code": "LOT-42"},
            "body": {"description": "Kale"},
        }
        mapping = FieldMapping(
            cte_type="header.event_type",
            traceability_lot_code="lot.code",
            product_description="body.description",
        )
        result = _apply_mapping(event, mapping)

        assert result["cte_type"] == "harvesting"
        assert result["traceability_lot_code"] == "LOT-42"
        assert result["product_description"] == "Kale"

    def test_no_kdes_key_when_no_extras(self):
        """When every source field is in the mapping, no 'kdes' key is added."""
        event = {"cte_type": "receiving", "traceability_lot_code": "TLC1"}
        result = _apply_mapping(event, FieldMapping())
        assert "kdes" not in result


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TestPydanticModels:
    def test_field_mapping_defaults(self):
        m = FieldMapping()
        assert m.cte_type == "cte_type"
        assert m.traceability_lot_code == "traceability_lot_code"
        assert m.timestamp == "timestamp"

    def test_webhook_payload_accepts_empty_events(self):
        p = WebhookPayload(events=[])
        assert p.events == []
        assert p.field_mapping is None

    def test_webhook_response_defaults(self):
        r = WebhookResponse(received=0, mapped=0)
        assert r.errors == []


# ---------------------------------------------------------------------------
# POST /webhook/{connector_id}
# ---------------------------------------------------------------------------


class TestReceiveWebhook:
    def test_happy_path(self, client):
        r = client.post(
            "/api/v1/integrations/webhook/prod-pro",
            json={"events": [_valid_event(), _valid_event(traceability_lot_code="TLC2")]},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["received"] == 2
        assert body["mapped"] == 2
        assert body["errors"] == []

    def test_missing_cte_type_records_error(self, client):
        bad = _valid_event()
        del bad["cte_type"]
        r = client.post(
            "/api/v1/integrations/webhook/erp1",
            json={"events": [bad, _valid_event()]},
        )
        body = r.json()
        assert body["received"] == 2
        assert body["mapped"] == 1
        assert len(body["errors"]) == 1
        assert "missing cte_type" in body["errors"][0]
        assert "Event 0" in body["errors"][0]

    def test_missing_tlc_records_error(self, client):
        bad = _valid_event()
        del bad["traceability_lot_code"]
        r = client.post(
            "/api/v1/integrations/webhook/erp1",
            json={"events": [bad]},
        )
        body = r.json()
        assert body["received"] == 1
        assert body["mapped"] == 0
        assert len(body["errors"]) == 1
        assert "missing traceability_lot_code" in body["errors"][0]

    def test_custom_field_mapping_honored(self, client):
        """Caller supplies a mapping pointing to their internal field names."""
        event = {
            "EventType": "receiving",
            "LotNo": "TLC-X",
            "SKU": "Carrots",
        }
        r = client.post(
            "/api/v1/integrations/webhook/sap",
            json={
                "events": [event],
                "field_mapping": {
                    "cte_type": "EventType",
                    "traceability_lot_code": "LotNo",
                    "product_description": "SKU",
                    "quantity": "quantity",
                    "unit_of_measure": "unit_of_measure",
                    "location_name": "location_name",
                    "timestamp": "timestamp",
                },
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["mapped"] == 1
        assert body["errors"] == []

    def test_default_mapping_when_field_mapping_omitted(self, client):
        """Omitting field_mapping uses default canonical names."""
        r = client.post(
            "/api/v1/integrations/webhook/default",
            json={"events": [_valid_event()]},
        )
        assert r.status_code == 200
        assert r.json()["mapped"] == 1

    def test_mapping_exception_caught_as_error(self, client, monkeypatch):
        """An exception inside _apply_mapping is caught and recorded."""

        def _raise(event, mapping):
            raise RuntimeError("explode")

        monkeypatch.setattr(iw, "_apply_mapping", _raise)

        r = client.post(
            "/api/v1/integrations/webhook/bad",
            json={"events": [_valid_event()]},
        )
        body = r.json()
        assert body["received"] == 1
        assert body["mapped"] == 0
        assert len(body["errors"]) == 1
        assert "mapping error" in body["errors"][0]
        assert "explode" in body["errors"][0]

    def test_empty_events_list(self, client):
        r = client.post(
            "/api/v1/integrations/webhook/empty",
            json={"events": []},
        )
        body = r.json()
        assert body["received"] == 0
        assert body["mapped"] == 0
        assert body["errors"] == []


# ---------------------------------------------------------------------------
# Router surface
# ---------------------------------------------------------------------------


class TestRouterSurface:
    def test_route_registered(self):
        paths = {r.path for r in router.routes}
        assert "/api/v1/integrations/webhook/{connector_id}" in paths
