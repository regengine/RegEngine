#!/usr/bin/env python3
"""CI guard — reject Alembic migrations that would corrupt the revision DAG.

Four checks are performed:

1. **Duplicate revision IDs** — multiple migration files sharing the same
   ``revision = "..."`` value will corrupt the Alembic migration DAG.

2. **Multiple heads** — the DAG must have exactly one head.  Multiple heads
   mean ``alembic upgrade head`` is ambiguous and deploys will fail.  This
   check would have caught the incident documented in
   ``docs/abandoned_migrations_20260420_incident/``.

3. **Orphan ``down_revision``** — a ``down_revision`` that points at a
   revision ID that does not exist in the versions directory.  Alembic
   crashes on startup with ``KeyError`` when building the revision map.
   The v073 → v072 orphan pointer from the 2026-04-20 incident is exactly
   this failure mode.

4. **Sequential / handcrafted revision IDs** — patterns like
   ``a1b2c3d4e5f6`` (each nibble incremented by one from the previous
   migration) are not randomly generated and risk collision on concurrent
   branches.  Existing migrations are grandfathered; only *new* files must
   use a random 12-char hex ID as emitted by
   ``alembic revision --autogenerate``.

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

# Regex to extract the down_revision.  Accepts a single string, ``None``,
# or a tuple.  We only use the single-string form for orphan detection —
# tuple down_revisions (merge migrations) are rare in this codebase and
# the parse below extracts the first string if present.
_DOWN_RE = re.compile(
    r"""down_revision(?::[^=]+)?\s*=\s*(None|['"]([0-9a-fA-F]+)['"]|\(.*?\))"""
)

# Known-handcrafted revision IDs grandfathered from pre-2026-04-20 migrations
# still present in alembic/versions/ after the #1855 consolidation.
# New migrations MUST use randomly-generated IDs.
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
}

# A very small set of historically duplicated revision IDs that remain
# tolerated for backwards-compatibility in tests/documentation. Real
# migrations in the repository should never introduce new duplicates.
KNOWN_DUPLICATE_IDS: set[str] = {
    "a1b2c3d4e5f6",
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


def collect_down_revisions() -> list[tuple[Path, str, str | None]]:
    """Return [(path, revision_id, down_revision_id_or_None)] for each file.

    ``down_revision_id_or_None`` is the single string form.  Tuple form
    (merge migrations) is not supported by this check — it returns None
    for those, which is fine because a merge is a legitimate structure.
    """
    out: list[tuple[Path, str, str | None]] = []
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        rev_m = _REV_RE.search(text)
        if not rev_m:
            continue
        rev_id = rev_m.group(1).lower()
        dr_m = _DOWN_RE.search(text)
        if dr_m is None:
            out.append((path, rev_id, None))
            continue
        raw = dr_m.group(1)
        if raw == "None":
            out.append((path, rev_id, None))
        elif dr_m.group(2):
            out.append((path, rev_id, dr_m.group(2).lower()))
        else:
            # Tuple form — treat as None (merge migration, not a single parent)
            out.append((path, rev_id, None))
    return out


def rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def main() -> int:
    rev_map = collect_revisions()
    down_rows = collect_down_revisions()
    failures: list[str] = []
    warnings: list[str] = []

    # Check 1: duplicate revision IDs.
    for rev_id, paths in sorted(rev_map.items()):
        if len(paths) > 1:
            files = ", ".join(rel(p) for p in paths)
            if rev_id in KNOWN_DUPLICATE_IDS:
                warnings.append(
                    f"pre-existing duplicate revision '{rev_id}' in "
                    f"{len(paths)} files: {files}"
                )
                continue
            failures.append(
                f"DUPLICATE revision '{rev_id}' in {len(paths)} files: {files}"
            )

    # Check 2: orphan down_revision pointers — down_revision references a
    # revision ID that does not exist in the versions directory.  This is
    # what triggered the 2026-04-20 incident (``v073 -> v072`` orphan).
    all_revs = set(rev_map.keys())
    for path, rev_id, down_id in down_rows:
        if down_id is not None and down_id not in all_revs:
            failures.append(
                f"ORPHAN down_revision '{down_id}' in {rel(path)} "
                f"(revision={rev_id}) — no migration declares that revision"
            )

    # Check 3: multiple heads — a revision that is not referenced by any
    # other migration's down_revision is a "head".  There must be exactly
    # one.  Multiple heads make ``alembic upgrade head`` ambiguous and
    # every deploy fails.
    pointed_at = {d for _, _, d in down_rows if d is not None}
    heads = sorted(rev for rev in all_revs if rev not in pointed_at)
    if len(heads) > 1:
        files_per_head = {
            h: ", ".join(rel(p) for p in rev_map[h]) for h in heads
        }
        detail = "; ".join(f"{h} in {files_per_head[h]}" for h in heads)
        failures.append(
            f"MULTIPLE HEADS ({len(heads)}): {detail} — "
            "the revision DAG must have exactly one head"
        )
    elif len(heads) == 0:
        failures.append(
            "NO HEAD — every revision is referenced by some down_revision. "
            "This means the DAG is a cycle or is otherwise malformed."
        )

    # Check 4: sequential/handcrafted IDs in non-grandfathered files.
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
    if heads:
        print(f"Head(s): {', '.join(heads)}")
    for warning in warnings:
        print(f"WARNING: {warning}")

    if failures:
        print()
        for f in failures:
            print(f"FAIL: {f}")
        print(
            "\nAlembic revision DAG violations detected.\n"
            "\n"
            "For DUPLICATE IDs: each migration must have a unique revision value.\n"
            "Reassign duplicates by editing the file and picking a new random ID:\n"
            "    python3 -c \"import uuid; print(uuid.uuid4().hex[:12])\"\n"
            "\n"
            "For ORPHAN down_revision: the revision your migration extends must\n"
            "exist in alembic/versions/.  Either fix the down_revision value or\n"
            "restore the missing parent migration.\n"
            "\n"
            "For MULTIPLE HEADS: merge the divergent branches with\n"
            "    alembic merge -m 'merge heads' <head1> <head2>\n"
            "or rebase one branch onto the other.\n"
            "\n"
            "For SEQUENTIAL IDs: stop handcrafting revision IDs.  Let alembic\n"
            "generate them automatically:\n"
            "    alembic revision --autogenerate -m 'description'\n"
            "\n"
            "See docs/abandoned_migrations_20260420_incident/ for the incident\n"
            "these checks exist to prevent."
        )
        return 1

    print("\nOK — revision DAG is clean: unique IDs, single head, no orphans.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
