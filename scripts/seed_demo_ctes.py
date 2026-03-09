#!/usr/bin/env python3
"""Seed all 7 FSMA 204 CTE types to push compliance score toward 100%.

Usage:
    python3 scripts/seed_demo_ctes.py [BASE_URL] [API_KEY]

Defaults to the production ingestion service URL.
"""
import sys
import json
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "https://believable-respect-production-2fb3.up.railway.app"
API_KEY = sys.argv[2] if len(sys.argv) > 2 else "rge_e8c4b6962620ecb6c43d09e62ab0f65715a7d692eeb0d74000c68bf63d4962ac"
ENDPOINT = f"{BASE}/api/v1/webhooks/ingest"

# One event per CTE type with all required KDEs
EVENTS = [
    {
        "cte_type": "harvesting",
        "timestamp": "2026-03-07T06:00:00Z",
        "location_name": "Valley Fresh Farms - Field 12",
        "product_description": "Romaine Lettuce - Organic",
        "traceability_lot_code": "TLC-SEED-HARVEST-001",
        "quantity": 2000,
        "unit_of_measure": "lbs",
        "kdes": {
            "harvest_date": "2026-03-07",
            "location_name": "Valley Fresh Farms - Field 12",
            "farm_name": "Valley Fresh Farms",
            "growing_area": "Field 12 - Block A",
        },
    },
    {
        "cte_type": "cooling",
        "timestamp": "2026-03-07T08:00:00Z",
        "location_name": "Valley Fresh Farms - Cooling Facility",
        "product_description": "Romaine Lettuce - Organic",
        "traceability_lot_code": "TLC-SEED-COOL-001",
        "quantity": 2000,
        "unit_of_measure": "lbs",
        "kdes": {
            "cooling_date": "2026-03-07",
            "location_name": "Valley Fresh Farms - Cooling Facility",
            "cooling_method": "vacuum_cooling",
            "target_temperature": "34",
        },
    },
    {
        "cte_type": "initial_packing",
        "timestamp": "2026-03-07T10:00:00Z",
        "location_name": "Valley Fresh Farms - Pack House",
        "product_description": "Romaine Lettuce - Organic 5oz Bag",
        "traceability_lot_code": "TLC-SEED-PACK-001",
        "quantity": 800,
        "unit_of_measure": "cases",
        "kdes": {
            "packing_date": "2026-03-07",
            "location_name": "Valley Fresh Farms - Pack House",
            "package_type": "5oz_bag",
            "upc": "0011110838001",
        },
    },
    {
        "cte_type": "shipping",
        "timestamp": "2026-03-07T14:00:00Z",
        "location_name": "Valley Fresh Farms",
        "product_description": "Romaine Lettuce - Organic 5oz Bag",
        "traceability_lot_code": "TLC-SEED-SHIP-001",
        "quantity": 800,
        "unit_of_measure": "cases",
        "kdes": {
            "ship_date": "2026-03-07",
            "ship_from_location": "Valley Fresh Farms",
            "ship_to_location": "FreshCo Distribution Center",
            "carrier": "ColdChain Express",
            "bol_number": "BOL-2026-0307-001",
        },
    },
    {
        "cte_type": "first_land_based_receiving",
        "timestamp": "2026-03-07T18:00:00Z",
        "location_name": "Port of Long Beach - Cold Storage",
        "product_description": "Atlantic Salmon - Fresh Fillet",
        "traceability_lot_code": "TLC-SEED-FLBR-001",
        "quantity": 500,
        "unit_of_measure": "lbs",
        "kdes": {
            "landing_date": "2026-03-07",
            "receiving_location": "Port of Long Beach - Cold Storage",
            "vessel_name": "Pacific Star",
            "harvest_area": "FAO Area 27",
        },
    },
    {
        "cte_type": "receiving",
        "timestamp": "2026-03-08T08:00:00Z",
        "location_name": "FreshCo Distribution Center",
        "product_description": "Romaine Lettuce - Organic 5oz Bag",
        "traceability_lot_code": "TLC-SEED-RECV-001",
        "quantity": 800,
        "unit_of_measure": "cases",
        "kdes": {
            "receive_date": "2026-03-08",
            "receiving_location": "FreshCo Distribution Center",
            "temperature_on_arrival": "35.2",
            "po_number": "PO-2026-0308-SEED",
        },
    },
    {
        "cte_type": "transformation",
        "timestamp": "2026-03-08T10:00:00Z",
        "location_name": "FreshCo Distribution Center - Processing",
        "product_description": "Spring Mix Salad Kit - 12oz",
        "traceability_lot_code": "TLC-SEED-XFORM-001",
        "quantity": 400,
        "unit_of_measure": "units",
        "kdes": {
            "transformation_date": "2026-03-08",
            "input_lot_codes": "TLC-SEED-RECV-001,TLC-SEED-FLBR-001",
            "output_product": "Spring Mix Salad Kit - 12oz",
            "processing_facility": "FreshCo Distribution Center",
        },
    },
]

payload = {
    "tenant_id": "5946c58f-ddf9-4db0-9baa-acb11c6fce91",
    "source": "demo_seed",
    "events": EVENTS,
}

data = json.dumps(payload).encode()
req = urllib.request.Request(
    ENDPOINT,
    data=data,
    headers={
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
    },
    method="POST",
)

try:
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
        print(json.dumps(result, indent=2))
        accepted = result.get("accepted", 0)
        rejected = result.get("rejected", 0)
        print(f"\n✅ Accepted: {accepted}  ❌ Rejected: {rejected}")
        if rejected > 0:
            for ev in result.get("events", []):
                if ev.get("status") == "rejected":
                    print(f"  {ev['cte_type']}: {ev.get('errors', [])}")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"HTTP {e.code}: {body}")
    sys.exit(1)
