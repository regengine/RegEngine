#!/usr/bin/env python3
"""Render ``--ignore=<path>`` flags for the ingestion suite-runs gate.

The allowlist lives in ``services/ingestion/tests/suite-runs.toml`` so it's
explicit and grep-able. CI calls this script and ``$(...)``-splices the
output into the pytest invocation; same script works locally.

Output is a single line of space-separated flags, e.g.

    --ignore=services/ingestion/tests/test_boundaries.py --ignore=...

Exits non-zero if any listed file is missing on disk — keeps the allowlist
honest after deletes/renames.
"""
from __future__ import annotations

import sys
from pathlib import Path

# tomllib is stdlib on 3.11+; we standardize on 3.11 in CI.
try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover  - Python <3.11 fallback
    import tomli as tomllib  # type: ignore[no-redef]

REPO_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = REPO_ROOT / "services" / "ingestion" / "tests"
CONFIG = TESTS_DIR / "suite-runs.toml"


def _load_ignores() -> list[str]:
    if not CONFIG.is_file():
        print(f"ERROR: {CONFIG} missing", file=sys.stderr)
        sys.exit(2)
    with CONFIG.open("rb") as handle:
        data = tomllib.load(handle)
    section = data.get("ignore", {})
    files: list[str] = []
    for group in ("poisoners", "pre_existing_failures"):
        files.extend(section.get(group, []))
    return files


def main() -> int:
    files = _load_ignores()
    flags: list[str] = []
    missing: list[str] = []
    for name in files:
        if "/" in name or name.startswith(".."):
            print(f"ERROR: refusing path-traversal entry: {name!r}", file=sys.stderr)
            return 2
        path = TESTS_DIR / name
        if not path.is_file():
            missing.append(name)
            continue
        # Emit a repo-root-relative path so the splice works from any
        # working directory.
        flags.append(f"--ignore={path.relative_to(REPO_ROOT)}")
    if missing:
        print(
            "ERROR: suite-runs.toml lists files that no longer exist: "
            + ", ".join(missing),
            file=sys.stderr,
        )
        return 2
    print(" ".join(flags))
    return 0


if __name__ == "__main__":
    sys.exit(main())
