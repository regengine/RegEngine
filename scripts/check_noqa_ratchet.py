#!/usr/bin/env python3
"""CI guard — the number of ``# noqa`` markers without a reason under services/ only goes down.

Tech-debt work item WI-03 (2026-11-04). A suppression is acceptable when it
says why: ``# noqa: S105 -- enum member name, not a credential``. One without
the ``--`` reason is unexplained debt. This script counts the unexplained
markers in production code under ``services/`` (test files and ``tests/``
trees excluded) and fails when the count exceeds the committed baseline in
``scripts/noqa_baseline.txt``. Lower the baseline whenever a PR removes
markers; never raise it in a PR that adds one.

Exit code 0 = at or under the baseline. 1 = over the baseline. 2 = layout
problem (missing services/ or baseline file).

Usage:
    python scripts/check_noqa_ratchet.py
    python scripts/check_noqa_ratchet.py --repo-root /path --list
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SCAN_ROOT = "services"
BASELINE_FILE = "scripts/noqa_baseline.txt"
_NOQA = re.compile(r"#\s*noqa\b(?P<rest>[^#\n]*)")


def is_production_python(relative: str) -> bool:
    if not relative.endswith(".py"):
        return False
    parts = relative.split("/")
    return "tests" not in parts and not parts[-1].startswith("test_") and parts[-1] != "conftest.py"


def unexplained_markers(repo_root: Path) -> list[tuple[str, int, str]]:
    """(relative path, line number, line) for every ``# noqa`` lacking a ``--`` reason."""
    root = repo_root / SCAN_ROOT
    found: list[tuple[str, int, str]] = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(repo_root).as_posix()
        if not is_production_python(relative) or "__pycache__" in path.parts:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            match = _NOQA.search(line)
            if match and "--" not in match.group("rest"):
                found.append((relative, number, line.strip()))
    return found


def read_baseline(repo_root: Path) -> int:
    text = (repo_root / BASELINE_FILE).read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return int(line)
    raise ValueError(f"{BASELINE_FILE} holds no integer line")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--list", action="store_true", help="print every unexplained marker")
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    if not (repo_root / SCAN_ROOT).is_dir() or not (repo_root / BASELINE_FILE).is_file():
        print(f"!! {SCAN_ROOT}/ or {BASELINE_FILE} not found under {repo_root}", file=sys.stderr)
        return 2
    markers = unexplained_markers(repo_root)
    baseline = read_baseline(repo_root)
    if args.list:
        for relative, number, line in markers:
            print(f"{relative}:{number}: {line}")
    print(f"{len(markers)} unexplained noqa marker(s) under {SCAN_ROOT}/ (baseline {baseline})")
    if len(markers) > baseline:
        print(
            f"\nnoqa ratchet FAILED: {len(markers) - baseline} new marker(s) without a reason. "
            "Write `# noqa: <code> -- <why>` (see CONTRIBUTING.md, Code Guidelines) or fix the finding."
        )
        return 1
    if len(markers) < baseline:
        print(f"OK — below the baseline; lower {BASELINE_FILE} to {len(markers)} in this PR.")
    else:
        print("OK — at the baseline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
