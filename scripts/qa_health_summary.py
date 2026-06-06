#!/usr/bin/env python3
"""Build a redacted QA health dashboard artifact from CI test outputs."""

from __future__ import annotations

import argparse
import json
import os
import sys
import defusedxml.ElementTree as ET  # XXE-safe drop-in for xml.etree (OWASP gate)
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"


def _load_json_artifact(path: Path) -> Any | None:
    """Load a JSON artifact, tolerating empty, unreadable, or malformed files.

    Covers zero-byte artifacts, non-UTF8 / binary garbage, and unreadable
    paths — any of which a CI step can emit — so a single bad artifact never
    crashes the whole summary build.
    """
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except (UnicodeDecodeError, OSError):
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def parse_junit(path: Path | None) -> dict[str, float | int] | None:
    if path is None or not path.exists():
        return None

    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        # Empty, malformed, or unreadable JUnit XML (e.g. a zero-byte
        # artifact) — treat as absent rather than crashing the build.
        return None
    suites = [root] if root.tag == "testsuite" else list(root.findall(".//testsuite"))
    if not suites and root.tag == "testsuites":
        suites = [root]

    tests = failures = errors = skipped = 0
    duration = 0.0
    for suite in suites:
        tests += int(float(suite.attrib.get("tests", "0") or 0))
        failures += int(float(suite.attrib.get("failures", "0") or 0))
        errors += int(float(suite.attrib.get("errors", "0") or 0))
        skipped += int(float(suite.attrib.get("skipped", suite.attrib.get("disabled", "0")) or 0))
        duration += float(suite.attrib.get("time", "0") or 0)

    passed = max(tests - failures - errors - skipped, 0)
    return {
        "passed": passed,
        "failed": failures,
        "errors": errors,
        "skipped": skipped,
        "duration_seconds": round(duration, 2),
    }


def parse_eslint(path: Path | None) -> dict[str, float | int] | None:
    if path is None or not path.exists():
        return None

    data = _load_json_artifact(path)
    if data is None:
        return None
    files = data if isinstance(data, list) else []
    errors = 0
    warnings = 0
    for item in files:
        if not isinstance(item, dict):
            continue
        errors += int(item.get("errorCount") or 0)
        warnings += int(item.get("warningCount") or 0)

    return {
        "passed": max(len(files) - errors, 0),
        "failed": errors,
        "errors": 0,
        "skipped": warnings,
        "duration_seconds": None,
    }


def parse_playwright(path: Path | None) -> dict[str, float | int] | None:
    if path is None or not path.exists():
        return None

    data = _load_json_artifact(path)
    if data is None:
        return None
    stats = data.get("stats") if isinstance(data, dict) else None
    if isinstance(stats, dict):
        passed = int(stats.get("expected") or stats.get("passed") or 0)
        failed = int(stats.get("unexpected") or stats.get("failed") or 0)
        skipped = int(stats.get("skipped") or 0)
        return {
            "passed": passed,
            "failed": failed,
            "errors": 0,
            "skipped": skipped,
            "duration_seconds": _coerce_duration(stats.get("duration")),
        }

    counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    for status in _walk_playwright_statuses(data):
        if status in {"passed", "expected"}:
            counts["passed"] += 1
        elif status in {"skipped", "interrupted"}:
            counts["skipped"] += 1
        elif status in {"failed", "timedOut", "unexpected"}:
            counts["failed"] += 1
        else:
            counts["errors"] += 1
    return {**counts, "duration_seconds": None}


def build_summary(args: argparse.Namespace) -> dict[str, Any]:
    npm_ci_exit = args.npm_ci_exit_code
    suites = [
        _npm_ci_suite(npm_ci_exit),
        _suite_from_counts(
            "backend-pytest",
            "Backend pytest",
            "python3 -m pytest --no-cov",
            parse_junit(args.pytest_xml),
            blocking=True,
        ),
        _suite_from_counts(
            "frontend-lint",
            "Frontend lint",
            "npm run lint",
            parse_eslint(args.eslint_json),
            blocking=False,
        ),
        _suite_from_counts(
            "frontend-vitest",
            "Frontend Vitest",
            "npm run test:run",
            parse_junit(args.vitest_junit),
            blocking=True,
        ),
        _suite_from_counts(
            "frontend-e2e",
            "Playwright E2E",
            "npm run test:e2e",
            parse_playwright(args.playwright_json),
            blocking=True,
        ),
    ]

    clusters = _classify_clusters(suites)
    decision_checks = _decision_checks(suites)
    blocking_count = sum(1 for suite in suites if suite["blocking"] and suite["status"] == "failed")
    advisory_count = sum(1 for suite in suites if (not suite["blocking"]) and suite["status"] == "failed")
    blocking_suites = [suite for suite in suites if suite["blocking"]]
    passed_blocking = sum(1 for suite in blocking_suites if suite["status"] == "passed")
    ready_percent = int(round((passed_blocking / len(blocking_suites)) * 100)) if blocking_suites else 0

    if blocking_count:
        overall_status = "failing"
    elif advisory_count:
        overall_status = "degraded"
    elif any(suite["status"] == "unavailable" for suite in suites):
        overall_status = "unavailable"
    else:
        overall_status = "passing"

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "source": {
            "kind": "ci_artifact",
            "path": _relpath(args.out),
            "workflow": args.workflow,
            "run_id": args.run_id,
            "commit": args.commit,
            "branch": args.branch,
        },
        "overall": {
            "status": overall_status,
            "ready_percent": ready_percent,
            "blocking_count": blocking_count,
            "advisory_count": advisory_count,
        },
        "suites": suites,
        "clusters": clusters,
        "decision_checks": decision_checks,
        "artifact_refs": _artifact_refs(args),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--pytest-xml", type=Path)
    parser.add_argument("--eslint-json", type=Path)
    parser.add_argument("--vitest-junit", type=Path)
    parser.add_argument("--playwright-json", type=Path)
    parser.add_argument("--npm-ci-exit-code", type=int)
    parser.add_argument("--workflow", default=os.getenv("GITHUB_WORKFLOW", "QA Health"))
    parser.add_argument("--run-id", default=os.getenv("GITHUB_RUN_ID"))
    parser.add_argument("--commit", default=os.getenv("GITHUB_SHA"))
    parser.add_argument("--branch", default=os.getenv("GITHUB_REF_NAME"))
    args = parser.parse_args(argv)

    summary = build_summary(args)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


def _suite_from_counts(
    suite_id: str,
    label: str,
    command: str,
    counts: dict[str, float | int] | None,
    *,
    blocking: bool,
) -> dict[str, Any]:
    if counts is None:
        return {
            "id": suite_id,
            "label": label,
            "command": command,
            "status": "unavailable",
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "errors": 0,
            "duration_seconds": None,
            "blocking": blocking,
        }

    failed = int(counts["failed"])
    errors = int(counts["errors"])
    status = "failed" if failed or errors else "passed"
    return {
        "id": suite_id,
        "label": label,
        "command": command,
        "status": status,
        "passed": int(counts["passed"]),
        "failed": failed,
        "skipped": int(counts["skipped"]),
        "errors": errors,
        "duration_seconds": counts.get("duration_seconds"),
        "blocking": blocking,
    }


def _npm_ci_suite(exit_code: int | None) -> dict[str, Any]:
    if exit_code is None:
        status = "unavailable"
        passed = failed = 0
    elif exit_code == 0:
        status = "passed"
        passed = 1
        failed = 0
    else:
        status = "failed"
        passed = 0
        failed = 1
    return {
        "id": "frontend-install",
        "label": "Install drift",
        "command": "npm ci",
        "status": status,
        "passed": passed,
        "failed": failed,
        "skipped": 0,
        "errors": 0,
        "duration_seconds": None,
        "blocking": True,
    }


def _classify_clusters(suites: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {suite["id"]: suite for suite in suites}
    clusters: list[dict[str, Any]] = []
    if by_id["frontend-install"]["status"] == "failed":
        clusters.append(
            _cluster(
                "Dependency lock drift",
                "high",
                ["frontend-install"],
                "frontend",
                "Release installs are not reproducible.",
                "Reconcile frontend/package-lock.json with package.json and rerun npm ci.",
            )
        )
    if by_id["frontend-e2e"]["status"] == "failed":
        clusters.append(
            _cluster(
                "E2E auth path failures",
                "critical",
                ["frontend-e2e"],
                "frontend",
                "Browser release signal is blocked.",
                "Align Playwright login flows with the selected password/email-code mode.",
            )
        )
    if by_id["backend-pytest"]["status"] == "failed":
        clusters.append(
            _cluster(
                "Backend regression cluster",
                "critical",
                ["backend-pytest"],
                "backend",
                "Core service test signal is blocked.",
                "Split failures by owning service and fix the first shared assertion drift.",
            )
        )
    return clusters


def _cluster(
    title: str,
    severity: str,
    suites: list[str],
    owner_lane: str,
    impact: str,
    next_action: str,
) -> dict[str, Any]:
    return {
        "title": title,
        "severity": severity,
        "affected_suites": suites,
        "owner_lane": owner_lane,
        "impact": impact,
        "next_action": next_action,
    }


def _decision_checks(suites: list[dict[str, Any]]) -> list[dict[str, Any]]:
    checks = []
    for suite in suites:
        if suite["status"] == "unavailable":
            status = "unavailable"
        elif suite["status"] == "passed":
            status = "passed"
        elif suite["blocking"]:
            status = "blocking"
        else:
            status = "advisory"
        checks.append(
            {
                "label": suite["label"],
                "status": status,
                "detail": _suite_detail(suite),
            }
        )
    return checks


def _suite_detail(suite: dict[str, Any]) -> str:
    if suite["status"] == "unavailable":
        return "No output artifact was available for this suite."
    if suite["status"] == "passed":
        return f"{suite['passed']} passed"
    return f"{suite['failed']} failed, {suite['errors']} errors, {suite['skipped']} skipped"


def _artifact_refs(args: argparse.Namespace) -> list[dict[str, str]]:
    candidates = [
        ("pytest-junit", "Pytest JUnit", args.pytest_xml, "junit"),
        ("eslint-json", "ESLint JSON", args.eslint_json, "json"),
        ("vitest-junit", "Vitest JUnit", args.vitest_junit, "junit"),
        ("playwright-json", "Playwright JSON", args.playwright_json, "json"),
    ]
    refs = []
    for ref_id, label, path, ref_type in candidates:
        if path and path.exists():
            refs.append({"id": ref_id, "label": label, "path": _relpath(path), "type": ref_type})
    return refs


def _walk_playwright_statuses(value: Any) -> list[str]:
    statuses: list[str] = []
    if isinstance(value, dict):
        status = value.get("status")
        if isinstance(status, str):
            statuses.append(status)
        for child in value.values():
            statuses.extend(_walk_playwright_statuses(child))
    elif isinstance(value, list):
        for child in value:
            statuses.extend(_walk_playwright_statuses(child))
    return statuses


def _coerce_duration(value: Any) -> float | None:
    if value is None:
        return None
    try:
        duration = float(value)
    except (TypeError, ValueError):
        return None
    return round(duration / 1000 if duration > 10000 else duration, 2)


def _relpath(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd()).as_posix()
    except (OSError, ValueError):
        return path.name


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
