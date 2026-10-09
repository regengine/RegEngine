"""Regression tests for scripts/security/deps_audit.sh (audit re-platform-2-ops #79).

Two defects: the Node check looked for package-lock.json/package.json at the
repo root, but the Node project lives in frontend/, so npm audit was always
skipped; and a missing pip-audit scanner printed a hint yet exited zero,
certifying an audit that never ran.

These tests run the real script with stubbed npm/pip-audit on PATH, so they
need no network and no real scanner. Each test fails on the old script and
passes on the fixed one.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "security" / "deps_audit.sh"
BASH = shutil.which("bash") or "/bin/bash"


def _run(cwd: Path, bin_dir: Path, *, hide: tuple[str, ...] = ()) -> subprocess.CompletedProcess[str]:
    # Stubs in bin_dir shadow the real tools. System dirs stay on PATH so the
    # shell itself resolves, except directories holding a real tool we mean to
    # hide (a scanner that must look absent).
    path_dirs = [str(bin_dir)]
    for entry in os.environ.get("PATH", "/usr/bin:/bin").split(os.pathsep):
        if not entry or entry == str(bin_dir):
            continue
        if any((Path(entry) / name).exists() for name in hide):
            continue
        path_dirs.append(entry)
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join(path_dirs)
    assert shutil.which("pip-audit", path=env["PATH"]) is None or "pip-audit" not in hide, (
        "test setup: a real pip-audit is visible, cannot simulate absence"
    )
    return subprocess.run(
        [BASH, str(SCRIPT)],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _write_stub(bin_dir: Path, name: str, body: str) -> None:
    stub = bin_dir / name
    stub.write_text("#!/bin/sh\n" + body + "\n")
    stub.chmod(0o755)


def test_node_audit_runs_for_frontend_project(tmp_path: Path) -> None:
    """A checkout with frontend/package.json must trigger npm audit.

    Old script checked the repo root, found nothing, and skipped npm audit,
    so the stub was never called. New script points at frontend/ and calls
    npm with --prefix frontend.
    """
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text('{"name": "sentinel"}\n')
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "npm-called"
    _write_stub(bin_dir, "npm", f'touch "{marker}"\nexit 0')
    _write_stub(bin_dir, "pip-audit", "exit 0")

    result = _run(tmp_path, bin_dir)

    assert marker.exists(), f"npm audit was skipped for a frontend/ project.\nstdout:\n{result.stdout}"
    assert result.returncode == 0


def test_missing_pip_audit_scanner_fails(tmp_path: Path) -> None:
    """A missing pip-audit scanner must fail, not certify a clean audit.

    Old script printed an install hint and exited zero. New script records a
    failure so the run ends nonzero with the FAIL banner.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    result = _run(tmp_path, bin_dir, hide=("pip-audit",))

    assert "pip-audit not installed" in result.stdout
    assert result.returncode != 0, f"script exited zero with no scanner installed.\nstdout:\n{result.stdout}"
    assert "FAIL" in result.stdout
