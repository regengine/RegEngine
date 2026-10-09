"""scripts/chaos/README.md must not document helper scripts that do not exist.

Low-severity audit finding: the README gave run commands for
``kill_neo4j.sh`` and ``kill_kafka.sh`` and described a scheduled workflow at
``.github/workflows/nightly-resilience-test.yml``, but none of those files
exist. These tests fail on that old README and pass once the doc matches
reality.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "scripts" / "chaos" / "README.md"

_TOKEN = re.compile(r"(?:\./)?(?:scripts/chaos/|\.github/workflows/)[^\s`'\"()\[\]\\]+")


def _referenced_paths(text: str) -> list[str]:
    """Collect runnable path tokens, skipping template placeholders."""
    found: list[str] = []
    for match in _TOKEN.finditer(text):
        token = match.group(0).removeprefix("./").rstrip(".,;:)")
        if any(char in token for char in ("<", ">", "*", "{", "}")):
            continue
        found.append(token)
    return found


def _read_readme() -> str:
    assert README.is_file(), f"expected chaos README at {README}"
    return README.read_text(encoding="utf-8")


def test_no_run_command_for_missing_kill_helpers() -> None:
    """The old README showed `./scripts/chaos/kill_*.sh` as runnable commands."""
    text = _read_readme()
    assert "./scripts/chaos/kill_" not in text, (
        "README still documents kill_* helper scripts as runnable, but no such scripts exist in scripts/chaos/"
    )


def test_no_reference_to_missing_resilience_workflow() -> None:
    """The old README pointed at a workflow file that was never added."""
    text = _read_readme()
    assert "nightly-resilience-test.yml" not in text, (
        "README still references nightly-resilience-test.yml, but no such workflow exists in .github/workflows/"
    )


def test_every_referenced_chaos_or_workflow_path_exists() -> None:
    """Any scripts/chaos or workflow path the README names must exist on disk."""
    text = _read_readme()
    missing = [token for token in _referenced_paths(text) if not (REPO_ROOT / token).exists()]
    assert missing == [], f"README references paths that do not exist: {missing}"


@pytest.mark.parametrize("script", ["run_all_chaos_tests.sh"])
def test_named_runner_script_still_exists(script: str) -> None:
    """Guard the other direction: the runner the README names must keep existing."""
    assert (REPO_ROOT / "scripts" / "chaos" / script).is_file()
