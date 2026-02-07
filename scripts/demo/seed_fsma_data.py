#!/usr/bin/env python3
"""
FSMA 204 Demo Data Seeder (v3) — Recall-Based Chains.

Generates traceability records modeled on real FDA recalls:
  Chain 1: Rizo Lopez–style dairy (mixed FTL coverage)
  Chain 2: Cs-137 shrimp (imported seafood, FLBR CTE)
  Chain 3: Cucumber/produce (farm-to-fork, 5 CTEs)

Every record includes a SHA-256 hash compatible with verify_chain.py.
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

_PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

try:
    import structlog
    logger = structlog.get_logger("fsma-seeder")
except ImportError:
    import logging
    logger = logging.getLogger("fsma-seeder")


# ─── SHA-256 Hash ────────────────────────────────────────────────────────────

def compute_record_hash(record: dict) -> str:
    """SHA-256 hash using canonical field ordering (matches verify_chain.py)."""
    canonical = {
        "tlc": record.get("tlc", ""),
        "cte_type": record.get("cte_type", ""),
        "location": record.get("location", ""),
        "quantity": record.get("quantity", 0),
        "unit_of_measure": record.get("unit_of_measure", ""),
        "product_description": record.get("product_description", ""),
        "event_timestamp": record.get("event_timestamp", ""),
        "input_tlcs": sorted(record.get("input_tlcs", [])),
    }
    canonical_json = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()}"


def make_event(
    tlc: str, cte_type: str, location: str, quantity: int,
    unit: str, product: str, timestamp: str,
    input_tlcs: list[str] | None = None, **extra: Any,
) -> dict:
    """Create an event dict and compute its SHA-256 hash."""
    record = {
        "event_id": str(uuid.uuid4()),
        "tlc": tlc,
        "cte_type": cte_type,
        "location": location,
        "quantity": quantity,
        "unit_of_measure": unit,
        "product_description": product,
        "event_timestamp": timestamp,
        "input_tlcs": sorted(input_tlcs or []),
        **extra,
    }
    record["hash"] = compute_record_hash(record)
    return record


# ═══════════════════════════════════════════════════════════════════════════
# CHAIN 1: RIZO LOPEZ–STYLE DAIRY (Mixed FTL Coverage)
#
# Story: A single manufacturer making 8 cheese/dairy products.
#        5 are ON the FTL, 3 are OFF. Demonstrates FTL Checker value.
# Recall basis: Rizo Lopez Foods (2024) — Listeria monocytogenes
# ═══════════════════════════════════════════════════════════════════════════

RIZO_FACILITY = {
    "name": "Valle Fresco Creamery",
    "gln": "0860000100001",
    "type": "MANUFACTURER",
    "address": "1200 Dairy Lane, Modesto, CA 95351",
}

RIZO_DISTRIBUTOR = {
    "name": "Central Valley Foods Distribution",
    "gln": "0860000100002",
    "type": "DISTRIBUTOR",
    "address": "800 Commerce Way, Stockton, CA 95206",
}

RIZO_RETAILERS = [
    {"name": "Mercado Fresco #12", "gln": "0860000100010", "type": "RETAILER", "address": "245 Mission St, San Jose, CA"},
    {"name": "La Tienda Market", "gln": "0860000100011", "type": "RETAILER", "address": "3100 E 14th St, Oakland, CA"},
    {"name": "FreshMart Grocery", "gln": "0860000100012", "type": "RETAILER", "address": "900 S Broadway, Los Angeles, CA"},
]

# Products — ON FTL vs OFF FTL (this IS the demo story)
RIZO_PRODUCTS_ON_FTL = [
    {"name": "Queso Fresco 12oz", "gtin": "00860001000012", "ftl_category": "Fresh Soft Cheese", "on_ftl": True},
    {"name": "Ricotta Fresca 16oz", "gtin": "00860001000029", "ftl_category": "Fresh Soft Cheese", "on_ftl": True},
    {"name": "Oaxaca String Cheese 1lb", "gtin": "00860001000036", "ftl_category": "Soft Ripened & Semi-Soft", "on_ftl": True},
    {"name": "Panela Cheese 10oz", "gtin": "00860001000043", "ftl_category": "Fresh Soft Cheese", "on_ftl": True},
    {"name": "Monterey Jack Block 8oz", "gtin": "00860001000050", "ftl_category": "Soft Ripened & Semi-Soft", "on_ftl": True},
]

RIZO_PRODUCTS_OFF_FTL = [
    {"name": "Aged Cotija 8oz", "gtin": "00860001000067", "ftl_category": "Hard Cheese (NOT on FTL)", "on_ftl": False},
    {"name": "Sharp Cheddar Block 8oz", "gtin": "00860001000074", "ftl_category": "Hard Cheese (NOT on FTL)", "on_ftl": False},
    {"name": "Crema Mexicana 15oz", "gtin": "00860001000081", "ftl_category": "Sour Cream (NOT on FTL)", "on_ftl": False},
]


def generate_rizo_chain(base_dt: datetime) -> List[Dict[str, Any]]:
    """Generate Rizo Lopez–style dairy events. Mix of ON and OFF FTL products."""
    events = []
    all_products = RIZO_PRODUCTS_ON_FTL + RIZO_PRODUCTS_OFF_FTL

    for batch_idx in range(15):  # 15 production batches
        product = all_products[batch_idx % len(all_products)]
        batch_dt = base_dt + timedelta(days=batch_idx)
        date_str = batch_dt.strftime("%Y%m%d")
        raw_tlc = f"{product['gtin']}-{date_str}-RAW"
        finished_tlc = f"{product['gtin']}-{date_str}-FIN"
        quantity = random.randint(200, 800)
        finished_qty = int(quantity * 0.92)  # ~8% yield loss
        retailer = RIZO_RETAILERS[batch_idx % len(RIZO_RETAILERS)]

        # CTE 1: RECEIVING raw milk at creamery (§1.1345)
        ts = (batch_dt + timedelta(hours=5)).isoformat() + "Z"
        events.append(make_event(
            tlc=raw_tlc, cte_type="RECEIVING", location=RIZO_FACILITY["gln"],
            quantity=quantity, unit="lbs", product=f"Raw Milk for {product['name']}",
            timestamp=ts,
            facility_name=RIZO_FACILITY["name"],
            reference_document_type="BOL",
            reference_document_number=f"RL-BOL-{date_str}-{batch_idx:03d}",
            cfr_section="§1.1345",
            on_ftl=product["on_ftl"],
            ftl_category=product["ftl_category"],
        ))

        # CTE 2: TRANSFORMATION — cheese making (§1.1350)
        ts = (batch_dt + timedelta(hours=10)).isoformat() + "Z"
        events.append(make_event(
            tlc=finished_tlc, cte_type="TRANSFORMATION", location=RIZO_FACILITY["gln"],
            quantity=finished_qty, unit="units", product=product["name"],
            timestamp=ts,
            input_tlcs=[raw_tlc],
            facility_name=RIZO_FACILITY["name"],
            new_product_description=product["name"],
            cfr_section="§1.1350",
            on_ftl=product["on_ftl"],
            ftl_category=product["ftl_category"],
        ))

        # CTE 3: SHIPPING from creamery → distributor (§1.1340)
        ship_dt = batch_dt + timedelta(days=1)
        ts = (ship_dt + timedelta(hours=4)).isoformat() + "Z"
        events.append(make_event(
            tlc=finished_tlc, cte_type="SHIPPING", location=RIZO_FACILITY["gln"],
            quantity=finished_qty, unit="units", product=product["name"],
            timestamp=ts,
            facility_name=RIZO_FACILITY["name"],
            ship_from_gln=RIZO_FACILITY["gln"],
            ship_to_gln=RIZO_DISTRIBUTOR["gln"],
            cfr_section="§1.1340",
            on_ftl=product["on_ftl"],
        ))

        # CTE 4: RECEIVING at distributor (§1.1345)
        ts = (ship_dt + timedelta(hours=12)).isoformat() + "Z"
        events.append(make_event(
            tlc=finished_tlc, cte_type="RECEIVING", location=RIZO_DISTRIBUTOR["gln"],
            quantity=finished_qty, unit="units", product=product["name"],
            timestamp=ts,
            facility_name=RIZO_DISTRIBUTOR["name"],
            ship_from_gln=RIZO_FACILITY["gln"],
            ship_to_gln=RIZO_DISTRIBUTOR["gln"],
            tlc_source_gln=RIZO_FACILITY["gln"],
            reference_document_type="BOL",
            reference_document_number=f"RL-BOL-{date_str}-{batch_idx:03d}",
            cfr_section="§1.1345",
            on_ftl=product["on_ftl"],
        ))

        # CTE 5: SHIPPING distributor → retailer (§1.1340)
        retail_dt = ship_dt + timedelta(days=1)
        ts = (retail_dt + timedelta(hours=3)).isoformat() + "Z"
        events.append(make_event(
            tlc=finished_tlc, cte_type="SHIPPING", location=RIZO_DISTRIBUTOR["gln"],
            quantity=finished_qty, unit="units", product=product["name"],
            timestamp=ts,
            facility_name=RIZO_DISTRIBUTOR["name"],
            ship_from_gln=RIZO_DISTRIBUTOR["gln"],
            ship_to_gln=retailer["gln"],
            cfr_section="§1.1340",
            on_ftl=product["on_ftl"],
        ))

        # CTE 6: RECEIVING at retailer (§1.1345)
        ts = (retail_dt + timedelta(hours=10)).isoformat() + "Z"
        events.append(make_event(
            tlc=finished_tlc, cte_type="RECEIVING", location=retailer["gln"],
            quantity=finished_qty, unit="units", product=product["name"],
            timestamp=ts,
            facility_name=retailer["name"],
            ship_from_gln=RIZO_DISTRIBUTOR["gln"],
            ship_to_gln=retailer["gln"],
            tlc_source_gln=RIZO_DISTRIBUTOR["gln"],
            reference_document_type="PO",
            reference_document_number=f"RL-PO-{date_str}-{batch_idx:03d}",
            cfr_section="§1.1345",
            on_ftl=product["on_ftl"],
        ))

    return events


# ═══════════════════════════════════════════════════════════════════════════
# CHAIN 2: CESIUM-137 SHRIMP (Imported Seafood + FLBR)
#
# Story: Indonesian processor → U.S. port → Southwind Foods → retail.
#        Demonstrates First Land-Based Receiving CTE (§1.1335).
# Recall basis: Cs-137 frozen shrimp recall (2025)
# ═══════════════════════════════════════════════════════════════════════════

SHRIMP_FACILITIES = {
    "vessel": {
        "name": "KM Sinar Laut (Indonesian Trawler)",
        "gln": "8991234560001",
        "type": "VESSEL",
        "vessel_name": "KM Sinar Laut",
        "harvest_area": "FAO Area 71 — Western Central Pacific",
    },
    "indo_processor": {
        "name": "PT Makassar Seafood Processing",
        "gln": "8991234560002",
        "type": "FOREIGN_PROCESSOR",
        "address": "Jl. Pelabuhan No. 15, Makassar, South Sulawesi, Indonesia",
    },
    "port": {
        "name": "Port of Long Beach — Cold Storage Terminal",
        "gln": "0078742000010",
        "type": "FIRST_RECEIVER",
        "address": "Pier J, Long Beach, CA 90802",
        "landing_port": "Port of Long Beach, CA",
    },
    "importer": {
        "name": "Southwind Foods LLC",  # Actual Tier 3 prospect
        "gln": "0078742000020",
        "type": "IMPORTER",
        "address": "2100 Carson St, Carson, CA 90745",
    },
    "distributor": {
        "name": "Pacific Rim Seafood Distribution",
        "gln": "0078742000030",
        "type": "DISTRIBUTOR",
        "address": "1500 Harbor Blvd, Long Beach, CA 90802",
    },
    "retailers": [
        {"name": "99 Ranch Market - Rowland Heights", "gln": "0078742000040", "type": "RETAILER"},
        {"name": "H Mart - Koreatown", "gln": "0078742000041", "type": "RETAILER"},
        {"name": "Costco Wholesale #681", "gln": "0078742000042", "type": "RETAILER"},
    ],
}

SHRIMP_PRODUCTS = [
    {"name": "Frozen White Shrimp 16/20ct 2lb Bag", "gtin": "00787420000012", "category": "Crustaceans"},
    {"name": "Frozen Tiger Shrimp 21/25ct 1lb Bag", "gtin": "00787420000029", "category": "Crustaceans"},
    {"name": "Frozen Peeled Shrimp 26/30ct 2lb Bag", "gtin": "00787420000036", "category": "Crustaceans"},
]


def generate_shrimp_chain(base_dt: datetime) -> List[Dict[str, Any]]:
    """Generate Cs-137 imported shrimp events with FLBR CTE."""
    events = []
    vessel = SHRIMP_FACILITIES["vessel"]
    indo = SHRIMP_FACILITIES["indo_processor"]
    port = SHRIMP_FACILITIES["port"]
    importer = SHRIMP_FACILITIES["importer"]
    dist = SHRIMP_FACILITIES["distributor"]
    retailers = SHRIMP_FACILITIES["retailers"]

    for batch_idx in range(20):  # 20 shipment batches
        product = SHRIMP_PRODUCTS[batch_idx % len(SHRIMP_PRODUCTS)]
        batch_dt = base_dt + timedelta(days=batch_idx * 2)  # Every 2 days
        date_str = batch_dt.strftime("%Y%m%d")
        harvest_tlc = f"{product['gtin']}-{date_str}-HARV"
        processed_tlc = f"{product['gtin']}-{date_str}-PROC"
        quantity = random.randint(500, 2000)
        proc_qty = int(quantity * 0.80)  # 20% processing loss
        retailer = retailers[batch_idx % len(retailers)]

        # CTE 1: HARVESTING at sea (§1.1325(a))
        ts = (batch_dt + timedelta(hours=3)).isoformat() + "Z"
        events.append(make_event(
            tlc=harvest_tlc, cte_type="HARVESTING", location=vessel["gln"],
            quantity=quantity, unit="lbs", product=product["name"],
            timestamp=ts,
            facility_name=vessel["name"],
            vessel_name=vessel["vessel_name"],
            harvest_area=vessel["harvest_area"],
            commodity=product["category"],
            cfr_section="§1.1325(a)",
        ))

        # CTE 2: TRANSFORMATION at Indonesian processor (§1.1350)
        proc_dt = batch_dt + timedelta(days=1)
        ts = (proc_dt + timedelta(hours=6)).isoformat() + "Z"
        events.append(make_event(
            tlc=processed_tlc, cte_type="TRANSFORMATION", location=indo["gln"],
            quantity=proc_qty, unit="lbs", product=product["name"],
            timestamp=ts,
            input_tlcs=[harvest_tlc],
            facility_name=indo["name"],
            new_product_description=f"{product['name']} — Frozen IQF",
            cfr_section="§1.1350",
        ))

        # CTE 3: SHIPPING from Indonesia → U.S. port (§1.1340)
        ship_dt = proc_dt + timedelta(days=14)  # ~2 weeks ocean freight
        ts = (ship_dt + timedelta(hours=0)).isoformat() + "Z"
        events.append(make_event(
            tlc=processed_tlc, cte_type="SHIPPING", location=indo["gln"],
            quantity=proc_qty, unit="lbs", product=product["name"],
            timestamp=ts,
            facility_name=indo["name"],
            ship_from_gln=indo["gln"],
            ship_to_gln=port["gln"],
            container_id=f"MAEU{random.randint(1000000, 9999999)}",
            cfr_section="§1.1340",
        ))

        # CTE 4: FIRST LAND-BASED RECEIVING at Port of Long Beach (§1.1335)
        # This is the KEY CTE for imported seafood
        flbr_dt = ship_dt + timedelta(days=1)
        ts = (flbr_dt + timedelta(hours=8)).isoformat() + "Z"
        events.append(make_event(
            tlc=processed_tlc, cte_type="FIRST_LAND_BASED_RECEIVING",
            location=port["gln"],
            quantity=proc_qty, unit="lbs", product=product["name"],
            timestamp=ts,
            facility_name=port["name"],
            vessel_name=vessel["vessel_name"],
            harvest_area=vessel["harvest_area"],
            landing_port=port["landing_port"],
            cfr_section="§1.1335",
        ))

        # CTE 5: SHIPPING port → Southwind Foods / importer (§1.1340)
        ts = (flbr_dt + timedelta(hours=14)).isoformat() + "Z"
        events.append(make_event(
            tlc=processed_tlc, cte_type="SHIPPING", location=port["gln"],
            quantity=proc_qty, unit="lbs", product=product["name"],
            timestamp=ts,
            facility_name=port["name"],
            ship_from_gln=port["gln"],
            ship_to_gln=importer["gln"],
            cfr_section="§1.1340",
        ))

        # CTE 6: RECEIVING at Southwind Foods (§1.1345)
        recv_dt = flbr_dt + timedelta(days=1)
        ts = (recv_dt + timedelta(hours=7)).isoformat() + "Z"
        events.append(make_event(
            tlc=processed_tlc, cte_type="RECEIVING", location=importer["gln"],
            quantity=proc_qty, unit="lbs", product=product["name"],
            timestamp=ts,
            facility_name=importer["name"],
            ship_from_gln=port["gln"],
            ship_to_gln=importer["gln"],
            tlc_source_gln=port["gln"],
            reference_document_type="BOL",
            reference_document_number=f"SHR-BOL-{date_str}-{batch_idx:03d}",
            cfr_section="§1.1345",
        ))

        # CTE 7: SHIPPING importer → distributor (§1.1340)
        ts = (recv_dt + timedelta(hours=14)).isoformat() + "Z"
        events.append(make_event(
            tlc=processed_tlc, cte_type="SHIPPING", location=importer["gln"],
            quantity=proc_qty, unit="lbs", product=product["name"],
            timestamp=ts,
            facility_name=importer["name"],
            ship_from_gln=importer["gln"],
            ship_to_gln=dist["gln"],
            cfr_section="§1.1340",
        ))

        # CTE 8: RECEIVING at distributor (§1.1345)
        dist_dt = recv_dt + timedelta(days=1)
        ts = (dist_dt + timedelta(hours=6)).isoformat() + "Z"
        events.append(make_event(
            tlc=processed_tlc, cte_type="RECEIVING", location=dist["gln"],
            quantity=proc_qty, unit="lbs", product=product["name"],
            timestamp=ts,
            facility_name=dist["name"],
            ship_from_gln=importer["gln"],
            ship_to_gln=dist["gln"],
            tlc_source_gln=importer["gln"],
            reference_document_type="BOL",
            reference_document_number=f"SHR-BOL2-{date_str}-{batch_idx:03d}",
            cfr_section="§1.1345",
        ))

        # CTE 9: SHIPPING distributor → retailer (§1.1340)
        ts = (dist_dt + timedelta(hours=12)).isoformat() + "Z"
        events.append(make_event(
            tlc=processed_tlc, cte_type="SHIPPING", location=dist["gln"],
            quantity=proc_qty, unit="lbs", product=product["name"],
            timestamp=ts,
            facility_name=dist["name"],
            ship_from_gln=dist["gln"],
            ship_to_gln=retailer["gln"],
            cfr_section="§1.1340",
        ))

        # CTE 10: RECEIVING at retailer (§1.1345)
        retail_dt = dist_dt + timedelta(days=1)
        ts = (retail_dt + timedelta(hours=7)).isoformat() + "Z"
        events.append(make_event(
            tlc=processed_tlc, cte_type="RECEIVING", location=retailer["gln"],
            quantity=proc_qty, unit="lbs", product=product["name"],
            timestamp=ts,
            facility_name=retailer["name"],
            ship_from_gln=dist["gln"],
            ship_to_gln=retailer["gln"],
            tlc_source_gln=dist["gln"],
            reference_document_type="PO",
            reference_document_number=f"SHR-PO-{date_str}-{batch_idx:03d}",
            cfr_section="§1.1345",
        ))

    return events


# ═══════════════════════════════════════════════════════════════════════════
# CHAIN 3: CUCUMBER/PRODUCE (Farm-to-Fork, 5+ CTEs)
#
# Story: Farm → Cooling → Initial Packing → Distribution → Retail.
#        Standard FSMA 204 produce traceability flow.
# Recall basis: 2024 cucumber Salmonella recall
# ═══════════════════════════════════════════════════════════════════════════

CUCUMBER_FACILITIES = {
    "farm": {
        "name": "Suncoast Farms",
        "gln": "0071430000001",
        "type": "FARM",
        "address": "4500 Agricultural Rd, Immokalee, FL 34142",
        "field_ids": ["SC-North-A", "SC-North-B", "SC-South-1", "SC-Organic"],
    },
    "cooler": {
        "name": "Suncoast Cold Storage",
        "gln": "0071430000002",
        "type": "COOLER",
        "address": "4520 Agricultural Rd, Immokalee, FL 34142",
    },
    "packer": {
        "name": "Fresh Fields Packing Co",
        "gln": "0071430000003",
        "type": "PACKER",
        "address": "200 Packing House Blvd, Plant City, FL 33563",
    },
    "distributor": {
        "name": "Southeast Fresh Distribution",
        "gln": "0071430000004",
        "type": "DISTRIBUTOR",
        "address": "1000 Distribution Center Dr, Atlanta, GA 30318",
    },
    "retailers": [
        {"name": "Publix Super Markets #1247", "gln": "0071430000010", "type": "RETAILER"},
        {"name": "Kroger #432", "gln": "0071430000011", "type": "RETAILER"},
        {"name": "Walmart Supercenter #2891", "gln": "0071430000012", "type": "RETAILER"},
        {"name": "Whole Foods Market - Buckhead", "gln": "0071430000013", "type": "RETAILER"},
    ],
}

CUCUMBER_PRODUCTS = [
    {"name": "Fresh Cucumbers (bulk)", "gtin": "00714300000012", "category": "Cucumbers"},
    {"name": "English Cucumbers 2ct Sleeve", "gtin": "00714300000029", "category": "Cucumbers"},
    {"name": "Mini Cucumbers 1lb Bag", "gtin": "00714300000036", "category": "Cucumbers"},
    {"name": "Organic Cucumbers (bulk)", "gtin": "00714300000043", "category": "Cucumbers"},
]


def generate_cucumber_chain(base_dt: datetime) -> List[Dict[str, Any]]:
    """Generate cucumber produce chain with full 5-CTE flow."""
    events = []
    farm = CUCUMBER_FACILITIES["farm"]
    cooler = CUCUMBER_FACILITIES["cooler"]
    packer = CUCUMBER_FACILITIES["packer"]
    dist = CUCUMBER_FACILITIES["distributor"]
    retailers = CUCUMBER_FACILITIES["retailers"]

    for batch_idx in range(20):  # 20 harvest batches
        product = CUCUMBER_PRODUCTS[batch_idx % len(CUCUMBER_PRODUCTS)]
        batch_dt = base_dt + timedelta(days=batch_idx)
        date_str = batch_dt.strftime("%Y%m%d")
        harvest_tlc = f"{product['gtin']}-{date_str}-HARV"
        pack_tlc = f"{product['gtin']}-{date_str}-PACK"
        field_id = farm["field_ids"][batch_idx % len(farm["field_ids"])]
        quantity = random.randint(200, 1000)
        pack_qty = int(quantity * 0.95)  # 5% field cull
        retailer = retailers[batch_idx % len(retailers)]

        # CTE 1: HARVESTING (§1.1325(a))
        ts = (batch_dt + timedelta(hours=5)).isoformat() + "Z"
        events.append(make_event(
            tlc=harvest_tlc, cte_type="HARVESTING", location=farm["gln"],
            quantity=quantity, unit="cases", product=product["name"],
            timestamp=ts,
            facility_name=farm["name"],
            field_identifier=field_id,
            commodity=product["category"],
            cfr_section="§1.1325(a)",
        ))

        # CTE 2: COOLING (§1.1325(b))
        ts = (batch_dt + timedelta(hours=7)).isoformat() + "Z"
        events.append(make_event(
            tlc=harvest_tlc, cte_type="COOLING", location=cooler["gln"],
            quantity=quantity, unit="cases", product=product["name"],
            timestamp=ts,
            facility_name=cooler["name"],
            cfr_section="§1.1325(b)",
        ))

        # CTE 3: INITIAL PACKING (§1.1330)
        pack_dt = batch_dt + timedelta(days=1)
        ts = (pack_dt + timedelta(hours=6)).isoformat() + "Z"
        events.append(make_event(
            tlc=pack_tlc, cte_type="INITIAL_PACKING", location=packer["gln"],
            quantity=pack_qty, unit="cases", product=product["name"],
            timestamp=ts,
            input_tlcs=[harvest_tlc],
            facility_name=packer["name"],
            tlc_source_gln=farm["gln"],
            cfr_section="§1.1330",
        ))

        # CTE 4: SHIPPING packer → distributor (§1.1340)
        ts = (pack_dt + timedelta(hours=14)).isoformat() + "Z"
        events.append(make_event(
            tlc=pack_tlc, cte_type="SHIPPING", location=packer["gln"],
            quantity=pack_qty, unit="cases", product=product["name"],
            timestamp=ts,
            facility_name=packer["name"],
            ship_from_gln=packer["gln"],
            ship_to_gln=dist["gln"],
            cfr_section="§1.1340",
        ))

        # CTE 5: RECEIVING at distributor (§1.1345)
        recv_dt = pack_dt + timedelta(days=1)
        ts = (recv_dt + timedelta(hours=8)).isoformat() + "Z"
        events.append(make_event(
            tlc=pack_tlc, cte_type="RECEIVING", location=dist["gln"],
            quantity=pack_qty, unit="cases", product=product["name"],
            timestamp=ts,
            facility_name=dist["name"],
            ship_from_gln=packer["gln"],
            ship_to_gln=dist["gln"],
            tlc_source_gln=packer["gln"],
            reference_document_type="BOL",
            reference_document_number=f"CUC-BOL-{date_str}-{batch_idx:03d}",
            cfr_section="§1.1345",
        ))

        # CTE 6: SHIPPING distributor → retailer (§1.1340)
        ts = (recv_dt + timedelta(hours=14)).isoformat() + "Z"
        events.append(make_event(
            tlc=pack_tlc, cte_type="SHIPPING", location=dist["gln"],
            quantity=pack_qty, unit="cases", product=product["name"],
            timestamp=ts,
            facility_name=dist["name"],
            ship_from_gln=dist["gln"],
            ship_to_gln=retailer["gln"],
            cfr_section="§1.1340",
        ))

        # CTE 7: RECEIVING at retailer (§1.1345)
        retail_dt = recv_dt + timedelta(days=1)
        ts = (retail_dt + timedelta(hours=7)).isoformat() + "Z"
        events.append(make_event(
            tlc=pack_tlc, cte_type="RECEIVING", location=retailer["gln"],
            quantity=pack_qty, unit="cases", product=product["name"],
            timestamp=ts,
            facility_name=retailer["name"],
            ship_from_gln=dist["gln"],
            ship_to_gln=retailer["gln"],
            tlc_source_gln=dist["gln"],
            reference_document_type="PO",
            reference_document_number=f"CUC-PO-{date_str}-{batch_idx:03d}",
            cfr_section="§1.1345",
        ))

    return events


# ─── Main Generator ─────────────────────────────────────────────────────────

def generate_demo_events(base_date: str = "2025-11-01") -> List[Dict[str, Any]]:
    """Generate all 3 recall-based demo chains."""
    base_dt = datetime.strptime(base_date, "%Y-%m-%d")
    events = []

    # Chain 1: Rizo Lopez dairy — 15 batches × 6 events = 90
    rizo = generate_rizo_chain(base_dt)
    events.extend(rizo)

    # Chain 2: Cs-137 shrimp — 20 batches × 10 events = 200
    shrimp = generate_shrimp_chain(base_dt + timedelta(days=5))
    events.extend(shrimp)

    # Chain 3: Cucumber produce — 20 batches × 7 events = 140
    cucumber = generate_cucumber_chain(base_dt + timedelta(days=10))
    events.extend(cucumber)

    logger.info(
        "demo_events_generated",
        rizo_events=len(rizo),
        shrimp_events=len(shrimp),
        cucumber_events=len(cucumber),
        total=len(events),
    )

    return events


# ─── Output ──────────────────────────────────────────────────────────────────

def get_all_facilities() -> list:
    """Collect all facility definitions for JSON export."""
    return (
        [RIZO_FACILITY, RIZO_DISTRIBUTOR] + RIZO_RETAILERS +
        list(SHRIMP_FACILITIES.values())[:-1] +  # Exclude retailers list
        SHRIMP_FACILITIES["retailers"] +
        [CUCUMBER_FACILITIES["farm"], CUCUMBER_FACILITIES["cooler"],
         CUCUMBER_FACILITIES["packer"], CUCUMBER_FACILITIES["distributor"]] +
        CUCUMBER_FACILITIES["retailers"]
    )


def seed_to_json(output_path: str = "demo_fsma_events.json") -> None:
    """Generate demo events and save to JSON."""
    events = generate_demo_events()

    # Count ON vs OFF FTL for Rizo chain
    rizo_on = sum(1 for e in events if e.get("on_ftl") is True)
    rizo_off = sum(1 for e in events if e.get("on_ftl") is False)

    all_products = (
        RIZO_PRODUCTS_ON_FTL + RIZO_PRODUCTS_OFF_FTL +
        SHRIMP_PRODUCTS + CUCUMBER_PRODUCTS
    )

    output = {
        "schema_version": "3.0",
        "generator": "RegEngine FSMA 204 Demo Seeder v3 — Recall-Based",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "facilities": get_all_facilities(),
        "products": all_products,
        "records": events,
        "event_count": len(events),
        "chain_summary": {
            "chain_1_rizo_dairy": {
                "description": "Rizo Lopez–style dairy (mixed FTL coverage)",
                "recall_basis": "Rizo Lopez Foods 2024 — Listeria monocytogenes",
                "events_on_ftl": rizo_on,
                "events_off_ftl": rizo_off,
                "demo_story": "Not everything this company makes is covered. The FTL Checker tells you which products are — and which aren't.",
            },
            "chain_2_shrimp": {
                "description": "Imported frozen shrimp (Cs-137 recall-style)",
                "recall_basis": "Cesium-137 frozen shrimp recall 2025",
                "prospect_connection": "Southwind Foods LLC (Carson, CA) — Tier 3 prospect",
                "key_cte": "FIRST_LAND_BASED_RECEIVING (§1.1335)",
                "demo_story": "Vessel name + harvest area are the KDEs that catch imported seafood failures.",
            },
            "chain_3_cucumber": {
                "description": "Farm-to-fork cucumber produce",
                "recall_basis": "2024 cucumber Salmonella recall",
                "cte_count": "5 CTEs: Harvesting → Cooling → Initial Packing → Shipping/Receiving",
                "demo_story": "Standard FSMA 204 produce flow. Field ID traces back to exact harvest location.",
            },
            "cte_types": sorted(set(e["cte_type"] for e in events)),
        },
    }

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Generated {len(events)} demo events to {output_path}")
    print(f"  Chain 1 (Rizo dairy):  {rizo_on + rizo_off} events ({rizo_on} ON FTL, {rizo_off} OFF FTL)")
    print(f"  Chain 2 (Shrimp):      {len([e for e in events if 'SHR-' in e.get('reference_document_number', '') or e.get('harvest_area', '')])} events")
    print(f"  Chain 3 (Cucumber):    {len([e for e in events if 'CUC-' in e.get('reference_document_number', '') or e.get('field_identifier', '')])} events")
    print(f"  CTE types: {output['chain_summary']['cte_types']}")


def seed_to_kafka(kafka_bootstrap: str = "localhost:9092") -> None:
    """Generate demo events and send to Kafka."""
    try:
        from kafka import KafkaProducer
    except ImportError:
        print("kafka-python not installed. Run: pip install kafka-python")
        return

    events = generate_demo_events()
    producer = KafkaProducer(
        bootstrap_servers=kafka_bootstrap,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )

    for event in events:
        payload = {
            "document_id": f"demo-{event['event_id']}",
            "document_type": "DEMO",
            "ctes": [{
                "type": event["cte_type"],
                "kdes": {
                    "traceability_lot_code": event["tlc"],
                    "product_description": event.get("product_description"),
                    "quantity": event.get("quantity"),
                    "unit_of_measure": event.get("unit_of_measure"),
                    "location_identifier": f"urn:gln:{event.get('location', '')}",
                    "event_timestamp": event["event_timestamp"],
                    "vessel_name": event.get("vessel_name"),
                    "harvest_area": event.get("harvest_area"),
                    "landing_port": event.get("landing_port"),
                    "field_identifier": event.get("field_identifier"),
                    "on_ftl": event.get("on_ftl"),
                },
                "confidence": 0.95,
            }],
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        producer.send("fsma.events.extracted", payload)

    producer.flush()
    producer.close()
    print(f"Sent {len(events)} demo events to Kafka")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="FSMA 204 Demo Seeder v3 — Recall-Based")
    parser.add_argument("--output", choices=["json", "kafka"], default="json")
    parser.add_argument("--kafka-bootstrap", default="localhost:9092")
    parser.add_argument("--json-path", default="demo_fsma_events.json")

    args = parser.parse_args()
    if args.output == "json":
        seed_to_json(args.json_path)
    else:
        seed_to_kafka(args.kafka_bootstrap)
