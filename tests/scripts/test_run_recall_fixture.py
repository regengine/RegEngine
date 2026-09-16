import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run_recall_fixture.py"


def test_run_recall_fixture_runs_all_three_cases(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--case", "all", "--output-dir", str(tmp_path), "--json"],
        check=True,
        capture_output=True,
        text=True,
    )
    summary = json.loads(result.stdout)
    assert summary["passed"] is True
    assert set(summary["cases"]) == {"complete", "missing_3pl_contents", "erp_unavailable"}
    assert summary["cases"]["complete"]["rows_by_label"] == {"linked": 4, "no_link_established": 3, "unresolved": 0}
    assert summary["cases"]["missing_3pl_contents"]["rows_by_label"]["unresolved"] == 3
    assert summary["cases"]["erp_unavailable"]["unavailable_sources"]["dc_erp"]["last_successful_sync_at"] == (
        "2026-08-05T12:00:00Z"
    )

    for case in summary["cases"]:
        export = tmp_path / case / "fda_export.csv"
        rows = list(csv.DictReader(export.read_text(encoding="utf-8").splitlines()))
        assert rows, case
        assert all(len(row["Record Hash (SHA-256)"]) == 64 for row in rows)
        assert all(len(row["Chain Hash"]) == 64 for row in rows)
        assert all(row["System Entry Timestamp"] for row in rows)
    # The missing-contents case cannot canonicalize P10's movements without inventing a lot.
    missing = json.loads((tmp_path / "missing_3pl_contents" / "canonical_events.json").read_text())
    assert len(missing["not_canonicalized"]) == 2
    assert all(entry["pallet_id"] == "008610001100000102" for entry in missing["not_canonicalized"])
