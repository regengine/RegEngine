#!/usr/bin/env python3
"""Require complete security evidence for the exact revision being deployed."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time

REQUIRED_JOBS = (
    "Privileged Workflow Tool Pinning",
    "Secrets Scan (gitleaks)",
    "Secrets Audit (detect-secrets)",
    "Browser Storage PII Guard",
    "SAST (Semgrep)",
    "Dependency Audit",
    "Tenant Isolation & Auth Tests",
    "security.txt Expiry Check",
    "Generate SBOM (SPDX)",
    "Container Scan (Trivy)",
)


class SecurityGateError(Exception):
    """The available evidence cannot authorize deployment."""


def github_items(endpoint: str, key: str) -> list[dict]:
    result = subprocess.run(
        ["gh", "api", "--paginate", "--slurp", endpoint],
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if result.returncode:
        # Do not echo external stderr: it can contain authentication details.
        raise SecurityGateError("Unable to read security evidence from GitHub")
    pages = json.loads(result.stdout)
    return [item for page in pages for item in page[key]]


def latest_security_run(repository: str, sha: str) -> dict | None:
    runs = github_items(
        f"repos/{repository}/actions/workflows/security.yml/runs?head_sha={sha}&per_page=100",
        "workflow_runs",
    )
    eligible = [
        run
        for run in runs
        if run["head_sha"] == sha
        and run["repository"]["full_name"] == repository
        and run["head_repository"]["full_name"] == repository
        and run["path"].split("@", 1)[0] == ".github/workflows/security.yml"
        and run["event"] in {"push", "workflow_dispatch", "schedule"}
    ]
    return max(eligible, key=lambda run: run["id"], default=None)


def security_ready(repository: str, sha: str) -> bool:
    run = latest_security_run(repository, sha)
    if run is None or run["status"] != "completed":
        return False
    if run["conclusion"] != "success":
        raise SecurityGateError(f"Latest security run {run['id']} did not succeed")

    jobs = github_items(
        f"repos/{repository}/actions/runs/{run['id']}/jobs?filter=latest&per_page=100",
        "jobs",
    )
    for name in REQUIRED_JOBS:
        matching = [job for job in jobs if job["name"] == name]
        if len(matching) != 1 or any(
            job["run_id"] != run["id"]
            or job["head_sha"] != sha
            or job["status"] != "completed"
            or job["conclusion"] != "success"
            for job in matching
        ):
            raise SecurityGateError(f"Security job {name} lacks successful evidence for {sha}")

    # A rerun or newer run may have started while its jobs were read.
    latest = latest_security_run(repository, sha)
    if latest is None or any(latest[key] != run[key] for key in ("id", "run_attempt", "status", "conclusion")):
        return False
    print(f"Security run {run['id']} passed all release checks for {sha}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout-seconds", type=float, default=2700)
    parser.add_argument("--poll-interval-seconds", type=float, default=30)
    args = parser.parse_args()
    repository = os.environ.get("RELEASE_REPOSITORY", "")
    sha = os.environ.get("RELEASE_SHA", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        print("::error::Security gate requires the release repository and full commit SHA", file=sys.stderr)
        return 1
    deadline = time.monotonic() + args.timeout_seconds
    try:
        while True:
            if security_ready(repository, sha):
                return 0
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SecurityGateError(f"No completed security evidence for {sha} before the deadline")
            print(f"Waiting for security evidence for {sha}", flush=True)
            time.sleep(min(args.poll_interval_seconds, remaining))
    except SecurityGateError as exc:
        print(f"::error::{exc}", file=sys.stderr)
    except (KeyError, TypeError, ValueError, OSError, subprocess.SubprocessError):
        print("::error::Security evidence could not be read or validated", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
