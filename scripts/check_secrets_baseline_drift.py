#!/usr/bin/env python3
"""Accept detect-secrets exit 3 only for baseline line-number drift."""

import json
import subprocess
from pathlib import Path


def without_scan_metadata(baseline: dict) -> dict:
    """Keep every finding and scanner setting; ignore only scan bookkeeping."""
    normalized = {key: value for key, value in baseline.items() if key != "generated_at"}
    normalized["results"] = {
        path: [{key: value for key, value in finding.items() if key != "line_number"} for finding in findings]
        for path, findings in baseline["results"].items()
    }
    return normalized


def main() -> int:
    committed = json.loads(
        subprocess.run(
            ["git", "show", "HEAD:.secrets.baseline"],
            check=True,
            capture_output=True,
        ).stdout
    )
    updated = json.loads(Path(".secrets.baseline").read_text(encoding="utf-8"))
    if without_scan_metadata(committed) == without_scan_metadata(updated):
        print("::notice::detect-secrets baseline line numbers drifted; findings are unchanged")
        return 0
    print("::error::detect-secrets baseline changed beyond line numbers or generated_at")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
