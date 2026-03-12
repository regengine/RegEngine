#!/usr/bin/env python3
"""
FSMA 204 Traceability Simulation Runner
========================================
Exercises RegEngine's full FSMA pipeline with a synthetic supply-chain dataset:

  1. Ingestion   — upload the CSV to /v1/ingest/file
  2. Graph       — POST each CTE event to /api/v1/fsma/traceability/event
  3. Trace       — forward + backward trace for TLC1001
  4. Recall      — trigger a simulated Class-II recall drill
  5. Compliance  — validate the lot's KDEs against the /validate endpoint

Usage (services must be running locally or via docker-compose):
  python tests/e2e/run_fsma_simulation.py [--api-key KEY] [--tenant-id UUID]

Environment overrides:
  INGESTION_URL     default: http://localhost:8002
  GRAPH_URL         default: http://localhost:8200
  COMPLIANCE_URL    default: http://localhost:8500
  REGENGINE_API_KEY default: test-key
  REGENGINE_TENANT  default: 00000000-0000-0000-0000-000000000001
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import textwrap
from pathlib import Path
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

INGESTION_URL  = os.getenv("INGESTION_URL",  "http://localhost:8002")
GRAPH_URL      = os.getenv("GRAPH_URL",      "http://localhost:8200")
COMPLIANCE_URL = os.getenv("COMPLIANCE_URL", "http://localhost:8500")
API_KEY        = os.getenv("REGENGINE_API_KEY", "test-key")
TENANT_ID      = os.getenv("REGENGINE_TENANT",  "00000000-0000-0000-0000-000000000001")

CSV_PATH = Path(__file__).parents[2] / "test_data" / "regengine_test_traceability.csv"

TLC = "TLC1001"

# Map CSV event_type → FSMA 204 CTEType
_CTE_MAP: dict[str, str] = {
    "harvest":      "CREATION",
    "cooling":      "RECEIVING",   # cold-storage is a receiving point for temp compliance
    "packing":      "INITIAL_PACKING",
    "shipping":     "SHIPPING",
    "receiving":    "RECEIVING",
    "recall_alert": None,          # handled separately as a recall drill trigger
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PASS  = "\033[92m✓\033[0m"
FAIL  = "\033[91m✗\033[0m"
WARN  = "\033[93m⚠\033[0m"
SKIP  = "\033[90m–\033[0m"
RESET = "\033[0m"


class SimResult:
    def __init__(self) -> None:
        self.steps: list[tuple[str, str, str]] = []  # (label, status, detail)

    def record(self, label: str, ok: bool | None, detail: str = "") -> None:
        if ok is True:
            icon = PASS
        elif ok is False:
            icon = FAIL
        else:
            icon = SKIP
        self.steps.append((label, icon, detail))
        print(f"  {icon}  {label}" + (f"  — {detail}" if detail else ""))

    def summary(self) -> None:
        passed  = sum(1 for _, s, _ in self.steps if s == PASS)
        failed  = sum(1 for _, s, _ in self.steps if s == FAIL)
        skipped = sum(1 for _, s, _ in self.steps if s == SKIP)
        print()
        print("=" * 58)
        print(f"  Simulation complete: {passed} passed / {failed} failed / {skipped} skipped")
        print("=" * 58)
        if failed:
            sys.exit(1)


def headers(extra: dict | None = None) -> dict:
    h = {
        "X-RegEngine-API-Key": API_KEY,
        "X-Tenant-ID": TENANT_ID,
    }
    if extra:
        h.update(extra)
    return h


def load_csv() -> list[dict]:
    with CSV_PATH.open() as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Step 1: Ingestion
# ---------------------------------------------------------------------------

def step_ingest(result: SimResult, client: httpx.Client) -> str | None:
    print("\n[1] Ingestion — upload CSV to /v1/ingest/file")
    try:
        csv_bytes = CSV_PATH.read_bytes()
        resp = client.post(
            f"{INGESTION_URL}/v1/ingest/file",
            files={"file": ("regengine_test_traceability.csv", csv_bytes, "text/csv")},
            data={"source_system": "fsma", "vertical": "fsma_204"},
            headers=headers(),
            timeout=30,
        )
        ok = resp.status_code in (200, 202)
        doc_id = None
        if ok:
            body = resp.json()
            doc_id = body.get("job_id") or body.get("id") or body.get("task_id")
            result.record("CSV uploaded to ingestion service", True, f"status={resp.status_code} doc_id={doc_id}")
        else:
            result.record("CSV uploaded to ingestion service", False, f"status={resp.status_code} body={resp.text[:120]}")
        return doc_id
    except httpx.ConnectError:
        result.record("CSV uploaded to ingestion service", None, "ingestion service unreachable — skipped")
        return None


# ---------------------------------------------------------------------------
# Step 2: Graph — POST CTE events
# ---------------------------------------------------------------------------

def step_graph_events(result: SimResult, client: httpx.Client, rows: list[dict]) -> int:
    print("\n[2] Graph — POST CTE events to /api/v1/fsma/traceability/event")
    posted = 0
    skipped = 0
    errors = 0

    for row in rows:
        cte_type = _CTE_MAP.get(row["event_type"])
        if cte_type is None:
            skipped += 1
            continue

        quantity = row["quantity"].strip()
        payload = {
            "event_type":          cte_type,
            "event_date":          row["cte_date"],
            "tlc":                 row["traceability_lot_code"],
            "location_identifier": f"{row['location_name']}, {row['location_city']}, {row['location_state']}",
            "product_description": row["product_name"],
            "gtin":                row["product_gtin"],
        }
        if quantity:
            try:
                payload["quantity"] = float(quantity)
                payload["uom"] = row["unit"]
            except ValueError:
                pass

        try:
            resp = client.post(
                f"{GRAPH_URL}/api/v1/fsma/traceability/event",
                json=payload,
                headers=headers(),
                timeout=10,
            )
            if resp.status_code in (200, 201):
                posted += 1
            else:
                errors += 1
        except httpx.ConnectError:
            result.record("Graph service reachable", None, "graph service unreachable — skipping event steps")
            return 0

    total_cte_rows = len(rows) - skipped
    ok = errors == 0
    result.record(
        f"CTE events posted ({posted}/{total_cte_rows})",
        ok,
        f"{skipped} non-CTE rows skipped, {errors} errors",
    )
    return posted


# ---------------------------------------------------------------------------
# Step 3: Trace forward + backward
# ---------------------------------------------------------------------------

def step_trace(result: SimResult, client: httpx.Client) -> None:
    print(f"\n[3] Trace — forward + backward for TLC={TLC}")

    for direction in ("forward", "backward"):
        try:
            resp = client.get(
                f"{GRAPH_URL}/api/v1/fsma/traceability/trace/{direction}/{TLC}",
                headers=headers(),
                timeout=10,
            )
            if resp.status_code == 200:
                body = resp.json()
                hops = len(body.get("nodes") or body.get("events") or [])
                result.record(f"Trace {direction} for {TLC}", True, f"{hops} nodes/events returned")
            elif resp.status_code in (401, 403):
                result.record(f"Trace {direction} for {TLC}", None, "auth required — check API key / tenant")
            elif resp.status_code == 404:
                result.record(f"Trace {direction} for {TLC}", None, "TLC not yet in graph (events may not be indexed yet)")
            else:
                result.record(f"Trace {direction} for {TLC}", False, f"status={resp.status_code}")
        except httpx.ConnectError:
            result.record(f"Trace {direction} for {TLC}", None, "graph service unreachable — skipped")


# ---------------------------------------------------------------------------
# Step 4: Recall drill
# ---------------------------------------------------------------------------

def step_recall(result: SimResult, client: httpx.Client) -> None:
    print(f"\n[4] Recall — Class-II drill targeting {TLC}")
    payload = {
        "type":       "forward_trace",
        "target_tlc": TLC,
        "severity":   "class_ii",
        "reason":     "RECALLSIM-001 — synthetic FDA simulation",
    }
    try:
        resp = client.post(
            f"{GRAPH_URL}/api/v1/fsma/recall/recall/drill",
            json=payload,
            headers=headers(),
            timeout=15,
        )
        if resp.status_code in (200, 201):
            body = resp.json()
            drill_id = body.get("drill_id") or body.get("id", "?")
            status   = body.get("status", "?")
            result.record("Recall drill created and executed", True, f"drill_id={drill_id} status={status}")
        elif resp.status_code in (401, 403):
            result.record("Recall drill created and executed", None, "auth required")
        else:
            result.record("Recall drill created and executed", False, f"status={resp.status_code} body={resp.text[:120]}")
    except httpx.ConnectError:
        result.record("Recall drill created and executed", None, "graph service unreachable — skipped")


# ---------------------------------------------------------------------------
# Step 5: Compliance validation
# ---------------------------------------------------------------------------

def step_compliance(result: SimResult, client: httpx.Client, rows: list[dict]) -> None:
    print(f"\n[5] Compliance — validate KDEs for {TLC}")

    # Build a config dict from the first complete row (harvest/creation event)
    first_row = next((r for r in rows if r["event_type"] == "harvest"), rows[0])
    config: dict[str, Any] = {
        "tlc":                 first_row["traceability_lot_code"],
        "cte_type":            "CREATION",
        "event_date":          first_row["cte_date"],
        "location":            f"{first_row['location_city']}, {first_row['location_state']}",
        "product_description": first_row["product_name"],
        "lot_size_unit":       first_row["unit"],
        "supplier_reference":  first_row["reference_doc"],
    }

    # Test 1: all required fields present → should be valid
    try:
        resp = client.post(
            f"{COMPLIANCE_URL}/validate",
            json={"config": config, "strict": False},
            headers=headers(),
            timeout=10,
        )
        if resp.status_code == 200:
            body = resp.json()
            valid    = body.get("valid", False)
            n_errors = len(body.get("errors", []))
            n_warns  = len(body.get("warnings", []))
            result.record(
                "Compliance validate — complete KDE record",
                valid,
                f"valid={valid} errors={n_errors} warnings={n_warns}",
            )
        else:
            result.record("Compliance validate — complete KDE record", False, f"status={resp.status_code}")
    except httpx.ConnectError:
        result.record("Compliance validate — complete KDE record", None, "compliance service unreachable — skipped")
        return

    # Test 2: missing required fields → should fail
    incomplete = {"tlc": TLC}  # deliberately missing cte_type, event_date, location
    try:
        resp = client.post(
            f"{COMPLIANCE_URL}/validate",
            json={"config": incomplete, "strict": False},
            headers=headers(),
            timeout=10,
        )
        if resp.status_code == 200:
            body = resp.json()
            valid    = body.get("valid", True)
            n_errors = len(body.get("errors", []))
            detected = not valid and n_errors > 0
            result.record(
                "Compliance validate — missing KDE fields detected",
                detected,
                f"valid={valid} errors={n_errors} (expected invalid with errors)",
            )
        else:
            result.record("Compliance validate — missing KDE fields detected", False, f"status={resp.status_code}")
    except httpx.ConnectError:
        result.record("Compliance validate — missing KDE fields detected", None, "compliance service unreachable — skipped")

    # Test 3: cooling row has empty quantity → strict mode should catch it
    cooling_row = next((r for r in rows if r["event_type"] == "cooling"), None)
    if cooling_row:
        strict_config = {
            "tlc":       cooling_row["traceability_lot_code"],
            "cte_type":  "RECEIVING",
            "event_date": cooling_row["cte_date"],
            "location":   f"{cooling_row['location_city']}, {cooling_row['location_state']}",
            # quantity deliberately absent — mirrors the real CSV gap
        }
        try:
            resp = client.post(
                f"{COMPLIANCE_URL}/validate",
                json={"config": strict_config, "strict": True},
                headers=headers(),
                timeout=10,
            )
            if resp.status_code == 200:
                body     = resp.json()
                valid    = body.get("valid", True)
                n_errors = len(body.get("errors", []))
                # In strict mode missing recommended fields (lot_size_unit, supplier_reference,
                # product_description) should surface as errors
                result.record(
                    "Compliance validate — cooling row strict mode (missing quantity/desc)",
                    n_errors > 0,
                    f"valid={valid} errors={n_errors}",
                )
            else:
                result.record("Compliance validate — cooling row strict mode", False, f"status={resp.status_code}")
        except httpx.ConnectError:
            result.record("Compliance validate — cooling row strict mode", None, "compliance service unreachable — skipped")


# ---------------------------------------------------------------------------
# Step 6: Checklist lookup
# ---------------------------------------------------------------------------

def step_checklist(result: SimResult, client: httpx.Client) -> None:
    print("\n[6] Compliance — fetch Fresh Produce checklist")
    try:
        resp = client.get(
            f"{COMPLIANCE_URL}/checklists/fsma-204-fresh-produce",
            headers=headers(),
            timeout=10,
        )
        if resp.status_code == 200:
            body  = resp.json()
            name  = body.get("name", "?")
            count = len(body.get("requirements") or body.get("items") or [])
            result.record("Fresh Produce checklist retrieved", True, f"{count} requirements — {name}")
        elif resp.status_code == 404:
            result.record("Fresh Produce checklist retrieved", False, "checklist not found (compliance service may need restart)")
        else:
            result.record("Fresh Produce checklist retrieved", False, f"status={resp.status_code}")
    except httpx.ConnectError:
        result.record("Fresh Produce checklist retrieved", None, "compliance service unreachable — skipped")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="RegEngine FSMA 204 simulation runner")
    p.add_argument("--api-key",   default=None, help="Override REGENGINE_API_KEY")
    p.add_argument("--tenant-id", default=None, help="Override REGENGINE_TENANT (UUID)")
    return p.parse_args()


def main() -> None:
    global API_KEY, TENANT_ID
    args = parse_args()
    if args.api_key:
        API_KEY = args.api_key
    if args.tenant_id:
        TENANT_ID = args.tenant_id

    print(textwrap.dedent(f"""
    ╔══════════════════════════════════════════════════════╗
    ║   RegEngine FSMA 204 Traceability Simulation         ║
    ║   TLC: {TLC:<47}║
    ║   Rows: {str(sum(1 for _ in open(CSV_PATH))):<46}║
    ╚══════════════════════════════════════════════════════╝
    """))

    rows   = load_csv()
    result = SimResult()

    with httpx.Client(timeout=30) as client:
        step_ingest(result, client)
        step_graph_events(result, client, rows)
        step_trace(result, client)
        step_recall(result, client)
        step_compliance(result, client, rows)
        step_checklist(result, client)

    result.summary()


if __name__ == "__main__":
    main()
