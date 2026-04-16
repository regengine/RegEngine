"""
Sandbox CSV parsing — map common CSV column headers to canonical field names.

Moved from sandbox_router.py.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4


# Map common CSV column headers to our internal field names.
# Aliases cover abbreviations, snake_case variants, and common spreadsheet headers.
_CSV_COLUMN_MAP = {
    # CTE type
    "cte_type": "cte_type",
    "event_type": "cte_type",
    "type": "cte_type",
    "cte": "cte_type",
    "event": "cte_type",
    # Traceability lot code
    "traceability_lot_code": "traceability_lot_code",
    "tlc": "traceability_lot_code",
    "lot_code": "traceability_lot_code",
    "lot": "traceability_lot_code",
    "lot_number": "traceability_lot_code",
    "lot_no": "traceability_lot_code",
    "lot_id": "traceability_lot_code",
    "trace_lot_code": "traceability_lot_code",
    "batch": "traceability_lot_code",
    "batch_number": "traceability_lot_code",
    "batch_no": "traceability_lot_code",
    "batch_id": "traceability_lot_code",
    # Product
    "product_description": "product_description",
    "product": "product_description",
    "product_name": "product_description",
    "description": "product_description",
    "commodity": "product_description",
    "commodity_variety": "product_description",
    "item": "product_description",
    "item_description": "product_description",
    "sku": "product_description",
    "sku_description": "product_description",
    "material": "product_description",
    "material_description": "product_description",
    # Quantity
    "quantity": "quantity",
    "qty": "quantity",
    "amount": "quantity",
    "count": "quantity",
    "units": "quantity",
    "weight": "quantity",
    "volume": "quantity",
    # Unit of measure
    "unit_of_measure": "unit_of_measure",
    "unit": "unit_of_measure",
    "uom": "unit_of_measure",
    "measure": "unit_of_measure",
    "unit_measure": "unit_of_measure",
    # Location GLN
    "location_gln": "location_gln",
    "gln": "location_gln",
    "facility_gln": "location_gln",
    "site_gln": "location_gln",
    # Location name
    "location_name": "location_name",
    "location": "location_name",
    "facility": "location_name",
    "facility_name": "location_name",
    "site": "location_name",
    "site_name": "location_name",
    "loc_name": "location_name",
    "plant": "location_name",
    "plant_name": "location_name",
    "warehouse": "location_name",
    # Timestamp
    "timestamp": "timestamp",
    "date": "timestamp",
    "event_date": "timestamp",
    "event_time": "timestamp",
    "event_timestamp": "timestamp",
    "datetime": "timestamp",
    "date_time": "timestamp",
    # Supplier / source
    "supplier": "location_name",
    "supplier_name": "location_name",
    "vendor": "location_name",
    "vendor_name": "location_name",
}

# Fields that go into kdes dict rather than top-level.
# Includes aliases — multiple header names map to the same KDE key.
_KDE_FIELD_ALIASES = {
    # Harvest
    "harvest_date": "harvest_date",
    "harvested": "harvest_date",
    "date_harvested": "harvest_date",
    "harvest_dt": "harvest_date",
    # Cooling
    "cooling_date": "cooling_date",
    "cooled_date": "cooling_date",
    "date_cooled": "cooling_date",
    "cool_date": "cooling_date",
    # Packing
    "packing_date": "packing_date",
    "pack_date": "packing_date",
    "date_packed": "packing_date",
    "packed_date": "packing_date",
    # Landing (seafood)
    "landing_date": "landing_date",
    "land_date": "landing_date",
    "date_landed": "landing_date",
    # Ship date
    "ship_date": "ship_date",
    "shipped_date": "ship_date",
    "date_shipped": "ship_date",
    "shipping_date": "ship_date",
    # Receive date
    "receive_date": "receive_date",
    "received_date": "receive_date",
    "date_received": "receive_date",
    "receiving_date": "receive_date",
    "receipt_date": "receive_date",
    # Transformation
    "transformation_date": "transformation_date",
    "transform_date": "transformation_date",
    "date_transformed": "transformation_date",
    # Ship-from
    "ship_from_location": "ship_from_location",
    "ship_from": "ship_from_location",
    "shipped_from": "ship_from_location",
    "from_location": "ship_from_location",
    "origin": "ship_from_location",
    "origin_location": "ship_from_location",
    "source_location": "ship_from_location",
    "from_facility": "ship_from_location",
    "from_site": "ship_from_location",
    # Ship-to
    "ship_to_location": "ship_to_location",
    "ship_to": "ship_to_location",
    "shipped_to": "ship_to_location",
    "to_location": "ship_to_location",
    "destination": "ship_to_location",
    "destination_location": "ship_to_location",
    "dest_location": "ship_to_location",
    "to_facility": "ship_to_location",
    "to_site": "ship_to_location",
    # GLNs
    "ship_from_gln": "ship_from_gln",
    "from_gln": "ship_from_gln",
    "origin_gln": "ship_from_gln",
    "ship_to_gln": "ship_to_gln",
    "to_gln": "ship_to_gln",
    "destination_gln": "ship_to_gln",
    "dest_gln": "ship_to_gln",
    # Receiving location
    "receiving_location": "receiving_location",
    "received_at": "receiving_location",
    "receive_location": "receiving_location",
    # Reference documents
    "reference_document": "reference_document",
    "ref_doc": "reference_document",
    "reference_doc": "reference_document",
    "document": "reference_document",
    "doc_number": "reference_document",
    "doc_no": "reference_document",
    "bol": "reference_document",
    "bol_number": "reference_document",
    "bill_of_lading": "reference_document",
    "invoice": "reference_document",
    "invoice_number": "reference_document",
    "invoice_no": "reference_document",
    "po": "reference_document",
    "po_number": "reference_document",
    "purchase_order": "reference_document",
    # Carrier / transport
    "carrier": "carrier",
    "carrier_name": "carrier",
    "transport": "carrier",
    "transport_reference": "carrier",
    "trucker": "carrier",
    "freight_carrier": "carrier",
    # Harvester
    "harvester_business_name": "harvester_business_name",
    "harvester": "harvester_business_name",
    "harvester_name": "harvester_business_name",
    "grower": "harvester_business_name",
    "grower_name": "harvester_business_name",
    "farm": "harvester_business_name",
    "farm_name": "harvester_business_name",
    # TLC source
    "tlc_source_reference": "tlc_source_reference",
    "tlc_source": "tlc_source_reference",
    "lot_code_source": "tlc_source_reference",
    "source_reference": "tlc_source_reference",
    "assigned_by": "tlc_source_reference",
    # Previous source
    "immediate_previous_source": "immediate_previous_source",
    "previous_source": "immediate_previous_source",
    "prev_source": "immediate_previous_source",
    "ips": "immediate_previous_source",
    "source": "immediate_previous_source",
    # Input TLCs (transformation)
    "input_traceability_lot_codes": "input_traceability_lot_codes",
    "input_tlcs": "input_traceability_lot_codes",
    "input_lots": "input_traceability_lot_codes",
    "input_lot_codes": "input_traceability_lot_codes",
    "source_lots": "input_traceability_lot_codes",
    "source_tlcs": "input_traceability_lot_codes",
    # Other
    "temperature": "temperature",
    "temp": "temperature",
    "field_name": "field_name",
    "field": "field_name",
    "growing_area": "field_name",
}

# Set of canonical KDE field names for quick lookup
_KDE_FIELDS = set(_KDE_FIELD_ALIASES.values())


def _parse_csv_to_events(
    csv_text: str,
    *,
    track_normalizations: bool = False,
) -> List[Dict[str, Any]]:
    """Parse CSV text into a list of event dicts matching our JSON format.

    Supports flexible header naming — maps common aliases, abbreviations,
    and spreadsheet conventions to canonical field names.

    When track_normalizations=True, also returns normalization actions via
    a side-channel key "__normalizations__" on the first event (list of dicts).
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    events = []
    normalizations: List[Dict[str, str]] = []
    header_aliases_logged: set = set()

    for row in reader:
        event: Dict[str, Any] = {"kdes": {}}
        for col, value in row.items():
            if not col or not value or not value.strip():
                continue
            col_lower = col.strip().lower().replace(" ", "_")

            # 1. Check top-level field map
            mapped = _CSV_COLUMN_MAP.get(col_lower)
            if mapped:
                if mapped == "quantity":
                    try:
                        event[mapped] = float(value.strip())
                    except ValueError:
                        event[mapped] = value.strip()
                else:
                    event[mapped] = value.strip()

                # Track header alias (once per unique alias)
                if track_normalizations and col_lower != mapped and col_lower not in header_aliases_logged:
                    header_aliases_logged.add(col_lower)
                    normalizations.append({
                        "field": mapped,
                        "original": col.strip(),
                        "normalized": mapped,
                        "action_type": "header_alias",
                    })
                continue

            # 2. Check KDE alias map → store under canonical KDE name
            kde_canonical = _KDE_FIELD_ALIASES.get(col_lower)
            if kde_canonical:
                val = value.strip()
                # Parse comma-separated input TLCs into a list
                if kde_canonical == "input_traceability_lot_codes" and "," in val:
                    val = [t.strip() for t in val.split(",") if t.strip()]
                event["kdes"][kde_canonical] = val

                # Track KDE alias (once per unique alias)
                if track_normalizations and col_lower != kde_canonical and col_lower not in header_aliases_logged:
                    header_aliases_logged.add(col_lower)
                    normalizations.append({
                        "field": kde_canonical,
                        "original": col.strip(),
                        "normalized": kde_canonical,
                        "action_type": "header_alias",
                    })
                continue

            # 3. Unknown columns go into kdes as-is
            event["kdes"][col_lower] = value.strip()

        # Default timestamp if missing
        if "timestamp" not in event:
            event["timestamp"] = datetime.now(timezone.utc).isoformat()

        if "cte_type" in event:
            events.append(event)

    # Attach normalizations to be retrieved by caller
    if track_normalizations and events:
        events[0]["__normalizations__"] = normalizations

    return events


def _collect_value_normalizations(
    raw_events: List[Dict[str, Any]],
    canonical_events: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    """Compare raw vs canonical events to find value-level normalizations.

    Detects UOM standardization, CTE type mapping, and quantity parsing.
    """
    normalizations: List[Dict[str, str]] = []
    seen: set = set()

    for raw, canonical in zip(raw_events, canonical_events):
        # UOM normalization
        raw_uom = (raw.get("unit_of_measure") or "").strip()
        can_uom = (canonical.get("unit_of_measure") or "").strip()
        if raw_uom and can_uom and raw_uom != can_uom:
            key = ("uom", raw_uom)
            if key not in seen:
                seen.add(key)
                normalizations.append({
                    "field": "unit_of_measure",
                    "original": raw_uom,
                    "normalized": can_uom,
                    "action_type": "uom_normalize",
                })

        # CTE type normalization
        raw_cte = (raw.get("cte_type") or "").strip()
        can_cte = (canonical.get("event_type") or "").strip()
        if raw_cte and can_cte and raw_cte != can_cte:
            key = ("cte", raw_cte)
            if key not in seen:
                seen.add(key)
                normalizations.append({
                    "field": "cte_type",
                    "original": raw_cte,
                    "normalized": can_cte,
                    "action_type": "cte_type_normalize",
                })

    return normalizations


def _normalize_for_rules(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a raw event dict into the canonical format expected by the rules engine.
    Maps webhook-style fields to canonical TraceabilityEvent field names.
    """
    kdes = dict(event.get("kdes", {}))
    event_type = event.get("cte_type", "")

    # Build facility references from available data
    from_facility = (
        event.get("location_gln")
        or kdes.get("ship_from_gln")
        or kdes.get("ship_from_location")
        or event.get("location_name")
    )
    to_facility = (
        kdes.get("ship_to_gln")
        or kdes.get("ship_to_location")
        or kdes.get("receiving_location")
    )

    if event_type == "shipping":
        from_facility = from_facility or event.get("location_name")
    elif event_type == "receiving":
        to_facility = to_facility or event.get("location_name") or event.get("location_gln")

    return {
        "event_id": str(uuid4()),
        "event_type": event_type,
        "traceability_lot_code": event.get("traceability_lot_code", ""),
        "product_reference": event.get("product_description", ""),
        "quantity": event.get("quantity"),
        "unit_of_measure": event.get("unit_of_measure", ""),
        "event_timestamp": event.get("timestamp", ""),
        "from_facility_reference": from_facility,
        "to_facility_reference": to_facility,
        "from_entity_reference": kdes.get("ship_from_entity") or kdes.get("harvester_business_name"),
        "to_entity_reference": kdes.get("ship_to_entity") or kdes.get("immediate_previous_source"),
        "transport_reference": kdes.get("carrier") or kdes.get("transport_reference"),
        "kdes": kdes,
    }
