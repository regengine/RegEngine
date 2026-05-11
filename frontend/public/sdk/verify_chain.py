#!/usr/bin/env python3
"""RegEngine /proof bundle verifier.

Recomputes every per-file SHA-256 and the Merkle root inside an audit
bundle and compares them against the values RegEngine signed into
manifest.json. Exits non-zero on any mismatch.

The Merkle algorithm matches services/shared/merkle_tree.py in production:
    leaf  = sha256("leaf|" + hex_file_sha256)
    pair  = sha256(left + "|" + right)
    odd-node padding: duplicate the last node

Usage:
    python verify_chain.py audit-bundle.zip
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


def _fail(msg: str) -> int:
    sys.stdout.flush()
    print(f"verify: FAILED — {msg}")
    print("result: bundle TAMPERED")
    return 1


def verify_bundle(zip_path: str) -> int:
    try:
        bundle = zipfile.ZipFile(zip_path, "r")
    except (FileNotFoundError, zipfile.BadZipFile) as exc:
        return _fail(f"could not open {zip_path}: {exc}")

    with bundle:
        names = set(bundle.namelist())
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
                return _fail(
                    f"{path}: size {len(data)} != declared {declared_size}"
                )
            actual = _sha256_bytes(data)
            if actual != declared:
                return _fail(
                    f"{path}: sha256 mismatch (got {actual}, declared {declared})"
                )
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
            return _fail(
                f"merkle root mismatch (recomputed {root}, declared {merkle['root']})"
            )
        print("merkle: root recomputed and matched")
        print("result: bundle intact")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify a RegEngine audit bundle (zip with manifest.json)."
    )
    parser.add_argument("bundle", help="Path to audit-bundle.zip")
    args = parser.parse_args()
    return verify_bundle(args.bundle)


if __name__ == "__main__":
    raise SystemExit(main())
