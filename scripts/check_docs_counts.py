#!/usr/bin/env python3
"""CI guard — the numbers and lists that orientation documents state match the tree.

Tech-debt work item WI-07 (2026-11-04). ``docs/CODEBASE_MAP.md`` opens with
"every claim below was checked against the working tree"; this script is what
keeps that true for the claims that are counts or lists. Each check names a
document, a regex that captures the stated value, and a pure-Python function
that computes the live value. A mismatch fails CI with both values printed.

Checks:

1. ``docs/CODEBASE_MAP.md`` §2 and §7 — the number of workflow files under
   ``.github/workflows/``.
2. ``docs/CODEBASE_MAP.md`` §4 — the number of ``include_owned_router`` calls
   in ``server/routers_mount.py`` (split out of ``server/main.py`` in WI-14).
3. ``docs/CODEBASE_MAP.md`` §4 — the fenced list of experimental routers
   equals ``EXPERIMENTAL_ROUTERS`` in ``server/router_policy.py`` (parsed
   with ``ast``, not imported).
4. ``ARCHITECTURE.md`` "Large Modules" — the table's file set equals the live
   set of non-test Python modules over 1,000 lines under the source roots.

Exit code 0 = clean. 1 = mismatch. 2 = a document or source file is missing.

Usage:
    python scripts/check_docs_counts.py
    python scripts/check_docs_counts.py --repo-root /path/to/checkout
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

CODEBASE_MAP = "docs/CODEBASE_MAP.md"
ARCHITECTURE = "ARCHITECTURE.md"
ROUTER_POLICY = "server/router_policy.py"
ROUTERS_MOUNT = "server/routers_mount.py"
SOURCE_ROOTS = ("server", "services", "regengine", "kernel", "plugins", "shared")
LARGE_MODULE_LINES = 1000
EXPERIMENTAL_MARKER = "`EXPERIMENTAL_ROUTERS` names"
LARGE_MODULES_HEADING = "### Large Modules"

_TABLE_ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*(\d+)\s*\|")


@dataclass(frozen=True)
class CountCheck:
    document: str
    pattern: str
    compute: Callable[[Path], int]
    label: str


# --- live values -----------------------------------------------------------


def workflow_count(repo_root: Path) -> int:
    folder = repo_root / ".github" / "workflows"
    return len([p for p in folder.iterdir() if p.suffix in (".yml", ".yaml")]) if folder.is_dir() else 0


def owned_router_calls(repo_root: Path) -> int:
    text = _read(repo_root / ROUTERS_MOUNT)
    return len(re.findall(r"\binclude_owned_router\(", text))


def experimental_routers(repo_root: Path) -> set[str]:
    """``EXPERIMENTAL_ROUTERS = frozenset({...})`` from server/router_policy.py."""
    tree = ast.parse(_read(repo_root / ROUTER_POLICY))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "EXPERIMENTAL_ROUTERS" for t in node.targets
        ):
            value = node.value
            if isinstance(value, ast.Call) and value.args:
                value = value.args[0]
            if isinstance(value, (ast.Set, ast.List, ast.Tuple)):
                return {elt.value for elt in value.elts if isinstance(elt, ast.Constant)}
    raise SystemExit(f"!! EXPERIMENTAL_ROUTERS literal not found in {ROUTER_POLICY}")


def large_modules(repo_root: Path) -> dict[str, int]:
    """Non-test .py files over LARGE_MODULE_LINES newlines under SOURCE_ROOTS."""
    found: dict[str, int] = {}
    for root in SOURCE_ROOTS:
        base = repo_root / root
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            parts = path.relative_to(repo_root).parts
            if "tests" in parts or "node_modules" in parts or "__pycache__" in parts or path.name.startswith("test_"):
                continue
            lines = path.read_text(encoding="utf-8", errors="replace").count("\n")
            if lines > LARGE_MODULE_LINES:
                found[path.relative_to(repo_root).as_posix()] = lines
    return found


# --- stated values ---------------------------------------------------------


def fenced_block_after(text: str, marker: str) -> list[str] | None:
    """Tokens of the first fenced code block that follows the line holding ``marker``."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if marker in line), None)
    if start is None:
        return None
    try:
        open_idx = next(i for i in range(start, len(lines)) if lines[i].startswith("```"))
        close_idx = next(i for i in range(open_idx + 1, len(lines)) if lines[i].startswith("```"))
    except StopIteration:
        return None
    return " ".join(lines[open_idx + 1 : close_idx]).split()


def render_experimental_block(names: set[str], width: int = 70) -> str:
    """The canonical fenced block: sorted names, wrapped. Used to correct the doc."""
    rows: list[str] = []
    current = ""
    for name in sorted(names):
        candidate = f"{current}  {name}" if current else name
        if len(candidate) > width:
            rows.append(current)
            current = name
        else:
            current = candidate
    if current:
        rows.append(current)
    return "```\n" + "\n".join(rows) + "\n```"


def stated_large_modules(text: str) -> dict[str, int] | None:
    start = text.find(LARGE_MODULES_HEADING)
    if start < 0:
        return None
    rows: dict[str, int] = {}
    for line in text[start:].splitlines():
        match = _TABLE_ROW.match(line)
        if match:
            rows[match.group(1)] = int(match.group(2))
        elif rows and line.startswith("#"):
            break
    return rows


COUNT_CHECKS: tuple[CountCheck, ...] = (
    CountCheck(CODEBASE_MAP, r"`\.github/workflows/` \| (\d+) workflows", workflow_count, "§2 workflow count"),
    CountCheck(CODEBASE_MAP, r"CI is (\d+) workflows under", workflow_count, "§7 workflow count"),
    CountCheck(
        CODEBASE_MAP,
        r"`server/routers_mount.py` makes (\d+) `include_owned_router` calls",
        owned_router_calls,
        "§4 include_owned_router count",
    ),
)


# --- scan ------------------------------------------------------------------


def _read(path: Path) -> str:
    if not path.is_file():
        raise SystemExit(f"!! missing file: {path}")
    return path.read_text(encoding="utf-8")


def scan(repo_root: Path) -> list[str]:
    problems: list[str] = []
    for check in COUNT_CHECKS:
        text = _read(repo_root / check.document)
        match = re.search(check.pattern, text)
        if match is None:
            problems.append(f"{check.document}: {check.label}: no sentence matches /{check.pattern}/")
            continue
        stated, live = int(match.group(1)), check.compute(repo_root)
        if stated != live:
            problems.append(f"{check.document}: {check.label}: document says {stated}, tree has {live}")

    map_text = _read(repo_root / CODEBASE_MAP)
    tokens = fenced_block_after(map_text, EXPERIMENTAL_MARKER)
    if tokens is None:
        problems.append(f"{CODEBASE_MAP}: §4: no fenced block follows the line containing {EXPERIMENTAL_MARKER!r}")
    else:
        stated_set, live_set = set(tokens), experimental_routers(repo_root)
        if stated_set != live_set:
            problems.append(
                f"{CODEBASE_MAP}: §4 experimental routers: document lists "
                f"{sorted(stated_set - live_set) or '-'} that the frozenset lacks and omits "
                f"{sorted(live_set - stated_set) or '-'}; replace the block with:\n"
                + render_experimental_block(live_set)
            )

    arch_text = _read(repo_root / ARCHITECTURE)
    stated_rows = stated_large_modules(arch_text)
    if stated_rows is None:
        problems.append(f"{ARCHITECTURE}: heading {LARGE_MODULES_HEADING!r} not found")
    else:
        live_rows = large_modules(repo_root)
        missing = sorted(set(live_rows) - set(stated_rows))
        extra = sorted(set(stated_rows) - set(live_rows))
        if missing or extra:
            problems.append(
                f"{ARCHITECTURE}: large-module table: not listed {missing or '-'}; "
                f"listed but no longer over {LARGE_MODULE_LINES} lines {extra or '-'}"
            )
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
    if problems:
        print("Docs count check FAILED:")
        for problem in problems:
            print(f"  {problem}")
        print("\nCorrect the document (or the code, if the document is right). Numbers in docs/CODEBASE_MAP.md and")
        print("ARCHITECTURE.md are checked against the tree by scripts/check_docs_counts.py (WI-07).")
        return 1
    print(f"OK — {len(COUNT_CHECKS)} counts, the experimental router list and the large-module table match the tree.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
