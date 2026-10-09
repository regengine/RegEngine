"""Regression tests for scripts/chaos/run_all_chaos_tests.sh (audit finding:
dangling helper references plus a fully-skipped run exiting zero as
"all-passed").

The runner needs Docker for its pre-flight check, so each test puts a fake
`docker` executable on PATH (supports `docker info` and `docker ps`) and
invokes the real script via subprocess. No containers are touched.

Set CHAOS_RUNNER_UNDER_TEST to point at an alternate copy of the runner
(for example the pre-fix revision) to confirm these tests fail there.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNNER = REPO_ROOT / "scripts" / "chaos" / "run_all_chaos_tests.sh"


def _runner_path() -> Path:
    override = os.environ.get("CHAOS_RUNNER_UNDER_TEST")
    return Path(override) if override else DEFAULT_RUNNER


def _fake_docker_bin(tmp_path: Path) -> Path:
    """Create a directory with a fake `docker` that passes pre-flight."""
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    docker = bindir / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "info" ]; then exit 0; fi\n'
        'if [ "$1" = "ps" ]; then echo "CONTAINER ID   IMAGE"; exit 0; fi\n'
        "exit 0\n"
    )
    docker.chmod(docker.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return bindir


def _run_runner(tmp_path: Path, *args: str, script: Path | None = None) -> subprocess.CompletedProcess[str]:
    bindir = _fake_docker_bin(tmp_path)
    env = {**os.environ, "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}"}
    return subprocess.run(
        ["bash", str(script or _runner_path()), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def test_fully_skipped_run_fails(tmp_path):
    """A run where every test is filtered out must exit nonzero and must
    not print the all-passed banner."""
    result = _run_runner(tmp_path, "--test", "No Such Test")
    assert result.returncode != 0
    assert "All chaos tests passed!" not in result.stdout
    assert "No chaos tests were executed" in result.stdout


def test_empty_suite_has_no_false_resiliency_claims(tmp_path):
    """With no helpers wired up, the suite must fail instead of certifying
    resiliency outcomes it never measured."""
    result = _run_runner(tmp_path)
    assert result.returncode != 0
    assert "No chaos tests were executed" in result.stdout
    assert "Zero data loss" not in result.stdout


def test_missing_helper_is_reported_not_silent(tmp_path):
    """A run_test reference to a helper that does not exist must be
    reported by name as a failed test, not abort with a bare shell
    "No such file" error and no summary."""
    source = _runner_path().read_text()
    anchor = "# Print summary"
    assert anchor in source
    probe = source.replace(
        anchor,
        'run_test "Ghost Helper" "does_not_exist.sh" true\n' + anchor,
        1,
    )
    script = tmp_path / "runner_probe.sh"
    script.write_text(probe)
    result = _run_runner(tmp_path, script=script)
    assert result.returncode != 0
    assert "helper script not found: does_not_exist.sh" in result.stdout


if __name__ == "__main__":
    sys.exit("Run with: pytest tests/scripts/test_run_all_chaos_tests.py -q")
