"""Regression tests for the deploy_railway.sh audit finding (re-platform-2-ops #53).

The defect, in two halves:

1. The Neo4j step installed a package without verifying its integrity and
   carried a fallback that bypassed system-package protection. The install
   must now pin versions and verify every downloaded artifact against
   hashes copied from requirements.lock, with no unprotected retry.
2. The verify step waited a fixed ``sleep 30`` and then probed each
   endpoint exactly once, reporting a still-deploying service as a warning
   while exiting 0. It must now poll until healthy or a deadline expires,
   and fail loudly past the deadline.

The static tests below fail against the pre-fix script (unpinned install,
``sleep 30``, single-shot warn-only checks). The dynamic tests execute the
real ``scripts/wait_for_service.sh`` with a stubbed ``curl``/``sleep`` on
PATH, so they need no network and run in seconds.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = ROOT / "scripts" / "deploy_railway.sh"
WAIT_SCRIPT = ROOT / "scripts" / "wait_for_service.sh"
LOCK = ROOT / "requirements.lock"


def _code_lines(path: Path) -> str:
    """Script text without full-line comments.

    The scripts deliberately *name* forbidden flags in comments to explain
    why they are absent, so assertions about executable content must skip
    comment lines (same approach as test_backup_postgres_format.py).
    """
    return "\n".join(line for line in path.read_text().splitlines() if not line.lstrip().startswith("#"))


def _script_hashes(code: str) -> list[str]:
    return re.findall(r'--hash="?(sha256:[0-9a-f]+)"?', code)


# --- Half 1: hash-pinned install -------------------------------------------


def test_neo4j_install_verifies_hashes():
    """The neo4j install must pin versions and check artifact hashes.

    Fails against the pre-fix script, whose ``pip install "neo4j==6.3.1"``
    carried no ``--hash`` and therefore accepted any artifact.
    """
    code = _code_lines(DEPLOY_SCRIPT)
    assert "--require-hashes" in code, "install must run pip in hash-enforcing mode"
    assert "neo4j==6.3.1" in code, "neo4j version pin went missing"
    assert len(_script_hashes(code)) >= 2, "expected artifact hashes on the install line"
    assert re.search(r"pip install --require-hashes[^\n]*-r ", code), (
        "hashes must be passed via a requirements file: pip rejects command-line --hash"
    )


def test_install_hashes_match_requirements_lock():
    """Every hash in the deploy script must exist in requirements.lock.

    The lock file is the single source of truth (pip-compile
    --generate-hashes); a typo here would fail closed at deploy time, and
    this test catches it before that.
    """
    code = _code_lines(DEPLOY_SCRIPT)
    lock = LOCK.read_text()
    hashes = _script_hashes(code)
    assert hashes, "no hashes found in deploy script"
    for digest in hashes:
        assert digest in lock, f"{digest} is not in requirements.lock; copy it from the lock"


def test_install_has_no_system_package_bypass():
    """No --break-system-packages fallback may remain on the install path.

    Fails against the pre-fix script, which retried a failed install with
    the protection bypassed.
    """
    assert "--break-system-packages" not in _code_lines(DEPLOY_SCRIPT)


# --- Half 2: poll with a deadline -------------------------------------------


def test_no_fixed_sleep_before_health_check():
    """The fixed ``sleep 30`` wait must be gone from the verify step.

    A fixed sleep cannot know when Railway finishes the redeploy: too short
    and the check probes the old revision, too long and every deploy waits
    for nothing.
    """
    code = _code_lines(DEPLOY_SCRIPT)
    assert re.search(r"^\s*sleep\b", code, re.M) is None, "fixed sleep wait is still in the deploy script"


def test_deploy_verifies_through_polling_helper_with_deadline():
    """The deploy script must poll health through a deadline-bound helper."""
    code = _code_lines(DEPLOY_SCRIPT)
    assert "wait_for_service.sh" in code, "deploy script must call the polling helper"
    assert "MONOLITH_WAIT_SECS" in code, "operator must be able to tune the deadline"
    helper = WAIT_SCRIPT.read_text()
    assert "WAIT_TIMEOUT_SECS" in helper
    assert "exit 1" in helper, "helper must fail loudly past the deadline, not warn and exit 0"
    assert "--max-time" in helper, "each probe needs its own timeout so one stuck probe cannot hang the wait"


# --- Dynamic tests: the real helper, stubbed curl/sleep ---------------------

_CURL_STUB = """\
#!/usr/bin/env bash
# Stub curl: replays canned HTTP codes from $CURL_CODES_FILE, one per call,
# repeating the last code once the file is exhausted.
codes_file="${CURL_CODES_FILE:?}"
echo "curl $*" >> "${CURL_CALL_LOG:?}"
idx_file="${codes_file}.idx"
idx=0
if [ -f "$idx_file" ]; then idx=$(cat "$idx_file"); fi
mapfile -t codes < "$codes_file"
n=${#codes[@]}
if [ "$idx" -ge "$n" ]; then idx=$((n - 1)); fi
printf '%s' "${codes[$idx]}"
echo $((idx + 1)) > "$idx_file"
exit 0
"""

_SLEEP_STUB = """\
#!/usr/bin/env bash
echo "sleep $*" >> "${SLEEP_CALL_LOG:?}"
exit 0
"""


def _run_wait(
    tmp_path: Path, codes: list[str], timeout_secs: str = "60"
) -> tuple[subprocess.CompletedProcess, list[str], list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "curl").write_text(_CURL_STUB)
    (bin_dir / "sleep").write_text(_SLEEP_STUB)
    for name in ("curl", "sleep"):
        (bin_dir / name).chmod(0o755)

    codes_file = tmp_path / "codes.txt"
    codes_file.write_text("\n".join(codes) + "\n")
    curl_log = tmp_path / "curl.log"
    sleep_log = tmp_path / "sleep.log"

    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["CURL_CODES_FILE"] = str(codes_file)
    env["CURL_CALL_LOG"] = str(curl_log)
    env["SLEEP_CALL_LOG"] = str(sleep_log)
    env["WAIT_TIMEOUT_SECS"] = timeout_secs
    env["WAIT_INTERVAL_SECS"] = "10"
    env["WAIT_CURL_MAX_SECS"] = "5"

    proc = subprocess.run(
        ["bash", str(WAIT_SCRIPT), "http://probe-target:9999"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    curl_calls = curl_log.read_text().splitlines() if curl_log.exists() else []
    sleep_calls = sleep_log.read_text().splitlines() if sleep_log.exists() else []
    return proc, curl_calls, sleep_calls


def test_wait_succeeds_after_transient_failures(tmp_path):
    """Flapping endpoints must converge to success without human timing.

    Fails against the pre-fix single-shot check, which probed each endpoint
    exactly once and could only report the first 503.
    """
    proc, curl_calls, sleep_calls = _run_wait(tmp_path, ["503", "503", "200", "200"])
    assert proc.returncode == 0, proc.stderr
    assert "Service is healthy" in proc.stdout
    assert len(curl_calls) == 4, f"expected two polling rounds, got: {curl_calls}"
    assert len(sleep_calls) == 1, f"expected one wait between rounds, got: {sleep_calls}"


def test_wait_fails_loudly_past_deadline(tmp_path):
    """A service that never becomes healthy must fail, not warn-and-pass.

    Fails against the pre-fix check, which printed "(may still be deploying)"
    and exited 0. Uses a 2s deadline with sleeping stubbed out.
    """
    proc, curl_calls, _ = _run_wait(tmp_path, ["500"], timeout_secs="2")
    assert proc.returncode != 0, "unhealthy service past the deadline must exit nonzero"
    assert "within 2s" in proc.stderr
    assert len(curl_calls) > 2, f"expected repeated polling until the deadline, got: {curl_calls}"


def test_wait_does_not_sleep_when_already_healthy(tmp_path):
    """A healthy service must verify immediately: no fixed wait remains."""
    proc, curl_calls, sleep_calls = _run_wait(tmp_path, ["200"])
    assert proc.returncode == 0, proc.stderr
    assert len(curl_calls) == 2, f"expected one probe per endpoint, got: {curl_calls}"
    assert sleep_calls == [], f"no waiting should happen when healthy on first probe: {sleep_calls}"
