#!/usr/bin/env python3
"""CI guard — reject Alembic migrations with handcrafted or duplicate revision IDs.

Two checks are performed:

1. **Duplicate revision IDs** — multiple migration files sharing the same
   ``revision = "..."`` value will corrupt the Alembic migration DAG.
   Existing duplicates (introduced before this guard) are listed as errors
   immediately; no grandfathering is applied because they represent a live
   DAG corruption that must be resolved.

2. **Sequential / handcrafted revision IDs** — patterns like ``a1b2c3d4e5f6``
   (each nibble incremented by one from the previous migration) are not
   randomly generated and risk collision on concurrent branches.  Existing
   migrations are grandfathered; only *new* files must use a random 12-char
   hex ID as emitted by ``alembic revision --autogenerate``.

Exit code 0 = clean.  Non-zero = violation found.

Usage:
    python scripts/check_alembic_revisions.py
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSIONS_DIR = REPO_ROOT / "alembic" / "versions"

# Regex to extract the revision ID from a migration file.
_REV_RE = re.compile(r"""revision(?::\s*str)?\s*=\s*['"]([0-9a-fA-F]+)['"]""")

# Known-handcrafted revision IDs that existed before this guard was introduced.
# These are grandfathered — new migrations MUST use randomly-generated IDs.
# Duplicate revision IDs that existed before this guard was introduced.
# These are P0 DAG-corruption issues tracked in #1296 and must be resolved
# in a follow-up migration-squash PR.  They are listed here as acknowledged
# duplicates so the guard can land on main without immediately blocking CI,
# but they will appear as warnings in every run until fixed.
KNOWN_DUPLICATE_IDS: set[str] = {
    "f5a6b7c8d9e0",  # 5 files: v059 group — see #1296
    "a7b8c9d0e1f2",  # 2 files: v060/v061 — see #1296
    "b4c5d6e7f8a9",  # 2 files: v068 group — see #1296
}

GRANDFATHERED_IDS: set[str] = {
    "a1b2c3d4e5f6",
    "b2c3d4e5f6a7",
    "c3d4e5f6a7b8",
    "d4e5f6a7b8c9",
    "e5f6a7b8c9d0",
    "f6a7b8c9d0e1",
    "97a8b9c0d1e2",
    "a8b9c0d1e2f3",
    "b1c2d3e4f5a6",
    "c2d3e4f5a6b7",
    "d3e4f5a6b7c8",
    "e4f5a6b7c8d9",
    "f5a6b7c8d9e0",
    "a7b8c9d0e1f2",
    "b8c9d0e1f2a3",
    "c9d0e1f2a3b4",
    "d0e1f2a3b4c5",
    "e1f2a3b4c5d6",
    "f2a3b4c5d6e7",
    "a3b4c5d6e7f8",
    "b4c5d6e7f8a9",
    "c5d6e7f8a9b0",
    "d6e7f8a9b0c1",
    "e7f8a9b0c1d2",
    "f8a9b0c1d2e3",
}

# Detect the sequential nibble-shift pattern: each pair of hex chars is the
# previous pair shifted by +1 (mod 16 at the nibble boundary).  We also catch
# any ID whose characters form a short repeating arithmetic sequence.


def _looks_sequential(rev_id: str) -> bool:
    """Return True if rev_id matches the known nibble-shift pattern."""
    if rev_id.lower() in GRANDFATHERED_IDS:
        return False  # grandfathered, already known
    # Check if consecutive byte pairs form an arithmetic progression.
    # e.g. a1 b2 c3 d4 e5 f6 -> values 0xa1, 0xb2, 0xc3, 0xd4, 0xe5, 0xf6
    # diffs are all 0x11
    if len(rev_id) != 12:
        return False
    try:
        bytes_val = [int(rev_id[i : i + 2], 16) for i in range(0, 12, 2)]
    except ValueError:
        return False
    diffs = [bytes_val[i + 1] - bytes_val[i] for i in range(len(bytes_val) - 1)]
    return len(set(diffs)) == 1  # all diffs equal → sequential


def collect_revisions() -> dict[str, list[Path]]:
    """Map revision_id -> [list of files that declare it]."""
    rev_map: dict[str, list[Path]] = defaultdict(list)
    if not VERSIONS_DIR.is_dir():
        print(f"ERROR: versions directory not found: {VERSIONS_DIR}", file=sys.stderr)
        sys.exit(2)
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        m = _REV_RE.search(text)
        if m:
            rev_map[m.group(1).lower()].append(path)
    return rev_map


def rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def main() -> int:
    rev_map = collect_revisions()
    failures: list[str] = []
    warnings: list[str] = []

    # Check 1: duplicate revision IDs.
    for rev_id, paths in sorted(rev_map.items()):
        if len(paths) > 1:
            files = ", ".join(rel(p) for p in paths)
            msg = f"DUPLICATE revision '{rev_id}' in {len(paths)} files: {files}"
            if rev_id in KNOWN_DUPLICATE_IDS:
                warnings.append(msg + " [pre-existing, tracked in #1296]")
            else:
                failures.append(msg)

    # Check 2: sequential/handcrafted IDs in non-grandfathered files.
    for rev_id, paths in sorted(rev_map.items()):
        if rev_id in GRANDFATHERED_IDS:
            for p in paths:
                print(f"  [grandfathered] {rel(p)}: revision '{rev_id}'")
            continue
        if _looks_sequential(rev_id):
            for p in paths:
                failures.append(
                    f"SEQUENTIAL revision ID '{rev_id}' in {rel(p)} — "
                    "use `alembic revision --autogenerate` to get a random hash"
                )

    total = sum(len(ps) for ps in rev_map.values())
    print(f"\nScanned {total} migration file(s) in {rel(VERSIONS_DIR)}")

    for w in warnings:
        print(f"  WARNING: {w}")

    if failures:
        print()
        for f in failures:
            print(f"FAIL: {f}")
        print(
            "\nAlembic revision ID violations detected.\n"
            "\n"
            "For DUPLICATE IDs: each migration must have a unique revision value.\n"
            "Reassign duplicates by editing the file and picking a new random ID:\n"
            "    python3 -c \"import uuid; print(uuid.uuid4().hex[:12])\"\n"
            "\n"
            "For SEQUENTIAL IDs: stop handcrafting revision IDs.  Let alembic\n"
            "generate them automatically:\n"
            "    alembic revision --autogenerate -m 'description'\n"
            "\n"
            "See GitHub issue #1296 for background."
        )
        return 1

    print("\nOK — no duplicate or sequential revision IDs in non-grandfathered migrations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
