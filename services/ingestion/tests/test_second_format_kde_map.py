"""Second format shipping KDE map cases T1 to T5 (synthetic fixtures only).

Locks the map in /workspace/rnd/second-format-kde-map.md against
services/ingestion/tests/fixtures. No partner file. SEL-549 hold stays.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

_ingestion_dir = Path(__file__).resolve().parent.parent
if str(_ingestion_dir) not in sys.path:
    sys.path.insert(0, str(_ingestion_dir))
_services_dir = _ingestion_dir.parent
if str(_services_dir) not in sys.path:
    sys.path.insert(0, str(_services_dir))

from app.webhook_models import REQUIRED_KDES_BY_CTE, WebhookCTEType
from shared.fsma_validation import validate_tlc

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ASN_EXPECTED = FIXTURES / "edi_corpus" / "asn_856.expected.json"
HARVEST_CSV = FIXTURES / "01_harvesting.csv"

SHIPPING_REQUIRED = list(REQUIRED_KDES_BY_CTE[WebhookCTEType.SHIPPING])


def _harvest_lot() -> str:
    with HARVEST_CSV.open(newline="") as fh:
        row = next(csv.DictReader(fh))
    return row["traceability_lot_code"]


def _asn_to_shipping_kdes(asn: dict, *, lot=None, tlc_source=None, extras=None) -> dict:
    """Map asn_856.expected.json shape onto REQUIRED shipping KDEs (map B)."""
    item = asn["line_items"][0]
    raw_date = asn.get("ship_date_raw") or ""
    ship_date = None
    if len(raw_date) == 8 and raw_date.isdigit():
        ship_date = f"{raw_date[0:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
    kdes = {
        "traceability_lot_code": lot if lot is not None else item.get("lot_number"),
        "product_description": item.get("product_description"),
        "quantity": item.get("quantity"),
        "unit_of_measure": item.get("unit_of_measure"),
        "ship_date": ship_date,
        "ship_from_location": asn.get("ship_from_name"),
        "ship_to_location": asn.get("ship_to_name"),
        "reference_document": (
            f"BM:{asn['reference_document_number']}"
            if asn.get("reference_document_number")
            else None
        ),
        "tlc_source_reference": tlc_source,
    }
    unmapped = {
        "ship_from_gln": asn.get("ship_from_gln"),
        "ship_to_gln": asn.get("ship_to_gln"),
        "asn_number": asn.get("asn_number"),
        "carrier": asn.get("carrier"),
    }
    if extras:
        unmapped.update(extras)
    return {"kdes": kdes, "unmapped_fields": unmapped}


def _gaps(kdes: dict) -> list[str]:
    missing = []
    for key in SHIPPING_REQUIRED:
        val = kdes.get(key)
        if val is None or val == "":
            missing.append(key)
    return missing


def test_t1_asn_856_expected_gaps() -> None:
    """T1: current asn_856 fixture is gap (missing TLC and TLC source)."""
    asn = json.loads(ASN_EXPECTED.read_text())
    assert asn["line_items"][0]["lot_number"] is None
    mapped = _asn_to_shipping_kdes(asn)
    gaps = _gaps(mapped["kdes"])
    assert "traceability_lot_code" in gaps
    assert "tlc_source_reference" in gaps
    # Present fields from fixture must not be dropped
    assert mapped["kdes"]["product_description"] == "ROMAINE-12CT"
    assert mapped["kdes"]["quantity"] == 200.0
    assert mapped["kdes"]["reference_document"] == "BM:BOL-9001"
    assert mapped["unmapped_fields"]["ship_from_gln"] == "6141410000014"


def test_t2_asn_plus_synthetic_lot_and_tlc_source_can_pass() -> None:
    """T2: asn_856 + harvest lot + synthetic TLC source fills required nine."""
    asn = json.loads(ASN_EXPECTED.read_text())
    lot = _harvest_lot()
    mapped = _asn_to_shipping_kdes(
        asn,
        lot=lot,
        tlc_source="https://id.gs1.org/414/6141410000014",
    )
    assert _gaps(mapped["kdes"]) == []
    lenient = validate_tlc(lot, strict=False)
    assert lenient.is_valid
    strict = validate_tlc(lot, strict=True)
    # Harvest style lot is lenient-only; GS1 mismatch is warning not failure
    assert not strict.is_valid


def test_t3_strict_style_tlc_no_format_warning() -> None:
    """T3: production style TLC passes lenient and strict format checks."""
    asn = json.loads(ASN_EXPECTED.read_text())
    lot = "00012345678901-LotA"
    mapped = _asn_to_shipping_kdes(
        asn,
        lot=lot,
        tlc_source="https://id.gs1.org/414/6141410000014",
    )
    assert _gaps(mapped["kdes"]) == []
    assert validate_tlc(lot, strict=False).is_valid
    assert validate_tlc(lot, strict=True).is_valid


def test_t4_fda_spreadsheet_shaped_shipping_row() -> None:
    """T4: FDA Shipping sheet shaped synthetic row maps to the same nine KDEs."""
    lot = _harvest_lot()
    row = {
        "Traceability Lot Code (assigned by Initial Packer / First Land Based Receiver / person who Transformed the Food)": lot,
        "Quantity": "200",
        "Unit of Measure": "cases",
        "Product Description - Product Name": "Organic Romaine Hearts",
        "Product Description - Brand Name (if applicable)": "Valley Fresh",
        "Shipping Date (mm/dd/yyyy)": "03/12/2026",
        "Location Description for the Immediate Subsequent Recipient - Business Name": "Metro Distribution Center",
        "Location Description for the Location from which you Shipped the Food - Business Name": "Valley Fresh Farms",
        "Traceability Lot Code Source Reference (may be provided instead of the TLC Source location description)": "https://id.gs1.org/414/6141410000014",
        "Reference Document Type": "BOL",
        "Reference Document Number": "BOL-9001",
        "PartnerInternalScore": "42",
    }
    kdes = {
        "traceability_lot_code": row[
            "Traceability Lot Code (assigned by Initial Packer / First Land Based Receiver / person who Transformed the Food)"
        ],
        "product_description": row["Product Description - Product Name"],
        "quantity": float(row["Quantity"]),
        "unit_of_measure": row["Unit of Measure"],
        "ship_date": "2026-03-12",
        "ship_from_location": row[
            "Location Description for the Location from which you Shipped the Food - Business Name"
        ],
        "ship_to_location": row[
            "Location Description for the Immediate Subsequent Recipient - Business Name"
        ],
        "reference_document": f"{row['Reference Document Type']}:{row['Reference Document Number']}",
        "tlc_source_reference": row[
            "Traceability Lot Code Source Reference (may be provided instead of the TLC Source location description)"
        ],
    }
    extras = {
        "Product Description - Brand Name (if applicable)": row[
            "Product Description - Brand Name (if applicable)"
        ],
        "PartnerInternalScore": row["PartnerInternalScore"],
    }
    assert _gaps(kdes) == []
    assert extras["PartnerInternalScore"] == "42"
    assert "Valley Fresh" in extras["Product Description - Brand Name (if applicable)"]


def test_t5_unknown_column_preserved() -> None:
    """T5: deliberate extra column is flagged and retained, never dropped."""
    asn = json.loads(ASN_EXPECTED.read_text())
    mapped = _asn_to_shipping_kdes(
        asn,
        lot=_harvest_lot(),
        tlc_source="https://id.gs1.org/414/6141410000014",
        extras={"PartnerInternalScore": "42", "REF*ZZ*CUSTOM": "KEEP-ME"},
    )
    assert "PartnerInternalScore" in mapped["unmapped_fields"]
    assert mapped["unmapped_fields"]["REF*ZZ*CUSTOM"] == "KEEP-ME"
    assert mapped["unmapped_fields"]["PartnerInternalScore"] == "42"
    assert _gaps(mapped["kdes"]) == []
