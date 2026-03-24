"""FDA 204 Sortable Spreadsheet CSV exporter."""

from __future__ import annotations

import csv
import io
from pathlib import Path


FDA_COLUMNS = [
    "event_type", "event_date", "event_time",
    "traceability_lot_code", "product_description", "quantity", "unit_of_measure",
    "origin_gln", "origin_name", "origin_address",
    "destination_gln", "destination_name", "destination_address",
    "tlc_source_gln", "tlc_source_fda_reg",
    "reference_document_type", "reference_document_number",
    "harvest_date", "cooling_date", "pack_date", "ship_date",
    "receive_date", "transformation_date", "landing_date",
    "temperature", "carrier", "immediate_previous_source",
    "additional_kdes_json", "risk_flag",
]

FDA_HEADERS = [
    "Event Type", "Event Date", "Event Time",
    "Traceability Lot Code", "Product Description", "Quantity", "Unit of Measure",
    "Origin GLN", "Origin Name", "Origin Address",
    "Destination GLN", "Destination Name", "Destination Address",
    "TLC Source GLN", "TLC Source FDA Registration",
    "Reference Document Type", "Reference Document Number",
    "Harvest Date", "Cooling Date", "Pack Date", "Ship Date",
    "Receive Date", "Transformation Date", "Landing Date",
    "Temperature", "Carrier", "Immediate Previous Source",
    "Additional KDEs (JSON)", "Risk Flag",
]


class CSVExporter:
    """Export CTE records to FDA 204 Sortable Spreadsheet CSV format."""

    def export_string(self, records: list[dict]) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(FDA_HEADERS)
        for rec in records:
            row = [str(rec.get(col, "")) for col in FDA_COLUMNS]
            writer.writerow(row)
        return buf.getvalue()

    def export_file(self, records: list[dict], path: str | Path) -> str:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = self.export_string(records)
        path.write_text(content, encoding="utf-8")
        return str(path)
