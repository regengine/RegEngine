#!/usr/bin/env python3
"""Fail CI when trust-and-safety outcome claims drift back into UI copy."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC = ROOT / "frontend" / "src"
TOOLS_SRC = FRONTEND_SRC / "app" / "tools"
ALLOWLIST_FILE = ROOT / "scripts" / "trust_safety_copy_allowlist.txt"

TEXT_EXTENSIONS = {".ts", ".tsx", ".md", ".mdx"}

OUTCOME_PROMISE_RE = re.compile(
    r"FDA-ready|FDA-compliant|100%\s+FDA\s+compliance|FDA[ -]?certified",
    re.IGNORECASE,
)

SELF_CHECK_VERDICT_RE = re.compile(
    r"Compliance Score|Compliance Grade|Get Your.*Compliance Report|Compliance Report",
    re.IGNORECASE,
)
STANDALONE_PASS_FAIL_JSX_RE = re.compile(r">\s*(Pass|Fail)\s*<")
GRADE_DISPLAY_RE = re.compile(
    r"text-(?:3xl|4xl|5xl)[^'\"]*(?:\{[^}]*\bgrade\b[^}]*\}|\bgrade\b)",
    re.IGNORECASE,
)
VERDICT_COLOR_RE = re.compile(r"bg-re-(?:success|danger)\b")
SELF_CHECK_CONTEXT_RE = re.compile(r"Self-Check|Self-Reported", re.IGNORECASE)


def _allowlisted_paths() -> set[Path]:
    if not ALLOWLIST_FILE.exists():
        return set()

    paths: set[Path] = set()
    for raw_line in ALLOWLIST_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        rel = line.split("#", 1)[0].strip().split()[0]
        if rel:
            paths.add((ROOT / rel).resolve())
    return paths


def _source_files(base: Path) -> list[Path]:
    if not base.exists():
        return []
    return sorted(path for path in base.rglob("*") if path.is_file() and path.suffix in TEXT_EXTENSIONS)


def _line_hits(path: Path, pattern: re.Pattern[str]) -> list[str]:
    hits: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return hits

    for lineno, line in enumerate(lines, start=1):
        if pattern.search(line):
            hits.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")
    return hits


def _windowed_self_check_color_hits(path: Path) -> list[str]:
    hits: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return hits

    for index, line in enumerate(lines):
        if not VERDICT_COLOR_RE.search(line):
            continue
        start = max(0, index - 3)
        end = min(len(lines), index + 4)
        if any(SELF_CHECK_CONTEXT_RE.search(candidate) for candidate in lines[start:end]):
            hits.append(f"{path.relative_to(ROOT)}:{index + 1}: {line.strip()}")
    return hits


def main() -> int:
    allowlisted = _allowlisted_paths()
    failures: list[str] = []

    for path in _source_files(FRONTEND_SRC):
        if path.resolve() in allowlisted:
            continue
        failures.extend(_line_hits(path, OUTCOME_PROMISE_RE))

    for path in _source_files(TOOLS_SRC):
        failures.extend(_line_hits(path, SELF_CHECK_VERDICT_RE))
        failures.extend(_line_hits(path, STANDALONE_PASS_FAIL_JSX_RE))
        failures.extend(_line_hits(path, GRADE_DISPLAY_RE))
        failures.extend(_windowed_self_check_color_hits(path))

    if failures:
        print("Banned trust-and-safety copy or grade-verdict UI found.")
        print("Use neutral self-check / gap-indicated language; operators remain responsible for compliance.")
        print()
        for failure in failures:
            print(failure)
        return 1

    print("Trust-and-safety copy gate passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
