"""Regression tests for least-privilege workflow permissions.

The defect: test-suite-check.yml and pr-quality.yml requested
``checks: write`` at the top level even though no job in either workflow
publishes check runs. Unused write permissions widen what a compromised
job or action can do with the token. These tests pin the reduced scope
and the absence of any Checks API use that would justify widening it.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = {
    ".github/workflows/test-suite-check.yml": ("checks",),
    ".github/workflows/pr-quality.yml": ("checks",),
}

# Substrings that indicate a step publishes or mutates check runs. Plain
# status annotations (``::error::``, ``::warning::``) and the step summary
# file need no Checks API permission, so they are deliberately absent here.
CHECK_PUBLISH_MARKERS = (
    "check-runs",
    "create-check",
    "update-check",
    "checks/create",
    "checks/update",
)


def _workflow(name: str) -> dict:
    text = (REPO_ROOT / name).read_text()
    doc = yaml.safe_load(text)
    assert isinstance(doc, dict), f"{name} did not parse as a mapping"
    return doc


def test_no_workflow_requests_checks_write():
    """Fails on the old workflows, which granted ``checks: write``."""
    for name in WORKFLOWS:
        permissions = _workflow(name).get("permissions", {})
        assert isinstance(permissions, dict), f"{name} has no permissions map"
        granted = permissions.get("checks")
        assert granted in (None, "read"), f"{name} grants checks: {granted!r}, nothing in it publishes checks"


def test_no_step_publishes_check_runs():
    """No job calls the Checks API, so read scope stays sufficient."""
    for name in WORKFLOWS:
        text = (REPO_ROOT / name).read_text().lower()
        hits = [m for m in CHECK_PUBLISH_MARKERS if m in text]
        assert not hits, (
            f"{name} references Checks API markers {hits}, reassess the checks permission before widening it"
        )
