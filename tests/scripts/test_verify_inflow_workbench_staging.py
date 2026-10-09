"""Disposable staging tenant for verify_inflow_workbench_staging.sh.

The verifier used to default to one hardcoded shared tenant UUID, so all
concurrent verifiers wrote into the same namespace. It must now generate a
disposable tenant per run (explicit TENANT_ID still honored) and use
per-run lot codes so reruns cannot collide.

Every value below is a sentinel, never a real secret.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "railway" / "verify_inflow_workbench_staging.sh"
SHARED_TENANT = "11111111-1111-4111-8111-111111111111"
FIXED_RUN_ID = "22222222-2222-4222-8222-222222222222"
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def test_no_hardcoded_shared_tenant_default():
    assert SHARED_TENANT not in SCRIPT.read_text()


def _make_fake_bin(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    (bin_dir / "psql").write_text(
        "#!/usr/bin/env bash\n"
        'n=$(cat "$FAKE_STATE_DIR/psql_calls" 2>/dev/null || echo 0)\n'
        "n=$((n + 1))\n"
        'echo "$n" > "$FAKE_STATE_DIR/psql_calls"\n'
        'case "$n" in\n'
        '  1) printf "t" ;;\n'
        '  2) printf "4" ;;\n'
        '  *) printf "2" ;;\n'
        "esac\n"
        "exit 0\n"
    )
    (bin_dir / "curl").write_text(
        "#!/usr/bin/env bash\n"
        'out=""; url=""; datafile=""; prev=""\n'
        'for a in "$@"; do\n'
        '  if [[ "$prev" == "-o" ]]; then out="$a"; prev=""; continue; fi\n'
        '  if [[ "$prev" == "--data" ]]; then datafile="${a#@}"; prev=""; continue; fi\n'
        '  case "$a" in\n'
        '    -o|--data) prev="$a" ;;\n'
        '    http*://*) url="$a" ;;\n'
        "  esac\n"
        "done\n"
        'echo "URL: $url" >> "$FAKE_STATE_DIR/curl.log"\n'
        'if [[ -n "$datafile" && -f "$datafile" ]]; then\n'
        '  cat "$datafile" >> "$FAKE_STATE_DIR/curl.log"\n'
        '  echo >> "$FAKE_STATE_DIR/curl.log"\n'
        "fi\n"
        'if [[ "$url" == *"/runs" ]]; then\n'
        f'  printf \'{{"run_id": "{FIXED_RUN_ID}"}}\' > "$out"\n'
        "else\n"
        f'  printf \'{{"run_id": "{FIXED_RUN_ID}", "score": 90, "label": "ready"}}\' > "$out"\n'
        "fi\n"
        'printf "200"\n'
        "exit 0\n"
    )
    for name in ("psql", "curl"):
        os.chmod(bin_dir / name, 0o755)
    return bin_dir


def _run_script(tmp_path: Path, extra_env: dict | None = None):
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    bin_dir = _make_fake_bin(tmp_path)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "DATABASE_URL": "postgresql://localhost:5432/staging_sentinel",
        "INGESTION_URL": "http://staging-sentinel.invalid",
        "FAKE_STATE_DIR": str(state_dir),
        **(extra_env or {}),
    }
    env.pop("TENANT_ID", None)
    if extra_env and "TENANT_ID" in extra_env:
        env["TENANT_ID"] = extra_env["TENANT_ID"]
    proc = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    return proc, state_dir


def test_unset_tenant_generates_disposable_uuid_and_passes(tmp_path):
    proc, state_dir = _run_script(tmp_path)
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    assert "generated disposable tenant" in combined
    assert "verification passed" in combined.lower()
    payload_log = (state_dir / "curl.log").read_text()
    tenant_in_payload = re.search(r'"tenant_id": "([^"]+)"', payload_log)
    assert tenant_in_payload is not None
    UUID(str(tenant_in_payload.group(1)))
    assert tenant_in_payload.group(1) != SHARED_TENANT
    assert re.search(r"TLC-STAGING-VERIFY-[0-9a-f]{8}", payload_log)


def test_two_runs_get_different_tenants(tmp_path):
    first, _ = _run_script(tmp_path / "first")
    second, _ = _run_script(tmp_path / "second")
    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0, second.stdout + second.stderr
    first_tenant = UUID_RE.search(first.stdout + first.stderr)
    second_tenant = UUID_RE.search(second.stdout + second.stderr)
    assert first_tenant and second_tenant
    assert first_tenant.group(0) != second_tenant.group(0)


def test_explicit_tenant_is_honored(tmp_path):
    explicit = "33333333-3333-4333-8333-333333333333"
    proc, state_dir = _run_script(tmp_path, {"TENANT_ID": explicit})
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    assert "generated disposable tenant" not in combined
    payload_log = (state_dir / "curl.log").read_text()
    assert explicit in payload_log


def test_invalid_tenant_is_rejected_before_any_request(tmp_path):
    proc, state_dir = _run_script(tmp_path, {"TENANT_ID": "not-a-uuid"})
    combined = (proc.stdout + proc.stderr).lower()
    assert proc.returncode == 2
    assert "tenant_id" in combined and "uuid" in combined
    assert not (state_dir / "curl.log").exists()


def test_script_has_strict_mode_and_is_executable():
    text = SCRIPT.read_text()
    assert "set -euo pipefail" in text
    mode = stat.S_IMODE(os.stat(SCRIPT).st_mode)
    assert mode & 0o111
