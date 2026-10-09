"""Probe hygiene for the health check and staging verifier scripts.

Covers audit finding 88 (re-platform-2-ops): ``scripts/verify-health.sh``
depended on netcat with no fallback, and
``scripts/railway/verify_inflow_workbench_staging.sh`` left synthetic rows
behind while printing full error bodies to logs unredacted.

These tests run the scripts' real shell code with stubbed ``psql``/``curl``
on PATH, so they need no live staging database or service. Script paths can
be overridden with VERIFY_HEALTH_SH / STAGING_VERIFY_SH to run the same
assertions against older copies of the scripts.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERIFY_HEALTH_SH = Path(os.environ.get("VERIFY_HEALTH_SH", ROOT / "scripts/verify-health.sh"))
STAGING_VERIFY_SH = Path(
    os.environ.get("STAGING_VERIFY_SH", ROOT / "scripts/railway/verify_inflow_workbench_staging.sh")
)


def extract_function(path: Path, name: str) -> str:
    """Return the source of the top-level ``name() { ... }`` shell function."""
    lines = path.read_text().splitlines(keepends=True)
    start = next((i for i, line in enumerate(lines) if line.startswith(f"{name}() {{")), None)
    assert start is not None, f"{name}() not found in {path}"
    for i in range(start + 1, len(lines)):
        if lines[i] == "}\n":
            return "".join(lines[start : i + 1])
    raise AssertionError(f"unterminated {name}() in {path}")


BASH = shutil.which("bash") or "/bin/bash"


def run_bash(script: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    # Absolute bash path: several tests restrict PATH so far that "bash"
    # itself would no longer resolve inside the child environment.
    return subprocess.run([BASH, "-c", script], capture_output=True, text=True, env=env, timeout=120)


def test_check_service_probes_tcp_without_netcat() -> None:
    """check_service must route TCP checks through tcp_probe, not bare nc."""
    text = VERIFY_HEALTH_SH.read_text()
    assert 'tcp_probe "$host" "$port" "$timeout"' in text
    assert "nc -z -w $timeout $host $port" not in text


def test_tcp_probe_falls_back_to_python3_without_netcat(tmp_path: Path) -> None:
    """Without nc, tcp_probe must use the python3 fallback (and pass args)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "python3.calls"
    _write_stub(
        bin_dir / "python3",
        f'#!/bin/bash\necho "$*" >> {calls}\ncat > /dev/null\nexit 0\n',
    )
    env = {**os.environ, "PATH": str(bin_dir)}
    fn = extract_function(VERIFY_HEALTH_SH, "tcp_probe")
    result = run_bash(f"{fn}\ntcp_probe db-host 5432 4", env)
    assert result.returncode == 0, result.stderr
    assert calls.read_text().strip() == "- db-host 5432 4"


def test_tcp_probe_closed_port_reports_down_without_netcat(tmp_path: Path) -> None:
    """The python3 fallback must still report a closed port as down."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "python3").symlink_to(sys.executable)
    env = {**os.environ, "PATH": str(bin_dir)}
    fn = extract_function(VERIFY_HEALTH_SH, "tcp_probe")
    # Port 9 (discard) is unlistened on loopback in every sane environment;
    # even a sandbox connect denial yields the nonzero result asserted here.
    result = run_bash(f"{fn}\ntcp_probe 127.0.0.1 9 2", env)
    assert result.returncode != 0


def test_tcp_probe_degrades_gracefully_with_only_bash(tmp_path: Path) -> None:
    """With neither nc nor python3, the /dev/tcp branch must run, not crash."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "bash").symlink_to("/bin/bash")
    env = {**os.environ, "PATH": str(bin_dir)}
    fn = extract_function(VERIFY_HEALTH_SH, "tcp_probe")
    assert 'exec 3<>"/dev/tcp/$0/$1"' in fn
    result = run_bash(f"{fn}\ntcp_probe 127.0.0.1 9 2", env)
    assert result.returncode != 0


def _write_stub(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _staging_env(tmp_path: Path, psql_body: str, curl_body: str) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    _write_stub(bin_dir / "psql", psql_body)
    _write_stub(bin_dir / "curl", curl_body)
    (bin_dir / "python3").symlink_to(sys.executable)
    env = {**os.environ, "PATH": f"{bin_dir}:/usr/bin:/bin"}
    env["DATABASE_URL"] = "postgres://stub/staging"
    env["INGESTION_URL"] = "http://staging.test"
    # The script supports an empty AUTH_ARGS array only on bash 4.4+; macOS
    # ships bash 3.2, where "${AUTH_ARGS[@]}" under `set -u` aborts. Exercise
    # the authenticated path so the tests run on the developer Mac too.
    env["REGENGINE_API_KEY"] = "test-key-stub-456"
    env["PSQL_LOG"] = str(tmp_path / "psql.log")
    return env


def test_staging_error_body_is_truncated_and_redacted(tmp_path: Path) -> None:
    """A failed save must not print the full error body or secrets to logs."""
    psql = """#!/bin/bash
args="$*"
if [[ "$args" == *"to_regclass"* ]]; then echo "t"; exit 0; fi
if [[ "$args" == *"pg_trigger"* ]]; then echo "4"; exit 0; fi
echo "0"
"""
    curl = """#!/bin/bash
outfile=""
prev=""
for arg in "$@"; do
  if [[ "$prev" == "-o" ]]; then outfile="$arg"; fi
  prev="$arg"
done
{
  printf '{"error":"save failed","api_key":"SECRET-ABC-123",'
  printf '"token":"tok_xyz_secret","auth":"Bearer SECRET-BEARER-999",'
  printf '"detail":"'
  for _ in $(seq 1 120); do printf 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'; done
  printf '"}'
} > "$outfile"
printf '500'
"""
    env = _staging_env(tmp_path, psql, curl)
    result = subprocess.run(["bash", str(STAGING_VERIFY_SH)], capture_output=True, text=True, env=env, timeout=120)
    assert result.returncode == 1, result.stdout
    assert "Save run failed with HTTP 500" in result.stderr
    assert "SECRET-ABC-123" not in result.stderr
    assert "SECRET-BEARER-999" not in result.stderr
    assert "tok_xyz_secret" not in result.stderr
    assert "test-key-stub-456" not in result.stderr
    assert "[REDACTED]" in result.stderr
    assert "truncated to 2000 bytes" in result.stderr


def test_staging_success_cleans_up_probe_fix_items(tmp_path: Path) -> None:
    """A passing run must delete the probe's fix-item rows keyed by run_id."""
    psql = """#!/bin/bash
args="$*"
echo "$args" >> "$PSQL_LOG"
if [[ "$args" == *"to_regclass"* ]]; then echo "t"; exit 0; fi
if [[ "$args" == *"pg_trigger"* ]]; then echo "4"; exit 0; fi
if [[ "$args" == *"DELETE FROM"* ]]; then echo "DELETE 1"; exit 0; fi
echo "2"
"""
    curl = """#!/bin/bash
outfile=""
prev=""
for arg in "$@"; do
  if [[ "$prev" == "-o" ]]; then outfile="$arg"; fi
  prev="$arg"
done
if [[ "$*" == *"readiness/summary"* ]]; then
  printf '{"run_id":"run-probe-test-1","score":95,"label":"Ready"}' > "$outfile"
else
  printf '{"run_id":"run-probe-test-1"}' > "$outfile"
fi
printf '200'
"""
    env = _staging_env(tmp_path, psql, curl)
    result = subprocess.run(["bash", str(STAGING_VERIFY_SH)], capture_output=True, text=True, env=env, timeout=120)
    assert result.returncode == 0, result.stderr
    assert "Inflow Workbench staging verification passed." in result.stdout
    log = (tmp_path / "psql.log").read_text()
    assert "DELETE FROM fsma.inflow_workbench_fix_items" in log
    assert "run-probe-test-1" in log
