"""Tests for scripts/ci/check_supply_chain.py (Pattern 6: unpinned supply chain).

Every test asserts a *failure* is produced for genuinely unpinned input,
not merely that the checker runs. Fixture inputs reproduce the exact
shapes removed from this repo by the fix (unpinned pip install with a
system-package bypass fallback, locked to unlocked npm fallback).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "ci" / "check_supply_chain.py"
)
REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_module():
    spec = importlib.util.spec_from_file_location("check_supply_chain", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # Dataclasses resolve their module namespace through sys.modules,
    # so the module must be registered before execution.
    sys.modules["check_supply_chain"] = module
    spec.loader.exec_module(module)
    return module


mod = _load_module()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "frontend").mkdir()
    (tmp_path / "requirements.lock").write_text("# locked\n")
    (tmp_path / "frontend" / "package-lock.json").write_text("{}\n")
    (tmp_path / "scripts" / "ci").mkdir(parents=True)
    baseline = {"version": 1, "entries": []}
    (tmp_path / "scripts" / "ci" / "supply_chain_baseline.json").write_text(
        json.dumps(baseline)
    )
    return tmp_path


def _write(repo: Path, name: str, body: str) -> Path:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


def _rules(violations) -> set[str]:
    return {v.rule for v in violations}


# Action pinning ------------------------------------------------------------


def test_action_pin_accepts_full_sha(repo: Path) -> None:
    path = _write(
        repo,
        ".github/workflows/ok.yml",
        "steps:\n"
        "  - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1\n",
    )
    assert mod.check_action_pin(path, "ok.yml") == []


def test_action_pin_rejects_tag_ref(repo: Path) -> None:
    path = _write(
        repo, ".github/workflows/bad.yml", "steps:\n  - uses: actions/checkout@v4\n"
    )
    violations = mod.check_action_pin(path, "bad.yml")
    assert len(violations) == 1
    assert violations[0].rule == "action-pin"


def test_action_pin_rejects_branch_ref(repo: Path) -> None:
    path = _write(
        repo,
        ".github/workflows/bad.yml",
        "steps:\n  - uses: owner/action@main\n",
    )
    assert _rules(mod.check_action_pin(path, "bad.yml")) == {"action-pin"}


def test_action_pin_allows_local_reusable_workflow(repo: Path) -> None:
    path = _write(
        repo,
        ".github/workflows/ok.yml",
        "jobs:\n  call:\n    uses: ./.github/workflows/other.yml\n",
    )
    assert mod.check_action_pin(path, "ok.yml") == []


# Pipe to shell ------------------------------------------------------------


def test_pipe_to_shell_detected(repo: Path) -> None:
    path = _write(
        repo, "scripts/setup.sh", "#!/bin/sh\ncurl -fsSL https://x.io/i.sh | sh\n"
    )
    assert _rules(mod.check_pipe_shell(path, "setup.sh")) == {"pipe-shell"}


def test_checksum_pipe_not_flagged_as_shell(repo: Path) -> None:
    # A checksum verification pipe must not trip the shell rule.
    path = _write(
        repo,
        "scripts/ok.sh",
        'echo "${SHA}  /tmp/t.tar.gz" | sha256sum -c -\n',
    )
    assert mod.check_pipe_shell(path, "ok.sh") == []


# Floating versions --------------------------------------------------------


def test_latest_url_detected(repo: Path) -> None:
    path = _write(
        repo,
        ".github/workflows/bad.yml",
        "run: curl -sSfL https://x.io/releases/latest/dl.tar.gz -o /tmp/dl.tar.gz\n",
    )
    assert _rules(mod.check_latest_url(path, "bad.yml")) == {"latest-url"}


def test_at_latest_install_detected(repo: Path) -> None:
    path = _write(
        repo,
        "scripts/setup.sh",
        "go install github.com/gitleaks/gitleaks/v8@latest\n",
    )
    assert _rules(mod.check_latest_url(path, "setup.sh")) == {"latest-url"}


def test_image_without_digest_detected(repo: Path) -> None:
    path = _write(repo, "Dockerfile", "FROM python:3.11-slim AS base\n")
    violations = mod.check_image_digest_dockerfile(path, "Dockerfile")
    assert len(violations) == 1
    assert violations[0].rule == "image-digest"


def test_image_with_digest_passes(repo: Path) -> None:
    path = _write(
        repo,
        "Dockerfile",
        "FROM python:3.11-slim@sha256:0123456789abcdef0123456789abcdef"
        "0123456789abcdef0123456789abcdef AS base\n",
    )
    assert mod.check_image_digest_dockerfile(path, "Dockerfile") == []


def test_compose_image_without_digest_detected(repo: Path) -> None:
    path = _write(repo, "docker-compose.dev.yml", "services:\n  db:\n    image: postgres:17\n")
    assert _rules(mod.check_image_digest_yaml(path, "compose")) == {"image-digest"}


# Downloads and installs ---------------------------------------------------


def test_archive_download_without_checksum_detected(repo: Path) -> None:
    path = _write(
        repo,
        "scripts/get.sh",
        "wget https://github.com/grafana/k6/releases/download/v0.47.0/k6.tar.gz\n",
    )
    assert _rules(mod.check_download_checksum(path, "get.sh")) == {
        "download-checksum"
    }


def test_archive_download_with_checksum_passes(repo: Path) -> None:
    path = _write(
        repo,
        "scripts/get.sh",
        'K_SHA256: abc123  # pragma: allowlist secret\n'
        "curl -sSfL https://x.io/k.tar.gz -o /tmp/k.tar.gz\n"
        'echo "${K_SHA256}  /tmp/k.tar.gz" | sha256sum -c -\n',
    )
    assert mod.check_download_checksum(path, "get.sh") == []


def test_unpinned_pip_install_detected(repo: Path) -> None:
    # Exact shape removed from scripts/deploy_railway.sh by this fix.
    path = _write(
        repo,
        "scripts/deploy.sh",
        "pip install neo4j --quiet 2>/dev/null "
        "|| pip install neo4j --quiet --break-system-packages 2>/dev/null\n",
    )
    assert {"pip-pin", "pip-break-system"} <= _rules(
        mod.check_pip(path, "deploy.sh")
    )


def test_pinned_pip_install_passes(repo: Path) -> None:
    path = _write(
        repo,
        ".github/workflows/ok.yml",
        'run: pip install "neo4j==6.3.1" --quiet\n',
    )
    assert mod.check_pip(path, "ok.yml") == []


def test_locked_requirements_pass(repo: Path) -> None:
    path = _write(
        repo,
        "scripts/ok.sh",
        "pip install --quiet --require-hashes -r requirements.lock\n",
    )
    assert mod.check_pip(path, "ok.sh") == []


def test_npm_unlocked_fallback_detected(repo: Path) -> None:
    # Exact shape removed from scripts/install_pkgs.sh by this fix.
    path = _write(
        repo,
        "scripts/bootstrap.sh",
        "if ! (cd frontend && npm ci --silent); then\n"
        "    (cd frontend && npm install --silent)\n"
        "fi\n",
    )
    assert _rules(mod.check_npm(path, "bootstrap.sh")) == {"npm-unlocked"}


def test_npm_ci_and_pinned_global_pass(repo: Path) -> None:
    path = _write(
        repo,
        "scripts/ok.sh",
        "(cd frontend && npm ci --silent)\n"
        'npm install -g "@railway/cli@4.44.0"\n',
    )
    assert mod.check_npm(path, "ok.sh") == []


# Baseline behavior --------------------------------------------------------


def test_baseline_covers_known_violation() -> None:
    violations = [
        mod.Violation("image-digest", "Dockerfile", 4, "FROM python:3.11-slim")
    ]
    baseline = [
        mod.BaselineEntry(
            "image-digest", "Dockerfile", "FROM python:3.11-slim", "reason"
        )
    ]
    failures, stale = mod.apply_baseline(violations, baseline)
    assert failures == []
    assert stale == []


def test_stale_baseline_entry_is_reported() -> None:
    baseline = [
        mod.BaselineEntry("pip-pin", "scripts/gone.sh", "pip install x", "reason")
    ]
    failures, stale = mod.apply_baseline([], baseline)
    assert failures == []
    assert stale == baseline


def test_unbaselined_violation_survives() -> None:
    violations = [mod.Violation("pipe-shell", "scripts/x.sh", 1, "curl | sh")]
    failures, _ = mod.apply_baseline(violations, [])
    assert failures == violations


# End to end against the real tree -----------------------------------------


def test_real_tree_passes_with_committed_baseline() -> None:
    baseline_path = REPO_ROOT / "scripts" / "ci" / "supply_chain_baseline.json"
    violations = mod.find_violations(REPO_ROOT)
    assert violations, "expected the gate to find baselined items in this repo"
    baseline = mod.load_baseline(baseline_path)
    failures, stale = mod.apply_baseline(violations, baseline)
    assert failures == []
    assert stale == []


def test_real_tree_fails_with_empty_baseline(tmp_path: Path) -> None:
    # Without the baseline (the pre-fix state), the gate must fail: this
    # proves the checker actually detects the violations it claims to gate.
    empty = tmp_path / "baseline.json"
    empty.write_text('{"version": 1, "entries": []}')
    violations = mod.find_violations(REPO_ROOT)
    baseline = mod.load_baseline(empty)
    failures, _ = mod.apply_baseline(violations, baseline)
    assert failures, "gate must fail on the unbaselined tree"
    assert {v.rule for v in failures} >= {"image-digest", "pip-pin"}
