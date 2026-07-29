#!/usr/bin/env python3
"""Seed varied FSMA 204 CTE data into the RegEngine FOUNDER demo tenant.

Writes ~13 events across all 7 CTE types, 3 source systems, valid 13-digit
GLNs, and coherent multi-commodity traceability-lot chains — enough to flip
the readiness checks: ingest_records(>=10), multiple_sources(>=2),
cte_coverage(>=4), all_ctes_covered(==7), facility_identifiers(>=50% GLN),
plus chain_integrity / provenance_complete / rules_evaluated.

Mechanism (validated against main @ 8e6e4b6):
  POST {BASE}/api/v1/webhooks/ingest  — one request per source system.
  Auth: preshared master key in X-RegEngine-API-Key (env REGENGINE_API_KEY)
        + X-Tenant-ID = founder tenant  (auth.py:355-398 → tenant from header)
  Required headers the stock scripts/seed_demo_ctes.py omits:
        X-Tenant-ID       (else 401 E_TENANT_HEADER_REQUIRED under master key)
        Idempotency-Key   (else 428/400 — routes.py:56,83 strict)
        X-Webhook-Signature: sha256=<hmac>  (prod HAS WEBHOOK_HMAC_SECRET set)
  Body tenant_id is intentionally NOT set (ignored; conflict -> 409).

Timestamps are within the last ~90 days (route replay window, security.py:232).

Secrets come from the environment ONLY (inject via `railway run`):
  REGENGINE_API_KEY     (required) — prod preshared master key
  WEBHOOK_HMAC_SECRET   (required for the write; prod has it configured)

Usage:
  railway run python3 seed_founder_demo_ctes.py --status    # read-only score
  python3 seed_founder_demo_ctes.py --dry-run               # print+validate, no net
  python3 seed_founder_demo_ctes.py --check                 # GET /health HMAC state
  railway run python3 seed_founder_demo_ctes.py             # SEED prod (writes!)
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

FOUNDER_TENANT = os.getenv("SEED_TENANT_ID", "38e99859-7364-4932-99fa-b1f114bf0202")
DEFAULT_BASE = os.getenv("SEED_BASE_URL", "https://regengine-production.up.railway.app")
SEED_VERSION = "founderseed-v1"  # bump to force re-processing past the 24h idempotency cache


# GS1 check digit — mirrors services/shared/fsma_validation.py:_gs1_check_digit
def gs1_check_digit(digits12: str) -> str:
    total = sum(int(d) * (1 if i % 2 else 3) for i, d in enumerate(reversed(digits12)))
    return str((10 - (total % 10)) % 10)


def gln(base12: str) -> str:
    assert len(base12) == 12 and base12.isdigit(), base12
    return base12 + gs1_check_digit(base12)


F = {
    "vff_field": gln("030600002001"),
    "vff_cool": gln("030600002002"),
    "vff_pack": gln("030600002003"),
    "freshco_dc": gln("030600002010"),
    "freshco_pr": gln("030600002011"),
    "retail_rdc": gln("030600002020"),
    "sungrove_f": gln("030600002030"),
    "sungrove_p": gln("030600002031"),
    "metro_dc": gln("030600002040"),
    "port_glou": gln("030600002050"),
    "seafresh": gln("030600002051"),
}


def _ev(cte_type, ts, gln_key, product, tlc, qty, uom, kdes, inputs=None):
    e = {
        "cte_type": cte_type,
        "timestamp": ts,
        "location_gln": F[gln_key],
        "location_name": kdes.get("location_name")
        or kdes.get("receiving_location")
        or kdes.get("ship_from_location")
        or product,
        "product_description": product,
        "traceability_lot_code": tlc,
        "quantity": qty,
        "unit_of_measure": uom,
        "kdes": kdes,
    }
    if inputs:
        e["input_traceability_lot_codes"] = inputs
    return e


CHAIN_A = (
    "erp_netsuite",
    [
        _ev(
            "harvesting",
            "2026-07-08T06:00:00Z",
            "vff_field",
            "Romaine Lettuce - Organic",
            "VFF-ROM-0708-H",
            2400,
            "lbs",
            {
                "harvest_date": "2026-07-08",
                "location_name": "Valley Fresh Farms - Field 12",
                "farm_name": "Valley Fresh Farms",
                "growing_area": "Field 12 - Block A",
                "reference_document": "INV-VFF-2026-0708",
            },
        ),
        _ev(
            "cooling",
            "2026-07-08T08:30:00Z",
            "vff_cool",
            "Romaine Lettuce - Organic",
            "VFF-ROM-0708-C",
            2400,
            "lbs",
            {
                "cooling_date": "2026-07-08",
                "location_name": "Valley Fresh Farms - Cooling Facility",
                "cooling_method": "vacuum_cooling",
                "target_temperature": "34",
                "reference_document": "COOL-VFF-2026-0708",
            },
        ),
        _ev(
            "initial_packing",
            "2026-07-08T11:00:00Z",
            "vff_pack",
            "Romaine Lettuce - Organic 5oz Bag",
            "VFF-ROM-0708-P",
            900,
            "cases",
            {
                "packing_date": "2026-07-08",
                "location_name": "Valley Fresh Farms - Pack House",
                "package_type": "5oz_bag",
                "upc": "0011110838001",
                "harvester_business_name": "Valley Fresh Farms LLC",
                "harvest_location_ref": F["vff_field"],
                "harvest_location": "Valley Fresh Farms - Field 12",
                "reference_document": "PACK-VFF-2026-0708",
            },
        ),
        _ev(
            "shipping",
            "2026-07-08T15:00:00Z",
            "vff_pack",
            "Romaine Lettuce - Organic 5oz Bag",
            "VFF-ROM-0708-S",
            900,
            "cases",
            {
                "ship_date": "2026-07-08",
                "ship_from_location": "Valley Fresh Farms",
                "ship_to_location": "FreshCo Distribution Center",
                "ship_to_gln": F["freshco_dc"],
                "carrier": "ColdChain Express",
                "bol_number": "BOL-2026-0708-001",
                "reference_document": "BOL-2026-0708-001",
                "tlc_source_reference": "VFF-ROM-0708-P",
            },
        ),
        _ev(
            "receiving",
            "2026-07-09T07:30:00Z",
            "freshco_dc",
            "Romaine Lettuce - Organic 5oz Bag",
            "FC-ROM-0709-R",
            900,
            "cases",
            {
                "receive_date": "2026-07-09",
                "receiving_location": "FreshCo Distribution Center",
                "temperature_on_arrival": "35.1",
                "po_number": "PO-2026-0709-A",
                "immediate_previous_source": "Valley Fresh Farms",
                "reference_document": "PO-2026-0709-A",
                "tlc_source_reference": "VFF-ROM-0708-S",
            },
        ),
        _ev(
            "transformation",
            "2026-07-09T10:00:00Z",
            "freshco_pr",
            "Spring Mix Salad Kit - 12oz",
            "FC-MIX-0709-X",
            500,
            "units",
            {
                "transformation_date": "2026-07-09",
                "location_name": "FreshCo DC - Processing",
                "output_product": "Spring Mix Salad Kit - 12oz",
                "processing_facility": "FreshCo Distribution Center",
                "input_traceability_lot_codes": ["FC-ROM-0709-R"],
                "input_tlcs": "FC-ROM-0709-R",
                "reference_document": "WO-FC-2026-0709-001",
            },
            inputs=["FC-ROM-0709-R"],
        ),
        _ev(
            "shipping",
            "2026-07-10T09:00:00Z",
            "freshco_pr",
            "Spring Mix Salad Kit - 12oz",
            "FC-MIX-0710-S",
            500,
            "units",
            {
                "ship_date": "2026-07-10",
                "ship_from_location": "FreshCo Distribution Center",
                "ship_to_location": "MetroMart Regional DC",
                "ship_to_gln": F["retail_rdc"],
                "carrier": "ColdChain Express",
                "bol_number": "BOL-2026-0710-009",
                "reference_document": "BOL-2026-0710-009",
                "tlc_source_reference": "FC-MIX-0709-X",
            },
        ),
    ],
)

CHAIN_B = (
    "iot_sensecap",
    [
        _ev(
            "harvesting",
            "2026-07-12T06:30:00Z",
            "sungrove_f",
            "Roma Tomatoes - Field Grown",
            "SGF-TOM-0712-H",
            5000,
            "lbs",
            {
                "harvest_date": "2026-07-12",
                "location_name": "SunGrove Farms - South Block",
                "farm_name": "SunGrove Farms",
                "growing_area": "South Block - Row 4",
                "reference_document": "INV-SGF-2026-0712",
            },
        ),
        _ev(
            "initial_packing",
            "2026-07-12T13:00:00Z",
            "sungrove_p",
            "Roma Tomatoes - 25lb Carton",
            "SGF-TOM-0712-P",
            200,
            "cartons",
            {
                "packing_date": "2026-07-12",
                "location_name": "SunGrove Farms - Pack Line 2",
                "package_type": "25lb_carton",
                "harvester_business_name": "SunGrove Farms Inc",
                "harvest_location_ref": F["sungrove_f"],
                "harvest_location": "SunGrove Farms - South Block",
                "reference_document": "PACK-SGF-2026-0712",
            },
        ),
        _ev(
            "shipping",
            "2026-07-13T08:00:00Z",
            "sungrove_p",
            "Roma Tomatoes - 25lb Carton",
            "SGF-TOM-0713-S",
            200,
            "cartons",
            {
                "ship_date": "2026-07-13",
                "ship_from_location": "SunGrove Farms",
                "ship_to_location": "MetroProduce Distribution",
                "ship_to_gln": F["metro_dc"],
                "carrier": "Interstate Cold",
                "bol_number": "BOL-2026-0713-044",
                "reference_document": "BOL-2026-0713-044",
                "tlc_source_reference": "SGF-TOM-0712-P",
            },
        ),
        _ev(
            "receiving",
            "2026-07-14T06:45:00Z",
            "metro_dc",
            "Roma Tomatoes - 25lb Carton",
            "MP-TOM-0714-R",
            200,
            "cartons",
            {
                "receive_date": "2026-07-14",
                "receiving_location": "MetroProduce Distribution",
                "temperature_on_arrival": "52.0",
                "po_number": "PO-2026-0714-B",
                "immediate_previous_source": "SunGrove Farms",
                "reference_document": "PO-2026-0714-B",
                "tlc_source_reference": "SGF-TOM-0713-S",
            },
        ),
    ],
)

CHAIN_C = (
    "manual_entry",
    [
        _ev(
            "first_land_based_receiving",
            "2026-07-15T05:30:00Z",
            "port_glou",
            "Atlantic Salmon - Fresh Fillet",
            "PGC-SAL-0715-F",
            800,
            "lbs",
            {
                "landing_date": "2026-07-15",
                "receiving_location": "Port of Gloucester - Cold Storage",
                "vessel_name": "Northern Dawn",
                "source_vessel_name": "Northern Dawn",
                "entry_point": "Port of Gloucester",
                "harvest_area": "FAO Area 21",
                "reference_document": "LAND-PGC-2026-0715",
            },
        ),
        _ev(
            "shipping",
            "2026-07-16T09:15:00Z",
            "port_glou",
            "Atlantic Salmon - Fresh Fillet",
            "PGC-SAL-0716-S",
            800,
            "lbs",
            {
                "ship_date": "2026-07-16",
                "ship_from_location": "Port of Gloucester - Cold Storage",
                "ship_to_location": "SeaFresh Distributors",
                "ship_to_gln": F["seafresh"],
                "carrier": "FrozenLine Logistics",
                "bol_number": "BOL-2026-0716-071",
                "reference_document": "BOL-2026-0716-071",
                "tlc_source_reference": "PGC-SAL-0715-F",
            },
        ),
    ],
)

BATCHES = [CHAIN_A, CHAIN_B, CHAIN_C]

# TLCs rejected by the prod rules engine on the v1 run — re-submit only these.
RESUBMIT_TLCS = {"VFF-ROM-0708-P", "FC-MIX-0709-X", "SGF-TOM-0712-P", "PGC-SAL-0715-F"}


def _ssl_ctx(base: str):
    ctx = ssl.create_default_context()
    try:
        urllib.request.urlopen(urllib.request.Request(f"{base}/health"), context=ctx, timeout=8)
    except ssl.SSLCertVerificationError:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    except Exception:
        pass
    return ctx


def check_health(base: str) -> None:
    ctx = _ssl_ctx(base)
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{base}/health"), context=ctx, timeout=10) as r:
            body = json.loads(r.read())
    except Exception as e:  # noqa: BLE001
        print(f"health check failed: {e}")
        return
    print(f"BASE={base}")
    print("webhook_hmac_configured:", body.get("webhook_hmac_configured"))
    print(json.dumps(body, indent=2)[:1500])


def status(base: str, tenant: str) -> int:
    """Read-only: GET /api/v1/readiness/assessment for the founder tenant."""
    api_key = os.getenv("REGENGINE_API_KEY", "").strip()
    if not api_key:
        print("ERROR: REGENGINE_API_KEY not in environment (run under `railway run`).")
        return 2
    ctx = _ssl_ctx(base)
    url = f"{base}/api/v1/readiness/assessment?tenant_id={tenant}"
    req = urllib.request.Request(url, headers={"X-RegEngine-API-Key": api_key, "X-Tenant-ID": tenant})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
            body = json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:400]}")
        return 1
    # nosemgrep: tenant-id-from-request-body — `body` is the authenticated API *response*, printed for CLI display
    print(f"tenant={body.get('tenant_id')}")
    print(
        f"overall_score={body.get('overall_score')}  "
        f"maturity={body.get('maturity_level')} ({body.get('maturity_name')})  "
        f"items={body.get('items_completed')}/{body.get('items_total')}"
    )
    ns = body.get("next_steps", [])
    print("next unmet steps:", ", ".join(s.get("id", "?") for s in ns) or "(none)")
    return 0


def validate_local() -> int:
    seen_types, sources, total, gln_ok = set(), set(), 0, 0
    problems = []
    for source, events in BATCHES:
        sources.add(source)
        for e in events:
            total += 1
            seen_types.add(e["cte_type"])
            g = e["location_gln"]
            if len(g) == 13 and g.isdigit() and gs1_check_digit(g[:-1]) == g[-1]:
                gln_ok += 1
            else:
                problems.append(f"bad GLN {g} on {e['traceability_lot_code']}")
    print(f"events={total}  distinct_cte_types={len(seen_types)} {sorted(seen_types)}")
    print(f"distinct_sources={len(sources)} {sorted(sources)}")
    print(f"valid_GLN_events={gln_ok}/{total}  ({gln_ok / total * 100:.0f}%)")
    print(
        "Gate preview:",
        f"ingest_records({'PASS' if total >= 10 else 'FAIL'})",
        f"multiple_sources({'PASS' if len(sources) >= 2 else 'FAIL'})",
        f"cte_coverage({'PASS' if len(seen_types) >= 4 else 'FAIL'})",
        f"all_ctes_covered({'PASS' if len(seen_types) == 7 else 'FAIL'})",
        f"facility_identifiers({'PASS' if gln_ok / total >= 0.5 else 'FAIL'})",
    )
    if problems:
        print("PROBLEMS:", *problems, sep="\n  ")
        return 1
    print("static validation: OK")
    return 0


def post_batch(base, api_key, tenant, source, events, idem, hmac_secret, ctx) -> dict:
    payload = {"source": source, "events": events}  # NB: no tenant_id in body
    data = json.dumps(payload).encode()
    headers = {
        "Content-Type": "application/json",
        "X-RegEngine-API-Key": api_key,
        "X-Tenant-ID": tenant,
        "Idempotency-Key": idem,
    }
    if hmac_secret:
        sig = hmac.new(hmac_secret.encode(), data, hashlib.sha256).hexdigest()
        headers["X-Webhook-Signature"] = f"sha256={sig}"
    req = urllib.request.Request(f"{base}/api/v1/webhooks/ingest", data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
        return json.loads(resp.read())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--fix", action="store_true", help="re-submit only the RESUBMIT_TLCS with fresh idem keys")
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--tenant", default=FOUNDER_TENANT)
    args = ap.parse_args()
    tenant = args.tenant

    if args.check:
        check_health(args.base)
        return 0
    if args.status:
        return status(args.base, tenant)

    rc = validate_local()
    if args.dry_run:
        print("\n--- DRY RUN: payloads that WOULD be POSTed ---")
        for source, events in BATCHES:
            print(f"\n### source={source}  events={len(events)}  idem={SEED_VERSION}-{source}")
            print(json.dumps({"source": source, "events": events}, indent=2))
        return rc
    if rc != 0:
        print("Refusing to seed: static validation failed.")
        return rc

    api_key = os.getenv("REGENGINE_API_KEY", "").strip()
    if not api_key:
        print("ERROR: REGENGINE_API_KEY (prod master key) not in environment.")
        return 2
    hmac_secret = os.getenv("WEBHOOK_HMAC_SECRET", "").strip() or None
    print(
        f"Seeding tenant={tenant} base={args.base} "
        f"hmac={'signing' if hmac_secret else 'NONE — will 401 (prod requires it)'}"
    )

    ctx = _ssl_ctx(args.base)
    grand_ok = grand_bad = 0
    for source, events in BATCHES:
        if args.fix:
            events = [e for e in events if e["traceability_lot_code"] in RESUBMIT_TLCS]
            if not events:
                continue
        idem = f"{SEED_VERSION}-{'fix1-' if args.fix else ''}{source}"
        try:
            result = post_batch(args.base, api_key, tenant, source, events, idem, hmac_secret, ctx)
        except urllib.error.HTTPError as e:
            print(f"[{source}] HTTP {e.code}: {e.read().decode()[:500]}")
            return 1
        acc, rej = result.get("accepted", 0), result.get("rejected", 0)
        grand_ok += acc
        grand_bad += rej
        print(f"[{source}] accepted={acc} rejected={rej}")
        for ev in result.get("events", []):
            if ev.get("status") == "rejected":
                print(f"    REJECT {ev.get('traceability_lot_code')} {ev.get('cte_type')}: {ev.get('errors')}")
    print(f"\nTOTAL accepted={grand_ok} rejected={grand_bad}")
    return 0 if grand_bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
