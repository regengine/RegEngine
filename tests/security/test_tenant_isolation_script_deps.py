"""Regression test for audit finding on scripts/security/tenant_isolation_test.sh.

The script passes --json-report flags to pytest, which requires the
pytest-json-report plugin. That plugin is not declared in requirements.in,
so on machines without it the script failed with pytest's confusing
"unrecognized arguments" error. The script must instead fail fast with a
clear message naming the missing dependency.
"""

import os
import stat
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "security" / "tenant_isolation_test.sh"


def _run_script_with_broken_python3(tmp_path):
    """Run the script with a stub python3 that always fails.

    This simulates an environment where the pytest-json-report plugin (or
    pytest itself) is unusable, without running the real security suite.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "python3"
    fake.write_text(
        '#!/usr/bin/env bash\necho "fake python3: no usable pytest installation" >&2\nexit 1\n',
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    env = dict(os.environ)
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_missing_plugin_fails_with_clear_dependency_message(tmp_path):
    proc = _run_script_with_broken_python3(tmp_path)
    assert proc.returncode != 0
    combined = proc.stdout + proc.stderr
    assert "pytest-json-report" in combined, (
        "script must name the missing 'pytest-json-report' dependency; got: " + combined
    )


def test_plugin_check_runs_before_pytest_invocation():
    text = SCRIPT.read_text(encoding="utf-8")
    check_pos = text.find("pytest-json-report")
    pytest_pos = text.find("python3 -m pytest")
    assert check_pos != -1, "script must reference the pytest-json-report dependency"
    assert pytest_pos != -1
    assert check_pos < pytest_pos, "dependency check must come before the pytest run"
