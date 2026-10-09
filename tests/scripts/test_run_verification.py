"""Regression tests for scripts/run_verification.sh (audit finding re-platform-2-ops #70).

The defect: the orchestrator chained three live-write stages with fixed
``sleep 10`` / ``sleep 60`` pauses, unquoted ``$RUN_ID`` arguments, and no
per-stage verification, so a silently failed seed still triggered live
ingestion and the lineage check ran against evidence that might not exist.

The fix: each stage command must exit zero AND a readiness poll must observe
the run's document in the Admin API before the script advances; polls have
deadlines and fail loudly instead of sleeping a fixed time.

These tests run the real script with stubbed ``python3`` / ``curl`` /
``sleep`` on PATH, so they need no live services. ``sleep`` is stubbed to a
no-op so the tests stay fast. Set RUN_VERIFICATION_SCRIPT to point the suite
at another copy of the script (for example the pre-fix version) to confirm
the behavioral tests fail there.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path(os.environ.get("RUN_VERIFICATION_SCRIPT", ROOT / "scripts" / "run_verification.sh"))

_PYTHON_STUB = """\
#!/usr/bin/env bash
echo "$#:$*" >> "$STUB_LOG/calls"
step=""
case "$1" in
  *seed_v1_data.py) step="seed" ;;
  *verify_live_freshness.py) step="live" ;;
  *verify_compliance_lineage.py) step="lineage" ;;
esac
if [ "${PYTHON_FAIL_STEP:-}" = "$step" ]; then
  echo "$step failed (stub)" >&2
  exit 1
fi
exit 0
"""

_CURL_STUB = """\
#!/usr/bin/env bash
echo "curl $*" >> "$STUB_LOG/calls"
n=$(cat "$STUB_LOG/curl_count" 2>/dev/null || echo 0)
n=$((n + 1)); echo "$n" > "$STUB_LOG/curl_count"
if [ -n "${CURL_MATCH_AFTER:-}" ] && [ "$n" -ge "$CURL_MATCH_AFTER" ]; then
  printf '%s' "$CURL_MATCH_BODY"
else
  printf '%s' "${CURL_BODY:-[]}"
fi
exit 0
"""

_SLEEP_STUB = """\
#!/usr/bin/env bash
echo "sleep $*" >> "$STUB_LOG/calls"
exit 0
"""


def _install_stubs(tmp_path: Path) -> tuple[Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "python3").write_text(_PYTHON_STUB)
    (bin_dir / "curl").write_text(_CURL_STUB)
    (bin_dir / "sleep").write_text(_SLEEP_STUB)
    for stub in bin_dir.iterdir():
        stub.chmod(0o755)
    log_dir = tmp_path / "log"
    log_dir.mkdir()
    return bin_dir, log_dir


def _run_script(
    tmp_path: Path,
    run_id: str,
    *,
    fail_step: str = "",
    curl_body: str = "",
    match_after: str = "",
    match_body: str = "",
    seed_timeout: str = "120",
    live_timeout: str = "180",
) -> tuple[subprocess.CompletedProcess, list[str]]:
    bin_dir, log_dir = _install_stubs(tmp_path)
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["STUB_LOG"] = str(log_dir)
    env["ADMIN_API_URL"] = "http://127.0.0.1:9"
    env["SEED_TIMEOUT_SECS"] = seed_timeout
    env["LIVE_TIMEOUT_SECS"] = live_timeout
    env["POLL_INTERVAL_SECS"] = "1"
    env["PYTHON_FAIL_STEP"] = fail_step
    env["CURL_BODY"] = curl_body
    env["CURL_MATCH_AFTER"] = match_after
    env["CURL_MATCH_BODY"] = match_body
    proc = subprocess.run(
        ["bash", str(SCRIPT), run_id],
        env=env,
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=120,
    )
    calls_file = log_dir / "calls"
    calls = calls_file.read_text().splitlines() if calls_file.exists() else []
    return proc, calls


def _evidence_body(run_id: str) -> str:
    return f'[{{"original_file_path": "https://www.fda.gov/fsma-rule?run={run_id}"}}]'


def test_failed_stage_aborts_before_next_stage(tmp_path):
    """A failing live-ingestion stage must stop the run before lineage."""
    run_id = "abort-on-failure-run"
    proc, calls = _run_script(tmp_path, run_id, fail_step="live", curl_body=_evidence_body(run_id))

    assert proc.returncode != 0, f"script reported success:\n{proc.stdout}\n{proc.stderr}"
    assert "Step 2" in proc.stderr, f"no stage-specific error:\n{proc.stderr}"
    assert not any("verify_compliance_lineage" in call for call in calls), (
        f"lineage stage ran after a failed stage:\n{calls}"
    )


def test_missing_evidence_aborts_before_next_stage(tmp_path):
    """The seed stage succeeding is not enough: without observed evidence
    the script must not advance to live ingestion.

    Fails against the pre-fix script, which sleeps a fixed time and then
    advances regardless, exiting zero here.
    """
    run_id = "missing-evidence-run"
    proc, calls = _run_script(tmp_path, run_id, curl_body="[]", seed_timeout="2")

    assert proc.returncode != 0, f"script advanced without evidence:\n{proc.stdout}\n{proc.stderr}"
    assert "Step 1" in proc.stderr, f"no stage-specific error:\n{proc.stderr}"
    assert not any("verify_live_freshness" in call for call in calls), f"live stage ran without seed evidence:\n{calls}"


def test_readiness_poll_observes_evidence_then_advances(tmp_path):
    """The script must poll (not sleep once) until evidence appears.

    Fails against the pre-fix script, which never calls curl at all.
    """
    run_id = "poll-then-advance-run"
    proc, calls = _run_script(
        tmp_path,
        run_id,
        curl_body="[]",
        match_after="3",
        match_body=_evidence_body(run_id),
    )

    assert proc.returncode == 0, f"script failed despite evidence appearing:\n{proc.stdout}\n{proc.stderr}"
    curl_calls = [call for call in calls if call.startswith("curl ")]
    assert len(curl_calls) >= 3, f"expected repeated readiness polls, got {len(curl_calls)} curl calls:\n{calls}"
    assert any("verify_compliance_lineage" in call for call in calls), f"lineage stage never ran:\n{calls}"


def test_run_id_forwarded_as_single_quoted_argument(tmp_path):
    """A run id containing spaces must reach every stage as one argument."""
    run_id = "run with spaces"
    proc, calls = _run_script(tmp_path, run_id, curl_body=_evidence_body(run_id))

    assert proc.returncode == 0, f"script failed:\n{proc.stdout}\n{proc.stderr}"
    python_calls = [call for call in calls if call.startswith(("1:", "2:", "3:", "4:"))]
    assert len(python_calls) == 3, f"expected three stage calls, got:\n{calls}"
    for call in python_calls:
        argc = call.split(":", 1)[0]
        assert argc == "2", f'run id was word-split ({call}); quote "$RUN_ID"'


def test_script_has_no_fixed_sleeps_and_uses_strict_mode():
    """Static guard: fixed sleeps must not come back, strict mode must stay."""
    text = SCRIPT.read_text()

    assert "set -euo pipefail" in text or "set -u" in text, "strict mode (nounset) missing"
    assert not re.search(r"^\s*sleep 10\s*$", text, re.MULTILINE), "fixed sleep 10 is back"
    assert not re.search(r"^\s*sleep 60\s*$", text, re.MULTILINE), "fixed sleep 60 is back"
    assert '"$RUN_ID"' in text, 'stages must receive a quoted "$RUN_ID"'
    assert "wait_for_run_document" in text, "readiness polling helper missing"
    assert text.count("wait_for_run_document") >= 3, "every advancing stage needs a readiness gate"
