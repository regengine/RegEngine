"""Regression tests for the standalone audit-pack verifier.

The verifier must recompute every recorded hash and fail closed. These
tests build fixture packs with the real pack builder
(``app.fda_export_service``) so the fixtures match the production format,
then prove that tampering is caught.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
INGESTION_DIR = REPO_ROOT / "services" / "ingestion"
SERVICES_DIR = REPO_ROOT / "services"
SCRIPT_PATH = REPO_ROOT / "services" / "admin" / "scripts" / "verify_audit_pack.py"

for candidate in (str(INGESTION_DIR), str(SERVICES_DIR)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)


def _load_verifier():
    spec = importlib.util.spec_from_file_location("verify_audit_pack", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_verifier()

from ingestion.app.fda_export_service import (  # noqa: E402
    _build_chain_verification_payload,
    _build_fda_package,
)
from shared.merkle_tree import MerkleTree  # noqa: E402


def _make_pack(tmp_path, *, valid_chain=True):
    events = [
        {
            "traceability_lot_code": "TLC1",
            "event_type": "shipping",
            "sha256_hash": "a" * 64,
            "chain_hash": "b" * 64,
        }
    ]
    csv_content = "TLC,Event\nTLC1,shipping\n"
    csv_hash = hashlib.sha256(csv_content.encode("utf-8")).hexdigest()
    chain_state = SimpleNamespace(
        valid=valid_chain,
        chain_length=1,
        errors=[],
        checked_at="2026-01-01T00:00:00+00:00",
    )
    completeness = {
        "required_kde_coverage_ratio": 1.0,
        "events_with_missing_required_fields": 0,
    }
    chain_payload = _build_chain_verification_payload(
        tenant_id="tenant-1",
        tlc="TLC1",
        events=events,
        csv_hash=csv_hash,
        chain_verification=chain_state,
        completeness_summary=completeness,
    )
    package_bytes, meta = _build_fda_package(
        events=events,
        csv_content=csv_content,
        csv_hash=csv_hash,
        chain_payload=chain_payload,
        completeness_summary=completeness,
        tenant_id="tenant-1",
        tlc="TLC1",
        query_start_date=None,
        query_end_date=None,
    )
    pack_path = tmp_path / "pack.zip"
    pack_path.write_bytes(package_bytes)
    return pack_path, meta


def _read_members(pack_path):
    with zipfile.ZipFile(pack_path) as zf:
        return {name: zf.read(name) for name in zf.namelist()}


def _resign_members(members):
    """Rebuild manifest hashes and the Merkle root after editing a member.

    This keeps the manifest internally consistent so a test isolates the
    single check under test (for example the CSV content-hash comparison)
    instead of tripping the manifest file-hash check first.
    """
    manifest = json.loads(members["manifest.json"].decode("utf-8"))
    new_files = []
    for entry in manifest["files"]:
        data = members[entry["path"]]
        new_files.append(
            {
                "name": entry.get("name", entry["path"]),
                "path": entry["path"],
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    manifest["files"] = new_files
    leaves = [entry["sha256"] for entry in new_files]
    manifest["merkle"]["leaves"] = leaves
    manifest["merkle"]["root"] = MerkleTree(leaves).root
    members["manifest.json"] = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    return members


def _write_members(tmp_path, name, members):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for member_name, data in members.items():
            zf.writestr(member_name, data)
    pack_path = tmp_path / name
    pack_path.write_bytes(out.getvalue())
    return pack_path


def _chain_name(members):
    names = [n for n in members if n.startswith("chain_verification_") and n.endswith(".json")]
    assert len(names) == 1
    return names[0]


def _csv_name(members):
    names = [n for n in members if n.startswith("fda_spreadsheet_") and n.endswith(".csv")]
    assert len(names) == 1
    return names[0]


def test_valid_pack_passes(tmp_path):
    pack_path, _ = _make_pack(tmp_path)
    assert verifier.verify_pack(str(pack_path)) is True


def test_tampered_csv_byte_fails(tmp_path):
    pack_path, _ = _make_pack(tmp_path)
    members = _read_members(pack_path)
    csv_name = _csv_name(members)
    members[csv_name] = members[csv_name].replace(b"shipping", b"shippinG", 1)
    tampered = _write_members(tmp_path, "tampered.zip", members)
    assert verifier.verify_pack(str(tampered)) is False


def test_missing_hash_field_fails(tmp_path):
    # The old verifier only required version/snapshot_id/content_hash/
    # verification_status, so dropping hash_algorithm slipped through with
    # a clean VERIFIED. The fixed verifier requires it and fails closed.
    pack_path, _ = _make_pack(tmp_path)
    members = _read_members(pack_path)
    chain_name = _chain_name(members)
    payload = json.loads(members[chain_name].decode("utf-8"))
    del payload["hash_algorithm"]
    members[chain_name] = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    members = _resign_members(members)
    rebuilt = _write_members(tmp_path, "missing_field.zip", members)
    assert verifier.verify_pack(str(rebuilt)) is False


def test_false_verified_claim_with_wrong_hash_fails(tmp_path):
    pack_path, _ = _make_pack(tmp_path)
    members = _read_members(pack_path)
    chain_name = _chain_name(members)
    payload = json.loads(members[chain_name].decode("utf-8"))
    assert payload["verification_status"] == "VERIFIED"
    payload["content_hash"] = "0" * 64
    members[chain_name] = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    members = _resign_members(members)
    forged = _write_members(tmp_path, "forged.zip", members)
    assert verifier.verify_pack(str(forged)) is False


def test_tampered_merkle_root_fails(tmp_path):
    pack_path, _ = _make_pack(tmp_path)
    members = _read_members(pack_path)
    manifest = json.loads(members["manifest.json"].decode("utf-8"))
    manifest["merkle"]["root"] = "f" * 64
    members["manifest.json"] = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    broken = _write_members(tmp_path, "bad_root.zip", members)
    assert verifier.verify_pack(str(broken)) is False


def test_verifier_merkle_matches_shared_tree():
    for leaf_count in (1, 2, 3, 4, 5):
        leaves = [hashlib.sha256(f"leaf-{i}".encode()).hexdigest() for i in range(leaf_count)]
        assert verifier._merkle_root(leaves) == MerkleTree(leaves).root


def test_unverified_chain_pack_fails(tmp_path):
    pack_path, _ = _make_pack(tmp_path, valid_chain=False)
    assert verifier.verify_pack(str(pack_path)) is False
