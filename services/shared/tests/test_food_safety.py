"""Focused tests for the food safety connectors.

Covers ``FoodReadyConnector``, ``FoodDocsConnector`` and ``TiveConnector``
in ``services/shared/external_connectors/food_safety.py``: event
normalization, connection checks, mocked fetch paths, and connector
metadata. No network access; HTTP is mocked at ``safe_httpx_get_async``.
"""

from __future__ import annotations

import pytest

from services.shared.external_connectors.base import ConnectionStatus, ConnectorConfig
from services.shared.external_connectors.food_safety import (
    FoodDocsConnector,
    FoodReadyConnector,
    TiveConnector,
)


def _config(**overrides) -> ConnectorConfig:
    base = dict(
        connector_id="c1",
        display_name="test",
        category="food_safety",
        tenant_id="t1",
        api_key="key-123",
    )
    base.update(overrides)
    return ConnectorConfig(**base)


class _FakeResponse:
    def __init__(self, payload, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http %s" % self.status_code)

    def json(self):
        return self._payload


class TestFoodReadyNormalize:
    def test_temperature_log_maps_to_cooling_with_kdes(self):
        connector = FoodReadyConnector(_config())
        event = connector.normalize_event(
            {
                "id": "r1",
                "record_type": "temperature_log",
                "lot_code": "LOT-1",
                "product": "Milk",
                "quantity": "10",
                "unit": "cases",
                "temperature": "38",
                "temp_unit": "F",
                "created_at": "2026-01-02T03:04:05Z",
                "location": "Cooler A",
            }
        )
        assert event.cte_type == "cooling"
        assert event.traceability_lot_code == "LOT-1"
        assert event.quantity == 10.0
        assert event.unit_of_measure == "cases"
        assert event.kdes["temperature"] == "38"
        assert event.kdes["temperature_unit"] == "F"
        assert event.kdes["foodready_record_id"] == "r1"
        assert event.source_event_id == "r1"

    def test_unknown_record_type_defaults_to_receiving_with_lot_fallback(self):
        connector = FoodReadyConnector(_config())
        event = connector.normalize_event({"id": "r9", "record_type": "mystery"})
        assert event.cte_type == "receiving"
        assert event.traceability_lot_code == "FR-r9"
        assert event.quantity is None
        assert event.unit_of_measure is None

    def test_corrective_action_is_carried(self):
        connector = FoodReadyConnector(_config())
        event = connector.normalize_event(
            {"id": "r2", "record_type": "receiving_inspection", "corrective_action": "rejected pallet"}
        )
        assert event.cte_type == "receiving"
        assert event.kdes["corrective_action"] == "rejected pallet"


class TestFoodReadyConnectionAndFetch:
    async def test_missing_api_key_disconnects_without_network(self):
        connector = FoodReadyConnector(_config(api_key=""))
        assert await connector.test_connection() is False
        assert connector.status == ConnectionStatus.DISCONNECTED

    async def test_fetch_returns_events_and_cursor(self, monkeypatch):
        import services.shared.external_connectors.food_safety as fs_module

        async def fake_get(url, **kwargs):
            assert url.endswith("/records")
            return _FakeResponse(
                {
                    "records": [
                        {"id": "r1", "record_type": "receiving_inspection", "lot_code": "LOT-1"},
                    ],
                    "next_cursor": "cur-2",
                }
            )

        monkeypatch.setattr(fs_module, "safe_httpx_get_async", fake_get)
        connector = FoodReadyConnector(_config())
        events, cursor = await connector.fetch_events(limit=10)
        assert len(events) == 1
        assert events[0].traceability_lot_code == "LOT-1"
        assert cursor == "cur-2"

    async def test_fetch_error_returns_empty(self, monkeypatch):
        import services.shared.external_connectors.food_safety as fs_module

        async def boom(url, **kwargs):
            raise RuntimeError("network down")

        monkeypatch.setattr(fs_module, "safe_httpx_get_async", boom)
        connector = FoodReadyConnector(_config())
        events, cursor = await connector.fetch_events(limit=10)
        assert events == []
        assert cursor is None


class TestFoodDocs:
    def test_goods_receiving_maps_to_receiving(self):
        connector = FoodDocsConnector(_config())
        event = connector.normalize_event(
            {
                "id": "t1",
                "task_type": "goods_receiving",
                "lot_code": "LOT-7",
                "product_name": "Cheese",
                "quantity": "5",
                "unit": "cases",
                "completed_at": "2026-02-03T04:05:06Z",
                "location": "Dock 2",
            }
        )
        assert event.cte_type == "receiving"
        assert event.product_description == "Cheese"
        assert event.quantity == 5.0
        assert event.kdes["fooddocs_task_id"] == "t1"

    def test_temperature_check_carries_reading(self):
        connector = FoodDocsConnector(_config())
        event = connector.normalize_event({"id": "t2", "task_type": "temperature_check", "reading": "41"})
        assert event.cte_type == "cooling"
        assert event.kdes["temperature"] == "41"
        assert event.traceability_lot_code == "FD-t2"

    def test_unknown_task_type_defaults_to_receiving(self):
        connector = FoodDocsConnector(_config())
        event = connector.normalize_event({"id": "t3", "task_type": "something_new"})
        assert event.cte_type == "receiving"

    async def test_missing_api_key_disconnects_without_network(self):
        connector = FoodDocsConnector(_config(api_key=""))
        assert await connector.test_connection() is False
        assert connector.status == ConnectionStatus.DISCONNECTED

    async def test_present_api_key_is_pending_without_network(self):
        connector = FoodDocsConnector(_config())
        assert await connector.test_connection() is True
        assert connector.status == ConnectionStatus.PENDING

    async def test_fetch_error_returns_empty(self, monkeypatch):
        import services.shared.external_connectors.food_safety as fs_module

        async def boom(url, **kwargs):
            raise RuntimeError("network down")

        monkeypatch.setattr(fs_module, "safe_httpx_get_async", boom)
        connector = FoodDocsConnector(_config())
        events, cursor = await connector.fetch_events(limit=10)
        assert events == []
        assert cursor is None


class TestTive:
    def _shipment(self, **overrides):
        base = dict(
            id="s1",
            lot_code="LOT-9",
            product_name="Yogurt",
            quantity=20,
            unit="cases",
            ship_date="2026-03-01T10:00:00Z",
            delivery_date="2026-03-02T10:00:00Z",
            origin={"name": "Plant A", "gln": "111"},
            destination={"name": "DC B", "gln": "222"},
            carrier="FastFreight",
            tracking_number="TRK-1",
            tracker_id="tracker-1",
            temperature_summary={"min": 34, "max": 40, "avg": 37, "unit": "F", "excursion_count": 1},
        )
        base.update(overrides)
        return base

    def test_shipment_produces_shipping_and_receiving_pair(self):
        connector = TiveConnector(_config())
        events = connector._shipment_to_ctes(self._shipment())
        assert [e.cte_type for e in events] == ["shipping", "receiving"]
        ship, recv = events
        assert ship.traceability_lot_code == "LOT-9"
        assert recv.traceability_lot_code == "LOT-9"
        assert ship.kdes["max_temperature"] == 40
        assert recv.kdes["temperature_excursions"] == 1
        assert ship.kdes["carrier_name"] == "FastFreight"
        assert ship.location_gln == "111"
        assert recv.location_gln == "222"
        assert ship.source_event_id == "tive-ship-s1"
        assert recv.source_event_id == "tive-recv-s1"

    def test_shipment_without_dates_yields_no_events_and_fallback(self):
        connector = TiveConnector(_config())
        assert connector._shipment_to_ctes({"id": "s2"}) == []
        fallback = connector.normalize_event({"id": "s2"})
        assert fallback.cte_type == "shipping"

    async def test_missing_api_key_disconnects_without_network(self):
        connector = TiveConnector(_config(api_key=""))
        assert await connector.test_connection() is False
        assert connector.status == ConnectionStatus.DISCONNECTED


class TestConnectorInfo:
    @pytest.mark.parametrize(
        ("cls", "connector_id"),
        [
            (FoodReadyConnector, "foodready"),
            (FoodDocsConnector, "fooddocs"),
            (TiveConnector, "tive"),
        ],
    )
    def test_info_ids_and_cte_types(self, cls, connector_id):
        info = cls(_config()).get_connector_info()
        assert info["id"] == connector_id
        assert info["supported_cte_types"]
        assert info["auth_type"] == "api_key"

    def test_default_base_url_applied_when_empty(self):
        config = _config(base_url="")
        assert FoodReadyConnector(config).config.base_url == FoodReadyConnector.API_BASE
        assert FoodDocsConnector(_config(base_url="")).config.base_url == FoodDocsConnector.API_BASE
        assert TiveConnector(_config(base_url="")).config.base_url == TiveConnector.API_BASE
