"""Generate realistic FSMA 204 traceability datasets for drill scenarios."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Iterator


_PRODUCTS = [
    ("Romaine Lettuce", "case", "fresh-produce"),
    ("Baby Spinach", "bag", "fresh-produce"),
    ("Atlantic Salmon Fillet", "lb", "seafood"),
    ("Gulf Shrimp", "lb", "seafood"),
    ("Whole Milk", "gallon", "dairy"),
    ("Cheddar Cheese Block", "lb", "dairy"),
    ("Turkey Club Sandwich", "unit", "deli-prepared"),
    ("Caesar Salad Kit", "unit", "deli-prepared"),
    ("Large White Eggs", "dozen", "shell-eggs"),
]

_FACILITIES = [
    ("0614141000012", "Sunbright Farms", "123 Farm Rd, Salinas CA"),
    ("0614141000029", "Pacific Cold Storage", "456 Dock Ave, Oakland CA"),
    ("0614141000036", "Fresh Direct DC", "789 Warehouse Blvd, Phoenix AZ"),
    ("0614141000043", "Metro Grocers #117", "321 Main St, Denver CO"),
    ("0614141000050", "OceanHarvest Processing", "555 Harbor Dr, Seattle WA"),
    ("0614141000067", "Valley Dairy Co-op", "100 Milk Ln, Fresno CA"),
]

_CTE_TYPES = ["harvesting", "cooling", "packing", "shipping", "receiving", "transformation"]


class DatasetGenerator:
    """Generate clean, valid FSMA 204 CTE/KDE datasets."""

    def __init__(self, seed: int = 42):
        import random
        self._rng = random.Random(seed)

    def generate_supply_chain(
        self,
        num_lots: int = 5,
        chain_depth: int = 4,
        base_date: datetime | None = None,
    ) -> list[dict]:
        """Generate a multi-lot supply chain with linked CTE events.

        Returns a list of CTE records where each lot flows through
        ``chain_depth`` facilities with proper temporal ordering and
        upstream linkage.
        """
        base = base_date or datetime(2026, 3, 1, 8, 0, 0, tzinfo=timezone.utc)
        records: list[dict] = []

        for lot_idx in range(num_lots):
            product_name, uom, vertical = self._rng.choice(_PRODUCTS)
            tlc = f"TLC-{uuid.uuid4().hex[:10].upper()}"
            qty = self._rng.randint(10, 500)
            prev_source = None
            facilities = self._rng.sample(_FACILITIES, min(chain_depth, len(_FACILITIES)))

            for step, (gln, name, addr) in enumerate(facilities):
                cte_type = _CTE_TYPES[min(step, len(_CTE_TYPES) - 1)]
                event_dt = base + timedelta(days=lot_idx, hours=step * 6)

                dest_idx = step + 1 if step + 1 < len(facilities) else step
                dest_gln, dest_name, dest_addr = facilities[dest_idx]

                rec = {
                    "traceability_lot_code": tlc,
                    "event_type": cte_type,
                    "event_date": event_dt.strftime("%Y-%m-%d"),
                    "event_time": event_dt.strftime("%H:%M:%S"),
                    "product_description": product_name,
                    "quantity": qty,
                    "unit_of_measure": uom,
                    "origin_gln": gln,
                    "origin_name": name,
                    "origin_address": addr,
                    "destination_gln": dest_gln,
                    "destination_name": dest_name,
                    "destination_address": dest_addr,
                    "tlc_source_gln": gln,
                    "tlc_source_fda_reg": f"FDA-{gln[-5:]}",
                    "reference_document_type": "BOL",
                    "reference_document_number": f"BOL-{uuid.uuid4().hex[:8].upper()}",
                    "temperature": str(self._rng.randint(33, 41)) + "F",
                    "carrier": f"Carrier-{self._rng.randint(1, 20):03d}",
                    "immediate_previous_source": prev_source or "",
                    "vertical": vertical,
                }

                # Set CTE-specific date fields
                date_field_map = {
                    "harvesting": "harvest_date",
                    "cooling": "cooling_date",
                    "packing": "pack_date",
                    "shipping": "ship_date",
                    "receiving": "receive_date",
                    "transformation": "transformation_date",
                }
                if cte_type in date_field_map:
                    rec[date_field_map[cte_type]] = event_dt.strftime("%Y-%m-%d")

                records.append(rec)
                prev_source = gln

        return records

    def generate_single_lot(self, tlc: str | None = None) -> list[dict]:
        """Generate a single lot with full chain for targeted recall drills."""
        return self.generate_supply_chain(num_lots=1, chain_depth=4)

    def to_csv(self, records: list[dict]) -> str:
        """Serialize records to CSV string matching FDA 204 spreadsheet format."""
        from recall_drill.export.csv_exporter import CSVExporter
        return CSVExporter().export_string(records)
