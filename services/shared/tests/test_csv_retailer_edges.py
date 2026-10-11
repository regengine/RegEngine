"""Edge cases for CSV parsing and retailer normalization.

Covers the upload path used by the ingestion router
(``CSVSFTPConnector.parse_csv``) and the retailer ``normalize_event``
helpers: malformed or minimal input must produce skips or ``None``
fields, never an unhandled exception that turns into a 500.
"""

from __future__ import annotations

import pytest

from services.shared.external_connectors.base import ConnectorConfig
from services.shared.external_connectors.csv_sftp import CSVSFTPConnector
from services.shared.external_connectors.retailers import (
    CostcoConnector,
    KrogerConnector,
    WalmartGDSNConnector,
    WholeFoodsConnector,
)


def _csv_config(**extra) -> ConnectorConfig:
    return ConnectorConfig(
        connector_id="csv_sftp",
        display_name="CSV",
        category="developer",
        tenant_id="t1",
        extra=extra,
    )


def _retailer_config(connector_id: str = "retailer") -> ConnectorConfig:
    return ConnectorConfig(
        connector_id=connector_id,
        display_name=connector_id,
        category="retailer",
        tenant_id="t1",
        api_key="key",
    )


class TestParseCsvEdges:
    def test_headers_only_csv_returns_empty_instead_of_crashing(self):
        connector = CSVSFTPConnector(_csv_config())
        assert connector.parse_csv("lot_code,product\n", source_file="empty.csv") == []

    def test_unmapped_columns_become_kdes_with_source_metadata(self):
        connector = CSVSFTPConnector(_csv_config())
        events = connector.parse_csv(
            "lot_code,product,custom_field\nLOT-9,Kale,keepme\n",
            source_file="drop.csv",
        )
        assert len(events) == 1
        event = events[0]
        assert event.traceability_lot_code == "LOT-9"
        assert event.kdes["custom_field"] == "keepme"
        assert event.kdes["csv_source_file"] == "drop.csv"
        assert event.kdes["csv_row_number"] == 2

    def test_cte_alias_is_normalized(self):
        connector = CSVSFTPConnector(_csv_config())
        events = connector.parse_csv(
            "lot_code,event_type\nLOT-1,shipped\n",
            source_file="alias.csv",
        )
        assert events[0].cte_type == "shipping"

class TestRetailerNormalizeNeverCrashes:
    @pytest.mark.parametrize("cls", [KrogerConnector, WholeFoodsConnector, CostcoConnector])
    @pytest.mark.parametrize("bad_quantity", [None, "", "lots"])
    def test_bad_quantity_becomes_none_not_exception(self, cls, bad_quantity):
        connector = cls(_retailer_config())
        key = "quantity" if cls is KrogerConnector else "qty"
        event = connector.normalize_event({"lot": "L1", "product": "Kale", key: bad_quantity})
        assert event.quantity is None

    def test_walmart_bad_quantity_becomes_none_not_exception(self):
        connector = WalmartGDSNConnector(_retailer_config("walmart"))
        event = connector.normalize_event({"lotNumber": "L1", "quantity": "lots"})
        assert event.quantity is None

    def test_walmart_none_quantity_becomes_none_not_exception(self):
        connector = WalmartGDSNConnector(_retailer_config("walmart"))
        event = connector.normalize_event({"lotNumber": "L1", "quantity": None})
        assert event.quantity is None

    @pytest.mark.parametrize("cls", [KrogerConnector, WholeFoodsConnector, CostcoConnector])
    def test_absent_quantity_keeps_current_default(self, cls):
        """Characterizes the existing default (1.0) when the key is absent."""
        connector = cls(_retailer_config())
        field = "lot_number" if cls is KrogerConnector else "lot"
        event = connector.normalize_event({field: "L1", "product": "Kale"})
        assert event.quantity == 1.0

    def test_inflow_lab_bad_quantity_becomes_none_not_exception(self):
        from services.shared.external_connectors.inflow_lab import InflowLabConnector

        connector = InflowLabConnector(
            ConnectorConfig(
                connector_id="inflow_lab",
                display_name="Inflow Lab",
                category="developer",
                tenant_id="t1",
            )
        )
        for bad in (None, "lots"):
            event = connector.normalize_event(
                {"traceability_lot_code": "LOT-1", "quantity": bad}
            )
            assert event.quantity is None

    def test_inflow_lab_missing_unit_falls_back_to_each(self):
        from services.shared.external_connectors.inflow_lab import InflowLabConnector

        connector = InflowLabConnector(
            ConnectorConfig(
                connector_id="inflow_lab",
                display_name="Inflow Lab",
                category="developer",
                tenant_id="t1",
            )
        )
        event = connector.normalize_event(
            {"traceability_lot_code": "LOT-1", "unit_of_measure": None}
        )
        assert event.unit_of_measure == "each"

    async def test_kroger_connection_pending_with_api_key(self):
        connector = KrogerConnector(_retailer_config("kroger"))
        assert await connector.test_connection() is True
