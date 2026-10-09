#!/usr/bin/env python3
"""
Full Product Lifecycle Test: Romaine Lettuce E. coli Recall Simulation
======================================================================

Seeds production with a realistic romaine lettuce supply chain across
3 suppliers, 2 distribution centers, and 5 retail locations. Then
fabricates an E. coli contamination event to test recall traceability.

Supply Chain:
  Valley Fresh Farms (Salinas, CA)     ──┐
  Sunrise Organics (Yuma, AZ)          ──┼── FreshCo DC (Stockton, CA) ── Retail stores
  Green Leaf Growers (Watsonville, CA) ──┘    Pacific DC (Portland, OR)

Recall Scenario:
  E. coli O157:H7 detected in lot TLC-VFF-HARVEST-0312 from Valley Fresh
  Farms. FDA requests full traceability within 24 hours.

Usage:
    python3 scripts/seed_lifecycle_test.py
    python3 scripts/seed_lifecycle_test.py --allow-production \
        # only to target a non-localhost REGENGINE_BASE_URL

Localhost is the default target. Pointing REGENGINE_BASE_URL (or
--base-url) at anything else, or running with REGENGINE_ENV=production,
requires the explicit --allow-production flag.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

# ── Configuration ──────────────────────────────────────────────────────
# This script seeds a live environment, so the API key is read from the
# environment rather than committed. Export REGENGINE_API_KEY (and
# optionally REGENGINE_BASE_URL / REGENGINE_TENANT_ID) before running.
LOCAL_DEFAULT_BASE = "http://localhost:8000"
BASE = os.getenv("REGENGINE_BASE_URL", LOCAL_DEFAULT_BASE)
API_KEY = os.getenv("REGENGINE_API_KEY", "")
TENANT_ID = os.getenv("REGENGINE_TENANT_ID", "5946c58f-ddf9-4db0-9baa-acb11c6fce91")
if not API_KEY:
    print(
        "Error: REGENGINE_API_KEY is not set. Export a key with ingest permissions "
        "for the target tenant before running this seeder.",
        file=sys.stderr,
    )
    sys.exit(1)
INGEST_URL = f"{BASE}/api/v1/webhooks/ingest"
PRODUCTS_URL = f"{BASE}/api/v1/products/{TENANT_ID}"
SUPPLIERS_URL = f"{BASE}/api/v1/suppliers/{TENANT_ID}"

HEADERS = {
    "Content-Type": "application/json",
    "X-RegEngine-API-Key": API_KEY,
    "X-Tenant-ID": TENANT_ID,
}


def is_production_base(base: str) -> bool:
    """True when a base URL points anywhere other than local loopback."""
    try:
        host = (urllib.parse.urlsplit(base).hostname or "").lower()
    except ValueError:
        return True
    return host not in {"localhost", "127.0.0.1", "::1"}


def ensure_local_target(base: str, allow_production: bool) -> None:
    """Refuse non-localhost targets (or REGENGINE_ENV=production) without opt-in."""
    env = os.getenv("REGENGINE_ENV", "").strip().lower()
    if (is_production_base(base) or env == "production") and not allow_production:
        print(
            f"Refusing to seed non-localhost target ({base}). Re-run with --allow-production only if you are certain.",
            file=sys.stderr,
        )
        sys.exit(2)


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed a lifecycle test scenario.")
    parser.add_argument(
        "--base-url",
        default=os.getenv("REGENGINE_BASE_URL", LOCAL_DEFAULT_BASE),
        help="API base URL (default http://localhost:8000)",
    )
    parser.add_argument(
        "--allow-production",
        action="store_true",
        help="Allow targeting a non-localhost environment. Almost never what you want.",
    )
    return parser.parse_args(argv)


def api_post(url, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=HEADERS, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  HTTP {e.code}: {body[:300]}")
        return {"error": e.code, "body": body}


def api_get(url):
    req = urllib.request.Request(url, headers=HEADERS, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  HTTP {e.code}: {body[:300]}")
        return {"error": e.code, "body": body}


# ── Step 1: Seed Suppliers ─────────────────────────────────────────────
# Fixture contacts below are deliberately synthetic: names are labeled,
# emails use the reserved example.invalid domain (never resolves), and
# phones use the reserved fictional 555-01XX range. Never put real
# personal data in this seeder; it writes into the target tenant.
SUPPLIERS = [
    {
        "name": "Valley Fresh Farms",
        "contact_name": "Synthetic Test Contact 1 (Valley Fresh)",
        "contact_email": "synthetic-valleyfresh-1@example.invalid",
        "phone": "+1-555-010-0001",
        "location": "Salinas, CA",
        "gln": "0614141000012",
        "compliance_status": "compliant",
        "fsma_registered": True,
        "fda_registration": "FDA-REG-11223344",
    },
    {
        "name": "Sunrise Organics",
        "contact_name": "Synthetic Test Contact 2 (Sunrise)",
        "contact_email": "synthetic-sunrise-2@example.invalid",
        "phone": "+1-555-010-0002",
        "location": "Yuma, AZ",
        "gln": "0614141000029",
        "compliance_status": "compliant",
        "fsma_registered": True,
        "fda_registration": "FDA-REG-55667788",
    },
    {
        "name": "Green Leaf Growers",
        "contact_name": "Synthetic Test Contact 3 (Green Leaf)",
        "contact_email": "synthetic-greenleaf-3@example.invalid",
        "phone": "+1-555-010-0003",
        "location": "Watsonville, CA",
        "gln": "0614141000036",
        "compliance_status": "at_risk",
        "fsma_registered": True,
        "fda_registration": "FDA-REG-99001122",
    },
]

# ── Step 2: Seed Products ──────────────────────────────────────────────
PRODUCTS = [
    {
        "name": "Romaine Lettuce Hearts - Organic",
        "gtin": "00611269991000",
        "category": "Fruits and Vegetables",
        "description": "Organic romaine lettuce hearts, triple-washed, 3-count pack",
        "unit_of_measure": "cases",
        "ftl_category": "leafy_greens",
    },
    {
        "name": "Chopped Romaine - Foodservice",
        "gtin": "00611269991017",
        "category": "Fruits and Vegetables",
        "description": "Pre-chopped romaine lettuce for foodservice, 2lb bag",
        "unit_of_measure": "cases",
        "ftl_category": "leafy_greens",
    },
    {
        "name": "Spring Mix Salad Kit",
        "gtin": "00611269991024",
        "category": "Fruits and Vegetables",
        "description": "Mixed greens salad kit with romaine, spinach, arugula - 12oz",
        "unit_of_measure": "units",
        "ftl_category": "leafy_greens",
    },
]

# ── Step 3: CTE Events — Full Supply Chain ─────────────────────────────
# Timeline: March 10-15, 2026 (normal flow)
#           March 12 harvest lot = CONTAMINATED (E. coli found later)


def build_supply_chain_events():
    """Build a realistic multi-day, multi-supplier supply chain."""
    events = []

    # ── Day 1: March 10 — Harvesting across all 3 farms ──
    events.append(
        {
            "cte_type": "harvesting",
            "timestamp": "2026-03-10T06:00:00Z",
            "location_name": "Valley Fresh Farms - Field 7",
            "product_description": "Romaine Lettuce Hearts - Organic",
            "traceability_lot_code": "TLC-VFF-HARVEST-0310",
            "quantity": 3000,
            "unit_of_measure": "lbs",
            "kdes": {
                "harvest_date": "2026-03-10",
                "location_name": "Valley Fresh Farms - Field 7",
                "farm_name": "Valley Fresh Farms",
                "growing_area": "Field 7 - Block C",
                "gtin": "00611269991000",
            },
        }
    )
    events.append(
        {
            "cte_type": "harvesting",
            "timestamp": "2026-03-10T06:30:00Z",
            "location_name": "Sunrise Organics - Plot 3A",
            "product_description": "Romaine Lettuce Hearts - Organic",
            "traceability_lot_code": "TLC-SO-HARVEST-0310",
            "quantity": 2500,
            "unit_of_measure": "lbs",
            "kdes": {
                "harvest_date": "2026-03-10",
                "location_name": "Sunrise Organics - Plot 3A",
                "farm_name": "Sunrise Organics",
                "growing_area": "Plot 3A - South Section",
                "gtin": "00611269991000",
            },
        }
    )

    # ── Day 1: Cooling ──
    events.append(
        {
            "cte_type": "cooling",
            "timestamp": "2026-03-10T08:00:00Z",
            "location_name": "Valley Fresh Farms - Vacuum Cooler",
            "product_description": "Romaine Lettuce Hearts - Organic",
            "traceability_lot_code": "TLC-VFF-COOL-0310",
            "quantity": 3000,
            "unit_of_measure": "lbs",
            "kdes": {
                "cooling_date": "2026-03-10",
                "location_name": "Valley Fresh Farms - Vacuum Cooler",
                "cooling_method": "vacuum_cooling",
                "target_temperature": "34",
                "input_tlc": "TLC-VFF-HARVEST-0310",
            },
        }
    )
    events.append(
        {
            "cte_type": "cooling",
            "timestamp": "2026-03-10T08:30:00Z",
            "location_name": "Sunrise Organics - Hydrocooler",
            "product_description": "Romaine Lettuce Hearts - Organic",
            "traceability_lot_code": "TLC-SO-COOL-0310",
            "quantity": 2500,
            "unit_of_measure": "lbs",
            "kdes": {
                "cooling_date": "2026-03-10",
                "location_name": "Sunrise Organics - Hydrocooler",
                "cooling_method": "hydrocooling",
                "target_temperature": "35",
                "input_tlc": "TLC-SO-HARVEST-0310",
            },
        }
    )

    # ── Day 1: Initial Packing ──
    events.append(
        {
            "cte_type": "initial_packing",
            "timestamp": "2026-03-10T10:00:00Z",
            "location_name": "Valley Fresh Farms - Pack House",
            "product_description": "Romaine Lettuce Hearts - Organic 3ct",
            "traceability_lot_code": "TLC-VFF-PACK-0310",
            "quantity": 1200,
            "unit_of_measure": "cases",
            "kdes": {
                "packing_date": "2026-03-10",
                "location_name": "Valley Fresh Farms - Pack House",
                "package_type": "3ct_clamshell",
                "upc": "00611269991000",
                "input_tlc": "TLC-VFF-COOL-0310",
            },
        }
    )

    # ── Day 1: Shipping to DC ──
    events.append(
        {
            "cte_type": "shipping",
            "timestamp": "2026-03-10T14:00:00Z",
            "location_name": "Valley Fresh Farms",
            "product_description": "Romaine Lettuce Hearts - Organic 3ct",
            "traceability_lot_code": "TLC-VFF-SHIP-0310",
            "quantity": 1200,
            "unit_of_measure": "cases",
            "kdes": {
                "ship_date": "2026-03-10",
                "ship_from_location": "Valley Fresh Farms, Salinas CA",
                "ship_to_location": "FreshCo DC, Stockton CA",
                "carrier": "ColdChain Logistics",
                "bol_number": "BOL-2026-0310-VFF-001",
                "trailer_temp": "34",
            },
        }
    )

    # ── Day 2: March 11 — Receiving at DC ──
    events.append(
        {
            "cte_type": "receiving",
            "timestamp": "2026-03-11T06:00:00Z",
            "location_name": "FreshCo Distribution Center - Stockton",
            "product_description": "Romaine Lettuce Hearts - Organic 3ct",
            "traceability_lot_code": "TLC-VFF-RECV-0311",
            "quantity": 1200,
            "unit_of_measure": "cases",
            "kdes": {
                "receive_date": "2026-03-11",
                "receiving_location": "FreshCo DC - Stockton, CA",
                "temperature_on_arrival": "35.8",
                "po_number": "PO-FC-2026-0310-001",
                "input_tlc": "TLC-VFF-SHIP-0310",
            },
        }
    )

    # ═══════════════════════════════════════════════════════════════════
    #  ★ CONTAMINATED LOT: March 12 harvest from Valley Fresh Field 12
    # ═══════════════════════════════════════════════════════════════════
    events.append(
        {
            "cte_type": "harvesting",
            "timestamp": "2026-03-12T05:30:00Z",
            "location_name": "Valley Fresh Farms - Field 12",
            "product_description": "Romaine Lettuce Hearts - Organic",
            "traceability_lot_code": "TLC-VFF-HARVEST-0312",
            "quantity": 4000,
            "unit_of_measure": "lbs",
            "kdes": {
                "harvest_date": "2026-03-12",
                "location_name": "Valley Fresh Farms - Field 12",
                "farm_name": "Valley Fresh Farms",
                "growing_area": "Field 12 - All Blocks",
                "gtin": "00611269991000",
            },
        }
    )
    events.append(
        {
            "cte_type": "cooling",
            "timestamp": "2026-03-12T07:30:00Z",
            "location_name": "Valley Fresh Farms - Vacuum Cooler",
            "product_description": "Romaine Lettuce Hearts - Organic",
            "traceability_lot_code": "TLC-VFF-COOL-0312",
            "quantity": 4000,
            "unit_of_measure": "lbs",
            "kdes": {
                "cooling_date": "2026-03-12",
                "location_name": "Valley Fresh Farms - Vacuum Cooler",
                "cooling_method": "vacuum_cooling",
                "target_temperature": "34",
                "input_tlc": "TLC-VFF-HARVEST-0312",
            },
        }
    )
    events.append(
        {
            "cte_type": "initial_packing",
            "timestamp": "2026-03-12T10:00:00Z",
            "location_name": "Valley Fresh Farms - Pack House",
            "product_description": "Romaine Lettuce Hearts - Organic 3ct",
            "traceability_lot_code": "TLC-VFF-PACK-0312",
            "quantity": 1600,
            "unit_of_measure": "cases",
            "kdes": {
                "packing_date": "2026-03-12",
                "location_name": "Valley Fresh Farms - Pack House",
                "package_type": "3ct_clamshell",
                "upc": "00611269991000",
                "input_tlc": "TLC-VFF-COOL-0312",
            },
        }
    )
    events.append(
        {
            "cte_type": "shipping",
            "timestamp": "2026-03-12T13:00:00Z",
            "location_name": "Valley Fresh Farms",
            "product_description": "Romaine Lettuce Hearts - Organic 3ct",
            "traceability_lot_code": "TLC-VFF-SHIP-0312",
            "quantity": 1600,
            "unit_of_measure": "cases",
            "kdes": {
                "ship_date": "2026-03-12",
                "ship_from_location": "Valley Fresh Farms, Salinas CA",
                "ship_to_location": "FreshCo DC, Stockton CA",
                "carrier": "ColdChain Logistics",
                "bol_number": "BOL-2026-0312-VFF-002",
                "trailer_temp": "33",
            },
        }
    )
    events.append(
        {
            "cte_type": "receiving",
            "timestamp": "2026-03-13T06:30:00Z",
            "location_name": "FreshCo Distribution Center - Stockton",
            "product_description": "Romaine Lettuce Hearts - Organic 3ct",
            "traceability_lot_code": "TLC-VFF-RECV-0313",
            "quantity": 1600,
            "unit_of_measure": "cases",
            "kdes": {
                "receive_date": "2026-03-13",
                "receiving_location": "FreshCo DC - Stockton, CA",
                "temperature_on_arrival": "36.1",
                "po_number": "PO-FC-2026-0312-002",
                "input_tlc": "TLC-VFF-SHIP-0312",
            },
        }
    )

    # ── Transformation: contaminated lot mixed into Spring Mix ──
    events.append(
        {
            "cte_type": "transformation",
            "timestamp": "2026-03-13T09:00:00Z",
            "location_name": "FreshCo DC - Processing Line A",
            "product_description": "Spring Mix Salad Kit - 12oz",
            "traceability_lot_code": "TLC-FC-XFORM-0313",
            "quantity": 600,
            "unit_of_measure": "units",
            "kdes": {
                "transformation_date": "2026-03-13",
                "input_lot_codes": "TLC-VFF-RECV-0313,TLC-SO-COOL-0310",
                "output_product": "Spring Mix Salad Kit - 12oz",
                "processing_facility": "FreshCo DC - Processing Line A",
                "gtin_output": "00611269991024",
            },
        }
    )

    # ── Shipping to retail (contaminated product distributed) ──
    events.append(
        {
            "cte_type": "shipping",
            "timestamp": "2026-03-13T15:00:00Z",
            "location_name": "FreshCo DC - Stockton",
            "product_description": "Spring Mix Salad Kit - 12oz",
            "traceability_lot_code": "TLC-FC-SHIP-RETAIL-0313A",
            "quantity": 300,
            "unit_of_measure": "units",
            "kdes": {
                "ship_date": "2026-03-13",
                "ship_from_location": "FreshCo DC, Stockton CA",
                "ship_to_location": "Whole Foods Market #1042, Sacramento CA",
                "carrier": "Regional Fresh Delivery",
                "bol_number": "BOL-2026-0313-FC-RETAIL-A",
            },
        }
    )
    events.append(
        {
            "cte_type": "shipping",
            "timestamp": "2026-03-13T15:30:00Z",
            "location_name": "FreshCo DC - Stockton",
            "product_description": "Spring Mix Salad Kit - 12oz",
            "traceability_lot_code": "TLC-FC-SHIP-RETAIL-0313B",
            "quantity": 300,
            "unit_of_measure": "units",
            "kdes": {
                "ship_date": "2026-03-13",
                "ship_from_location": "FreshCo DC, Stockton CA",
                "ship_to_location": "Safeway Store #2781, Oakland CA",
                "carrier": "Regional Fresh Delivery",
                "bol_number": "BOL-2026-0313-FC-RETAIL-B",
            },
        }
    )

    # ── Day 3: March 14 — Green Leaf Growers flow (clean lot) ──
    events.append(
        {
            "cte_type": "harvesting",
            "timestamp": "2026-03-14T06:00:00Z",
            "location_name": "Green Leaf Growers - Field 2",
            "product_description": "Chopped Romaine - Foodservice",
            "traceability_lot_code": "TLC-GLG-HARVEST-0314",
            "quantity": 1800,
            "unit_of_measure": "lbs",
            "kdes": {
                "harvest_date": "2026-03-14",
                "location_name": "Green Leaf Growers - Field 2",
                "farm_name": "Green Leaf Growers",
                "growing_area": "Field 2 - East",
                "gtin": "00611269991017",
            },
        }
    )
    events.append(
        {
            "cte_type": "cooling",
            "timestamp": "2026-03-14T08:00:00Z",
            "location_name": "Green Leaf Growers - Forced Air Cooler",
            "product_description": "Chopped Romaine - Foodservice",
            "traceability_lot_code": "TLC-GLG-COOL-0314",
            "quantity": 1800,
            "unit_of_measure": "lbs",
            "kdes": {
                "cooling_date": "2026-03-14",
                "location_name": "Green Leaf Growers - Forced Air Cooler",
                "cooling_method": "forced_air",
                "target_temperature": "36",
                "input_tlc": "TLC-GLG-HARVEST-0314",
            },
        }
    )
    events.append(
        {
            "cte_type": "initial_packing",
            "timestamp": "2026-03-14T11:00:00Z",
            "location_name": "Green Leaf Growers - Pack House",
            "product_description": "Chopped Romaine - Foodservice 2lb",
            "traceability_lot_code": "TLC-GLG-PACK-0314",
            "quantity": 450,
            "unit_of_measure": "cases",
            "kdes": {
                "packing_date": "2026-03-14",
                "location_name": "Green Leaf Growers - Pack House",
                "package_type": "2lb_foodservice_bag",
                "upc": "00611269991017",
                "input_tlc": "TLC-GLG-COOL-0314",
            },
        }
    )
    events.append(
        {
            "cte_type": "shipping",
            "timestamp": "2026-03-14T14:30:00Z",
            "location_name": "Green Leaf Growers",
            "product_description": "Chopped Romaine - Foodservice 2lb",
            "traceability_lot_code": "TLC-GLG-SHIP-0314",
            "quantity": 450,
            "unit_of_measure": "cases",
            "kdes": {
                "ship_date": "2026-03-14",
                "ship_from_location": "Green Leaf Growers, Watsonville CA",
                "ship_to_location": "Pacific DC, Portland OR",
                "carrier": "Northwest Cold Freight",
                "bol_number": "BOL-2026-0314-GLG-001",
            },
        }
    )

    # ── Day 5: March 15 — Receiving at Pacific DC ──
    events.append(
        {
            "cte_type": "receiving",
            "timestamp": "2026-03-15T07:00:00Z",
            "location_name": "Pacific Distribution Center - Portland",
            "product_description": "Chopped Romaine - Foodservice 2lb",
            "traceability_lot_code": "TLC-GLG-RECV-0315",
            "quantity": 450,
            "unit_of_measure": "cases",
            "kdes": {
                "receive_date": "2026-03-15",
                "receiving_location": "Pacific DC - Portland, OR",
                "temperature_on_arrival": "37.2",
                "po_number": "PO-PDC-2026-0314-001",
                "input_tlc": "TLC-GLG-SHIP-0314",
            },
        }
    )

    return events


# ══════════════════════════════════════════════════════════════════════
#  MAIN EXECUTION
# ══════════════════════════════════════════════════════════════════════


def _exit_code(results) -> int:
    """Aggregate seeding errors into a process exit code (0 means clean)."""
    return 1 if results.get("errors") else 0


def main(argv=None):
    global BASE, INGEST_URL, PRODUCTS_URL, SUPPLIERS_URL
    args = _parse_args(argv)
    BASE = args.base_url
    ensure_local_target(BASE, args.allow_production)
    INGEST_URL = f"{BASE}/api/v1/webhooks/ingest"
    PRODUCTS_URL = f"{BASE}/api/v1/products/{TENANT_ID}"
    SUPPLIERS_URL = f"{BASE}/api/v1/suppliers/{TENANT_ID}"
    results = {}
    # HTTP failures are collected here so the run exits nonzero instead
    # of logging them as successes.
    errors: list = []

    # ── Step 1: Add suppliers ──
    print("=" * 60)
    print("STEP 1: Seeding Suppliers")
    print("=" * 60)
    seeded_suppliers = 0
    for s in SUPPLIERS:
        print(f"  Adding: {s['name']}...")
        resp = api_post(SUPPLIERS_URL, s)
        if "error" in resp:
            print(f"    → error ({resp.get('error')})")
            errors.append(f"supplier {s['name']}: HTTP {resp.get('error')}")
        else:
            print("    → ok")
            seeded_suppliers += 1
    results["suppliers"] = seeded_suppliers

    # ── Step 2: Add products ──
    print("\n" + "=" * 60)
    print("STEP 2: Seeding Products")
    print("=" * 60)
    seeded_products = 0
    for p in PRODUCTS:
        print(f"  Adding: {p['name']}...")
        resp = api_post(PRODUCTS_URL, p)
        if "error" in resp:
            print(f"    → error ({resp.get('error')})")
            errors.append(f"product {p['name']}: HTTP {resp.get('error')}")
        else:
            print("    → ok")
            seeded_products += 1
    results["products"] = seeded_products

    # ── Step 3: Ingest CTE events ──
    print("\n" + "=" * 60)
    print("STEP 3: Ingesting CTE Events (Full Supply Chain)")
    print("=" * 60)
    events = build_supply_chain_events()
    print(f"  Total events: {len(events)}")

    payload = {
        "tenant_id": TENANT_ID,
        "source": "lifecycle_test",
        "events": events,
    }
    resp = api_post(INGEST_URL, payload)
    if "error" in resp:
        print(f"  Ingest request failed: HTTP {resp.get('error')}")
        errors.append(f"ingest: HTTP {resp.get('error')}")
        accepted, rejected = 0, 0
    else:
        accepted = resp.get("accepted", 0)
        rejected = resp.get("rejected", 0)
        print(f"  Accepted: {accepted}  Rejected: {rejected}")
        if rejected > 0:
            errors.append(f"ingest: {rejected} event(s) rejected")
            for ev in resp.get("events", []):
                if ev.get("status") == "rejected":
                    print(f"    REJECTED {ev.get('cte_type', '?')}: {ev.get('errors', [])}")
    results["cte_events"] = {"accepted": accepted, "rejected": rejected}

    # ── Step 4: Check compliance score ──
    print("\n" + "=" * 60)
    print("STEP 4: Checking Compliance Score")
    print("=" * 60)
    time.sleep(2)  # Let the ingestion settle
    score_url = f"{BASE}/api/v1/compliance/{TENANT_ID}"
    score = api_get(score_url)
    if "error" not in score:
        print(f"  Overall Score: {score.get('overall_score', 'N/A')}")
        print(f"  Grade: {score.get('grade', 'N/A')}")
        for cat in score.get("categories", []):
            print(f"    {cat.get('name', '?')}: {cat.get('score', '?')}%")
    else:
        print(f"  Could not fetch score: {score}")
        errors.append(f"compliance: HTTP {score.get('error')}")
    results["compliance"] = score

    # ── Step 5: Check audit log ──
    print("\n" + "=" * 60)
    print("STEP 5: Checking Audit Log")
    print("=" * 60)
    audit_url = f"{BASE}/api/v1/audit-log/{TENANT_ID}?page=1&page_size=5"
    audit = api_get(audit_url)
    if "error" not in audit:
        print(f"  Total entries: {audit.get('total', 0)}")
        for entry in audit.get("entries", [])[:5]:
            print(f"    [{entry.get('timestamp', '?')[:19]}] {entry.get('event_type')}: {entry.get('action')}")
    else:
        print(f"  Could not fetch audit log: {audit}")
        errors.append(f"audit-log: HTTP {audit.get('error')}")
    results["audit_log"] = audit

    # ── Step 6: Run recall simulation ──
    print("\n" + "=" * 60)
    print("STEP 6: Running Recall Simulation (E. coli in TLC-VFF-HARVEST-0312)")
    print("=" * 60)
    sim_url = f"{BASE}/api/v1/recall-simulations/run"
    sim_payload = {
        "tenant_id": TENANT_ID,
        "scenario": "custom",
        "contaminated_lot": "TLC-VFF-HARVEST-0312",
        "contaminant": "E. coli O157:H7",
        "source_location": "Valley Fresh Farms - Field 12",
        "product": "Romaine Lettuce Hearts - Organic",
        "severity": "critical",
    }
    sim_resp = api_post(sim_url, sim_payload)
    print(f"  Simulation result: {json.dumps(sim_resp, indent=2)[:500]}")
    if "error" in sim_resp:
        errors.append(f"recall-simulation: HTTP {sim_resp.get('error')}")
    results["recall_simulation"] = sim_resp

    # ── Step 7: Get recall readiness report ──
    print("\n" + "=" * 60)
    print("STEP 7: Recall Readiness Report")
    print("=" * 60)
    report_url = f"{BASE}/api/v1/recall-report/{TENANT_ID}/report"
    report = api_get(report_url)
    if "error" not in report:
        print(f"  Readiness Score: {report.get('overall_score', 'N/A')}")
        print(f"  Grade: {report.get('grade', 'N/A')}")
        for dim in report.get("dimensions", []):
            print(f"    {dim.get('name', '?')}: {dim.get('score', '?')}%")
    else:
        print(f"  Could not fetch recall report: {report}")
        errors.append(f"recall-report: HTTP {report.get('error')}")
    results["recall_report"] = report

    # ── Step 8: FDA Export ──
    print("\n" + "=" * 60)
    print("STEP 8: FDA Export (contaminated lot)")
    print("=" * 60)
    export_url = f"{BASE}/api/v1/fda/export?tlc=TLC-VFF-HARVEST-0312"
    export_resp = api_get(export_url)
    if isinstance(export_resp, dict) and "error" not in export_resp:
        print("  Export generated successfully")
        print(f"  Preview: {json.dumps(export_resp, indent=2)[:300]}")
    else:
        print(f"  Export result: {str(export_resp)[:300]}")
        errors.append(f"fda-export: {str(export_resp)[:100]}")
    results["fda_export"] = str(export_resp)[:500]

    # ── Step 9: Mock audit drill ──
    print("\n" + "=" * 60)
    print("STEP 9: Starting Mock FDA Audit Drill")
    print("=" * 60)
    drill_url = f"{BASE}/api/v1/mock-audit/drill/start"
    drill_payload = {
        "tenant_id": TENANT_ID,
        "drill_type": "fda_24hr_trace",
        "target_lot": "TLC-VFF-HARVEST-0312",
        "product": "Romaine Lettuce Hearts - Organic",
    }
    drill_resp = api_post(drill_url, drill_payload)
    print(f"  Drill result: {json.dumps(drill_resp, indent=2)[:500]}")
    if "error" in drill_resp:
        errors.append(f"mock-drill: HTTP {drill_resp.get('error')}")
    results["mock_drill"] = drill_resp

    # ── Summary ──
    print("\n" + "=" * 60)
    print("LIFECYCLE TEST COMPLETE")
    print("=" * 60)
    print(f"  Suppliers seeded: {results['suppliers']}")
    print(f"  Products seeded: {results['products']}")
    print(f"  CTE events: {results['cte_events']}")
    if errors:
        print(f"  ERRORS ({len(errors)}):")
        for err in errors:
            print(f"    - {err}")
    print()
    results["errors"] = errors
    results["success"] = not errors

    # Write full results to file
    outfile = "/sessions/amazing-trusting-pascal/mnt/RegEngine/scripts/lifecycle_test_results.json"
    with open(outfile, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"  Full results saved to: {outfile}")

    return results


if __name__ == "__main__":
    sys.exit(_exit_code(main()))
