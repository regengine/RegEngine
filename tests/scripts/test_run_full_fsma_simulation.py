import csv
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run_full_fsma_simulation.py"


def test_run_full_fsma_simulation_writes_export_and_summary(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--output-dir", str(tmp_path), "--json"],
        check=True,
        capture_output=True,
        text=True,
    )

    summary = json.loads(result.stdout)
    assert summary["passed"] is True
    assert summary["events_generated"] == 4
    assert summary["failure_points"][0]["key"] == "shipping-missing-destination"
    assert summary["remediation"]["corrected_event_key"] == "shipping-corrected-destination"
    assert summary["evidence"]["records_with_sha256_hash"] == 3
    assert summary["evidence"]["records_with_chain_hash"] == 3

    export_path = Path(summary["export"]["csv_path"])
    summary_path = Path(summary["summary_path"])
    assert export_path.exists()
    assert summary_path.exists()

    rows = list(csv.DictReader(export_path.read_text(encoding="utf-8").splitlines()))
    assert len(rows) == 3
    assert all(row["System Entry Timestamp"] for row in rows)
    assert all(len(row["Record Hash (SHA-256)"]) == 64 for row in rows)
    assert all(len(row["Chain Hash"]) == 64 for row in rows)
