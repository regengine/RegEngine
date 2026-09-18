"""Connector normalizers report a missing quantity or unit as missing.

``CSVSFTPConnector``, ``FoodReadyConnector``, ``FoodDocsConnector`` and
``SafetyCultureConnector`` used to fill an absent quantity with ``1.0`` and an
absent unit with ``"units"``. ``"units"`` is in the ingest schema's accepted
vocabulary, so the fabricated value passed every downstream check
indistinguishably from a real one. The normalizers now carry ``None`` and the
ingest schema (``IngestEvent``: ``quantity`` gt=0, ``unit_of_measure``
required) rejects the event with a field-level error.
"""

from __future__ import annotations

import pytest

from services.shared.external_connectors.base import ConnectorConfig, NormalizedCTEEvent, _optional_float
from services.shared.external_connectors.csv_sftp import CSVSFTPConnector
from services.shared.external_connectors.food_safety import FoodDocsConnector, FoodReadyConnector
from services.shared.external_connectors.safetyculture import SafetyCultureConnector


def _config() -> ConnectorConfig:
    return ConnectorConfig(connector_id="c1", display_name="test", category="food_safety", tenant_id="t1")


@pytest.mark.parametrize(
    "value,expected",
    [(None, None), ("", None), ("  ", None), ("12", 12.0), ("1,200", 1200.0), (3, 3.0), ("lots", None)],
)
def test_optional_float_never_substitutes(value, expected):
    assert _optional_float(value) == expected


def test_to_ingest_dict_carries_none_through():
    event = NormalizedCTEEvent(
        cte_type="receiving",
        traceability_lot_code="LOT-1",
        product_description="Kale",
        quantity=None,
        unit_of_measure=None,
        timestamp="2026-04-17T00:00:00Z",
    )
    d = event.to_ingest_dict()
    assert d["quantity"] is None
    assert d["unit_of_measure"] is None


class TestCsvSftp:
    def _connector(self) -> CSVSFTPConnector:
        return CSVSFTPConnector(_config())

    def test_row_without_quantity_or_unit_is_not_one_unit(self):
        c = self._connector()
        mapping = {"tlc": "traceability_lot_code", "product": "product_description", "date": "timestamp"}
        event = c._row_to_event({"tlc": "LOT-1", "product": "Kale", "date": "2026-04-17"}, mapping, "drop.csv", 2)
        assert event is not None
        assert event.quantity is None
        assert event.unit_of_measure is None

    def test_row_values_are_carried_verbatim(self):
        c = self._connector()
        mapping = {"tlc": "traceability_lot_code", "qty": "quantity", "uom": "unit_of_measure"}
        event = c._row_to_event({"tlc": "LOT-1", "qty": "1,250", "uom": "lbs"}, mapping, "drop.csv", 2)
        assert event.quantity == 1250.0
        assert event.unit_of_measure == "lbs"

    def test_non_numeric_quantity_is_none_and_logged(self, caplog):
        c = self._connector()
        mapping = {"tlc": "traceability_lot_code", "qty": "quantity"}
        with caplog.at_level("WARNING", logger="connector-csv-sftp"):
            event = c._row_to_event({"tlc": "LOT-1", "qty": "twelve"}, mapping, "drop.csv", 5)
        assert event.quantity is None
        assert any("csv_row_quantity_invalid" in r.message for r in caplog.records)

    def test_normalize_event_dict_path(self):
        c = self._connector()
        event = c.normalize_event({"traceability_lot_code": "LOT-1", "timestamp": "2026-04-17T00:00:00Z"})
        assert event.quantity is None
        assert event.unit_of_measure is None


class TestFoodSafetyConnectors:
    @pytest.mark.parametrize("cls", [FoodReadyConnector, FoodDocsConnector])
    def test_missing_quantity_and_unit_stay_missing(self, cls):
        event = cls(_config()).normalize_event({"id": "r1", "lot_code": "LOT-1"})
        assert event.quantity is None
        assert event.unit_of_measure is None

    @pytest.mark.parametrize("cls", [FoodReadyConnector, FoodDocsConnector])
    def test_reported_quantity_and_unit_are_carried(self, cls):
        event = cls(_config()).normalize_event({"id": "r1", "lot_code": "LOT-1", "quantity": "40", "unit": "cases"})
        assert event.quantity == 40.0
        assert event.unit_of_measure == "cases"


class TestSafetyCulture:
    def test_audit_without_quantity_is_not_one_unit(self):
        c = SafetyCultureConnector(_config())
        event = c.normalize_event(
            {"audit_id": "a1", "template_id": "t", "audit_data": {"name": "Receiving check", "items": []}}
        )
        assert event.quantity is None
        assert event.unit_of_measure is None

    def test_audit_responses_are_carried(self, monkeypatch):
        c = SafetyCultureConnector(_config())
        monkeypatch.setattr(
            c,
            "_extract_kdes_from_responses",
            lambda raw: {"quantity": "18", "unit_of_measure": "cases", "lot_code": "LOT-1"},
        )
        event = c.normalize_event({"audit_id": "a1", "template_id": "t", "audit_data": {"name": "Receiving"}})
        assert event.quantity == 18.0
        assert event.unit_of_measure == "cases"
