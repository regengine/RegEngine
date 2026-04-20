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
    "lot_#": "traceability_lot_code",
    "vendor_lot#": "traceability_lot_code",
    "vendor_lot": "traceability_lot_code",
    # Product
    "product_description": "product_description",
    "product": "product_description",
    "product_name": "product_description",
    "description": "product_description",
    "commodity": "product_description",
    "commodity_variety": "product_description",
    "commodity/variety": "product_description",
    "item_desc": "product_description",
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
    "wt": "quantity",
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
    "date_picked": "harvest_date",
    "pick_date": "harvest_date",
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
    "ship_dt": "ship_date",
    # Receive date
    "receive_date": "receive_date",
    "received_date": "receive_date",
    "date_received": "receive_date",
    "receiving_date": "receive_date",
    "receipt_date": "receive_date",
    "rcvd_dt": "receive_date",
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
    "dest": "ship_to_location",
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
    "bol#": "reference_document",
    "invoice": "reference_document",
    "invoice_number": "reference_document",
    "invoice_no": "reference_document",
    "po": "reference_document",
    "po_number": "reference_document",
    "purchase_order": "reference_document",
    "po#": "reference_document",
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

# CTE type VALUE aliases — normalize messy CTE type values to canonical names.
# Customers use all kinds of abbreviations and variations for CTE types.
_CTE_TYPE_ALIASES = {
    # Harvesting
    "harvest": "harvesting",
    "harvested": "harvesting",
    "pick": "harvesting",
    "picked": "harvesting",
    "h": "harvesting",
    # Cooling
    "cool": "cooling",
    "cooled": "cooling",
    "pre_cool": "cooling",
    "precool": "cooling",
    "c": "cooling",
    # Initial packing
    "packing": "initial_packing",
    "packed": "initial_packing",
    "pack": "initial_packing",
    "ip": "initial_packing",
    # First land-based receiving
    "flbr": "first_land_based_receiving",
    "first_receiver": "first_land_based_receiving",
    "landing": "first_land_based_receiving",
    "dock": "first_land_based_receiving",
    # Shipping
    "ship": "shipping",
    "shipped": "shipping",
    "shipment": "shipping",
    "dispatch": "shipping",
    "s": "shipping",
    # Receiving
    "receive": "receiving",
    "received": "receiving",
    "receipt": "receiving",
    "recv": "receiving",
    "rcv": "receiving",
    "r": "receiving",
    # Transformation
    "transform": "transformation",
    "transformed": "transformation",
    "process": "transformation",
    "processed": "transformation",
    "processing": "transformation",
    "production": "transformation",
    "mfg": "transformation",
    "manufacturing": "transformation",
    "t": "transformation",
}


# ---------------------------------------------------------------------------
# ERP-specific CSV column presets
# ---------------------------------------------------------------------------

_ERP_PRESETS: Dict[str, Dict[str, str]] = {
    "produce_pro": {
        "item_no": "traceability_lot_code",
        "item_desc": "product_description",
        "item_description": "product_description",
        "trans_type": "cte_type",
        "trans_date": "timestamp",
        "whse": "location_name",
        "warehouse": "location_name",
        "qty_shipped": "quantity",
        "qty_received": "quantity",
        "qty": "quantity",
        "uom": "unit_of_measure",
        "vendor_no": "location_name",
        "vendor_name": "location_name",
        "customer_no": "location_name",
        "bol_no": "reference_document",
        "po_no": "reference_document",
        "lot_no": "traceability_lot_code",
    },
    "sap_b1": {
        "docnum": "reference_document",
        "itemcode": "traceability_lot_code",
        "dscription": "product_description",
        "quantity": "quantity",
        "unitMsr": "unit_of_measure",
        "whscode": "location_name",
        "shiptocode": "location_name",
        "docdate": "timestamp",
        "batchnum": "traceability_lot_code",
        "cardname": "location_name",
    },
    "aptean": {
        "lot_number": "traceability_lot_code",
        "item_id": "traceability_lot_code",
        "item_name": "product_description",
        "transaction_type": "cte_type",
        "transaction_date": "timestamp",
        "facility": "location_name",
        "qty": "quantity",
        "unit": "unit_of_measure",
        "supplier": "location_name",
        "document_ref": "reference_document",
    },
}


def get_erp_presets() -> Dict[str, str]:
    """Return available ERP preset names with display labels."""
    return {
        "generic": "Generic / Auto-detect",
        "produce_pro": "Produce Pro",
        "sap_b1": "SAP Business One",
        "aptean": "Aptean (Freshlynx)",
    }


def _parse_csv_to_events(
    csv_text: str,
    *,
    erp_preset: str | None = None,
    track_normalizations: bool = False,
) -> List[Dict[str, Any]]:
    """Parse CSV text into a list of event dicts matching our JSON format.

    Supports flexible header naming — maps common aliases, abbreviations,
    and spreadsheet conventions to canonical field names.

    When track_normalizations=True, also returns normalization actions via
    a side-channel key "__normalizations__" on the first event (list of dicts).
    """
    # Build column map — start with defaults, merge ERP preset if specified
    col_map = dict(_CSV_COLUMN_MAP)
    if erp_preset and erp_preset in _ERP_PRESETS:
        for alias, canonical in _ERP_PRESETS[erp_preset].items():
            col_map.setdefault(alias.lower(), canonical)

    reader = csv.DictReader(io.StringIO(csv_text))
    events = []
    normalizations: List[Dict[str, Any]] = []
    header_aliases_logged: set = set()
    row_index = 0

    for row in reader:
        event: Dict[str, Any] = {"kdes": {}}
        for col, value in row.items():
            if not col or not value or not value.strip():
                continue
            col_lower = col.strip().lower().replace(" ", "_")

            # 1. Check top-level field map (includes ERP preset aliases)
            mapped = col_map.get(col_lower)
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
                        "reasoning": f"Column '{col.strip()}' is a common alias for the FSMA 204 field '{mapped}'. Renaming ensures consistent rule evaluation.",
                        "event_index": -1,
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
                        "reasoning": f"Column '{col.strip()}' maps to the KDE field '{kde_canonical}' required by FSMA 204 for rule evaluation.",
                        "event_index": -1,
                    })
                continue

            # 3. Unknown columns go into kdes as-is
            event["kdes"][col_lower] = value.strip()

        # Default timestamp if missing
        if "timestamp" not in event:
            event["timestamp"] = datetime.now(timezone.utc).isoformat()

        # Normalize CTE type value aliases (e.g., "receipt" → "receiving")
        if "cte_type" in event:
            raw_cte = event["cte_type"]
            cte_lower = raw_cte.strip().lower().replace(" ", "_").replace("-", "_")
            canonical_cte = _CTE_TYPE_ALIASES.get(cte_lower, cte_lower)
            if canonical_cte != cte_lower and track_normalizations:
                normalizations.append({
                    "field": "cte_type",
                    "original": raw_cte,
                    "normalized": canonical_cte,
                    "action_type": "cte_type_normalize",
                    "reasoning": f"CTE type '{raw_cte}' is not a canonical FSMA 204 type. Resolved to '{canonical_cte}' so CTE-specific rules (21 CFR 1.1310) can be applied.",
                    "event_index": row_index,
                })
            event["cte_type"] = canonical_cte
            events.append(event)
            row_index += 1

    # Attach normalizations to be retrieved by caller
    if track_normalizations and events:
        events[0]["__normalizations__"] = normalizations

    return events


def _collect_value_normalizations(
    raw_events: List[Dict[str, Any]],
    canonical_events: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Compare raw vs canonical events to find value-level normalizations.

    Detects UOM standardization, CTE type mapping, and quantity parsing.
    """
    normalizations: List[Dict[str, Any]] = []
    seen: set = set()

    for i, (raw, canonical) in enumerate(zip(raw_events, canonical_events)):
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
                    "reasoning": f"Unit '{raw_uom}' standardized to '{can_uom}' for consistent mass balance calculations across the supply chain.",
                    "event_index": i,
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
                    "reasoning": f"CTE type '{raw_cte}' resolved to canonical '{can_cte}' for FSMA 204 rule matching.",
                    "event_index": i,
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
