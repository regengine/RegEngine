"""``pytest --require-db`` turns database-availability skips into failures (WI-10).

Runs pytest in a subprocess on a throwaway test module placed under this
directory so the repo-root ``conftest.py`` (which defines the option) is in
force, then removes the module again.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_PROBE = '''
import pytest

from tests.migrations.rls_db import skip_or_fail_without_db


def test_helper_skip():
    skip_or_fail_without_db("no designated migrated scratch database")


def test_inline_db_skip():
    pytest.skip("migrated Postgres with fsma schema not available")


def test_non_db_skip():
    pytest.skip("prometheus_client not available in this env")


@pytest.mark.skipif(True, reason="DATABASE_URL not set — live DB required")
def test_marker_db_skip():
    pass
'''


def _run(extra_args: list[str]) -> subprocess.CompletedProcess[str]:
    probe_dir = REPO_ROOT / "tests" / "scripts" / f"_require_db_probe_{uuid.uuid4().hex}"
    probe_dir.mkdir()
    probe = probe_dir / "test_probe.py"
    try:
        probe.write_text(_PROBE)
        # A minimal environment: other tests in the same session mutate
        # os.environ (PYTHONPATH, REGENGINE_* variables) and a child that
        # inherits them can resolve a different checkout or a stale gate.
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", ""),
            "PYTHONPATH": str(REPO_ROOT),
            "PYTHONDONTWRITEBYTECODE": "1",
            "DATABASE_URL": "sqlite:///:memory:",
        }
        return subprocess.run(
            [sys.executable, "-m", "pytest", str(probe), "-q", "--no-cov", "-p", "no:cacheprovider", "-rA", *extra_args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env=env,
            timeout=300,
        )
    finally:
        shutil.rmtree(probe_dir, ignore_errors=True)


def _summary_lines(out: str, prefix: str) -> list[str]:
    return [line for line in out.splitlines() if line.startswith(prefix)]


def test_without_the_flag_every_probe_skips():
    result = _run([])
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(_summary_lines(result.stdout, "SKIPPED")) == 4, result.stdout


def test_with_the_flag_database_skips_fail_and_others_still_skip():
    result = _run(["--require-db"])
    assert result.returncode != 0, result.stdout + result.stderr
    out = result.stdout
    # The helper fails outright and the inline ``pytest.skip`` is converted by
    # the report hook (both FAILED); the ``skipif`` marker skips during setup,
    # so its conversion surfaces as a setup ERROR; the package skip is untouched.
    assert len(_summary_lines(out, "FAILED")) == 2, out
    assert len(_summary_lines(out, "ERROR")) == 1, out
    skipped = _summary_lines(out, "SKIPPED")
    assert len(skipped) == 1 and "prometheus_client not available" in skipped[0], out
    assert "database test must execute, not skip" in out, out
    assert "docker compose -f docker-compose.dev.yml up -d postgres" in out, out
    assert "skipped for a database reason while --require-db was set" in out, out
