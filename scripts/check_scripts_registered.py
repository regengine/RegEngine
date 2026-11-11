#!/usr/bin/env python3
"""CI guard — every top-level entry in ``scripts/`` has a row in ``scripts/README.md``.

Tech-debt work item WI-08 (2026-10-30): ``scripts/`` had 148 scripts and 67 of
them were referenced by nothing. The registry in ``scripts/README.md`` gives
each top-level file one line (status, purpose, what invokes it) and each
subdirectory one line. This guard keeps the registry and the directory in
step, in both directions:

1. A file or directory directly under ``scripts/`` that has no row fails.
2. A row whose file or directory no longer exists fails (the registry only
   describes what is there).

Only the first level is checked: files inside subdirectories are covered by
the subdirectory's row. Hidden entries, ``__pycache__``, ``README.md`` itself
and ``_archive/`` are ignored.

Exit code 0 = clean. 1 = violation. 2 = repository layout not found.

Usage:
    python scripts/check_scripts_registered.py
    python scripts/check_scripts_registered.py --repo-root /path/to/checkout
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SCRIPTS_DIR = "scripts"
REGISTRY = "scripts/README.md"
IGNORED_NAMES: frozenset[str] = frozenset({"README.md", "__pycache__", "_archive"})

_FILE_ROW = re.compile(r"^\|\s*`([^`/]+)`\s*\|")
_DIR_ROW = re.compile(r"^\|\s*`scripts/([^`/]+)/`\s*\|")


def tree_entries(scripts_dir: Path) -> tuple[set[str], set[str]]:
    """Return (files, directories) directly under ``scripts_dir``, minus ignored names."""
    files: set[str] = set()
    dirs: set[str] = set()
    for entry in scripts_dir.iterdir():
        if entry.name.startswith(".") or entry.name in IGNORED_NAMES:
            continue
        (dirs if entry.is_dir() else files).add(entry.name)
    return files, dirs


def registry_entries(readme: Path) -> tuple[set[str], set[str]]:
    """Return (files, directories) that have a table row in the registry."""
    files: set[str] = set()
    dirs: set[str] = set()
    for line in readme.read_text(encoding="utf-8").splitlines():
        match = _DIR_ROW.match(line)
        if match:
            dirs.add(match.group(1))
            continue
        match = _FILE_ROW.match(line)
        if match:
            files.add(match.group(1))
    return files, dirs


def scan(repo_root: Path) -> list[str]:
    scripts_dir = repo_root / SCRIPTS_DIR
    readme = repo_root / REGISTRY
    if not scripts_dir.is_dir() or not readme.is_file():
        print(f"!! {SCRIPTS_DIR}/ or {REGISTRY} not found under {repo_root}", file=sys.stderr)
        sys.exit(2)
    tree_files, tree_dirs = tree_entries(scripts_dir)
    reg_files, reg_dirs = registry_entries(readme)
    problems: list[str] = []
    for name in sorted(tree_files - reg_files):
        problems.append(f"{SCRIPTS_DIR}/{name}: no row in {REGISTRY}; add one (status, purpose, invoked by)")
    for name in sorted(tree_dirs - reg_dirs):
        problems.append(f"{SCRIPTS_DIR}/{name}/: no row in the Subdirectories table of {REGISTRY}")
    for name in sorted(reg_files - tree_files):
        problems.append(f"{REGISTRY} lists `{name}`, which is not in {SCRIPTS_DIR}/; remove or correct the row")
    for name in sorted(reg_dirs - tree_dirs):
        problems.append(f"{REGISTRY} lists `scripts/{name}/`, which does not exist; remove or correct the row")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parent.parent),
        help="repository root (default: parent of scripts/)",
    )
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    problems = scan(repo_root)
    tree_files, tree_dirs = tree_entries(repo_root / SCRIPTS_DIR)
    print(f"Checked {len(tree_files)} file(s) and {len(tree_dirs)} director(y/ies) under {SCRIPTS_DIR}/")
    if problems:
        print(f"\n{SCRIPTS_DIR}/ registry guard FAILED:")
        for problem in problems:
            print(f"  {problem}")
        print(f"\nEvery top-level entry in {SCRIPTS_DIR}/ needs one row in {REGISTRY} (WI-08).")
        return 1
    print(f"OK — {REGISTRY} and {SCRIPTS_DIR}/ agree.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
