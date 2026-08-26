#!/usr/bin/env python3
"""Fail CI when trust-and-safety outcome claims drift back into UI copy."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC = ROOT / "frontend" / "src"
TOOLS_SRC = FRONTEND_SRC / "app" / "tools"
SCAN_ROOTS = [
    ROOT / "SECURITY.md",
    FRONTEND_SRC,
    ROOT / "frontend" / "public",
    ROOT / "docs",
    ROOT / "sales",
    ROOT / "sales_enablement",
    ROOT / "scripts",
    ROOT / "services" / "ingestion" / "app" / "fda_export",
    ROOT / "services" / "ingestion" / "app" / "proof_recall_router.py",
    ROOT / "services" / "compliance" / "app" / "routes.py",
    ROOT / "services" / "graph" / "app" / "routers" / "fsma",
    ROOT / "services" / "graph" / "app" / "fsma_audit.py",
]
ALLOWLIST_FILE = ROOT / "scripts" / "trust_safety_copy_allowlist.txt"

TEXT_EXTENSIONS = {".ts", ".tsx", ".md", ".mdx", ".json", ".sh", ".py", ".html", ".csv", ".txt", ".yml", ".yaml"}
SKIPPED_PREFIXES = [
    ROOT / ".git",
    ROOT / "frontend" / ".next",
    ROOT / "frontend" / "node_modules",
    ROOT / "frontend" / "playwright-report",
    ROOT / "frontend" / "test-results",
    ROOT / "frontend" / "coverage",
    ROOT / "frontend" / "src" / "__tests__",
    ROOT / "frontend" / "tests",
    ROOT / "docs" / "archive",
    ROOT / "docs" / "_archive",
    ROOT / "docs" / "internal",
    ROOT / "docs" / "superpowers",
    ROOT / "sales" / "local",
    ROOT / "sales_enablement" / "_archive",
]
SKIPPED_FILES = {
    ROOT / "docs" / "security" / "TRUST_CLAIMS_MATRIX.md",
    ROOT / "scripts" / "check_trust_safety_copy.py",
    ROOT / "scripts" / "trust_safety_copy_allowlist.txt",
    ROOT / "scripts" / "lifecycle_test_results.json",
}

OUTCOME_PROMISE_RE = re.compile(
    r"FDA-ready|FDA-compliant|100%\s+FDA\s+compliance|FDA[ -]?certified|"
    r"FDA[ -]?approved|FDA[ -]?formatted|§1\.1455\(c\)-formatted|exact format|"
    r"FDA[ -]?required|FDA-\s*and\s+retailer-ready|audit-ready|"
    r"24-hour\s+SLA|SLA\s+compliance|fulfills?.{0,80}FDA|matching\s+FDA\s+21\s+CFR|"
    r"1\.1455\s+compliant|compliant\s+CSV|compliance\s+package|"
    r"FDA-recommended|FDA\s+recommended|FDA's\s+preferred|required\s+format|exact\s+shape|"
    r"meets\s+all\s+FSMA|regulator-grade|directly\s+copied|"
    r"SOC\s+2\s+Type\s+II|completed\s+pentest|pentest\s+summary|production\s+SLA|"
    r"Native\s+Bidirectional|paid\s+tenants|session\s+replay",
    re.IGNORECASE,
)
COMPLIANCE_AUTOMATION_RE = re.compile(
    r"\b(?:automate|automates|automated|automating)\s+compliance\b|"
    r"\bcompliance\s+automation\b",
    re.IGNORECASE,
)
HARD_DATE_RE = re.compile(
    r"\b(?:enforcement\s+begins|deadline(?:\s+is)?|compliance\s+deadline)\s+"
    r"(?:on\s+)?(?:July\s+20,\s+2028|July\s+2028)\b|"
    r"\bJuly\s+20,\s+2028\s+is\s+the\s+FSMA\s+204\s+compliance\s+deadline\b",
    re.IGNORECASE,
)
CASE_SENSITIVE_OVERCLAIM_RE = re.compile(r"Redpanda")
OVERBROAD_COMMITMENT_RE = re.compile(
    r"\b(?:ensure|ensures|ensured|guarantee|guarantees|guaranteed)\b.{0,80}"
    r"\b(?:compliance|FSMA|FDA|SLA|audit|security|deletion|retention)\b",
    re.IGNORECASE,
)
GA_STATUS_RE = re.compile(
    r"\bGA\b\s+(?:price|pricing|tenants?|release|status|language)|"
    r"(?:price|pricing|tenants?|release|status)\s+\bGA\b|status_ga",
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


def _should_skip(path: Path) -> bool:
    resolved = path.resolve()
    if resolved in {skipped.resolve() for skipped in SKIPPED_FILES}:
        return True

    return any(resolved == prefix.resolve() or resolved.is_relative_to(prefix.resolve()) for prefix in SKIPPED_PREFIXES)


def _source_files(base: Path) -> list[Path]:
    if not base.exists():
        return []
    if base.is_file():
        return [base] if base.suffix in TEXT_EXTENSIONS and not _should_skip(base) else []
    return sorted(
        path
        for path in base.rglob("*")
        if path.is_file() and path.suffix in TEXT_EXTENSIONS and not _should_skip(path)
    )


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

    scanned_files: set[Path] = set()
    for root in SCAN_ROOTS:
        for path in _source_files(root):
            resolved = path.resolve()
            if resolved in scanned_files or resolved in allowlisted:
                continue
            scanned_files.add(resolved)
            failures.extend(_line_hits(path, OUTCOME_PROMISE_RE))
            failures.extend(_line_hits(path, CASE_SENSITIVE_OVERCLAIM_RE))
            failures.extend(_line_hits(path, COMPLIANCE_AUTOMATION_RE))
            failures.extend(_line_hits(path, HARD_DATE_RE))
            failures.extend(_line_hits(path, OVERBROAD_COMMITMENT_RE))
            failures.extend(_line_hits(path, GA_STATUS_RE))

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
