#!/usr/bin/env python3
"""
Format chaos engineering test results for GitHub Step Summary.

Reads chaos_results.json (produced by chaos test runner) and outputs
a markdown summary table with pass/fail counts and scenario details.
"""

import argparse
import json
import os
import sys
from pathlib import Path


def load_results(path: str) -> list[dict]:
    """Load chaos results from JSON file."""
    results_path = Path(path)
    if not results_path.exists():
        return []
    with open(results_path) as f:
        data = json.load(f)
    return data if isinstance(data, list) else [data]


def format_markdown(results: list[dict]) -> str:
    """Format results as a markdown summary table."""
    lines = []
    total = len(results)
    passed = sum(1 for r in results if r.get("status") in ("passed", "success", "ok"))
    failed = total - passed

    lines.append("## Chaos Engineering Results\n")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Tests Run | {total} |")
    lines.append(f"| Passed | {passed} |")
    lines.append(f"| Failed | {failed} |")
    lines.append(f"| Pass Rate | {(passed / total * 100):.0f}% |" if total > 0 else "| Pass Rate | N/A |")
    lines.append("")

    if results:
        lines.append("### Scenario Details\n")
        lines.append("| Scenario | Status | Duration | Notes |")
        lines.append("|----------|--------|----------|-------|")
        for r in results:
            name = r.get("name", r.get("scenario", "unknown"))
            status = r.get("status", "unknown")
            duration = r.get("duration", r.get("elapsed_ms", "-"))
            if isinstance(duration, (int, float)):
                duration = f"{duration:.0f}ms"
            notes = r.get("error", r.get("message", "-"))
            emoji = "pass" if status in ("passed", "success", "ok") else "FAIL"
            lines.append(f"| {name} | {emoji} | {duration} | {notes} |")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Format chaos engineering test results as markdown.",
    )
    parser.add_argument(
        "--input",
        default=os.path.join(os.getcwd(), "chaos_results.json"),
        help="Path to chaos_results.json (default: ./chaos_results.json)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path (default: stdout)",
    )
    args = parser.parse_args()

    results = load_results(args.input)
    if not results:
        print("| Metric | Value |")
        print("|--------|-------|")
        print(f"| Tests Run | 0 (no results at {args.input}) |")
        print("| Status | No results file found |")
        return 0

    markdown = format_markdown(results)

    if args.output:
        Path(args.output).write_text(markdown)
        print(f"Results written to {args.output}")
    else:
        print(markdown)

    # Exit non-zero if any test failed
    failed = sum(1 for r in results if r.get("status") not in ("passed", "success", "ok"))
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
