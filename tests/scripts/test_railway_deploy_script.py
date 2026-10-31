"""scripts/railway_deploy.sh must ship commit identity and verify the rollout.

Production is deployed by running `railway up` from a checkout. A bare upload
leaves /health answering `build.commit_sha: null`, because the tracked
build-sha.txt placeholder is what reaches the image. The script under test
stamps HEAD into build-sha.txt for the upload only, restores the placeholder,
and polls /health until the served commit is the one it shipped.

These tests run the real script against a throwaway git repository with a
local bare "origin", a fake `railway` executable placed first on PATH, and a
local HTTP server standing in for /health.
"""

from __future__ import annotations

import http.server
import json
import os
import socket
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "railway_deploy.sh"
_PLACEHOLDER = "unknown\n"
_SUBJECT = "feat: initial deployable commit"

# Records each invocation as one argument per line and, for `up`, snapshots
# build-sha.txt exactly as it was at upload time. `status` prints the shape
# the real CLI prints for a linked project (ids are fakes).
_FAKE_RAILWAY = """#!/usr/bin/env bash
set -euo pipefail
n=$(find "$FAKE_RAILWAY_LOG_DIR" -name '*.args' | wc -l | tr -d ' ')
printf '%s\\n' "$@" > "$FAKE_RAILWAY_LOG_DIR/$n.args"
case "${1:-}" in
  status)
    cat <<STATUS
Workspace:       Example Workspace

Project:         ${FAKE_RAILWAY_PROJECT_NAME:-RegEngine-Prod}
Project ID:      00000000-0000-0000-0000-000000000001

Environment:     ${FAKE_RAILWAY_ENV_NAME:-production}
Environment ID:  env-from-status

Linked service

${FAKE_RAILWAY_SERVICE_NAME:-RegEngine}
    status:        Online
    deployment ID: 00000000-0000-0000-0000-000000000002
    service ID:    svc-from-status
STATUS
    ;;
  up)
    cp build-sha.txt "$FAKE_RAILWAY_LOG_DIR/$n.stamp"
    ;;
esac
"""

# Stands in for curl on the default-URL path only: records the URL it was
# asked for, writes a /health body to the -o file, and prints the status code
# the way `-w '%{http_code}'` does.
_FAKE_CURL = """#!/usr/bin/env bash
set -euo pipefail
out=""
url=""
while [ $# -gt 0 ]; do
  case "$1" in
    -o|-w|--max-time) out_or_opt="$1"; [ "$out_or_opt" = "-o" ] && out="$2"; shift 2 ;;
    -*) shift ;;
    *) url="$1"; shift ;;
  esac
done
printf '%s\\n' "$url" >> "$FAKE_CURL_LOG"
printf '{"build": {"commit_sha": "%s"}}' "$FAKE_CURL_SHA" > "$out"
printf '200'
"""


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env=_hermetic_git_env(),
    ).stdout.strip()


def _hermetic_git_env() -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


class _HealthState:
    def __init__(self) -> None:
        self.sha: str | None = None
        self.requests = 0
        self.url = ""


@dataclass
class _Harness:
    repo: Path
    bin_dir: Path
    log_dir: Path
    health: _HealthState
    env_overrides: dict[str, str | None] = field(default_factory=dict)

    def head(self) -> str:
        return _git(self.repo, "rev-parse", "HEAD")

    def short_head(self) -> str:
        return _git(self.repo, "rev-parse", "--short", "HEAD")

    def run(self, *args: str, cwd: Path | None = None, **overrides: str | None) -> subprocess.CompletedProcess[str]:
        env = _hermetic_git_env()
        for key in [k for k in env if k.startswith("RAILWAY_")]:
            env.pop(key)
        env.update(
            {
                "PATH": f"{self.bin_dir}{os.pathsep}{env['PATH']}",
                "FAKE_RAILWAY_LOG_DIR": str(self.log_dir),
                "BACKEND_URL": self.health.url,
                "RAILWAY_SERVICE_ID": "svc-from-env",
                "RAILWAY_ENVIRONMENT_ID": "env-from-env",
                # Keep the real 900 s / 15 s defaults out of the test run.
                "RAILWAY_DEPLOY_TIMEOUT_SECONDS": "3",
                "RAILWAY_DEPLOY_POLL_SECONDS": "0.2",
                # A token in the environment must never reach the output.
                "RAILWAY_TOKEN": "fake-token-must-not-be-printed",
            }
        )
        for key, value in {**self.env_overrides, **overrides}.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        return subprocess.run(
            ["bash", str(_SCRIPT), *args],
            cwd=cwd or self.repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def calls(self) -> list[list[str]]:
        files = sorted(self.log_dir.glob("*.args"), key=lambda p: int(p.stem))
        return [f.read_text(encoding="utf-8").splitlines() for f in files]

    def stamp_at_upload(self) -> str:
        (stamp,) = self.log_dir.glob("*.stamp")
        return stamp.read_text(encoding="utf-8")

    def stamp_file(self) -> str:
        return (self.repo / "build-sha.txt").read_text(encoding="utf-8")


@pytest.fixture
def health() -> _HealthState:
    state = _HealthState()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - http.server API
            state.requests += 1
            if self.path != "/health":
                self.send_response(404)
                self.end_headers()
                return
            body = json.dumps({"status": "ok", "build": {"commit_sha": state.sha}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args: object) -> None:
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    state.url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def harness(tmp_path: Path, health: _HealthState) -> _Harness:
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q", "-b", "main")
    _git(work, "config", "user.email", "deploy-test@example.com")
    _git(work, "config", "user.name", "Deploy Test")
    _git(work, "config", "commit.gpgsign", "false")
    (work / "build-sha.txt").write_text(_PLACEHOLDER, encoding="utf-8")
    (work / "app.txt").write_text("v1\n", encoding="utf-8")
    _git(work, "add", ".")
    _git(work, "commit", "-q", "-m", _SUBJECT)

    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    _git(work, "remote", "add", "origin", str(origin))
    _git(work, "push", "-q", "-u", "origin", "main")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "railway"
    fake.write_text(_FAKE_RAILWAY, encoding="utf-8")
    fake.chmod(0o755)
    log_dir = tmp_path / "railway-calls"
    log_dir.mkdir()
    return _Harness(repo=work, bin_dir=bin_dir, log_dir=log_dir, health=health)


def _commit_unpushed_change(harness: _Harness) -> None:
    (harness.repo / "app.txt").write_text("v2\n", encoding="utf-8")
    _git(harness.repo, "commit", "-q", "-am", "feat: not on origin/main yet")


def test_refuses_a_dirty_working_tree(harness: _Harness) -> None:
    (harness.repo / "app.txt").write_text("edited but not committed\n", encoding="utf-8")

    result = harness.run()

    assert result.returncode != 0
    assert "working tree is dirty" in result.stderr
    assert harness.calls() == [], "railway must not be invoked for a dirty tree"
    assert harness.stamp_file() == _PLACEHOLDER


def test_refuses_to_run_from_a_git_worktree(harness: _Harness) -> None:
    # `railway up` fails with "Indexing... prefix not found" when .git is a
    # worktree pointer file, which is where most agent sessions run.
    worktree = harness.repo.parent / "worktree"
    _git(harness.repo, "worktree", "add", "-q", str(worktree), "-b", "deploy-from-worktree")
    harness.health.sha = harness.head()

    result = harness.run(cwd=worktree)

    assert result.returncode != 0
    assert "git worktree" in result.stderr
    assert harness.calls() == []
    assert (worktree / "build-sha.txt").read_text(encoding="utf-8") == _PLACEHOLDER


def test_refuses_a_head_that_is_not_on_origin_main(harness: _Harness) -> None:
    _commit_unpushed_change(harness)

    result = harness.run()

    assert result.returncode != 0
    assert "not on origin/main" in result.stderr
    assert harness.calls() == []
    assert harness.stamp_file() == _PLACEHOLDER


def test_allow_unmerged_deploys_an_unpushed_head(harness: _Harness) -> None:
    _commit_unpushed_change(harness)
    harness.health.sha = harness.head()

    result = harness.run("--allow-unmerged")

    assert result.returncode == 0, result.stderr
    assert [call[0] for call in harness.calls()] == ["up"]
    assert harness.stamp_at_upload() == harness.head() + "\n"


def test_stamps_head_sha_for_the_upload_and_restores_the_placeholder(harness: _Harness) -> None:
    head = harness.head()
    harness.health.sha = head

    result = harness.run(RAILWAY_PROJECT_ID="proj-from-env")

    assert result.returncode == 0, result.stderr
    (up,) = harness.calls()
    assert up == [
        "up",
        "--ci",
        "--project",
        "proj-from-env",
        "--service",
        "svc-from-env",
        "--environment",
        "env-from-env",
        "--message",
        f"{_SUBJECT} @{harness.short_head()}",
    ]
    assert harness.stamp_at_upload() == head + "\n", "the full SHA must be in build-sha.txt when railway up runs"
    assert harness.stamp_file() == _PLACEHOLDER, "the tracked placeholder must be restored after the upload"
    assert _git(harness.repo, "status", "--porcelain") == ""
    assert f"Deployed commit matches: {head}" in result.stdout
    output = result.stdout + result.stderr
    assert "fake-token-must-not-be-printed" not in output
    assert "svc-from-env" not in output and "env-from-env" not in output
    assert "proj-from-env" not in output


def test_reads_service_and_environment_from_railway_status_when_unset(harness: _Harness) -> None:
    harness.health.sha = harness.head()

    result = harness.run(RAILWAY_SERVICE_ID=None, RAILWAY_ENVIRONMENT_ID=None)

    assert result.returncode == 0, result.stderr
    status, up = harness.calls()
    assert status == ["status"]
    assert up[:6] == ["up", "--ci", "--service", "svc-from-status", "--environment", "env-from-status"]
    assert "--project" not in up
    assert "svc-from-status" not in result.stdout + result.stderr


def test_refuses_a_plain_http_backend_url_that_is_not_loopback(harness: _Harness) -> None:
    # The /health body is trusted for the shipped SHA, so a public URL must be
    # https; the loopback http URL the other tests use stays allowed.
    harness.health.sha = harness.head()

    result = harness.run(BACKEND_URL="http://health.example.invalid:8080")

    assert result.returncode != 0
    assert "BACKEND_URL must be an https:// URL" in result.stderr
    assert harness.calls() == []
    assert harness.stamp_file() == _PLACEHOLDER


def test_requires_backend_url_when_the_environment_is_chosen_by_hand(harness: _Harness) -> None:
    # RAILWAY_ENVIRONMENT_ID may point at staging; the production default URL
    # would then verify the wrong deployment and could pass by accident.
    harness.health.sha = harness.head()

    result = harness.run(BACKEND_URL=None)

    assert result.returncode != 0
    assert "BACKEND_URL is unset" in result.stderr
    assert harness.calls() == []
    assert harness.stamp_file() == _PLACEHOLDER


@pytest.mark.parametrize(
    ("variable", "value", "expected"),
    [
        ("FAKE_RAILWAY_ENV_NAME", "staging", "environment 'staging'"),
        ("FAKE_RAILWAY_PROJECT_NAME", "Other-Project", "project 'Other-Project'"),
        ("FAKE_RAILWAY_SERVICE_NAME", "Worker", "service 'Worker'"),
    ],
)
def test_refuses_the_default_url_for_any_other_linked_target(
    harness: _Harness, variable: str, value: str, expected: str
) -> None:
    # The production default URL belongs to one project/environment/service.
    # A checkout linked anywhere else must say where to verify.
    harness.health.sha = harness.head()

    result = harness.run(RAILWAY_SERVICE_ID=None, RAILWAY_ENVIRONMENT_ID=None, BACKEND_URL=None, **{variable: value})

    assert result.returncode != 0
    assert expected in result.stderr
    assert "default BACKEND_URL belongs to RegEngine-Prod / production / RegEngine" in result.stderr
    assert harness.calls() == [["status"]]
    assert harness.stamp_file() == _PLACEHOLDER


def test_uses_the_default_url_for_the_linked_production_target(harness: _Harness) -> None:
    # No network: a fake curl answers for whatever URL the script chooses.
    fake_curl = harness.bin_dir / "curl"
    fake_curl.write_text(_FAKE_CURL, encoding="utf-8")
    fake_curl.chmod(0o755)
    curl_log = harness.log_dir / "curl.log"

    result = harness.run(
        RAILWAY_SERVICE_ID=None,
        RAILWAY_ENVIRONMENT_ID=None,
        BACKEND_URL=None,
        FAKE_CURL_LOG=str(curl_log),
        FAKE_CURL_SHA=harness.head(),
    )

    assert result.returncode == 0, result.stderr
    assert [call[0] for call in harness.calls()] == ["status", "up"]
    assert curl_log.read_text(encoding="utf-8").splitlines() == ["https://regengine-production.up.railway.app/health"]


def test_fails_when_health_never_reports_the_shipped_sha(harness: _Harness) -> None:
    stale = "0" * 40
    harness.health.sha = stale

    result = harness.run()

    assert result.returncode != 0
    assert harness.health.requests >= 2, "the script must keep polling until the budget is spent"
    assert "deploy did not converge" in result.stderr
    assert "status=200" in result.stderr
    assert f"commit_sha={stale}" in result.stderr
    assert "a different commit is serving" in result.stderr
    assert harness.stamp_file() == _PLACEHOLDER, "the placeholder must be restored even when verification fails"
    assert _git(harness.repo, "status", "--porcelain") == ""


def test_fails_when_health_is_unreachable(harness: _Harness) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        closed_port = probe.getsockname()[1]

    result = harness.run(BACKEND_URL=f"http://127.0.0.1:{closed_port}")

    assert result.returncode != 0
    assert "status=000" in result.stderr
    assert "never returned 200" in result.stderr
    assert harness.stamp_file() == _PLACEHOLDER
