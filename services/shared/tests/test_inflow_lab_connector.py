from __future__ import annotations

import pytest

from services.shared.external_connectors.base import AuthType, ConnectorConfig
from services.shared.external_connectors.inflow_lab import InflowLabConnector
from services.shared.external_connectors.register_all import register_all_connectors
from services.shared.external_connectors.registry import get_connector_class


@pytest.mark.asyncio
async def test_inflow_lab_is_push_only_and_available() -> None:
    connector = InflowLabConnector(
        ConnectorConfig(
            connector_id="inflow_lab",
            display_name="Inflow Lab",
            category="developer",
            auth_type=AuthType.NONE,
        )
    )

    assert await connector.test_connection() is True
    assert await connector.fetch_events() == ([], None)


def test_inflow_lab_metadata_points_to_docs() -> None:
    connector = InflowLabConnector(
        ConnectorConfig(
            connector_id="inflow_lab",
            display_name="Inflow Lab",
            category="developer",
            auth_type=AuthType.NONE,
        )
    )

    info = connector.get_connector_info()

    assert info["id"] == "inflow_lab"
    assert info["slug"] == "inflow-lab"
    assert "inflow-lab" in info["aliases"]
    assert info["name"] == "Inflow Lab"
    assert info["category"] == "developer"
    assert info["auth_type"] == "none"
    assert info["docs_url"] == "/docs/connectors/inflow-lab"
    assert "shipping" in info["supported_cte_types"]


def test_inflow_lab_normalizes_regengine_shaped_event() -> None:
    connector = InflowLabConnector(
        ConnectorConfig(
            connector_id="inflow_lab",
            display_name="Inflow Lab",
            category="developer",
            auth_type=AuthType.NONE,
        )
    )

    event = connector.normalize_event(
        {
            "id": "evt_demo_001",
            "cte_type": "shipping",
            "traceability_lot_code": "LOT-001",
            "product_description": "Romaine Lettuce",
            "quantity": 12,
            "unit_of_measure": "cases",
            "timestamp": "2026-04-27T12:00:00Z",
            "location_name": "Demo DC",
            "kdes": {"ship_to_location": "Retailer #4"},
        }
    )

    ingest = event.to_ingest_dict()

    assert ingest["cte_type"] == "shipping"
    assert ingest["traceability_lot_code"] == "LOT-001"
    assert ingest["kdes"]["integration_source"] == "inflow-lab"
    assert ingest["kdes"]["source_event_id"] == "evt_demo_001"


def test_register_all_includes_inflow_lab() -> None:
    register_all_connectors()

    assert get_connector_class("inflow_lab") is InflowLabConnector
    assert get_connector_class("inflow-lab") is InflowLabConnector
