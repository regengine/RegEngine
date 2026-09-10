"""Exercise the workflow's real probe shell with deterministic HTTP responses."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


@pytest.mark.parametrize("api_status,expected_failed", [("200", False), ("503", True), ("000", True)])
def test_product_uptime_excludes_optional_simulator(tmp_path, api_status, expected_failed):
    root = Path(__file__).resolve().parents[2]
    workflow = yaml.safe_load((root / ".github/workflows/production-uptime.yml").read_text())
    shell = next(step["run"] for step in workflow["jobs"]["probe"]["steps"] if step.get("id") == "probe")
    fake_curl = tmp_path / "curl"
    fake_curl.write_text(f"""#!{sys.executable}
import os, pathlib, sys
args = sys.argv[1:]
url = args[-1]
with open(os.environ["PROBE_CALLS"], "a") as calls:
    calls.write(url + "\\n")
pathlib.Path(args[args.index("-o") + 1]).write_text('{{"status":"test"}}')
print(os.environ["API_STATUS"] if url.endswith("/api/health") else "200", end="")
""")
    fake_curl.chmod(0o755)
    sleep = tmp_path / "sleep"
    sleep.write_text("#!/bin/sh\nexit 0\n")
    sleep.chmod(0o755)
    output = tmp_path / "output"
    calls = tmp_path / "calls"
    result = subprocess.run(
        ["bash", "-c", shell],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "BASE_URL": "https://example.test",
            "GITHUB_OUTPUT": str(output),
            "PROBE_CALLS": str(calls),
            "API_STATUS": api_status,
        },
    )
    assert result.returncode == int(expected_failed), result.stderr
    assert f"failed={str(expected_failed).lower()}" in output.read_text()
    targets = calls.read_text().splitlines()
    assert targets[0] == "https://example.test/"
    assert targets[1:] == ["https://example.test/api/health"] * (3 if expected_failed else 1)
