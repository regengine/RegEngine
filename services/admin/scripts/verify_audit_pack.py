#!/usr/bin/env python3
"""
RegEngine Independent Verification SDK (V2-Audit)
------------------------------------------------
A standalone utility for auditors and regulators to verify the integrity
of a Zero-Trust Audit Pack produced by RegEngine.

The verifier recomputes every hash the pack records (CSV content hash,
per-file manifest hashes, and the manifest Merkle root) and compares each
one against its declared value. Any mismatch, missing field, or missing
file fails closed with a non-zero exit status. The pack's self-declared
``verification_status`` is never trusted on its own. The persisted row
hash chain is not replayed and the pack carries no signature, so a
rebuilt but internally consistent pack still passes. A success result
means bundle consistency only, never that the chain was rechecked.

Stdlib only, so the script runs without the RegEngine codebase.

Usage:
  python verify_audit_pack.py <path_to_zip>
"""

import hashlib
import json
import os
import sys
import zipfile
import zlib

ACCEPTABLE_STATUSES = ("VERIFIED", "PARTIAL")


def _fail(message):
    clean = str(message).replace("\r", " ").replace("\n", " ")
    print(f"FAILED: {clean}")
    return False


def _display(value):
    """Render a pack-controlled string on a single log line.

    Pack strings are attacker controlled. Newlines could otherwise plant a
    fake success line in stdout while the pack still fails.
    """
    if not isinstance(value, str):
        return repr(value)
    return value.replace("\r", " ").replace("\n", " ")


def _is_sha256_hex(value):
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return value == value.lower() and all(c in "0123456789abcdef" for c in value)


def _merkle_root(leaves):
    """Recompute the manifest Merkle root.

    Mirrors services/shared/merkle_tree.py: leaves are domain separated
    with a "leaf|" prefix, internal nodes join children with "|", and an
    odd layer duplicates its last node.
    """
    if not leaves:
        return hashlib.sha256(b"empty").hexdigest()
    layer = [hashlib.sha256(f"leaf|{leaf}".encode("utf-8")).hexdigest() for leaf in leaves]
    if len(layer) % 2 == 1 and len(layer) > 1:
        layer.append(layer[-1])
    while len(layer) > 1:
        next_layer = []
        for i in range(0, len(layer), 2):
            if i + 1 < len(layer):
                pair = f"{layer[i]}|{layer[i + 1]}"
            else:
                pair = f"{layer[i]}|{layer[i]}"
            next_layer.append(hashlib.sha256(pair.encode("utf-8")).hexdigest())
        layer = next_layer
    return layer[0]


def _is_safe_member(name):
    if not isinstance(name, str) or not name:
        return False
    if name.startswith("/") or name.startswith("\\"):
        return False
    if "\\" in name:
        return False
    if ":" in name:
        # Windows drive letters (C:/...) are absolute paths on extraction.
        return False
    if name.endswith("/"):
        return False
    segments = name.split("/")
    if any(seg in ("", ".", "..") for seg in segments):
        # Empty and "." segments are dropped by ZipFile extraction, so two
        # distinct member names could collapse onto one path on disk while
        # the verifier reads them as separate entries.
        return False
    return True


def verify_pack(zip_path):
    if not os.path.exists(zip_path):
        print(f"ERROR: File not found: {zip_path}")
        return False

    print("--- RegEngine Audit Pack Verification ---")
    print(f"Package: {os.path.basename(zip_path)}")

    try:
        zipf = zipfile.ZipFile(zip_path, "r")
    except zipfile.BadZipFile as exc:
        return _fail(f"not a readable zip archive: {exc}")
    except OSError as exc:
        return _fail(f"could not open archive: {exc}")

    try:
        with zipf:
            file_list = zipf.namelist()

            if len(set(file_list)) != len(file_list):
                dupes = sorted({n for n in file_list if file_list.count(n) > 1})
                return _fail(f"duplicate zip entries rejected: {dupes}")
            lowered = [n.lower() for n in file_list]
            if len(set(lowered)) != len(lowered):
                dupes = sorted({n for n in file_list if lowered.count(n.lower()) > 1})
                return _fail(f"case-colliding zip entries rejected: {dupes!r}")

            for name in file_list:
                if not _is_safe_member(name):
                    return _fail(f"unsafe zip entry rejected: {name!r}")

            # 1. Manifest must exist and parse.
            if "manifest.json" not in file_list:
                return _fail("missing manifest.json")
            try:
                manifest = json.loads(zipf.read("manifest.json").decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                return _fail(f"manifest.json is unreadable: {exc}")
            if not isinstance(manifest, dict):
                return _fail("manifest.json must contain a JSON object")

            # 2. Manifest file entries must cover the bundle exactly and match.
            files = manifest.get("files")
            if not isinstance(files, list) or not files:
                return _fail("manifest.files must be a non-empty list")
            declared_paths = []
            bad_entries = []
            for idx, entry in enumerate(files):
                if not isinstance(entry, dict):
                    bad_entries.append(f"files[{idx}]")
                    continue
                path = entry.get("path")
                digest = entry.get("sha256")
                size = entry.get("size")
                if (
                    not isinstance(path, str)
                    or not _is_safe_member(path)
                    or not _is_sha256_hex(digest)
                    or not isinstance(size, int)
                    or isinstance(size, bool)
                    or size < 0
                ):
                    bad_entries.append(str(path) if isinstance(path, str) else f"files[{idx}]")
                    continue
                declared_paths.append(path)
            if bad_entries:
                return _fail(f"malformed manifest file entries: {sorted(bad_entries)}")
            if len(set(declared_paths)) != len(declared_paths):
                dupes = sorted({p for p in declared_paths if declared_paths.count(p) > 1})
                return _fail(f"manifest declares duplicate paths: {dupes}")
            lowered_declared = [p.lower() for p in declared_paths]
            if len(set(lowered_declared)) != len(lowered_declared):
                dupes = sorted(
                    {p for p in declared_paths if lowered_declared.count(p.lower()) > 1}
                )
                return _fail(f"manifest declares case-colliding paths: {dupes!r}")
            payload_members = {name for name in file_list if name != "manifest.json"}
            declared_set = set(declared_paths)
            missing = sorted(declared_set - payload_members)
            if missing:
                return _fail(f"manifest declares files missing from the pack: {missing}")
            undeclared = sorted(payload_members - declared_set)
            if undeclared:
                return _fail(f"pack contains files not declared in manifest: {undeclared}")

            recomputed_hashes = []
            for entry in files:
                path = entry["path"]
                data = zipf.read(path)
                if len(data) != entry["size"]:
                    return _fail(f"size mismatch for {path}: manifest says {entry['size']}, actual {len(data)}")
                actual = hashlib.sha256(data).hexdigest()
                recomputed_hashes.append(actual)
                if actual != entry["sha256"]:
                    return _fail(f"hash mismatch for {path}: manifest digest does not match file bytes")
            print(f"Manifest Files: {len(files)} entries, all hashes match")

            # 3. Manifest Merkle root must match the recomputed file hashes.
            merkle = manifest.get("merkle")
            if not isinstance(merkle, dict):
                return _fail("manifest.merkle must be present as an object")
            algorithm = merkle.get("algorithm")
            if algorithm is not None and algorithm != "sha256":
                return _fail(f"unsupported manifest merkle algorithm: {algorithm!r}")
            declared_leaves = merkle.get("leaves")
            declared_root = merkle.get("root")
            if not isinstance(declared_leaves, list) or not _is_sha256_hex(declared_root):
                return _fail("manifest.merkle must record leaves and a sha256 root")
            if declared_leaves != recomputed_hashes:
                return _fail("manifest merkle leaves differ from recomputed file hashes")
            if _merkle_root(recomputed_hashes) != declared_root:
                return _fail("manifest merkle root does not match recomputed file hashes")
            print(f"Merkle Root: {declared_root[:16]}... matches recomputed value")

            # 4. Exactly one CSV evidence file and one chain artifact.
            csv_files = [n for n in file_list if n.startswith("fda_spreadsheet_") and n.endswith(".csv")]
            if len(csv_files) != 1:
                return _fail(f"pack must contain exactly one fda_spreadsheet_*.csv file; found {len(csv_files)}")
            chain_files = [n for n in file_list if n.startswith("chain_verification_") and n.endswith(".json")]
            if len(chain_files) != 1:
                return _fail(f"pack must contain exactly one chain_verification_*.json file; found {len(chain_files)}")
            csv_bytes = zipf.read(csv_files[0])
            csv_hash = hashlib.sha256(csv_bytes).hexdigest()
            print(f"CSV Evidence Hash (Computed): {csv_hash}")

            # 5. Chain artifact must be well formed and bind to the CSV bytes.
            try:
                v_data = json.loads(zipf.read(chain_files[0]).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                return _fail(f"chain verification artifact is unreadable: {exc}")
            if not isinstance(v_data, dict):
                return _fail("chain verification artifact must contain a JSON object")

            print(f"Snapshot ID: {_display(v_data.get('snapshot_id'))}")
            print(f"Captured At: {_display(v_data.get('captured_at'))}")
            print(f"Content Hash: {_display(v_data.get('content_hash'))}")
            print(f"Algorithm: {_display(v_data.get('hash_algorithm'))}")

            required_fields = [
                "version",
                "snapshot_id",
                "content_hash",
                "verification_status",
                "hash_algorithm",
            ]
            for field in required_fields:
                if field not in v_data:
                    return _fail(f"malformed verification data (missing {field})")
            if v_data.get("hash_algorithm") != "SHA-256":
                return _fail(f"unsupported hash algorithm: {v_data.get('hash_algorithm')!r}")
            if not _is_sha256_hex(v_data.get("content_hash")):
                return _fail("chain content_hash must be a sha256 hex digest")
            if v_data["content_hash"] != csv_hash:
                return _fail(
                    "chain content_hash does not match the recomputed CSV hash; "
                    "the evidence file may have been modified"
                )
            print("CSV content hash matches the chain artifact")

            # 6. Manifest summary hash must agree with the same CSV bytes.
            summary = manifest.get("summary")
            if not isinstance(summary, dict):
                return _fail("manifest.summary must be present as an object")
            summary_hash = summary.get("csv_content_hash")
            if not _is_sha256_hex(summary_hash):
                return _fail("manifest.summary.csv_content_hash must be a sha256 hex digest")
            if summary_hash != csv_hash:
                return _fail("manifest summary CSV hash does not match the recomputed CSV hash")
            print("CSV content hash matches the manifest summary")

            # 7. Manifest verification summary must agree with the chain artifact,
            # and the status must be internally consistent. The status alone
            # never passes the pack; every hash above must already match.
            verification = manifest.get("verification")
            if not isinstance(verification, dict):
                return _fail("manifest.verification must be present as an object")
            status = verification.get("status")
            chain_valid = verification.get("chain_valid")
            manifest_chain_length = verification.get("chain_length")
            if status != v_data.get("verification_status"):
                return _fail(
                    f"manifest status {status!r} disagrees with chain artifact "
                    f"status {v_data.get('verification_status')!r}"
                )
            chain_result = v_data.get("chain_verification")
            coverage = v_data.get("row_hash_coverage")
            if not isinstance(chain_result, dict) or not isinstance(coverage, dict):
                return _fail("chain artifact is missing chain_verification or row_hash_coverage")
            artifact_valid = chain_result.get("valid")
            artifact_length = chain_result.get("chain_length")
            missing_record = coverage.get("missing_record_hashes")
            missing_chain = coverage.get("missing_chain_hashes")
            if chain_valid is not artifact_valid:
                return _fail("manifest chain_valid disagrees with the chain artifact")
            if not (
                isinstance(artifact_length, int) and not isinstance(artifact_length, bool) and artifact_length >= 0
            ):
                return _fail("chain artifact chain_length must be a non-negative integer")
            if manifest_chain_length is not None and (
                not isinstance(manifest_chain_length, int)
                or isinstance(manifest_chain_length, bool)
                or manifest_chain_length != artifact_length
            ):
                return _fail("manifest chain_length disagrees with the chain artifact")
            counts_ok = all(
                isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in (missing_record, missing_chain)
            )
            if not counts_ok:
                return _fail("chain artifact row-hash counts must be non-negative integers")
            missing_total = missing_record + missing_chain
            consistent = (
                (status == "VERIFIED" and chain_valid is True and missing_total == 0)
                or (status == "PARTIAL" and chain_valid is True and missing_total > 0)
                or (status == "UNVERIFIED" and chain_valid is False)
            )
            if not consistent:
                return _fail(
                    f"chain status {status!r} is inconsistent with chain_valid={chain_valid!r} "
                    f"and missing row hashes={missing_total}"
                )

            # 8. Result: all hashes match, so the status is now meaningful.
            # The success line claims bundle consistency only. The persisted
            # row chain was not recomputed and the pack carries no signature.
            attestation = v_data.get("attestation")
            if attestation is not None and not isinstance(attestation, dict):
                return _fail("chain attestation must be an object when present")
            if status in ACCEPTABLE_STATUSES:
                print(
                    f"\n[SUCCESS] Bundle Consistency: {status} "
                    "(file hashes match; persisted chain was not recomputed)"
                )
                if isinstance(attestation, dict) and attestation.get("attested_by"):
                    print(f"Attested By: {_display(attestation.get('attested_by'))}")
                return True
            print(f"\n[FAILED] Bundle Consistency: {status} (chain check did not pass)")
            return False

    except (OSError, zipfile.BadZipFile, zlib.error, EOFError) as exc:
        return _fail(f"could not read archive contents: {exc}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python verify_audit_pack.py <path_to_zip>")
        sys.exit(1)

    success = verify_pack(sys.argv[1])
    sys.exit(0 if success else 1)
