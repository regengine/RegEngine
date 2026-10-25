#!/usr/bin/env bash
# Build an audit bundle ZIP from a real FSMA 204 sortable export.
#
# Packages:
#   - <export>.csv   (the real export passed as the first argument)
#   - manifest.json  (per-file SHA-256 + Merkle root over those leaves)
#
# Merkle algorithm matches services/shared/merkle_tree.py:
#   leaf = sha256("leaf|" + sha256(file_bytes).hexdigest())
#   node = sha256(left + "|" + right)
#   odd-leaf-out: duplicate the last leaf (standard Merkle padding)
#   single-leaf tree: root = leaf hash
#
# Usage:
#   scripts/build_audit_bundle.sh <path-to-real-export.csv> [output.zip]
#
# There is no default sample. Output defaults to ./audit-bundle.zip in the
# current directory; it is never written into frontend/public automatically.

set -euo pipefail

usage() {
  echo "usage: $0 <path-to-real-export.csv> [output.zip]" >&2
  exit 2
}

[[ $# -ge 1 && -n "${1:-}" ]] || usage

CSV="$1"
OUT="${2:-audit-bundle.zip}"
# Resolve a relative output path against the caller's directory now, before
# anything changes into the temp directory (whose EXIT trap deletes it).
case "$OUT" in
  /*) ;;
  *) OUT="$PWD/$OUT" ;;
esac
NAME="$(basename "$CSV")"

if [[ ! -f "$CSV" ]]; then
  echo "error: $CSV not found" >&2
  usage
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

cp "$CSV" "$WORK/$NAME"

python3 - "$WORK" "$NAME" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

work = Path(sys.argv[1])
name = sys.argv[2]
csv_path = work / name

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

files = [{"path": name, "size": len(csv_bytes), "sha256": csv_hash}]
root = merkle_root([csv_hash])

manifest = {
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

# Build a fresh archive inside $WORK, then replace the destination only after
# zip succeeds, so entries from an earlier build never survive a rebuild.
(cd "$WORK" && zip -q -X "$WORK/bundle.zip" "$NAME" manifest.json)
mv -f "$WORK/bundle.zip" "$OUT"
echo "wrote $OUT"
