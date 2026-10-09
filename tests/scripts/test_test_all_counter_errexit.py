"""Regression tests for the scripts/test-all.sh counter finding.

The defect: every counter in the runner used the post-increment form
``((VAR++))``. When the counter starts at zero, the arithmetic expression
evaluates to zero, so the compound command exits nonzero. The script runs
under ``set -e``, so the very first passing test aborted the whole runner
instead of counting the pass.

The fix uses ``((VAR+=1))``, whose value is the new counter (always at
least 1 here), so the command exits zero and the runner survives.

These tests need no live services: they run the script's real ``run_test``
function, extracted from the script, under strict mode with stub commands.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "test-all.sh"

# Post-increment of a bare variable name, the pattern that trips errexit
# when the old value is zero: ((PASSED++)), (( VAR++ )), and friends.
_POST_INCREMENT = re.compile(r"\(\(\s*[A-Za-z_][A-Za-z0-9_]*\+\+\s*\)\)")


def test_no_errexit_tripping_post_increments():
    """The script must not contain ((VAR++)) counters.

    Fails against the pre-fix script, which had twelve of them.
    """
    text = SCRIPT.read_text()
    offenders = _POST_INCREMENT.findall(text)
    assert not offenders, (
        "post-increment counters abort the runner under set -e when the "
        f"old value is zero; use ((VAR+=1)) instead: {offenders}"
    )


def _run_extracted_run_test(*, stub_cmd: str) -> subprocess.CompletedProcess:
    """Run the script's real run_test function once under strict mode."""
    harness = (
        "set -eu\n"
        "RED='' GREEN='' YELLOW='' BLUE='' NC=''\n"
        "PASSED=0\n"
        "FAILED=0\n"
        f"{_extract_run_test()}\n"
        f'run_test "stub" "{stub_cmd}"\n'
        'echo "PASSED=$PASSED FAILED=$FAILED"\n'
    )
    return subprocess.run(
        ["bash", "-c", harness],
        capture_output=True,
        text=True,
        timeout=60,
    )


def _extract_run_test() -> str:
    """Return the run_test function body exactly as written in the script."""
    text = SCRIPT.read_text()
    match = re.search(r"^run_test\(\) \{.*?^\}", text, re.MULTILINE | re.DOTALL)
    assert match, "run_test function not found in scripts/test-all.sh"
    return match.group(0)


def test_first_passing_test_survives_strict_mode():
    """The first passing test must be counted, not abort the runner.

    Fails against the pre-fix script: ((PASSED++)) with PASSED=0 exits
    nonzero, and set -e kills the shell before the count is recorded.
    """
    proc = _run_extracted_run_test(stub_cmd="true")
    assert proc.returncode == 0, f"runner aborted on the first pass under strict mode:\n{proc.stdout}\n{proc.stderr}"
    assert "PASSED=1 FAILED=0" in proc.stdout, proc.stdout


def test_first_failing_test_survives_strict_mode():
    """The first failing test must be counted, not abort the runner.

    Same root cause on the else branch: ((FAILED++)) with FAILED=0.
    """
    proc = _run_extracted_run_test(stub_cmd="false")
    assert proc.returncode == 0, f"runner aborted on the first failure under strict mode:\n{proc.stdout}\n{proc.stderr}"
    assert "PASSED=0 FAILED=1" in proc.stdout, proc.stdout
