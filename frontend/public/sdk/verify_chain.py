#!/usr/bin/env python3
"""RegEngine hash-chain verification helper.

Usage:
    python verify_chain.py --file audit-log.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def compute_hash(prev_hash: str, payload: dict) -> str:
    body = f"{prev_hash}|{json.dumps(payload, sort_keys=True)}".encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def verify_chain(entries: list[dict]) -> bool:
    previous = "0"
    for index, entry in enumerate(entries):
        expected = compute_hash(previous, entry.get("record", {}))
        actual = entry.get("data_hash", "")
        if expected != actual:
            print(f"Mismatch at index {index}: expected {expected}, got {actual}")
            return False
        previous = actual
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify RegEngine hash chain")
    parser.add_argument("--file", required=True, help="Path to exported audit log JSON")
    args = parser.parse_args()

    path = Path(args.file)
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("entries", payload)
    ok = verify_chain(entries)
    if ok:
        print("Hash chain verified")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
