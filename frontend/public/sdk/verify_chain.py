#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""RegEngine /proof bundle verifier.

Recomputes each manifest-declared file's SHA-256 and the Merkle root inside
an audit bundle, then compares them with the values in that same manifest.
For FDA packages, it also rejects a declared failed chain and cross-checks the
manifest summary against the hashed chain artifact. It does not independently
recompute that persisted chain. Exits non-zero on a mismatch or failed chain.
These checks establish internal consistency; they do not authenticate the
issuer or establish that source data is accurate. No digital signature or
independently trusted hash is verified.

The Merkle algorithm matches services/shared/merkle_tree.py in production:
    leaf  = sha256("leaf|" + hex_file_sha256)
    pair  = sha256(left + "|" + right)
    odd-node padding: duplicate the last node

Usage:
    python verify_chain.py your-bundle.zip

Copyright (c) 2024-2026 RegEngine LLC
License: Apache License 2.0 (https://www.apache.org/licenses/LICENSE-2.0) —
free to use, copy, modify, embed, and redistribute.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from typing import Any

LEAF_PREFIX = "leaf|"
NODE_SEPARATOR = "|"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash_leaf(file_sha256: str) -> str:
    return hashlib.sha256(f"{LEAF_PREFIX}{file_sha256}".encode("utf-8")).hexdigest()


def _hash_pair(left: str, right: str) -> str:
    return hashlib.sha256(f"{left}{NODE_SEPARATOR}{right}".encode("utf-8")).hexdigest()


def _merkle_root(file_hashes: list[str]) -> str:
    if not file_hashes:
        return hashlib.sha256(b"empty").hexdigest()
    layer = [_hash_leaf(h) for h in file_hashes]
    if len(layer) % 2 == 1 and len(layer) > 1:
        layer.append(layer[-1])
    while len(layer) > 1:
        nxt = []
        for i in range(0, len(layer), 2):
            right = layer[i + 1] if i + 1 < len(layer) else layer[i]
            nxt.append(_hash_pair(layer[i], right))
        layer = nxt
    return layer[0]


def _fail(msg: str, *, result: str = "bundle TAMPERED") -> int:
    sys.stdout.flush()
    print(f"verify: FAILED — {msg}")
    print(f"result: {result}")
    return 1


def verify_bundle(zip_path: str) -> int:
    try:
        bundle = zipfile.ZipFile(zip_path, "r")
    except (FileNotFoundError, zipfile.BadZipFile) as exc:
        return _fail(f"could not open {zip_path}: {exc}")

    with bundle:
        name_list = bundle.namelist()
        duplicate_members = sorted(name for name in set(name_list) if name_list.count(name) > 1)
        if duplicate_members:
            return _fail(
                f"bundle contains duplicate ZIP entries: {duplicate_members}",
                result="bundle INVALID",
            )
        names = set(name_list)
        if "manifest.json" not in names:
            return _fail("manifest.json missing from bundle")

        try:
            manifest: dict[str, Any] = json.loads(bundle.read("manifest.json"))
        except json.JSONDecodeError as exc:
            return _fail(f"manifest.json is not valid JSON: {exc}")

        files = manifest.get("files")
        merkle = manifest.get("merkle")
        if not isinstance(files, list) or not files:
            return _fail("manifest.files missing or empty")
        if not isinstance(merkle, dict) or "root" not in merkle:
            return _fail("manifest.merkle.root missing")

        declared_paths = [
            entry.get("path") for entry in files if isinstance(entry, dict) and isinstance(entry.get("path"), str)
        ]
        duplicate_declared_paths = sorted(path for path in set(declared_paths) if declared_paths.count(path) > 1)
        if duplicate_declared_paths:
            return _fail(
                f"manifest declares duplicate file paths: {duplicate_declared_paths}",
                result="bundle INVALID",
            )
        undeclared_members = sorted(names - {"manifest.json", *declared_paths})
        if undeclared_members:
            return _fail(
                f"bundle has members not declared in manifest: {undeclared_members}",
                result="bundle INVALID",
            )

        print("manifest: ok")

        # Per-file SHA-256 + size check.
        recomputed: list[str] = []
        for entry in files:
            path = entry.get("path")
            declared = entry.get("sha256")
            declared_size = entry.get("size")
            if not path or not declared:
                return _fail("file entry missing path or sha256")
            if path not in names:
                return _fail(f"{path} declared in manifest but missing from bundle")
            data = bundle.read(path)
            if declared_size is not None and len(data) != declared_size:
                return _fail(f"{path}: size {len(data)} != declared {declared_size}")
            actual = _sha256_bytes(data)
            if actual != declared:
                return _fail(f"{path}: sha256 mismatch (got {actual}, declared {declared})")
            recomputed.append(actual)

        total = len(files)
        print(f"files: {total} / {total} sha256 matches")

        # Merkle root — recomputed from the file hashes we just verified,
        # not from manifest.merkle.leaves. The manifest's leaves array is
        # cross-checked but is not the source of truth.
        declared_leaves = merkle.get("leaves")
        if isinstance(declared_leaves, list) and declared_leaves != recomputed:
            return _fail("manifest.merkle.leaves does not match recomputed file hashes")

        root = _merkle_root(recomputed)
        if root != merkle["root"]:
            return _fail(f"merkle root mismatch (recomputed {root}, declared {merkle['root']})")
        print("merkle: root recomputed and matched")

        # FDA packages summarize the persisted-chain result in the manifest
        # and carry the complete result in a file covered by the checks above.
        # Cross-check both because manifest.json cannot hash itself. Generic
        # bundles without this metadata retain their integrity-only behavior.
        verification = manifest.get("verification")
        chain_paths = [
            entry.get("path")
            for entry in files
            if isinstance(entry, dict)
            and isinstance(entry.get("path"), str)
            and entry["path"].startswith("chain_verification_")
            and entry["path"].endswith(".json")
        ]
        is_fda_package = manifest.get("export_type") == "fda_traceability_package" or bool(chain_paths)
        if is_fda_package:
            if not isinstance(verification, dict):
                return _fail(
                    "FDA package manifest.verification must be present as an object",
                    result="bundle UNVERIFIED",
                )
            if len(chain_paths) != 1:
                return _fail(
                    f"FDA package must declare exactly one chain_verification_*.json member; found {len(chain_paths)}",
                    result="bundle UNVERIFIED",
                )
            try:
                chain_payload = json.loads(bundle.read(chain_paths[0]).decode("utf-8"))
            except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                return _fail(
                    f"chain verification artifact is unreadable: {exc}",
                    result="bundle UNVERIFIED",
                )
            if not isinstance(chain_payload, dict):
                return _fail(
                    "chain verification artifact must contain a JSON object",
                    result="bundle UNVERIFIED",
                )

            chain_result = chain_payload.get("chain_verification")
            coverage = chain_payload.get("row_hash_coverage")
            if not isinstance(chain_result, dict) or not isinstance(coverage, dict):
                return _fail(
                    "chain verification artifact is missing chain_verification or row_hash_coverage",
                    result="bundle UNVERIFIED",
                )

            status = verification.get("status")
            chain_valid = verification.get("chain_valid")
            manifest_chain_length = verification.get("chain_length")
            artifact_status = chain_payload.get("verification_status")
            artifact_chain_valid = chain_result.get("valid")
            artifact_chain_length = chain_result.get("chain_length")
            missing_counts = (
                coverage.get("missing_record_hashes"),
                coverage.get("missing_chain_hashes"),
            )
            counts_valid = all(
                isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in missing_counts
            )
            lengths_valid = (
                isinstance(artifact_chain_length, int)
                and not isinstance(artifact_chain_length, bool)
                and artifact_chain_length >= 0
                and (
                    manifest_chain_length is None
                    or (
                        isinstance(manifest_chain_length, int)
                        and not isinstance(manifest_chain_length, bool)
                        and manifest_chain_length >= 0
                    )
                )
            )
            missing_hashes = sum(missing_counts) if counts_valid else None
            truth_table_valid = (
                (status == "VERIFIED" and chain_valid is True and missing_hashes == 0)
                or (
                    status == "PARTIAL"
                    and chain_valid is True
                    and isinstance(missing_hashes, int)
                    and missing_hashes > 0
                )
                or (status == "UNVERIFIED" and chain_valid is False and counts_valid)
            )
            metadata_consistent = (
                truth_table_valid
                and lengths_valid
                and status == artifact_status
                and chain_valid is artifact_chain_valid
                and (manifest_chain_length is None or manifest_chain_length == artifact_chain_length)
            )
            if not metadata_consistent:
                return _fail(
                    "manifest/chain status, validity, length, or row-hash coverage is inconsistent",
                    result="bundle UNVERIFIED",
                )
            if status == "UNVERIFIED":
                return _fail(
                    "persisted chain status is UNVERIFIED",
                    result="bundle UNVERIFIED",
                )
            print(f"chain: persisted status {status} matches declared chain artifact")

        print("result: bundle intact")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a RegEngine audit bundle (zip with manifest.json).")
    parser.add_argument("bundle", help="Path to an exported audit bundle ZIP")
    args = parser.parse_args()
    return verify_bundle(args.bundle)


if __name__ == "__main__":
    raise SystemExit(main())
