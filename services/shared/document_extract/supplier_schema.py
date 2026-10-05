"""The FSMA 204 supplier-onboarding schema Extract fills from a PDF.

The bulk-upload parser (``services/admin/app/bulk_upload/parsers.py``)
accepts four record sections: ``facilities``, ``ftl_scopes``, ``tlcs`` and
``events``. This schema asks Extract for exactly those sections, with the
same canonical field names the CSV/JSON/XLSX paths use, so the result can be
fed through the parser's own ``_classify_row`` and the rest of the spine
(validate -> persist evidence) is unchanged.

Keep the schema flat and descriptive: Extract reads ``description`` text to
decide what belongs in a field. Bump ``SUPPLIER_SCHEMA_VERSION`` whenever a
field is added, removed or redefined; the version is recorded in evidence.
"""

from __future__ import annotations

from typing import Any

SUPPLIER_SCHEMA_VERSION = "1"

# Guard against a runaway array in a vendor response. A supplier onboarding
# packet is tens of rows, not thousands.
MAX_ROWS_PER_SECTION = 2000

CTE_TYPES = (
    "harvesting",
    "cooling",
    "initial_packing",
    "first_land_based_receiving",
    "shipping",
    "receiving",
    "transformation",
)

FACILITY_ROLES = ("Grower", "Packer", "Processor", "Distributor", "Importer", "Retailer")


def _string(description: str) -> dict[str, Any]:
    return {"type": "string", "description": description}


SUPPLIER_DOCUMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "description": (
        "FSMA 204 (Food Traceability Rule) records found in a supplier document: "
        "facilities, which Food Traceability List categories each facility handles, "
        "traceability lot codes, and critical tracking events. Leave a field empty when "
        "the document does not state it; never guess."
    ),
    "properties": {
        "facilities": {
            "type": "array",
            "description": "Each distinct facility, farm, plant, warehouse or business location named in the document.",
            "items": {
                "type": "object",
                "properties": {
                    "name": _string("Business or facility name exactly as written."),
                    "street": _string("Street address line (number and street)."),
                    "city": _string("City."),
                    "state": _string("Two-letter US state or province code, for example CA."),
                    "postal_code": _string("ZIP or postal code."),
                    "fda_registration_number": _string("FDA food facility registration number, if stated."),
                    "roles": {
                        "type": "array",
                        "description": (
                            "Supply-chain roles the document attributes to this facility. "
                            f"Use only these values: {', '.join(FACILITY_ROLES)}."
                        ),
                        "items": {"type": "string"},
                    },
                },
            },
        },
        "ftl_scopes": {
            "type": "array",
            "description": (
                "Food Traceability List (FTL) categories a facility grows, packs, ships or receives, "
                "for example leafy greens, tomatoes, fresh herbs, shell eggs, finfish."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "facility_name": _string("Facility name this scope belongs to (must match a facility name above)."),
                    "category_id": _string("FTL category identifier if the document gives a numeric or coded id."),
                    "category_name": _string("FTL category name as written, for example 'leafy greens'."),
                },
            },
        },
        "tlcs": {
            "type": "array",
            "description": "Traceability lot codes (TLC, lot number, lot code) assigned to products.",
            "items": {
                "type": "object",
                "properties": {
                    "tlc_code": _string("The traceability lot code exactly as written."),
                    "facility_name": _string("Facility that assigned the lot code, if stated."),
                    "product_description": _string("Product the lot code identifies, including variety and pack size."),
                    "status": _string("Lot status if stated: active, recalled or closed."),
                },
            },
        },
        "events": {
            "type": "array",
            "description": "Critical tracking events (CTEs): one per shipment, receipt, harvest, cooling, packing or transformation record.",
            "items": {
                "type": "object",
                "properties": {
                    "cte_type": _string(
                        "Event type. Use only these values: " + ", ".join(CTE_TYPES) + ". Map 'shipped' to shipping, "
                        "'received' to receiving, 'packed' to initial_packing, 'processed' to transformation."
                    ),
                    "event_time": _string(
                        "Date and time of the event in ISO 8601 (YYYY-MM-DDTHH:MM:SS); date only if no time is given."
                    ),
                    "facility_name": _string("Facility where the event happened or that recorded it."),
                    "tlc_code": _string("Traceability lot code of the product involved."),
                    "product_description": _string("Product description, variety and pack size."),
                    "quantity": _string("Quantity as a number string, for example 120."),
                    "unit_of_measure": _string("Unit for the quantity, for example cases, pounds, pallets."),
                    "source_facility_name": _string("For shipping/receiving: the facility the product came from."),
                    "destination_facility_name": _string("For shipping/receiving: the facility the product went to."),
                    "reference_document": _string("Reference document type and number: PO, BOL, invoice, ASN."),
                    "location_description": _string(
                        "Field, grow area, container or other location named for the event."
                    ),
                },
            },
        },
    },
}

_SECTION_RECORD_TYPES = (
    ("facilities", "facility"),
    ("ftl_scopes", "ftl_scope"),
    ("tlcs", "tlc"),
    ("events", "event"),
)


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def rows_from_extraction(data: Any) -> list[dict[str, Any]]:
    """Flatten an Extract result for this schema into parser rows.

    Each row carries ``record_type`` so the bulk-upload parser's
    ``_classify_row`` routes it without guessing. Blank fields are dropped,
    rows with nothing left are skipped, and each section is capped at
    :data:`MAX_ROWS_PER_SECTION`. Accepts the ``per_doc`` object or a list of
    them (``per_page``), merging sections across pages.
    """
    documents = data if isinstance(data, list) else [data]
    rows: list[dict[str, Any]] = []
    counts = {section: 0 for section, _ in _SECTION_RECORD_TYPES}
    for document in documents:
        if not isinstance(document, dict):
            continue
        for section, record_type in _SECTION_RECORD_TYPES:
            items = document.get(section)
            if not isinstance(items, list):
                continue
            for item in items:
                if counts[section] >= MAX_ROWS_PER_SECTION:
                    break
                if not isinstance(item, dict):
                    continue
                row = {key: value for key, value in item.items() if isinstance(key, str) and not _is_blank(value)}
                if not row:
                    continue
                row["record_type"] = record_type
                rows.append(row)
                counts[section] += 1
    return rows


__all__ = [
    "CTE_TYPES",
    "FACILITY_ROLES",
    "MAX_ROWS_PER_SECTION",
    "SUPPLIER_DOCUMENT_SCHEMA",
    "SUPPLIER_SCHEMA_VERSION",
    "rows_from_extraction",
]
