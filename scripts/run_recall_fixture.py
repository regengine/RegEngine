#!/usr/bin/env python3
"""Run the recall-reconstruction fixture: one lot, six pallets, three cases.

    complete              every record available
    missing_3pl_contents  the 3PL pallet-content (repack) record is withheld
    erp_unavailable       the DC ERP is unreachable; only its retained snapshot is used

Each case writes an evidence package (worksheet, findings, corrections, custody
timelines, canonical events with a hash chain, manifest with per-source last
sync time) and reconciles it against ``answer_key.json``. Exit code is 0 only
when every case reconciles.

DB-free by design, like ``scripts/run_full_fsma_simulation.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "services" / "ingestion", ROOT / "services"):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from app.fda_export_service import _generate_csv  # noqa: E402
from shared.recall_reconstruction import CASES, run_case  # noqa: E402

DEFAULT_FIXTURE = ROOT / "sample_data" / "recall_fixture"


def _fda_export_rows(canonical_path: Path) -> list[dict[str, Any]]:
    data = json.loads(canonical_path.read_text(encoding="utf-8"))
    rows = []
    for event in data["events"]:
        rows.append(
            {
                "traceability_lot_code": event["traceability_lot_code"],
                "product_description": event["product_reference"],
                "quantity": event["quantity"],
                "unit_of_measure": event["unit_of_measure"],
                "event_type": event["event_type"],
                "event_timestamp": event["event_timestamp"],
                "location_gln": event["to_facility_reference"] or event["from_facility_reference"] or "",
                "location_name": event["to_entity_reference"] or event["from_entity_reference"] or "",
                "source": event["source_system"],
                "kdes": dict(event["kdes"]),
                "sha256_hash": event["sha256_hash"],
                "chain_hash": event["chain_hash"],
                "ingested_at": event["ingested_at"],
            }
        )
    return rows


def run(fixture_dir: Path, output_dir: Path, cases: list[str]) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for case in cases:
        case_dir = output_dir / case
        manifest = run_case(fixture_dir, case, case_dir)
        csv_text = _generate_csv(_fda_export_rows(case_dir / "canonical_events.json"), include_pii=True)
        (case_dir / "fda_export.csv").write_text(csv_text, encoding="utf-8")
        reconciliation = manifest.get("reconciliation") or {"passed": False, "checks": []}
        results[case] = {
            "passed": reconciliation["passed"],
            "checks_failed": [c for c in reconciliation["checks"] if not c["passed"]],
            "rows_by_label": manifest["worksheet_summary"]["rows_by_label"],
            "findings_by_type": {k: v for k, v in manifest["findings_by_type"].items() if v},
            "unavailable_sources": manifest["unavailable_sources"],
            "package_hash": manifest["package_hash"],
            "output_dir": str(case_dir),
        }
    return {
        "passed": all(r["passed"] for r in results.values()),
        "cases": results,
        "fixture_dir": str(fixture_dir),
        "output_dir": str(output_dir),
    }


def _print_human(summary: dict[str, Any]) -> None:
    print(f"{'PASS' if summary['passed'] else 'FAIL'} recall reconstruction fixture ({summary['fixture_dir']})")
    for case, result in summary["cases"].items():
        status = "PASS" if result["passed"] else "FAIL"
        print(f"  [{status}] {case}: labels={result['rows_by_label']} findings={result['findings_by_type']}")
        for source, info in result["unavailable_sources"].items():
            print(f"         {source} unavailable; last successful sync {info['last_successful_sync_at']}")
        for check in result["checks_failed"]:
            print(f"         FAILED CHECK {check['name']}: {check['detail']}")
        print(f"         package: {result['output_dir']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", default="all", choices=["all", *CASES], help="which case to run (default: all)")
    parser.add_argument("--fixture-dir", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/regengine-recall-fixture"))
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON only")
    args = parser.parse_args(argv)

    cases = list(CASES) if args.case == "all" else [args.case]
    summary = run(args.fixture_dir, args.output_dir, cases)
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        _print_human(summary)
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
