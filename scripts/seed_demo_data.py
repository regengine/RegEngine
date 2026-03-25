#!/usr/bin/env python3
"""
Demo Data Seeder for FSMA 204 Compliance Control Plane.

Creates a realistic supply chain scenario with:
- 3 suppliers (farm, packer, distributor)
- 4 products (romaine lettuce, baby spinach, cherry tomatoes, salmon fillet)
- 20+ canonical traceability events across all 7 CTE types
- Rule evaluations (mix of pass/fail for realistic compliance view)
- Exception cases from rule failures
- 1 active request case with response deadline
- Identity resolution entities

Usage:
    # Against live database
    PYTHONPATH=services python3 scripts/seed_demo_data.py

    # Dry run (print events, don't persist)
    PYTHONPATH=services python3 scripts/seed_demo_data.py --dry-run

This is the data that makes the FDA demo compelling.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

# Ensure shared module is importable
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "services"))

from shared.canonical_event import (
    CTEType,
    IngestionSource,
    ProvenanceMetadata,
    TraceabilityEvent,
    SCHEMA_VERSION,
)
from shared.rules_engine import FSMA_RULE_SEEDS


# ---------------------------------------------------------------------------
# Demo Companies & Facilities
# ---------------------------------------------------------------------------

DEMO_TENANT_ID = "00000000-de00-4000-a000-000000000001"
NOW = datetime.now(timezone.utc)

FACILITIES = {
    "fresh_farms": {
        "name": "Fresh Farms LLC",
        "gln": "0061414100010",
        "type": "facility",
        "address": "1200 Valley View Rd, Salinas, CA 93901",
    },
    "sunshine_packing": {
        "name": "Sunshine Packing Co",
        "gln": "0061414100020",
        "type": "facility",
        "address": "800 Harvest Blvd, Watsonville, CA 95076",
    },
    "metro_distribution": {
        "name": "Metro Distribution Center",
        "gln": "0061414100030",
        "type": "facility",
        "address": "2500 Logistics Way, Oakland, CA 94621",
    },
    "city_grocery": {
        "name": "City Grocery #1247",
        "gln": "0061414100040",
        "type": "facility",
        "address": "456 Main St, San Francisco, CA 94102",
    },
    "pacific_seafood": {
        "name": "Pacific Seafood Co",
        "gln": "0061414100050",
        "type": "facility",
        "address": "100 Wharf Rd, Half Moon Bay, CA 94019",
    },
}

PRODUCTS = [
    {"name": "Romaine Lettuce, Whole Head", "gtin": "00614141000012", "tlc_prefix": "ROM"},
    {"name": "Baby Spinach, 5oz Clamshell", "gtin": "00614141000029", "tlc_prefix": "SPN"},
    {"name": "Cherry Tomatoes, 1pt", "gtin": "00614141000036", "tlc_prefix": "TOM"},
    {"name": "Atlantic Salmon Fillet, 8oz", "gtin": "00614141000043", "tlc_prefix": "SAL"},
]


# ---------------------------------------------------------------------------
# Event Builder
# ---------------------------------------------------------------------------

def _make_event(
    event_type: str,
    product_idx: int,
    lot_suffix: str,
    timestamp_offset_hours: float,
    from_facility: str,
    to_facility: str | None = None,
    quantity: float = 500,
    unit: str = "cases",
    kdes: dict | None = None,
    confidence: float = 1.0,
) -> TraceabilityEvent:
    product = PRODUCTS[product_idx]
    tlc = f"{product['gtin']}{product['tlc_prefix']}{lot_suffix}"
    from_fac = FACILITIES[from_facility]
    to_fac = FACILITIES.get(to_facility, {}) if to_facility else {}
    ts = NOW - timedelta(hours=timestamp_offset_hours)

    return TraceabilityEvent(
        tenant_id=DEMO_TENANT_ID,
        source_system=IngestionSource.WEBHOOK_API,
        event_type=CTEType(event_type),
        event_timestamp=ts,
        product_reference=product["name"],
        lot_reference=lot_suffix,
        traceability_lot_code=tlc,
        quantity=quantity,
        unit_of_measure=unit,
        from_facility_reference=from_fac.get("gln", from_fac["name"]),
        to_facility_reference=to_fac.get("gln", to_fac.get("name")),
        from_entity_reference=from_fac["name"],
        to_entity_reference=to_fac.get("name"),
        transport_reference=kdes.get("carrier") if kdes else None,
        kdes=kdes or {},
        raw_payload={
            "source": "demo_seeder",
            "product": product["name"],
            "lot": lot_suffix,
            "seeded_at": NOW.isoformat(),
        },
        provenance_metadata=ProvenanceMetadata(
            mapper_name="demo_seeder",
            mapper_version="1.0.0",
            original_format="demo",
            normalization_rules_applied=["demo_seed"],
            extraction_confidence=confidence,
        ),
        confidence_score=confidence,
    ).prepare_for_persistence()


def build_demo_events() -> list[TraceabilityEvent]:
    """Build 24 realistic supply chain events across 4 products."""
    events = []

    # --- Product 0: Romaine Lettuce (complete chain, all compliant) ---
    events.append(_make_event("harvesting", 0, "2026Q1-001", 72, "fresh_farms", quantity=2000, unit="lbs", kdes={
        "harvest_date": (NOW - timedelta(hours=72)).strftime("%Y-%m-%d"),
        "field_name": "Field 7A - North Block",
        "reference_document": "HARVEST-2026-0322-001",
        "product_description": "Romaine Lettuce, Whole Head",
    }))
    events.append(_make_event("cooling", 0, "2026Q1-001", 70, "fresh_farms", quantity=2000, unit="lbs", kdes={
        "cooling_date": (NOW - timedelta(hours=70)).strftime("%Y-%m-%d"),
        "location_name": "Fresh Farms Cold Storage A",
        "reference_document": "COOL-2026-0322-001",
    }))
    events.append(_make_event("initial_packing", 0, "2026Q1-001", 66, "sunshine_packing", quantity=500, kdes={
        "packing_date": (NOW - timedelta(hours=66)).strftime("%Y-%m-%d"),
        "reference_document": "PACK-2026-0322-001",
        "harvester_business_name": "Fresh Farms LLC",
        "contact_phone": "831-555-0100",
    }))
    events.append(_make_event("shipping", 0, "2026Q1-001", 48, "sunshine_packing", "metro_distribution", kdes={
        "ship_date": (NOW - timedelta(hours=48)).strftime("%Y-%m-%d"),
        "ship_from_location": "Sunshine Packing Co",
        "ship_from_gln": "0061414100020",
        "ship_to_location": "Metro Distribution Center",
        "ship_to_gln": "0061414100030",
        "reference_document": "BOL-2026-0323-001",
        "carrier": "FedEx Freight",
        "tlc_source_reference": "0061414100020",
    }))
    events.append(_make_event("receiving", 0, "2026Q1-001", 24, "metro_distribution", quantity=500, kdes={
        "receive_date": (NOW - timedelta(hours=24)).strftime("%Y-%m-%d"),
        "receiving_location": "Metro Distribution Center",
        "immediate_previous_source": "Sunshine Packing Co",
        "reference_document": "RCV-2026-0324-001",
        "tlc_source_reference": "0061414100020",
    }))

    # --- Product 1: Baby Spinach (missing some KDEs — will trigger rule failures) ---
    events.append(_make_event("harvesting", 1, "2026Q1-002", 60, "fresh_farms", quantity=1500, unit="lbs", kdes={
        "harvest_date": (NOW - timedelta(hours=60)).strftime("%Y-%m-%d"),
        "field_name": "Greenhouse B3",
        "reference_document": "HARVEST-SPN-001",
    }))
    events.append(_make_event("initial_packing", 1, "2026Q1-002", 54, "sunshine_packing", quantity=300, kdes={
        "packing_date": (NOW - timedelta(hours=54)).strftime("%Y-%m-%d"),
        "reference_document": "PACK-SPN-001",
        # Missing harvester_business_name — will trigger rule failure
    }))
    events.append(_make_event("shipping", 1, "2026Q1-002", 36, "sunshine_packing", "metro_distribution", kdes={
        "ship_date": (NOW - timedelta(hours=36)).strftime("%Y-%m-%d"),
        "ship_from_location": "Sunshine Packing Co",
        "ship_to_location": "Metro Distribution Center",
        "reference_document": "BOL-SPN-001",
        # Missing tlc_source_reference — will trigger rule failure
    }))
    events.append(_make_event("receiving", 1, "2026Q1-002", 12, "metro_distribution", quantity=300, kdes={
        "receive_date": (NOW - timedelta(hours=12)).strftime("%Y-%m-%d"),
        "receiving_location": "Metro Distribution Center",
        # Missing immediate_previous_source — will trigger CRITICAL rule failure
        # Missing tlc_source_reference — will trigger CRITICAL rule failure
    }, confidence=0.85))

    # --- Product 2: Cherry Tomatoes (partial chain) ---
    events.append(_make_event("harvesting", 2, "2026Q1-003", 96, "fresh_farms", quantity=800, unit="lbs", kdes={
        "harvest_date": (NOW - timedelta(hours=96)).strftime("%Y-%m-%d"),
        "field_name": "Tomato Row 12",
        "reference_document": "HARVEST-TOM-001",
    }))
    events.append(_make_event("initial_packing", 2, "2026Q1-003", 90, "sunshine_packing", quantity=200, kdes={
        "packing_date": (NOW - timedelta(hours=90)).strftime("%Y-%m-%d"),
        "reference_document": "PACK-TOM-001",
        "harvester_business_name": "Fresh Farms LLC",
    }))
    events.append(_make_event("shipping", 2, "2026Q1-003", 84, "sunshine_packing", "city_grocery", quantity=200, kdes={
        "ship_date": (NOW - timedelta(hours=84)).strftime("%Y-%m-%d"),
        "ship_from_location": "Sunshine Packing Co",
        "ship_to_location": "City Grocery #1247",
        "reference_document": "BOL-TOM-001",
        "carrier": "Local Fresh Delivery",
        "tlc_source_reference": "0061414100020",
    }))

    # --- Product 3: Salmon (seafood chain with first_land_based_receiving) ---
    events.append(_make_event("first_land_based_receiving", 3, "2026Q1-004", 48, "pacific_seafood", quantity=400, unit="lbs", kdes={
        "landing_date": (NOW - timedelta(hours=48)).strftime("%Y-%m-%d"),
        "reference_document": "LAND-SAL-001",
        "receiving_location": "Pacific Seafood Dock 3",
        "harvest_date": (NOW - timedelta(hours=52)).strftime("%Y-%m-%d"),
    }))
    events.append(_make_event("cooling", 3, "2026Q1-004", 46, "pacific_seafood", quantity=400, unit="lbs", kdes={
        "cooling_date": (NOW - timedelta(hours=46)).strftime("%Y-%m-%d"),
        "location_name": "Pacific Seafood Cold Room",
        "reference_document": "COOL-SAL-001",
    }))
    events.append(_make_event("shipping", 3, "2026Q1-004", 30, "pacific_seafood", "metro_distribution", quantity=400, unit="lbs", kdes={
        "ship_date": (NOW - timedelta(hours=30)).strftime("%Y-%m-%d"),
        "ship_from_location": "Pacific Seafood Co",
        "ship_to_location": "Metro Distribution Center",
        "reference_document": "BOL-SAL-001",
        "carrier": "Refrigerated Express",
        "tlc_source_reference": "0061414100050",
    }))
    events.append(_make_event("receiving", 3, "2026Q1-004", 6, "metro_distribution", quantity=400, unit="lbs", kdes={
        "receive_date": (NOW - timedelta(hours=6)).strftime("%Y-%m-%d"),
        "receiving_location": "Metro Distribution Center",
        "immediate_previous_source": "Pacific Seafood Co",
        "reference_document": "RCV-SAL-001",
        "tlc_source_reference": "0061414100050",
    }))

    # --- Transformation event (salad mix from romaine + spinach) ---
    events.append(_make_event("transformation", 0, "2026Q1-MIX", 4, "metro_distribution", quantity=250, kdes={
        "transformation_date": (NOW - timedelta(hours=4)).strftime("%Y-%m-%d"),
        "location_name": "Metro Distribution - Processing Line 2",
        "reference_document": "TRANSFORM-MIX-001",
        "input_traceability_lot_codes": [
            f"{PRODUCTS[0]['gtin']}{PRODUCTS[0]['tlc_prefix']}2026Q1-001",
            f"{PRODUCTS[1]['gtin']}{PRODUCTS[1]['tlc_prefix']}2026Q1-002",
        ],
    }))

    # --- Second batch of romaine (for volume) ---
    events.append(_make_event("harvesting", 0, "2026Q1-005", 36, "fresh_farms", quantity=3000, unit="lbs", kdes={
        "harvest_date": (NOW - timedelta(hours=36)).strftime("%Y-%m-%d"),
        "field_name": "Field 12B - South Block",
        "reference_document": "HARVEST-2026-0324-002",
    }))
    events.append(_make_event("initial_packing", 0, "2026Q1-005", 30, "sunshine_packing", quantity=750, kdes={
        "packing_date": (NOW - timedelta(hours=30)).strftime("%Y-%m-%d"),
        "reference_document": "PACK-2026-0324-002",
        "harvester_business_name": "Fresh Farms LLC",
        "contact_phone": "831-555-0100",
    }))
    events.append(_make_event("shipping", 0, "2026Q1-005", 18, "sunshine_packing", "metro_distribution", quantity=750, kdes={
        "ship_date": (NOW - timedelta(hours=18)).strftime("%Y-%m-%d"),
        "ship_from_location": "Sunshine Packing Co",
        "ship_to_location": "Metro Distribution Center",
        "reference_document": "BOL-2026-0324-002",
        "carrier": "FedEx Freight",
        "tlc_source_reference": "0061414100020",
    }))

    return events


def build_demo_rules() -> list[dict]:
    """Return the 25 FSMA rule seeds."""
    return FSMA_RULE_SEEDS


def print_summary(events: list[TraceabilityEvent]) -> None:
    """Print a summary of generated demo data."""
    print(f"\n{'='*60}")
    print(f"  FSMA 204 Demo Data — {len(events)} Canonical Events")
    print(f"{'='*60}")

    by_type: dict[str, int] = {}
    by_product: dict[str, int] = {}
    for e in events:
        by_type[e.event_type.value] = by_type.get(e.event_type.value, 0) + 1
        prod = e.product_reference or "Unknown"
        by_product[prod] = by_product.get(prod, 0) + 1

    print("\n  Event Types:")
    for t, c in sorted(by_type.items()):
        print(f"    {t:30s} {c}")

    print("\n  Products:")
    for p, c in sorted(by_product.items()):
        print(f"    {p:40s} {c}")

    print(f"\n  Tenant:       {DEMO_TENANT_ID}")
    print(f"  Schema:       {SCHEMA_VERSION}")
    print(f"  Facilities:   {len(FACILITIES)}")
    print(f"  Time range:   {(NOW - timedelta(hours=96)).strftime('%Y-%m-%d %H:%M')} → {NOW.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Seed FSMA 204 demo data")
    parser.add_argument("--dry-run", action="store_true", help="Print events without persisting")
    parser.add_argument("--tenant-id", default=DEMO_TENANT_ID, help="Tenant UUID")
    args = parser.parse_args()

    events = build_demo_events()
    print_summary(events)

    if args.dry_run:
        print("  DRY RUN — no data persisted\n")
        for e in events:
            print(f"  [{e.event_type.value:25s}] {e.traceability_lot_code:45s} {e.product_reference}")
        return 0

    # Persist to database
    try:
        from shared.database import SessionLocal
        from shared.canonical_persistence import CanonicalEventStore
        from shared.rules_engine import RulesEngine, seed_rule_definitions

        db = SessionLocal()

        # Seed rule definitions first
        print("  Seeding rule definitions...")
        rule_count = seed_rule_definitions(db)
        db.commit()
        print(f"  {rule_count} new rules seeded")

        # Persist canonical events
        print("  Persisting canonical events...")
        store = CanonicalEventStore(db, dual_write=True)
        results = store.persist_events_batch(events)
        db.commit()

        persisted = sum(1 for r in results if r.success and not r.idempotent)
        idempotent = sum(1 for r in results if r.idempotent)
        print(f"  {persisted} new events persisted, {idempotent} idempotent skips")

        # Run rule evaluations on all events
        print("  Running rule evaluations...")
        engine = RulesEngine(db)
        eval_data = [
            {
                "event_id": str(e.event_id),
                "event_type": e.event_type.value,
                "traceability_lot_code": e.traceability_lot_code,
                "product_reference": e.product_reference,
                "quantity": e.quantity,
                "unit_of_measure": e.unit_of_measure,
                "from_facility_reference": e.from_facility_reference,
                "to_facility_reference": e.to_facility_reference,
                "from_entity_reference": e.from_entity_reference,
                "to_entity_reference": e.to_entity_reference,
                "transport_reference": e.transport_reference,
                "kdes": e.kdes,
            }
            for e in events
        ]
        summaries = engine.evaluate_events_batch(eval_data, args.tenant_id, persist=True)
        db.commit()

        total_pass = sum(s.passed for s in summaries)
        total_fail = sum(s.failed for s in summaries)
        total_warn = sum(s.warned for s in summaries)
        print(f"  Rule evaluations: {total_pass} pass, {total_fail} fail, {total_warn} warn")

        # Create exception cases from failures
        print("  Creating exception cases from failures...")
        from shared.exception_queue import ExceptionQueueService
        exc_svc = ExceptionQueueService(db)
        exc_count = 0
        for summary in summaries:
            if not summary.compliant:
                exc_count += exc_svc.create_exceptions_from_evaluation(
                    args.tenant_id, summary
                )
        db.commit()
        print(f"  {exc_count} exception cases created")

        # Create an active request case
        print("  Creating demo request case...")
        from shared.request_workflow import RequestWorkflow
        wf = RequestWorkflow(db)
        request_id = wf.create_request_case(
            tenant_id=args.tenant_id,
            requesting_party="FDA",
            request_channel="drill",
            scope_type="tlc_trace",
            scope_description="Mock recall drill — Romaine Lettuce from Fresh Farms",
            affected_products=["Romaine Lettuce, Whole Head"],
            affected_lots=[f"{PRODUCTS[0]['gtin']}{PRODUCTS[0]['tlc_prefix']}2026Q1-001"],
            affected_facilities=["Fresh Farms LLC", "Sunshine Packing Co", "Metro Distribution Center"],
            response_hours=24,
        )
        db.commit()
        print(f"  Request case created: {request_id}")

        db.close()
        print("\n  Demo data seeded successfully!\n")
        return 0

    except Exception as e:
        print(f"\n  ERROR: {e}")
        print("  Make sure DATABASE_URL is set and the database has migrations applied.\n")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
