"""The fixture must stay internally consistent: valid GS1 identifiers, hashes that match the files."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from shared.fsma_validation import validate_gln, validate_gtin, validate_sscc
from shared.recall_reconstruction.loader import FILE_SPECS

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "sample_data" / "recall_fixture"


def _rows(path: Path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_every_gs1_identifier_in_the_fixture_validates():
    for name in FILE_SPECS:
        for row in _rows(FIXTURE / name):
            for column, value in row.items():
                if not value:
                    continue
                if column.endswith("pallet_id"):
                    assert validate_sscc(value).is_valid, (name, column, value)
                elif column.endswith("gln"):
                    assert validate_gln(value).is_valid, (name, column, value)
                elif column == "gtin":
                    assert validate_gtin(value).is_valid, (name, column, value)


def test_sync_manifest_hashes_match_files():
    manifest = json.loads((FIXTURE / "sync_manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["files"]) == set(FILE_SPECS)
    for name, entry in manifest["files"].items():
        assert entry["source_system"] == FILE_SPECS[name]["source_system"]
        assert entry["sha256"] == hashlib.sha256((FIXTURE / name).read_bytes()).hexdigest(), name
    for path, digest in manifest["retained_sha256"].items():
        assert digest == hashlib.sha256((FIXTURE / path).read_bytes()).hexdigest(), path


def test_retained_snapshot_matches_live_records_it_claims_to_retain():
    for name in ("dc_receiving.csv", "dc_repack.csv"):
        assert (FIXTURE / "retained" / "dc_erp" / name).read_bytes() == (FIXTURE / name).read_bytes()
    assert not (FIXTURE / "retained" / "dc_erp" / "dc_shipping.csv").exists()


def test_answer_key_totals_match_fixture_contents():
    key = json.loads((FIXTURE / "answer_key.json").read_text(encoding="utf-8"))
    produced = {r["lot_code"]: float(r["quantity"]) for r in _rows(FIXTURE / "mfg_lots.csv")}
    palletized: dict[str, float] = {}
    for r in _rows(FIXTURE / "mfg_pallet_contents.csv"):
        palletized[r["lot_code"]] = palletized.get(r["lot_code"], 0.0) + float(r["quantity"])
    assert produced == palletized
    for lot, truth in key["ground_truth"]["lots"].items():
        assert float(truth["produced"]) == produced[lot]
        assert sum(d["shipped"] for d in truth["by_destination"].values()) == produced[lot]
