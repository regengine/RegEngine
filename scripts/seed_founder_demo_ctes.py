#!/usr/bin/env python3
"""Seed varied FSMA 204 CTE data into the RegEngine FOUNDER demo tenant.

Writes ~13 events across all 7 CTE types, 3 source systems, valid 13-digit
GLNs, and coherent multi-commodity traceability-lot chains — enough to flip
the readiness checks: ingest_records(>=10), multiple_sources(>=2),
cte_coverage(>=4), all_ctes_covered(==7), facility_identifiers(>=50% GLN),
plus chain_integrity / provenance_complete / rules_evaluated.

Mechanism (validated against main @ 8e6e4b6):
  POST {BASE}/api/v1/webhooks/ingest  — one request per source system.
  Auth: individually attributable tenant key in X-RegEngine-API-Key
        (env REGENGINE_TENANT_API_KEY) + matching X-Tenant-ID assertion.
  Required headers the stock scripts/seed_demo_ctes.py omits:
        X-Tenant-ID       (must match the credential-bound tenant)
        Idempotency-Key   (else 428/400 — routes.py:56,83 strict)
        X-Webhook-Signature: sha256=<hmac>  (prod HAS WEBHOOK_HMAC_SECRET set)
  Body tenant_id is intentionally NOT set (ignored; conflict -> 409).

Timestamps are within the last ~90 days (route replay window, security.py:232).

Secrets come from the environment ONLY (inject via `railway run`):
  REGENGINE_TENANT_API_KEY (required) — scoped founder-tenant key
  WEBHOOK_HMAC_SECRET   (required for the write; prod has it configured)

Usage:
  python3 seed_founder_demo_ctes.py --status    # read-only score (localhost)
  python3 seed_founder_demo_ctes.py --dry-run   # print+validate, no net
  python3 seed_founder_demo_ctes.py --check     # GET /health HMAC state
  python3 seed_founder_demo_ctes.py --base https://host --allow-production  # SEED (writes!)

Defaults to the local ingestion service (http://localhost:8002) and refuses
to target any non-local host unless BOTH an explicit URL and
--allow-production are given. Secrets come from the environment only.
TLS certificate errors are never downgraded; they abort the run.
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
import urllib.parse
import urllib.request

FOUNDER_TENANT = os.getenv("SEED_TENANT_ID", "38e99859-7364-4932-99fa-b1f114bf0202")
DEFAULT_BASE = "http://localhost:8002"
BASE_ENV_VAR = "SEED_BASE_URL"
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
SEED_VERSION = "founderseed-v1"  # bump to force re-processing past the 24h idempotency cache


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
    (CLI --base or SEED_BASE_URL) AND allow_production is True.
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
                "harvester_business_phone": "+1-202-555-0100",
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
                "harvester_business_phone": "+1-202-555-0100",
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


def check_health(base: str) -> int:
    ctx = create_ssl_context()
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{base}/health"), context=ctx, timeout=10) as r:
            body = json.loads(r.read())
    except ssl.SSLCertVerificationError as e:
        print(f"ERROR: TLS certificate verification failed: {e}. Refusing to continue.")
        return 1
    except Exception as e:  # noqa: BLE001
        if is_tls_cert_failure(e):
            reason = getattr(e, "reason", e)
            print(f"ERROR: TLS certificate verification failed: {reason}. Refusing to continue.")
            return 1
        print(f"health check failed: {e}")
        return 0
    print(f"BASE={base}")
    print("webhook_hmac_configured:", body.get("webhook_hmac_configured"))
    print(json.dumps(body, indent=2)[:1500])
    return 0


def status(base: str, tenant: str) -> int:
    """Read-only: GET /api/v1/readiness/assessment for the founder tenant."""
    api_key = os.getenv("REGENGINE_TENANT_API_KEY", "").strip()
    if not api_key:
        print("ERROR: REGENGINE_TENANT_API_KEY not in environment (run under `railway run`).")
        return 2
    ctx = create_ssl_context()
    url = f"{base}/api/v1/readiness/assessment?tenant_id={tenant}"
    req = urllib.request.Request(url, headers={"X-RegEngine-API-Key": api_key, "X-Tenant-ID": tenant})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
            body = json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:400]}")
        return 1
    except urllib.error.URLError as e:
        if is_tls_cert_failure(e):
            print(f"ERROR: TLS certificate verification failed: {e.reason}. Refusing to continue.")
            return 1
        raise
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Seed founder demo CTEs (defaults to localhost).")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--fix", action="store_true", help="re-submit only the RESUBMIT_TLCS with fresh idem keys")
    ap.add_argument("--base", default=None, help="Explicit target base URL.")
    ap.add_argument(
        "--allow-production",
        action="store_true",
        help="Allow seeding a non-local target. Requires an explicit URL.",
    )
    ap.add_argument("--tenant", default=FOUNDER_TENANT)
    args = ap.parse_args(argv)
    tenant = args.tenant

    try:
        base = resolve_base(args.base, allow_production=args.allow_production)
    except UnsafeTargetError as e:
        print(f"ERROR: {e}")
        return 2

    if args.check:
        return check_health(base)
    if args.status:
        return status(base, tenant)

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

    api_key = os.getenv("REGENGINE_TENANT_API_KEY", "").strip()
    if not api_key:
        print("ERROR: REGENGINE_TENANT_API_KEY (scoped founder-tenant key) not in environment.")
        return 2
    hmac_secret = os.getenv("WEBHOOK_HMAC_SECRET", "").strip() or None
    print(
        f"Seeding tenant={tenant} base={base} hmac={'signing' if hmac_secret else 'NONE — will 401 (prod requires it)'}"
    )

    ctx = create_ssl_context()
    grand_ok = grand_bad = 0
    for source, events in BATCHES:
        if args.fix:
            events = [e for e in events if e["traceability_lot_code"] in RESUBMIT_TLCS]
            if not events:
                continue
        idem = f"{SEED_VERSION}-{'fix1-' if args.fix else ''}{source}"
        try:
            result = post_batch(base, api_key, tenant, source, events, idem, hmac_secret, ctx)
        except urllib.error.HTTPError as e:
            print(f"[{source}] HTTP {e.code}: {e.read().decode()[:500]}")
            return 1
        except ssl.SSLCertVerificationError as e:
            print(f"[{source}] TLS certificate verification failed: {e}. Refusing to continue.")
            return 1
        except urllib.error.URLError as e:
            if is_tls_cert_failure(e):
                print(f"[{source}] TLS certificate verification failed: {e.reason}. Refusing to continue.")
                return 1
            raise
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
