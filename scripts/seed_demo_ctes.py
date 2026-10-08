#!/usr/bin/env python3
"""Seed all 7 FSMA 204 CTE types to push compliance score toward 100%.

Usage:
    python3 scripts/seed_demo_ctes.py [--base BASE_URL] [--allow-production]
    python3 scripts/seed_demo_ctes.py [BASE_URL] [--allow-production]

Defaults to the local ingestion service (http://localhost:8002) and refuses
to target any non-local host unless BOTH an explicit URL and
--allow-production are given. The tenant API key comes from the
REGENGINE_TENANT_API_KEY environment variable only, never from CLI args.
TLS certificate errors are never downgraded; they abort the run.
"""

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE = "http://localhost:8002"
BASE_ENV_VAR = "SEED_BASE_URL"
API_KEY_ENV_VAR = "REGENGINE_TENANT_API_KEY"  # pragma: allowlist secret -- environment variable name
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class UnsafeTargetError(ValueError):
    """Raised when a seed target is not local and not explicitly allowed."""


def is_local_target(base: str) -> bool:
    """Return True when the URL targets this machine only."""
    try:
        host = (urllib.parse.urlparse(base).hostname or "").lower()
    except ValueError:
        return False
    return host in LOCAL_HOSTS


def resolve_base(cli_base=None, *, allow_production: bool = False) -> str:
    """Resolve the seed target. Defaults to localhost.

    A non-local target is returned only when it was explicitly supplied
    (CLI argument or SEED_BASE_URL) AND allow_production is True.
    Otherwise raises UnsafeTargetError.
    """
    env_base = os.getenv(BASE_ENV_VAR, "").strip()
    if cli_base:
        target, explicit = cli_base.strip(), True
    elif env_base:
        target, explicit = env_base, True
    else:
        target, explicit = DEFAULT_BASE, False
    if not is_local_target(target):
        if not explicit:
            raise UnsafeTargetError(f"Refusing to seed non-local target {target!r} without an explicit URL.")
        if not allow_production:
            raise UnsafeTargetError(
                f"Refusing to seed non-local target {target!r}. "
                "Pass --allow-production with an explicit URL only if you "
                "intentionally want demo data in that environment."
            )
    return target


def get_api_key() -> str:
    """Read the tenant API key from the environment only."""
    api_key = os.getenv(API_KEY_ENV_VAR, "").strip()
    if not api_key:
        raise UnsafeTargetError(
            f"No API key. Set {API_KEY_ENV_VAR} in the environment. API keys are never accepted as CLI arguments."
        )
    return api_key


def create_ssl_context() -> ssl.SSLContext:
    """Return a default verifying SSL context. Never downgraded."""
    return ssl.create_default_context()


def is_tls_cert_failure(exc: BaseException) -> bool:
    """True when exc is (or urllib-wraps) an SSL cert verification failure.

    urllib.request.urlopen surfaces TLS failures as
    urllib.error.URLError(reason=SSLCertVerificationError), never as the
    bare ssl exception, so both shapes must be detected.
    """
    if isinstance(exc, ssl.SSLCertVerificationError):
        return True
    return isinstance(getattr(exc, "reason", None), ssl.SSLCertVerificationError)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Seed demo CTE events (defaults to localhost).")
    ap.add_argument("base_positional", nargs="?", default=None, help="Explicit target base URL.")
    ap.add_argument("--base", default=None, help="Explicit target base URL.")
    ap.add_argument(
        "--allow-production",
        action="store_true",
        help="Allow seeding a non-local target. Requires an explicit URL.",
    )
    return ap


# One event per CTE type with all required KDEs (including reference_document)
EVENTS = [
    {
        "cte_type": "harvesting",
        "timestamp": "2026-03-26T06:00:00Z",
        "location_name": "Valley Fresh Farms - Field 12",
        "product_description": "Romaine Lettuce - Organic",
        "traceability_lot_code": "TLC-SEED-HARVEST-001",
        "quantity": 2000,
        "unit_of_measure": "lbs",
        "kdes": {
            "harvest_date": "2026-03-26",
            "location_name": "Valley Fresh Farms - Field 12",
            "farm_name": "Valley Fresh Farms",
            "growing_area": "Field 12 - Block A",
            "reference_document": "INV-VFF-2026-0326",
        },
    },
    {
        "cte_type": "cooling",
        "timestamp": "2026-03-26T08:00:00Z",
        "location_name": "Valley Fresh Farms - Cooling Facility",
        "product_description": "Romaine Lettuce - Organic",
        "traceability_lot_code": "TLC-SEED-COOL-001",
        "quantity": 2000,
        "unit_of_measure": "lbs",
        "kdes": {
            "cooling_date": "2026-03-26",
            "location_name": "Valley Fresh Farms - Cooling Facility",
            "cooling_method": "vacuum_cooling",
            "target_temperature": "34",
            "reference_document": "COOL-VFF-2026-0326",
        },
    },
    {
        "cte_type": "initial_packing",
        "timestamp": "2026-03-26T10:00:00Z",
        "location_name": "Valley Fresh Farms - Pack House",
        "product_description": "Romaine Lettuce - Organic 5oz Bag",
        "traceability_lot_code": "TLC-SEED-PACK-001",
        "quantity": 800,
        "unit_of_measure": "cases",
        "kdes": {
            "packing_date": "2026-03-26",
            "location_name": "Valley Fresh Farms - Pack House",
            "package_type": "5oz_bag",
            "upc": "0011110838001",
            "reference_document": "PACK-VFF-2026-0326",
            "harvester_business_name": "Valley Fresh Farms LLC",
            "harvester_business_phone": "+1-202-555-0100",
        },
    },
    {
        "cte_type": "shipping",
        "timestamp": "2026-03-26T14:00:00Z",
        "location_name": "Valley Fresh Farms",
        "product_description": "Romaine Lettuce - Organic 5oz Bag",
        "traceability_lot_code": "TLC-SEED-SHIP-001",
        "quantity": 800,
        "unit_of_measure": "cases",
        "kdes": {
            "ship_date": "2026-03-26",
            "ship_from_location": "Valley Fresh Farms",
            "ship_to_location": "FreshCo Distribution Center",
            "carrier": "ColdChain Express",
            "bol_number": "BOL-2026-0326-001",
            "reference_document": "BOL-2026-0326-001",
            "tlc_source_reference": "TLC-SEED-PACK-001",
        },
    },
    {
        "cte_type": "first_land_based_receiving",
        "timestamp": "2026-03-26T18:00:00Z",
        "location_name": "Port of Long Beach - Cold Storage",
        "product_description": "Atlantic Salmon - Fresh Fillet",
        "traceability_lot_code": "TLC-SEED-FLBR-001",
        "quantity": 500,
        "unit_of_measure": "lbs",
        "kdes": {
            "landing_date": "2026-03-26",
            "receiving_location": "Port of Long Beach - Cold Storage",
            "vessel_name": "Pacific Star",
            "harvest_area": "FAO Area 27",
            "reference_document": "LAND-PLB-2026-0326",
        },
    },
    {
        "cte_type": "receiving",
        "timestamp": "2026-03-27T08:00:00Z",
        "location_name": "FreshCo Distribution Center",
        "product_description": "Romaine Lettuce - Organic 5oz Bag",
        "traceability_lot_code": "TLC-SEED-RECV-001",
        "quantity": 800,
        "unit_of_measure": "cases",
        "kdes": {
            "receive_date": "2026-03-27",
            "receiving_location": "FreshCo Distribution Center",
            "temperature_on_arrival": "35.2",
            "po_number": "PO-2026-0327-SEED",
            "immediate_previous_source": "Valley Fresh Farms",
            "reference_document": "PO-2026-0327-SEED",
            "tlc_source_reference": "TLC-SEED-SHIP-001",
        },
    },
    {
        "cte_type": "transformation",
        "timestamp": "2026-03-27T10:00:00Z",
        "location_name": "FreshCo Distribution Center - Processing",
        "product_description": "Spring Mix Salad Kit - 12oz",
        "traceability_lot_code": "TLC-SEED-XFORM-001",
        "quantity": 400,
        "unit_of_measure": "units",
        "kdes": {
            "transformation_date": "2026-03-27",
            "input_lot_codes": "TLC-SEED-RECV-001,TLC-SEED-FLBR-001",
            "output_product": "Spring Mix Salad Kit - 12oz",
            "processing_facility": "FreshCo Distribution Center",
            "reference_document": "WO-FC-2026-0327-001",
            "input_traceability_lot_codes": ["TLC-SEED-RECV-001", "TLC-SEED-FLBR-001"],
        },
    },
]


def build_payload() -> dict:
    return {
        "tenant_id": "5946c58f-ddf9-4db0-9baa-acb11c6fce91",
        "source": "demo_seed",
        "events": EVENTS,
    }


def post_events(base: str, api_key: str, ctx: ssl.SSLContext) -> int:
    data = json.dumps(build_payload()).encode()
    req = urllib.request.Request(
        f"{base}/api/v1/webhooks/ingest",
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-RegEngine-API-Key": api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, context=ctx) as resp:
            result = json.loads(resp.read())
            print(json.dumps(result, indent=2))
            accepted = result.get("accepted", 0)
            rejected = result.get("rejected", 0)
            print(f"\nAccepted: {accepted}  Rejected: {rejected}")
            if rejected > 0:
                for ev in result.get("events", []):
                    if ev.get("status") == "rejected":
                        print(f"  {ev['cte_type']}: {ev.get('errors', [])}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"HTTP {e.code}: {body}")
        return 1
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    cli_base = args.base or args.base_positional
    try:
        base = resolve_base(cli_base, allow_production=args.allow_production)
        api_key = get_api_key()
    except UnsafeTargetError as e:
        print(f"ERROR: {e}")
        return 2
    print(f"Seeding demo CTEs to {base}")
    try:
        return post_events(base, api_key, create_ssl_context())
    except ssl.SSLCertVerificationError as e:
        print(f"ERROR: TLS certificate verification failed: {e}. Refusing to continue.")
        return 1
    except urllib.error.URLError as e:
        if is_tls_cert_failure(e):
            print(f"ERROR: TLS certificate verification failed: {e.reason}. Refusing to continue.")
            return 1
        raise


if __name__ == "__main__":
    sys.exit(main())
