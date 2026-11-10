"""Buyer-facing requirement provenance, without retailer deadline claims.

Legal sections verified against eCFR Part 1 Subpart S, 2026-11-06:
https://www.ecfr.gov/current/title-21/part-1/subpart-S
The retailer overlay is the existing Albertsons ASN list in
supplier_readiness/shipping.py; it is never treated as a legal requirement.
"""

_SECTIONS = {
    "harvesting": "1.1325(a)",
    "cooling": "1.1325(b)",
    "initial_packing": "1.1330",
    "first_land_based_receiving": "1.1335",
    "shipping": "1.1340(a)",
    "receiving": "1.1345(a)",
    "transformation": "1.1350(a)",
}
_SHIPPING_PARAGRAPHS = {
    "traceability_lot_code": "1",
    "quantity": "2",
    "unit_of_measure": "2",
    "product_description": "3",
    "ship_to_location": "4",
    "ship_from_location": "5",
    "ship_date": "6",
    "tlc_source_reference": "7",
    "reference_document": "8",
}
_FIELD_LABELS = {
    "traceability_lot_code": "traceability lot code",
    "tlc_source_reference": "traceability lot code source reference",
    "receive_date": "receiving date",
    "input_lot_codes": "input traceability lot codes",
    "sscc": "serial shipping container code (SSCC)",
}
_BUYER_LABELS = {
    "gtin": "global trade item number (GTIN)",
    "po_number": "purchase order number",
    "sscc": "serial shipping container code (SSCC)",
    "product_date": "product date",
}


def missing_field_reason(cte: str, field: str, *, retailer: bool = False) -> str:
    label = _BUYER_LABELS.get(field, _FIELD_LABELS.get(field, field.replace("_", " ")))
    if retailer:
        if field not in _BUYER_LABELS:
            raise ValueError("Field is not in the Albertsons ASN overlay")
        return f"Missing {label}: asked for by the retailer (Albertsons ASN field list)"
    section = _SECTIONS.get(cte)
    if section is None:
        return f"Missing {label}: required by the application intake schema"
    if cte == "shipping" and field in _SHIPPING_PARAGRAPHS:
        section += f"({_SHIPPING_PARAGRAPHS[field]})"
    return f"Missing {label}: required by law (21 CFR {section})"
