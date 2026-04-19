"""Built-in FSMA 204 rule seed data for initial database population."""

import json
import logging
from typing import Any, Dict, List
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("rules-engine")

FSMA_RULE_SEEDS: List[Dict[str, Any]] = [
    # --- KDE Presence Rules (per CTE type) ---
    {
        "title": "Receiving: TLC Source Reference Required",
        "description": "Receiving events must include the traceability lot code source reference identifying the entity that assigned the TLC",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["receiving"], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1345(b)(7)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.tlc_source_reference",
            "params": {"fields": ["kdes.tlc_source_reference", "kdes.tlc_source_gln", "from_entity_reference"]},
        },
        "failure_reason_template": "Receiving event missing {field_name} required by {citation}",
        "remediation_suggestion": "Request the traceability lot code source reference (GLN or business name) from your immediate supplier",
    },
    {
        "title": "Receiving: Immediate Previous Source Required",
        "description": "Receiving events must identify the immediate previous source of the food",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["receiving"], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1345(b)(5)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "from_entity_reference",
            "params": {"fields": ["from_entity_reference", "kdes.immediate_previous_source", "kdes.ship_from_location"]},
        },
        "failure_reason_template": "Receiving event missing {field_name} \u2014 cannot identify immediate previous source ({citation})",
        "remediation_suggestion": "Record the business name and location of the entity that shipped this food to you",
    },
    {
        "title": "Receiving: Reference Document Required",
        "description": "Receiving events must include a reference document number (BOL, invoice, etc.)",
        "severity": "warning",
        "category": "source_reference",
        "applicability_conditions": {"cte_types": ["receiving"], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1345(b)(6)",
        "evaluation_logic": {"type": "field_presence", "field": "kdes.reference_document"},
        "failure_reason_template": "Receiving event missing {field_name} (BOL, invoice, or purchase order number) required by {citation}",
        "remediation_suggestion": "Record the reference document type and number (e.g., BOL #12345, Invoice #INV-2026-001)",
    },
    {
        "title": "Receiving: Receive Date Required",
        "description": "Receiving events must include the date the food was received",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["receiving"], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1345(b)(2)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.receive_date",
            "params": {"fields": ["kdes.receive_date", "event_timestamp"]},
        },
        "failure_reason_template": "Receiving event missing {field_name} required by {citation}",
        "remediation_suggestion": "Record the date the food was received at your facility",
    },
    {
        "title": "Shipping: Ship-From Location Required",
        "description": "Shipping events must identify the location the food was shipped from",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["shipping"], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1340(b)(3)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "from_facility_reference",
            "params": {"fields": ["from_facility_reference", "kdes.ship_from_location", "kdes.ship_from_gln"]},
        },
        "failure_reason_template": "Shipping event missing {field_name} ({citation})",
        "remediation_suggestion": "Record the ship-from location (GLN preferred, or location description)",
    },
    {
        "title": "Shipping: Ship-To Location Required",
        "description": "Shipping events must identify the location the food was shipped to",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["shipping"], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1340(b)(4)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "to_facility_reference",
            "params": {"fields": ["to_facility_reference", "kdes.ship_to_location", "kdes.ship_to_gln"]},
        },
        "failure_reason_template": "Shipping event missing {field_name} ({citation})",
        "remediation_suggestion": "Record the ship-to location (GLN preferred, or location description)",
    },
    {
        "title": "Shipping: Ship Date Required",
        "description": "Shipping events must include the date the food was shipped",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["shipping"], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1340(b)(2)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.ship_date",
            "params": {"fields": ["kdes.ship_date", "event_timestamp"]},
        },
        "failure_reason_template": "Shipping event missing {field_name} ({citation})",
        "remediation_suggestion": "Record the date the food was shipped",
    },
    {
        "title": "Shipping: Reference Document Required",
        "description": "Shipping events must include a reference document number",
        "severity": "warning",
        "category": "source_reference",
        "applicability_conditions": {"cte_types": ["shipping"], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1340(b)(6)",
        "evaluation_logic": {"type": "field_presence", "field": "kdes.reference_document"},
        "failure_reason_template": "Shipping event missing {field_name} ({citation})",
        "remediation_suggestion": "Record the reference document type and number (BOL, invoice, or PO)",
    },
    {
        "title": "Harvesting: Harvest Date Required",
        "description": "Harvesting events must include the date of harvest",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["harvesting"], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1327(b)(2)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.harvest_date",
            "params": {"fields": ["kdes.harvest_date", "event_timestamp"]},
        },
        "failure_reason_template": "Harvesting event missing {field_name} ({citation})",
        "remediation_suggestion": "Record the date of harvest",
    },
    {
        "title": "Harvesting: Farm Location Required",
        "description": "Harvesting events must identify the farm or growing area location",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["harvesting"], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1327(b)(3)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "from_facility_reference",
            "params": {"fields": ["from_facility_reference", "kdes.location_name", "kdes.field_name"]},
        },
        "failure_reason_template": "Harvesting event missing {field_name} \u2014 cannot identify farm/growing area ({citation})",
        "remediation_suggestion": "Record the farm location description where food was harvested",
    },
    {
        "title": "Initial Packing: Packing Date Required",
        "description": "Initial packing events must include the date of packing",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["initial_packing"], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1335(b)(4)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.packing_date",
            "params": {"fields": ["kdes.packing_date", "event_timestamp"]},
        },
        "failure_reason_template": "Initial packing event missing {field_name} ({citation})",
        "remediation_suggestion": "Record the date of initial packing",
    },
    {
        "title": "Transformation: Transformation Date Required",
        "description": "Transformation events must include the date of transformation",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["transformation"], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1350(b)(4)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.transformation_date",
            "params": {"fields": ["kdes.transformation_date", "event_timestamp"]},
        },
        "failure_reason_template": "Transformation event missing {field_name} ({citation})",
        "remediation_suggestion": "Record the date of transformation",
    },
    {
        "title": "Cooling: Cooling Date Required",
        "description": "Cooling events must include the date of cooling",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["cooling"], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1330(b)(3)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.cooling_date",
            "params": {"fields": ["kdes.cooling_date", "event_timestamp"]},
        },
        "failure_reason_template": "Cooling event missing {field_name} ({citation})",
        "remediation_suggestion": "Record the date of cooling",
    },
    # --- Per-CTE KDE gap-fill (#1102): per 21 CFR 1.1325-1.1335 every
    # CTE needs enforcement of its mandated KDEs. Adding the rules the
    # audit flagged as missing: cooling location + temperature,
    # initial-packing location + harvest-location reference, and the
    # two first-land-based-receiving fields used for import tracking.
    {
        "title": "Cooling: Cooling Location Required",
        "description": "Cooling events must identify the location where cooling occurred",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["cooling"], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1330(b)(2)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.cooling_location",
            "params": {
                "fields": [
                    "kdes.cooling_location",
                    "kdes.location_name",
                    "from_facility_reference",
                ]
            },
        },
        "failure_reason_template": "Cooling event missing {field_name} \u2014 cannot identify where cooling occurred ({citation})",
        "remediation_suggestion": "Record the description or GLN of the location where the food was cooled",
    },
    {
        "title": "Cooling: Temperature Reading Required",
        "description": "Cooling events must include the achieved temperature (\u00b0F or \u00b0C) so thermal kill-step and cold-chain integrity can be audited",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["cooling"], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1330(b)(5)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.temperature",
            "params": {
                "fields": [
                    "kdes.temperature",
                    "kdes.temperature_celsius",
                    "kdes.temperature_fahrenheit",
                    "kdes.cooling_temperature",
                ]
            },
        },
        "failure_reason_template": "Cooling event missing {field_name} \u2014 temperature reading required for cold-chain audit ({citation})",
        "remediation_suggestion": "Record the temperature achieved during cooling in \u00b0F or \u00b0C",
    },
    # --- #1364: COOLING CTE was a checkbox.
    # Presence-only checks let a cooling event through with
    # ``cooling_temperature=80`` (°F) — clearly out of spec for a cold-chain
    # step — because no rule ever compared the number against a threshold.
    # The two rules below add:
    #   (1) a numeric_range gate that enforces the achieved cooling
    #       temperature is at or below the food-safety cold-chain ceiling,
    #       normalized to °C so rules can be written unit-agnostically
    #       (ingestion payloads arrive in both °F and °C);
    #   (2) a presence check on ``cooling_duration`` so the hold time
    #       required by 21 CFR \u00a71.1330(b)(5) can be audited (a
    #       temperature reading without a duration cannot prove the
    #       thermal kill-step or cold-hold was maintained).
    {
        "title": "Cooling: Achieved Temperature Within Cold-Chain Threshold",
        "description": (
            "The achieved cooling temperature must be at or below 5 \u00b0C / 41 \u00b0F "
            "(the FDA cold-chain ceiling). Evaluated via numeric_range so "
            "readings arriving in either unit are normalized before comparison."
        ),
        "severity": "critical",
        "category": "kde_threshold",
        "applicability_conditions": {"cte_types": ["cooling"], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1330(b)(5)",
        "evaluation_logic": {
            "type": "numeric_range",
            "field": "kdes.cooling_temperature",
            "params": {
                "max": 5,
                "unit": "celsius",
                "unit_field": "kdes.cooling_temperature_unit",
                # Default to Celsius when the payload omitted a unit —
                # raw numeric readings without a unit are rare but we
                # prefer the stricter interpretation (5 vs 41) over
                # failing the rule outright on legacy feeds.
                "assumed_unit": "celsius",
            },
        },
        "failure_reason_template": (
            "Cooling temperature {value} is above {max} \u00b0C ({citation}) "
            "\u2014 cold-chain ceiling exceeded"
        ),
        "remediation_suggestion": (
            "Re-verify the cooling temperature reading and unit. The achieved "
            "cold-chain temperature must be \u2264 5 \u00b0C (41 \u00b0F) per 21 CFR "
            "\u00a71.1330(b)(5). Record the unit alongside the value so the "
            "rules engine can normalize Fahrenheit readings."
        ),
    },
    {
        "title": "Cooling: Cooling Duration Required",
        "description": (
            "Cooling events must record the duration of the cooling hold so "
            "the thermal kill-step / cold-chain hold time can be audited "
            "alongside the achieved temperature"
        ),
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["cooling"], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1330(b)(5)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.cooling_duration",
            "params": {
                "fields": [
                    "kdes.cooling_duration",
                    "kdes.cooling_duration_minutes",
                    "kdes.cooling_hold_time",
                ]
            },
        },
        "failure_reason_template": (
            "Cooling event missing {field_name} \u2014 cannot audit hold time "
            "required by {citation}"
        ),
        "remediation_suggestion": (
            "Record the cooling duration (minutes) or cooling hold time so "
            "the thermal kill-step can be audited"
        ),
    },
    {
        "title": "Initial Packing: Packing Location Required",
        "description": "Initial-packing events must identify the location description of the packing facility",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["initial_packing"], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1335(b)(2)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.packing_location",
            "params": {
                "fields": [
                    "kdes.packing_location",
                    "kdes.location_name",
                    "from_facility_reference",
                ]
            },
        },
        "failure_reason_template": "Initial-packing event missing {field_name} \u2014 cannot identify packing facility ({citation})",
        "remediation_suggestion": "Record the description or GLN of the initial-packing location",
    },
    {
        "title": "Initial Packing: Harvest Location Reference Required",
        "description": "Initial-packing events must carry a reference to the originating harvest location so traceability back to the farm is preserved",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["initial_packing"], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1335(b)(3)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.harvest_location_ref",
            "params": {
                "fields": [
                    "kdes.harvest_location_ref",
                    "kdes.harvest_location",
                    "kdes.farm_reference",
                ]
            },
        },
        "failure_reason_template": "Initial-packing event missing {field_name} \u2014 cannot trace back to harvest location ({citation})",
        "remediation_suggestion": "Record the harvest location reference (GLN, farm name, or field identifier) this lot came from",
    },
    {
        "title": "First Land-Based Receiving: Entry Point Required",
        "description": "First land-based receiving events (FDA-regulated imports, aquatic catch landed from a vessel, etc.) must identify the point of entry",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["first_land_based_receiving"], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1325(c)(4)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.entry_point",
            "params": {
                "fields": [
                    "kdes.entry_point",
                    "kdes.port_of_entry",
                    "kdes.receiving_location",
                ]
            },
        },
        "failure_reason_template": "First land-based receiving event missing {field_name} \u2014 cannot identify point of entry ({citation})",
        "remediation_suggestion": "Record the port or land-based entry point where the food was received",
    },
    {
        "title": "First Land-Based Receiving: Source Vessel / Origin Required",
        "description": "First land-based receiving events must identify the source vessel or origin reference so the catch/shipment can be traced back to its pre-landing origin",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["first_land_based_receiving"], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1325(c)(5)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.source_vessel_name",
            "params": {
                "fields": [
                    "kdes.source_vessel_name",
                    "kdes.source_vessel",
                    "kdes.origin_reference",
                    "from_entity_reference",
                ]
            },
        },
        "failure_reason_template": "First land-based receiving event missing {field_name} \u2014 cannot identify source vessel or pre-landing origin ({citation})",
        "remediation_suggestion": "Record the source vessel name (for marine catch) or upstream origin reference for the incoming lot",
    },
    # --- Universal Rules (apply to all CTE types) ---
    {
        "title": "TLC Must Be Present",
        "description": "Every CTE must have a traceability lot code",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": [], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1310",
        "evaluation_logic": {"type": "field_presence", "field": "traceability_lot_code"},
        "failure_reason_template": "Event missing traceability lot code ({citation})",
        "remediation_suggestion": "Assign a traceability lot code to this event",
    },
    {
        "title": "Product Description Required",
        "description": "Every CTE must include a product description (commodity and variety)",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": [], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1310(b)(1)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "product_reference",
            "params": {"fields": ["product_reference", "kdes.product_description"]},
        },
        "failure_reason_template": "Event missing {field_name} (commodity and variety) ({citation})",
        "remediation_suggestion": "Record the commodity and variety of the food (e.g., 'Romaine Lettuce, Whole Head')",
    },
    {
        "title": "Quantity and Unit of Measure Required",
        "description": "Every CTE must include the quantity and unit of measure",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": [], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1310(b)(2)",
        "evaluation_logic": {"type": "field_presence", "field": "quantity"},
        "failure_reason_template": "Event missing quantity and unit of measure ({citation})",
        "remediation_suggestion": "Record the quantity and unit of measure for this event",
    },
    {
        "title": "Location Identifier Required",
        "description": "Every CTE must identify at least one facility location (GLN or description)",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": [], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1310(b)(3)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "from_facility_reference",
            "params": {"fields": ["from_facility_reference", "to_facility_reference", "kdes.location_name", "kdes.location_gln"]},
        },
        "failure_reason_template": "Event missing facility location identifier ({citation})",
        "remediation_suggestion": "Provide at least one location identifier: GLN (preferred) or location description",
    },
    # --- Identifier Format Rules ---
    {
        "title": "GLN Format Validation",
        "description": "If a GLN is provided, it must be exactly 13 digits with valid check digit",
        "severity": "warning",
        "category": "identifier_format",
        "applicability_conditions": {"cte_types": [], "ftl_scope": ["ALL"]},
        "citation_reference": "GS1 General Specifications \u00a73.4.2",
        "evaluation_logic": {
            "type": "field_format",
            "field": "from_facility_reference",
            "condition": "regex_if_present",
            "params": {"pattern": r"^\d{13}$|^[^0-9].*$|^$"},
        },
        "failure_reason_template": "Facility GLN '{field_name}' is not a valid 13-digit GS1 identifier",
        "remediation_suggestion": "Verify the GLN is exactly 13 digits with a valid GS1 check digit",
    },
    # --- Lot Linkage Rules ---
    {
        "title": "Shipping: TLC Source Reference Required",
        "description": "Shipping events must include TLC source reference identifying who assigned the lot code",
        "severity": "warning",
        "category": "lot_linkage",
        "applicability_conditions": {"cte_types": ["shipping"], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1340(b)(7)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.tlc_source_reference",
            "params": {"fields": ["kdes.tlc_source_reference", "kdes.tlc_source_gln"]},
        },
        "failure_reason_template": "Shipping event missing TLC source reference ({citation}) \u2014 cannot trace who assigned the lot code",
        "remediation_suggestion": "Record the GLN or business name of the entity that assigned the traceability lot code",
    },
    {
        "title": "Transformation: Input TLCs Required",
        "description": "Transformation events must list all input traceability lot codes that were transformed",
        "severity": "critical",
        "category": "lot_linkage",
        "applicability_conditions": {"cte_types": ["transformation"], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1350(a)(4)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.input_traceability_lot_codes",
            "params": {"fields": ["kdes.input_traceability_lot_codes", "kdes.input_tlcs"]},
        },
        "failure_reason_template": "Transformation event missing input TLCs ({citation}) \u2014 cannot link new lot to source lots",
        "remediation_suggestion": "List all input traceability lot codes that were combined or transformed into this new lot",
    },
    # --- Record Completeness Rules ---
    {
        "title": "Reference Document Required for All CTEs",
        "description": "All CTE types require at least one reference document (BOL, invoice, PO, production record)",
        "severity": "warning",
        "category": "source_reference",
        "applicability_conditions": {"cte_types": [], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1310(c)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.reference_document",
            "params": {"fields": ["kdes.reference_document", "transport_reference"]},
        },
        "failure_reason_template": "Event missing reference document \u2014 no BOL, invoice, or purchase order recorded ({citation})",
        "remediation_suggestion": "Record at least one reference document: bill of lading, invoice, purchase order, or production record",
    },
    {
        "title": "First Land-Based Receiving: Landing Date Required",
        "description": "First land-based receiving events for seafood must include the landing date",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["first_land_based_receiving"], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1325(b)(4)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.landing_date",
            "params": {"fields": ["kdes.landing_date", "event_timestamp"]},
        },
        "failure_reason_template": "First land-based receiving event missing {field_name} ({citation})",
        "remediation_suggestion": "Record the date the seafood was landed (date vessel arrived at port)",
    },
    {
        "title": "Harvesting: Commodity and Variety Required",
        "description": "Harvesting events must identify the commodity and variety of food harvested",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["harvesting"], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1327(b)(1)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "product_reference",
            "params": {"fields": ["product_reference", "kdes.product_description", "kdes.commodity"]},
        },
        "failure_reason_template": "Harvesting event missing commodity and variety ({citation})",
        "remediation_suggestion": "Record the commodity and variety of the food harvested (e.g., 'Romaine Lettuce')",
    },
    {
        "title": "Receiving: Receiving Location Required",
        "description": "Receiving events must identify the location where food was received",
        "severity": "critical",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["receiving"], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1345(b)(4)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "to_facility_reference",
            "params": {"fields": ["to_facility_reference", "kdes.receiving_location", "kdes.location_name"]},
        },
        "failure_reason_template": "Receiving event missing receiving location ({citation})",
        "remediation_suggestion": "Record the location description where food was received (GLN preferred)",
    },
    {
        "title": "Initial Packing: Harvester Business Name Required",
        "description": "Initial packing events must identify the harvester business name and phone number",
        "severity": "warning",
        "category": "kde_presence",
        "applicability_conditions": {"cte_types": ["initial_packing"], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1335(b)(8)",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "kdes.harvester_business_name",
            "params": {"fields": ["kdes.harvester_business_name", "from_entity_reference"]},
        },
        "failure_reason_template": "Initial packing event missing harvester business name ({citation})",
        "remediation_suggestion": "Record the harvester's business name and phone number",
    },
    # --- Relational Rules (cross-event validation) ---
    {
        "title": "Temporal Order: CTE Chronology Must Be Causal",
        "description": "CTE events for the same TLC must follow supply chain lifecycle order \u2014 harvesting before cooling before packing before shipping before receiving",
        "severity": "critical",
        "category": "temporal_ordering",
        "applicability_conditions": {
            "cte_types": ["shipping", "receiving", "transformation", "initial_packing", "cooling"],
            "ftl_scope": ["ALL"],
        },
        "citation_reference": "21 CFR \u00a71.1310",
        "evaluation_logic": {"type": "temporal_order"},
        "failure_reason_template": "Chronology paradox: {event_type} event timestamp violates supply chain lifecycle order for this TLC ({citation})",
        "remediation_suggestion": "Verify event timestamps \u2014 a later-stage CTE cannot occur before an earlier-stage CTE for the same traceability lot code",
    },
    {
        "title": "Identity Consistency: Product Must Not Change for Same TLC",
        "description": "The product description must remain consistent across all CTEs for the same traceability lot code (excluding transformation, which legitimately creates new products)",
        "severity": "warning",
        "category": "lot_linkage",
        "applicability_conditions": {
            "cte_types": ["harvesting", "cooling", "initial_packing", "first_land_based_receiving", "shipping", "receiving"],
            "ftl_scope": ["ALL"],
        },
        "citation_reference": "21 CFR \u00a71.1310(a)",
        "evaluation_logic": {"type": "identity_consistency"},
        "failure_reason_template": "Product identity changed for TLC: {event_type} event has a different product than prior events ({citation})",
        "remediation_suggestion": "Verify the product description matches across all events for this traceability lot code. If the product was legitimately transformed, use a transformation event",
    },
    {
        "title": "Mass Balance: Output Cannot Exceed Input for Same TLC",
        "description": "Total shipped/output quantity for a TLC cannot exceed total received/input quantity (within tolerance)",
        "severity": "critical",
        "category": "quantity_consistency",
        "applicability_conditions": {"cte_types": ["shipping", "transformation"], "ftl_scope": ["ALL"]},
        "citation_reference": "21 CFR \u00a71.1310",
        "evaluation_logic": {
            "type": "mass_balance",
            "params": {"tolerance_percent": 1.0},
        },
        "failure_reason_template": "Mass balance violation: output quantity exceeds input quantity for this TLC ({citation})",
        "remediation_suggestion": "Verify quantities \u2014 you cannot ship more than was received/harvested for the same traceability lot code. Check for data entry errors or missing input events",
    },
    # --- FTL Classification Rules (#1346) ---
    # This rule is intentionally scoped to NON_FTL so it fires on events
    # whose product is NOT on the FTL — ensuring we surface the gap
    # rather than silently stamp non-FTL events compliant.
    {
        "title": "FTL Classification: Product Must Be Classified",
        "description": (
            "Every event must carry an FTL classification signal "
            "(ftl_covered flag or ftl_category/product.category string) so "
            "the rules engine can determine whether FSMA 204 requirements apply"
        ),
        "severity": "critical",
        "category": "ftl_scoping",
        "applicability_conditions": {"cte_types": [], "ftl_scope": ["NON_FTL"]},
        "citation_reference": "21 CFR \u00a71.1300",
        "evaluation_logic": {
            "type": "multi_field_presence",
            "field": "ftl_covered",
            "params": {"fields": ["ftl_covered", "kdes.ftl_covered", "kdes.ftl_category", "product.category", "product_category"]},
        },
        "failure_reason_template": (
            "Event missing FTL classification \u2014 cannot determine whether "
            "FSMA 204 recordkeeping rules apply to this product ({citation})"
        ),
        "remediation_suggestion": (
            "Record ftl_covered (true/false) or the product's FTL category "
            "on every CTE so the compliance stamp only applies where required"
        ),
    },
]


def seed_rule_definitions(session: Session) -> int:
    """
    Seed the rule_definitions table with the built-in FSMA rules.

    Idempotent — skips rules that already exist (matched by title).
    Returns count of newly inserted rules.
    """
    inserted = 0
    for rule_data in FSMA_RULE_SEEDS:
        existing = session.execute(
            text("SELECT rule_id FROM fsma.rule_definitions WHERE title = :title"),
            {"title": rule_data["title"]},
        ).fetchone()

        if existing:
            continue

        rule_id = str(uuid4())
        session.execute(
            text("""
                INSERT INTO fsma.rule_definitions (
                    rule_id, title, description, severity, category,
                    applicability_conditions, citation_reference,
                    evaluation_logic, failure_reason_template,
                    remediation_suggestion
                ) VALUES (
                    :rule_id, :title, :description, :severity, :category,
                    CAST(:applicability AS jsonb), :citation,
                    CAST(:logic AS jsonb), :failure_template,
                    :remediation
                )
            """),
            {
                "rule_id": rule_id,
                "title": rule_data["title"],
                "description": rule_data.get("description"),
                "severity": rule_data["severity"],
                "category": rule_data["category"],
                "applicability": json.dumps(rule_data.get("applicability_conditions", {})),
                "citation": rule_data.get("citation_reference"),
                "logic": json.dumps(rule_data["evaluation_logic"]),
                "failure_template": rule_data["failure_reason_template"],
                "remediation": rule_data.get("remediation_suggestion"),
            },
        )

        # Audit log
        session.execute(
            text("""
                INSERT INTO fsma.rule_audit_log (rule_id, action, new_values, changed_by)
                VALUES (:rule_id, 'created', CAST(:values AS jsonb), 'system_seed')
            """),
            {
                "rule_id": rule_id,
                "values": json.dumps({"title": rule_data["title"], "severity": rule_data["severity"]}),
            },
        )

        inserted += 1

    logger.info("rule_definitions_seeded", extra={"inserted": inserted, "total_seeds": len(FSMA_RULE_SEEDS)})
    return inserted
