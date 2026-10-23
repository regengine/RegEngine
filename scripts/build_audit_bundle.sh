#!/usr/bin/env bash
# Build the public /proof audit bundle ZIP.
#
# Packages:
#   - fsma-204-sample.csv  (source CSV; removed from frontend/public/proof, so this
#     script now exits with "not found" until a real export is placed there)
#   - manifest.json        (per-file SHA-256 + Merkle root over those leaves)
#
# Merkle algorithm matches services/shared/merkle_tree.py:
#   leaf = sha256("leaf|" + sha256(file_bytes).hexdigest())
#   node = sha256(left + "|" + right)
#   odd-leaf-out: duplicate the last leaf (standard Merkle padding)
#   single-leaf tree: root = leaf hash
#
# Usage:
#   scripts/build_audit_bundle.sh
#
# Output: frontend/public/proof/audit-bundle.zip
#
# The companion sample-regenerator PR can invoke this to refresh the bundle
# whenever the underlying CSV is regenerated from production code.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROOF_DIR="$ROOT/frontend/public/proof"
CSV="$PROOF_DIR/fsma-204-sample.csv"
OUT="$PROOF_DIR/audit-bundle.zip"

if [[ ! -f "$CSV" ]]; then
  echo "error: $CSV not found" >&2
  exit 1
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

cp "$CSV" "$WORK/fsma-204-sample.csv"

python3 - "$WORK" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

work = Path(sys.argv[1])
csv_path = work / "fsma-204-sample.csv"

def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def hash_leaf(event_hash: str) -> str:
    return hashlib.sha256(f"leaf|{event_hash}".encode("utf-8")).hexdigest()

def hash_pair(left: str, right: str) -> str:
    return hashlib.sha256(f"{left}|{right}".encode("utf-8")).hexdigest()

def merkle_root(hashes: list[str]) -> str:
    if not hashes:
        return hashlib.sha256(b"empty").hexdigest()
    layer = [hash_leaf(h) for h in hashes]
    if len(layer) == 1:
        return layer[0]
    while len(layer) > 1:
        if len(layer) % 2 == 1:
            layer.append(layer[-1])
        layer = [hash_pair(layer[i], layer[i + 1]) for i in range(0, len(layer), 2)]
    return layer[0]

csv_bytes = csv_path.read_bytes()
csv_hash = sha256_hex(csv_bytes)

files = [{"path": "fsma-204-sample.csv", "size": len(csv_bytes), "sha256": csv_hash}]
root = merkle_root([csv_hash])

manifest = {
    "_comment": "SYNTHETIC — RegEngine /proof audit bundle. Hashes are real; data is not.",
    "version": "1.0",
    "merkle": {
        "algorithm": "sha256",
        "leaf_prefix": "leaf|",
        "node_separator": "|",
        "padding": "duplicate-last",
        "leaves": [csv_hash],
        "root": root,
    },
    "files": files,
    "verifier": "frontend/public/sdk/verify_chain.py",
}
(work / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(f"merkle_root={root}")
PY

(cd "$WORK" && zip -q -X "$OUT" fsma-204-sample.csv manifest.json)
echo "wrote $OUT"
