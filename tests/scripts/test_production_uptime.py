"""Exercise the workflow's real probe shell with deterministic HTTP responses."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


def _probe_shell():
    root = Path(__file__).resolve().parents[2]
    workflow = yaml.safe_load((root / ".github/workflows/production-uptime.yml").read_text())
    return next(step["run"] for step in workflow["jobs"]["probe"]["steps"] if step.get("id") == "probe")


def _probe_specs():
    """Return the raw PROBES entries by letting bash expand the real array."""
    shell = _probe_shell()
    prefix = shell.split("probe_path()")[0]
    result = subprocess.run(
        ["bash", "-c", prefix + '\nprintf "%s\\n" "${PROBES[@]}"'],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.splitlines()


def test_every_probe_configures_forbidden_content_pattern():
    specs = _probe_specs()
    assert specs, "expected PROBES entries in the probe shell"
    empty = [spec for spec in specs if not spec.split("|", 1)[1]]
    assert not empty, f"probes with an empty forbidden-content pattern count error pages as healthy: {empty}"


HEALTHY_HOME = "<html><body><h1>RegEngine</h1><p>FSMA 204 traceability</p></body></html>"
HEALTHY_API = '{"status":"healthy","services":[],"summary":{"healthy":0,"total":0}}'


def _run_probe_shell_with_bodies(tmp_path, bodies):
    shell = _probe_shell()
    bodies_file = tmp_path / "bodies.json"
    bodies_file.write_text(json.dumps(bodies))
    fake_curl = tmp_path / "curl"
    fake_curl.write_text(f"""#!{sys.executable}
import json, os, pathlib, sys
args = sys.argv[1:]
url = args[-1]
bodies = json.loads(pathlib.Path(os.environ["PROBE_BODIES"]).read_text())
key = "/api/health" if url.endswith("/api/health") else "/"
pathlib.Path(args[args.index("-o") + 1]).write_text(bodies[key])
print("200", end="")
""")
    fake_curl.chmod(0o755)
    sleep = tmp_path / "sleep"
    sleep.write_text("#!/bin/sh\nexit 0\n")
    sleep.chmod(0o755)
    output = tmp_path / "output"
    result = subprocess.run(
        ["bash", "-c", shell],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "BASE_URL": "https://example.test",
            "GITHUB_OUTPUT": str(output),
            "PROBE_BODIES": str(bodies_file),
        },
    )
    return result, output


@pytest.mark.parametrize(
    "target,error_body",
    [
        ("/", "DEPLOYMENT_PAUSED: this deployment has been paused"),
        ("/", "<html><body><h1>Application error: a client-side exception has occurred</h1></body></html>"),
        (
            "/api/health",
            '{"status":"degraded","services":[{"name":"admin","status":"unhealthy","code":503}],'
            '"summary":{"healthy":0,"total":1}}',
        ),
    ],
)
def test_probe_rejects_error_text_returned_with_200(tmp_path, target, error_body):
    bodies = {"/": HEALTHY_HOME, "/api/health": HEALTHY_API, target: error_body}
    result, output = _run_probe_shell_with_bodies(tmp_path, bodies)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "failed=true" in output.read_text()


def test_probe_accepts_healthy_bodies_with_200(tmp_path):
    result, output = _run_probe_shell_with_bodies(tmp_path, {"/": HEALTHY_HOME, "/api/health": HEALTHY_API})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "failed=false" in output.read_text()


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
