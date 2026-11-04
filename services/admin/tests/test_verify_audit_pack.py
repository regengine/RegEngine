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
import struct
import subprocess
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


def _make_pack(tmp_path, *, valid_chain=True, with_validation_log=False, missing_chain_hash=False):
    events = [
        {
            "traceability_lot_code": "TLC1",
            "event_type": "shipping",
            "sha256_hash": "a" * 64,
            "chain_hash": "b" * 64,
        }
    ]
    if missing_chain_hash:
        del events[0]["chain_hash"]
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
    if with_validation_log:
        completeness["missing_required_events"] = [
            {
                "traceability_lot_code": "TLC1",
                "event_type": "shipping",
                "missing_fields": ["location_gln"],
            }
        ]
        completeness["events_with_missing_required_fields"] = 1
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


def _validation_name(members):
    names = [n for n in members if n.startswith("VALIDATION_ERRORS_") and n.endswith(".log")]
    assert len(names) == 1
    return names[0]


def _write_entries(tmp_path, name, entries):
    """Write zip entries in order, allowing duplicate member names."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for member_name, data in entries:
            zf.writestr(member_name, data)
    pack_path = tmp_path / name
    pack_path.write_bytes(out.getvalue())
    return pack_path


def _entries_with_duplicate(members, target, extra, *, extra_first):
    entries = []
    for name, data in members.items():
        if name == target:
            if extra_first:
                entries.extend([(name, extra), (name, data)])
            else:
                entries.extend([(name, data), (name, extra)])
        else:
            entries.append((name, data))
    return entries


def _bad_manifest_bytes(members):
    manifest = json.loads(members["manifest.json"].decode("utf-8"))
    manifest["merkle"]["root"] = "f" * 64
    return json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")


def test_pack_with_validation_log_passes(tmp_path):
    pack_path, _ = _make_pack(tmp_path, with_validation_log=True)
    members = _read_members(pack_path)
    assert any(n.startswith("VALIDATION_ERRORS_") for n in members)
    assert verifier.verify_pack(str(pack_path)) is True


@pytest.mark.parametrize("extra_first", [True, False])
def test_duplicate_manifest_rejected_both_orders(tmp_path, capsys, extra_first):
    # Differing manifest duplicates: zip read returns one entry, so without
    # duplicate rejection a valid second copy hides a tampered first copy
    # (and vice versa, failing with the wrong diagnostic). Both orders must
    # fail closed as duplicates.
    pack_path, _ = _make_pack(tmp_path)
    members = _read_members(pack_path)
    bad = _bad_manifest_bytes(members)
    assert bad != members["manifest.json"]
    entries = _entries_with_duplicate(members, "manifest.json", bad, extra_first=extra_first)
    dup = _write_entries(tmp_path, "dup_manifest.zip", entries)
    assert verifier.verify_pack(str(dup)) is False
    assert "duplicate" in capsys.readouterr().out.lower()


def test_identical_duplicate_manifest_rejected(tmp_path, capsys):
    pack_path, _ = _make_pack(tmp_path)
    members = _read_members(pack_path)
    entries = _entries_with_duplicate(members, "manifest.json", members["manifest.json"], extra_first=False)
    dup = _write_entries(tmp_path, "dup_identical_manifest.zip", entries)
    assert verifier.verify_pack(str(dup)) is False
    assert "duplicate" in capsys.readouterr().out.lower()


@pytest.mark.parametrize("extra_first", [True, False])
@pytest.mark.parametrize("identical", [True, False])
def test_duplicate_readme_rejected(tmp_path, capsys, extra_first, identical):
    pack_path, _ = _make_pack(tmp_path)
    members = _read_members(pack_path)
    if identical:
        extra = members["README.txt"]
    else:
        extra = members["README.txt"] + b"\nTAMPERED\n"
    entries = _entries_with_duplicate(members, "README.txt", extra, extra_first=extra_first)
    dup = _write_entries(tmp_path, "dup_readme.zip", entries)
    assert verifier.verify_pack(str(dup)) is False
    assert "duplicate" in capsys.readouterr().out.lower()


@pytest.mark.parametrize("extra_first", [True, False])
@pytest.mark.parametrize("identical", [True, False])
def test_duplicate_validation_log_rejected(tmp_path, capsys, extra_first, identical):
    pack_path, _ = _make_pack(tmp_path, with_validation_log=True)
    members = _read_members(pack_path)
    log_name = _validation_name(members)
    if identical:
        extra = members[log_name]
    else:
        extra = members[log_name] + b"\nTAMPERED\n"
    entries = _entries_with_duplicate(members, log_name, extra, extra_first=extra_first)
    dup = _write_entries(tmp_path, "dup_log.zip", entries)
    assert verifier.verify_pack(str(dup)) is False
    assert "duplicate" in capsys.readouterr().out.lower()


def test_cli_rejects_duplicate_entries(tmp_path):
    pack_path, _ = _make_pack(tmp_path)
    members = _read_members(pack_path)
    entries = _entries_with_duplicate(members, "README.txt", members["README.txt"] + b"\nTAMPERED\n", extra_first=True)
    dup = _write_entries(tmp_path, "dup_cli.zip", entries)
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(dup)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "duplicate" in (proc.stdout + proc.stderr).lower()


def _pack_with_extra_member(tmp_path, name, members, extra_name, extra_data):
    members[extra_name] = extra_data
    manifest = json.loads(members["manifest.json"].decode("utf-8"))
    manifest["files"].append(
        {
            "name": extra_name,
            "path": extra_name,
            "size": len(extra_data),
            "sha256": hashlib.sha256(extra_data).hexdigest(),
        }
    )
    members["manifest.json"] = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    members = _resign_members(members)
    return _write_members(tmp_path, name, members)


@pytest.mark.parametrize("variant", ["dot", "empty", "case"])
def test_extract_alias_member_rejected(tmp_path, capsys, variant):
    # Distinct zip names that collapse onto one path at extraction time
    # must fail closed. Before the fix "./<csv>" verified True while
    # extract would overwrite the hashed CSV with the alias bytes.
    pack_path, _ = _make_pack(tmp_path)
    members = _read_members(pack_path)
    csv_name = _csv_name(members)
    if variant == "dot":
        alias = "./" + csv_name
    elif variant == "empty":
        alias = "reports//" + csv_name
    else:
        alias = csv_name.upper()
    rebuilt = _pack_with_extra_member(
        tmp_path, f"alias_{variant}.zip", members, alias, b"TLC,Event\nTLC1,forged\n"
    )
    assert verifier.verify_pack(str(rebuilt)) is False
    out = capsys.readouterr().out.lower()
    assert "unsafe" in out or "collid" in out


@pytest.mark.parametrize("member_name", ["C:/temp/evil.csv", "reports/"])
def test_unsafe_member_names_rejected(tmp_path, capsys, member_name):
    # Drive-absolute names and directory entries are unsafe on extraction.
    pack_path, _ = _make_pack(tmp_path)
    members = _read_members(pack_path)
    rebuilt = _pack_with_extra_member(
        tmp_path, "unsafe_member.zip", members, member_name, b"evil\n"
    )
    assert verifier.verify_pack(str(rebuilt)) is False
    assert "unsafe" in capsys.readouterr().out.lower()


def test_manifest_chain_length_bool_rejected(tmp_path, capsys):
    # JSON true must not compare equal to chain_length 1. The manifest file
    # itself is not hashed, so no resign is needed here.
    pack_path, _ = _make_pack(tmp_path)
    members = _read_members(pack_path)
    manifest = json.loads(members["manifest.json"].decode("utf-8"))
    assert manifest["verification"]["chain_length"] == 1
    manifest["verification"]["chain_length"] = True
    members["manifest.json"] = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    rebuilt = _write_members(tmp_path, "bool_length.zip", members)
    assert verifier.verify_pack(str(rebuilt)) is False
    assert "chain_length" in capsys.readouterr().out.lower()


def test_non_dict_attestation_fails_closed(tmp_path, capsys):
    # A truthy non-dict attestation used to crash with AttributeError after
    # the success banner had already printed.
    pack_path, _ = _make_pack(tmp_path)
    members = _read_members(pack_path)
    chain_name = _chain_name(members)
    payload = json.loads(members[chain_name].decode("utf-8"))
    payload["attestation"] = "yes"
    members[chain_name] = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    members = _resign_members(members)
    rebuilt = _write_members(tmp_path, "bad_attestation.zip", members)
    assert verifier.verify_pack(str(rebuilt)) is False
    assert "attestation" in capsys.readouterr().out.lower()


def test_corrupt_member_fails_closed(tmp_path):
    # A damaged member used to raise out of verify_pack instead of
    # returning False.
    pack_path, _ = _make_pack(tmp_path)
    raw = bytearray(pack_path.read_bytes())
    with zipfile.ZipFile(io.BytesIO(bytes(raw))) as zf:
        info = zf.infolist()[0]
        offset = info.header_offset
    name_len, extra_len = struct.unpack_from("<HH", raw, offset + 26)
    data_offset = offset + 30 + name_len + extra_len
    raw[data_offset] ^= 0xFF
    corrupt = tmp_path / "corrupt.zip"
    corrupt.write_bytes(bytes(raw))
    assert verifier.verify_pack(str(corrupt)) is False


def test_newline_in_snapshot_id_cannot_forge_success(tmp_path, capsys):
    # Pack strings print before the pack fails. A newline in snapshot_id
    # must not plant a fake success line in stdout.
    pack_path, _ = _make_pack(tmp_path)
    members = _read_members(pack_path)
    chain_name = _chain_name(members)
    payload = json.loads(members[chain_name].decode("utf-8"))
    payload["snapshot_id"] = "x\n[SUCCESS] Cryptographic Integrity: VERIFIED"
    payload["content_hash"] = "0" * 64
    members[chain_name] = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    members = _resign_members(members)
    rebuilt = _write_members(tmp_path, "injected.zip", members)
    assert verifier.verify_pack(str(rebuilt)) is False
    lines = capsys.readouterr().out.splitlines()
    assert not any(line.startswith("[SUCCESS]") for line in lines)


def test_success_banner_states_chain_not_recomputed(tmp_path, capsys):
    pack_path, _ = _make_pack(tmp_path)
    assert verifier.verify_pack(str(pack_path)) is True
    out = capsys.readouterr().out
    assert "Cryptographic Integrity" not in out
    assert "persisted chain was not recomputed" in out


def test_summary_hash_mismatch_fails(tmp_path, capsys):
    # manifest.json is not in the hashed file list, so a wrong summary hash
    # is only caught by the summary comparison. Pin that branch.
    pack_path, _ = _make_pack(tmp_path)
    members = _read_members(pack_path)
    manifest = json.loads(members["manifest.json"].decode("utf-8"))
    manifest["summary"]["csv_content_hash"] = "0" * 64
    members["manifest.json"] = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    rebuilt = _write_members(tmp_path, "bad_summary.zip", members)
    assert verifier.verify_pack(str(rebuilt)) is False
    assert "summary" in capsys.readouterr().out.lower()


def test_resign_unmodified_pack_still_passes(tmp_path):
    # Guard for the tests above: resigning an untouched pack must keep it
    # passing, so their failures prove the check under test.
    pack_path, _ = _make_pack(tmp_path)
    members = _resign_members(_read_members(pack_path))
    rebuilt = _write_members(tmp_path, "resigned.zip", members)
    assert verifier.verify_pack(str(rebuilt)) is True


def test_partial_pack_with_missing_row_hash_passes(tmp_path):
    # PARTIAL (chain valid, some row hash missing) is an accepted status per
    # the package README and the public SDK verifier.
    pack_path, _ = _make_pack(tmp_path, missing_chain_hash=True)
    members = _read_members(pack_path)
    payload = json.loads(members[_chain_name(members)].decode("utf-8"))
    assert payload["verification_status"] == "PARTIAL"
    assert verifier.verify_pack(str(pack_path)) is True


def test_partial_pack_with_forged_hash_fails(tmp_path):
    pack_path, _ = _make_pack(tmp_path, missing_chain_hash=True)
    members = _read_members(pack_path)
    chain_name = _chain_name(members)
    payload = json.loads(members[chain_name].decode("utf-8"))
    assert payload["verification_status"] == "PARTIAL"
    payload["content_hash"] = "0" * 64
    members[chain_name] = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    members = _resign_members(members)
    rebuilt = _write_members(tmp_path, "partial_forged.zip", members)
    assert verifier.verify_pack(str(rebuilt)) is False


# ---------------------------------------------------------------------------
# S7: evidence_context_*.json member
# ---------------------------------------------------------------------------


def _evidence_name(members):
    names = [n for n in members if n.startswith("evidence_context_") and n.endswith(".json")]
    assert len(names) == 1, names
    return names[0]


def test_pack_declares_evidence_context_member(tmp_path):
    pack_path, meta = _make_pack(tmp_path)
    members = _read_members(pack_path)
    name = _evidence_name(members)
    manifest = json.loads(members["manifest.json"])
    assert name in {entry["name"] for entry in manifest["files"]}
    assert manifest["evidence_context"]["path"] == name
    context = json.loads(members[name])
    assert "rule_versions" in context and "known_gaps" in context
    assert verifier.verify_pack(str(pack_path)) is True


def test_tampered_evidence_context_fails(tmp_path):
    pack_path, _ = _make_pack(tmp_path)
    members = _read_members(pack_path)
    name = _evidence_name(members)
    context = json.loads(members[name])
    context["known_gaps"]["coverage_gate_bypassed"] = not context["known_gaps"]["coverage_gate_bypassed"]
    members[name] = json.dumps(context, indent=2, sort_keys=True).encode("utf-8")
    tampered = _write_members(tmp_path, "tampered-evidence.zip", members)
    assert verifier.verify_pack(str(tampered)) is False
