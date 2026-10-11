"""Regression tests for scripts/test-all.sh command execution.

The defect: run_test() piped its command through `eval "$cmd"`, so any
shell metacharacters in a test command or its arguments were reinterpreted
by the shell. The fix runs the command and its arguments directly (no
eval); output is captured and tailed by the function instead of by an
in-string pipe.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "test-all.sh"


def _extract_run_test():
    """Return the run_test function source via brace matching."""
    lines = SCRIPT.read_text().splitlines(keepends=True)
    start = next(i for i, l in enumerate(lines) if l.startswith("run_test() {"))
    depth = 0
    end = start
    for i in range(start, len(lines)):
        depth += lines[i].count("{") - lines[i].count("}")
        if depth == 0:
            end = i
            break
    return "".join(lines[start : end + 1])


def test_no_eval_in_script():
    text = SCRIPT.read_text()
    assert not re.search(r"(?<![A-Za-z_])eval(?![A-Za-z_])", text)


def test_script_syntax_valid():
    result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_run_test_counts_pass_and_fail(tmp_path):
    harness = tmp_path / "harness.sh"
    harness.write_text(
        "PASSED=0\nFAILED=0\n"
        + _extract_run_test()
        + 'run_test "ok-cmd" true\n'
        + 'run_test "bad-cmd" false\n'
        + 'echo "PASSED=$PASSED FAILED=$FAILED"\n'
    )
    result = subprocess.run(["bash", str(harness)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert "PASSED=1 FAILED=1" in result.stdout


def test_run_test_does_not_interpret_arguments(tmp_path):
    marker = tmp_path / "pwned"
    harness = tmp_path / "harness_evil.sh"
    harness.write_text(
        "PASSED=0\nFAILED=0\n"
        + _extract_run_test()
        + f'run_test "evil" printf \'%s\' \'$(touch "{marker}")\'\n'
        + 'echo "PASSED=$PASSED"\n'
    )
    result = subprocess.run(["bash", str(harness)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert not marker.exists()
    assert "PASSED=1" in result.stdout
    assert f'$(touch "{marker}")' in result.stdout
