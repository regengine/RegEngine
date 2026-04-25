#!/usr/bin/env python3
"""Guardrail for high-confidence legacy and dead-code drift.

This is intentionally narrower than a general lint. It blocks code paths that
were already removed as unused or obsolete, and it can consume Knip JSON output
to fail only on whole unused frontend files.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_ROOT = Path(__file__).resolve().parents[1]

TEXT_SUFFIXES = {
    ".css",
    ".env",
    ".example",
    ".html",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".mdx",
    ".mjs",
    ".py",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}

EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".turbo",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "htmlcov",
    "node_modules",
    "venv",
    ".venv",
}

EXCLUDED_PREFIXES = (
    ".claude/worktrees/",
    "docs/archive/",
)

EXCLUDED_FILES = {
    ".secrets.baseline",
    "frontend/package-lock.json",
    "scripts/check_legacy_dead_code.py",
}


@dataclass(frozen=True)
class LegacyFile:
    path: str
    replacement: str


@dataclass(frozen=True)
class LegacyPattern:
    code: str
    regex: re.Pattern[str]
    message: str


@dataclass(frozen=True)
class Finding:
    code: str
    path: str
    line: int
    message: str


BANNED_FILES = (
    LegacyFile(
        "services/shared/health.py",
        "Use service-local /health routes or shared FastAPI setup helpers.",
    ),
    LegacyFile(
        "services/shared/correlation.py",
        "Use the active request/context helpers under services/shared/.",
    ),
    LegacyFile(
        "services/ingestion/app/epcis_ingestion.py",
        "Use services/ingestion/app/epcis/router.py.",
    ),
    LegacyFile(
        "services/ingestion/app/fda_export_router.py",
        "Use services/ingestion/app/fda_export/router.py.",
    ),
    LegacyFile(
        "services/ingestion/app/sandbox_router.py",
        "Sandbox shim routes were unused and should stay deleted.",
    ),
    LegacyFile(
        "services/shared/canonical_persistence/migration.py",
        "Use the active canonical persistence package and Alembic migrations.",
    ),
    LegacyFile(
        "frontend/src/app/alpha/AlphaSignupForm.tsx",
        "Use the active login/onboarding App Router surfaces.",
    ),
    LegacyFile(
        "frontend/src/app/developers/_components/code-examples.tsx",
        "Use the active docs/developer route implementation.",
    ),
    LegacyFile(
        "frontend/src/app/developers/_components/copy-button.tsx",
        "Use the active docs/developer route implementation.",
    ),
    LegacyFile(
        "frontend/src/app/developers/_components/dev-providers.tsx",
        "Use the active docs/developer route implementation.",
    ),
    LegacyFile(
        "frontend/src/app/developers/_components/env-context.tsx",
        "Use the active docs/developer route implementation.",
    ),
    LegacyFile(
        "frontend/src/app/developers/_components/sticky-nav.tsx",
        "Use the active docs/developer route implementation.",
    ),
    LegacyFile(
        "frontend/src/app/developers/_data.ts",
        "Use the active docs/developer route implementation.",
    ),
    LegacyFile(
        "frontend/src/app/developers/developers.css",
        "Use Tailwind and the active App Router route styles.",
    ),
    LegacyFile(
        "frontend/src/app/onboarding/supplier-flow/shared/components.jsx",
        "Use typed App Router components under frontend/src/components/.",
    ),
    LegacyFile(
        "frontend/src/app/onboarding/supplier-flow/shared/styles.js",
        "Use Tailwind and typed App Router components.",
    ),
    LegacyFile(
        "frontend/src/app/onboarding/supplier-flow/steps/CTEEntry.jsx",
        "Use the active supplier onboarding components/routes.",
    ),
    LegacyFile(
        "frontend/src/app/onboarding/supplier-flow/steps/Dashboard.jsx",
        "Use the active supplier onboarding components/routes.",
    ),
    LegacyFile(
        "frontend/src/app/onboarding/supplier-flow/steps/FDAExport.jsx",
        "Use the active supplier onboarding components/routes.",
    ),
    LegacyFile(
        "frontend/src/app/onboarding/supplier-flow/steps/FTLScoping.jsx",
        "Use the active supplier onboarding components/routes.",
    ),
    LegacyFile(
        "frontend/src/app/onboarding/supplier-flow/steps/FacilitySetup.jsx",
        "Use the active supplier onboarding components/routes.",
    ),
    LegacyFile(
        "frontend/src/app/onboarding/supplier-flow/steps/HowInviteWorks.jsx",
        "Use the active supplier onboarding components/routes.",
    ),
    LegacyFile(
        "frontend/src/app/onboarding/supplier-flow/steps/HowSignupWorks.jsx",
        "Use the active supplier onboarding components/routes.",
    ),
    LegacyFile(
        "frontend/src/app/onboarding/supplier-flow/steps/Overview.jsx",
        "Use the active supplier onboarding components/routes.",
    ),
    LegacyFile(
        "frontend/src/app/onboarding/supplier-flow/steps/TLCManagement.jsx",
        "Use the active supplier onboarding components/routes.",
    ),
    LegacyFile(
        "frontend/src/components/ingestion/AnalysisResults.tsx",
        "Use the active ingestion admin flow components.",
    ),
    LegacyFile(
        "frontend/src/components/ingestion/IngestionModal.tsx",
        "Use the active ingestion admin flow components.",
    ),
)

BANNED_PATTERNS = (
    LegacyPattern(
        "legacy-shared-health-import",
        re.compile(r"\b(?:from|import)\s+shared\.health\b"),
        "services/shared/health.py was deleted as an unused legacy shim.",
    ),
    LegacyPattern(
        "legacy-shared-correlation-import",
        re.compile(r"\b(?:from|import)\s+shared\.correlation\b"),
        "services/shared/correlation.py was deleted as an unused legacy shim.",
    ),
    LegacyPattern(
        "legacy-epcis-ingestion-import",
        re.compile(r"\b(?:from|import)\s+app\.epcis_ingestion\b"),
        "app.epcis_ingestion was deleted; import the active epcis package/router.",
    ),
    LegacyPattern(
        "legacy-fda-export-router-import",
        re.compile(r"\b(?:from|import)\s+app\.fda_export_router\b"),
        "app.fda_export_router was deleted; import app.fda_export instead.",
    ),
    LegacyPattern(
        "legacy-sandbox-router-import",
        re.compile(r"\b(?:from|import)\s+app\.sandbox_router\b"),
        "app.sandbox_router was deleted as an unused sandbox shim.",
    ),
    LegacyPattern(
        "legacy-shared-file-reference",
        re.compile(r"(^|[\s`'\"])(shared/(?:health|correlation)\.py)\b"),
        "Active docs/code should not point to deleted root-style shared shims.",
    ),
    LegacyPattern(
        "legacy-ingestion-file-reference",
        re.compile(
            r"(^|[\s`'\"])(app/(?:epcis_ingestion|fda_export_router|sandbox_router)\.py)\b"
        ),
        "Active docs/code should not point to deleted ingestion shim files.",
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check for high-confidence legacy/dead-code drift."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help="Repository root. Defaults to the parent of this script directory.",
    )
    parser.add_argument(
        "--skip-patterns",
        action="store_true",
        help="Skip banned file/import scanning.",
    )
    parser.add_argument(
        "--knip-json",
        type=Path,
        help="Optional Knip JSON report. Fails only on whole unused files.",
    )
    return parser.parse_args()


def relpath(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def git_files(root: Path) -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=root,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"Unable to list git-tracked files: {exc}") from exc

    return [root / line for line in result.stdout.splitlines() if line.strip()]


def should_skip(path: Path, root: Path) -> bool:
    relative = relpath(path, root)
    if relative in EXCLUDED_FILES:
        return True
    if any(relative.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
        return True
    return any(part in EXCLUDED_DIRS for part in path.parts)


def is_text_candidate(path: Path) -> bool:
    if path.name in {"Dockerfile", ".env.example"}:
        return True
    return path.suffix in TEXT_SUFFIXES


def check_banned_files(files: Iterable[Path], root: Path) -> list[Finding]:
    tracked = {relpath(path, root) for path in files}
    findings: list[Finding] = []
    for legacy_file in BANNED_FILES:
        if legacy_file.path in tracked:
            findings.append(
                Finding(
                    code="legacy-file-reintroduced",
                    path=legacy_file.path,
                    line=1,
                    message=(
                        f"Known legacy file was reintroduced. "
                        f"{legacy_file.replacement}"
                    ),
                )
            )
    return findings


def check_patterns(files: Iterable[Path], root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in files:
        if should_skip(path, root) or not is_text_candidate(path):
            continue

        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError as exc:
            findings.append(
                Finding(
                    code="legacy-scan-read-error",
                    path=relpath(path, root),
                    line=1,
                    message=f"Could not read file during legacy scan: {exc}",
                )
            )
            continue

        for line_number, line in enumerate(lines, start=1):
            for pattern in BANNED_PATTERNS:
                if pattern.regex.search(line):
                    findings.append(
                        Finding(
                            code=pattern.code,
                            path=relpath(path, root),
                            line=line_number,
                            message=pattern.message,
                        )
                    )
    return findings


def normalize_knip_file(file_entry: object) -> str | None:
    if isinstance(file_entry, str):
        return file_entry
    if isinstance(file_entry, dict):
        for key in ("file", "path", "name"):
            value = file_entry.get(key)
            if isinstance(value, str):
                return value
    return None


def check_knip_json(report_path: Path, root: Path) -> list[Finding]:
    path = report_path if report_path.is_absolute() else root / report_path
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        return [
            Finding(
                code="knip-report-missing",
                path=relpath(path, root) if path.exists() else path.as_posix(),
                line=1,
                message=f"Knip report not found: {exc}",
            )
        ]
    except json.JSONDecodeError as exc:
        return [
            Finding(
                code="knip-report-invalid",
                path=relpath(path, root),
                line=exc.lineno,
                message=f"Knip report is not valid JSON: {exc.msg}",
            )
        ]

    issues = data.get("issues")
    if not isinstance(issues, list):
        return [
            Finding(
                code="knip-report-invalid",
                path=relpath(path, root),
                line=1,
                message="Knip report does not contain an issues list.",
            )
        ]

    findings: list[Finding] = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        files = issue.get("files")
        if not isinstance(files, list) or not files:
            continue
        issue_type = str(issue.get("type") or issue.get("name") or "unused-file")
        for file_entry in files:
            file_path = normalize_knip_file(file_entry)
            if not file_path:
                continue
            findings.append(
                Finding(
                    code=f"knip-{issue_type}",
                    path=file_path,
                    line=1,
                    message=(
                        "Knip reports this frontend file as unused. "
                        "Delete it or wire it into an active route/module."
                    ),
                )
            )
    return findings


def emit_findings(findings: list[Finding]) -> None:
    for finding in findings:
        message = finding.message.replace("\n", " ")
        print(
            f"::error file={finding.path},line={finding.line},"
            f"title={finding.code}::{message}"
        )
        print(f"{finding.path}:{finding.line}: {finding.code}: {message}")


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    findings: list[Finding] = []

    if not args.skip_patterns:
        files = git_files(root)
        findings.extend(check_banned_files(files, root))
        findings.extend(check_patterns(files, root))

    if args.knip_json:
        findings.extend(check_knip_json(args.knip_json, root))

    if findings:
        emit_findings(findings)
        print(f"\nLegacy/dead-code scan failed with {len(findings)} finding(s).")
        return 1

    print("Legacy/dead-code scan passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
