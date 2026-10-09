"""Regression tests for scripts/export-openapi.sh (audit finding 104).

The defect: each endpoint block probed with `curl -sf` but swallowed the
failure in an if/else that printed a warning and carried on, so a run with
every endpoint down still exited 0 behind an "OpenAPI export complete"
message. Partial exports looked complete.

These tests run the real script with a stubbed `curl` on PATH, so they need
no live services. One scenario makes every endpoint unreachable and requires
a non-zero exit; the other serves a minimal spec from every endpoint and
requires a zero exit with all three files written.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "export-openapi.sh"

_STUB_TEMPLATE = """\
#!/usr/bin/env bash
# Stub curl: reproduces only the exit-status contract the script relies on.
if [ "${STUB_CURL_MODE}" = "ok" ]; then
  echo '{"openapi": "3.0.0", "info": {"title": "stub", "version": "0"}}'
  exit 0
else
  echo "curl: (7) Failed to connect to localhost" >&2
  exit 7
fi
"""


def _run_export(tmp_path: Path, *, mode: str):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "curl"
    stub.write_text(_STUB_TEMPLATE)
    stub.chmod(0o755)

    out_dir = tmp_path / "out"
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["REGENGINE_OPENAPI_OUTPUT_DIR"] = str(out_dir)
    env["STUB_CURL_MODE"] = mode

    proc = subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        timeout=120,
    )
    return proc, out_dir


def test_unreachable_endpoints_fail_loudly(tmp_path):
    """All endpoints down must exit non-zero, not print 'complete' as success.

    Fails against the pre-fix script, which exited 0 in this scenario.
    """
    proc, _ = _run_export(tmp_path, mode="fail")

    assert proc.returncode != 0, (
        "script exited 0 with every endpoint unreachable; "
        f"partial exports look complete.\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    combined = proc.stdout + proc.stderr
    assert "not available" in combined or "incomplete" in combined, (
        "script failed silently; it must say which endpoints were unreachable\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )


def test_reachable_endpoints_still_succeed(tmp_path):
    """All endpoints up must exit 0 with all three specs exported."""
    proc, out_dir = _run_export(tmp_path, mode="ok")

    assert proc.returncode == 0, f"script failed with all endpoints up:\n{proc.stdout}\n{proc.stderr}"
    for name in ("ingestion-api.json", "compliance-api.json", "graph-api.json"):
        exported = out_dir / name
        assert exported.exists(), f"expected exported spec {name} in {out_dir}"
        assert '"openapi"' in exported.read_text(), f"{name} does not hold the served spec"
