"""Regression tests for the launch_orchestrator findings (#2958, #2961, #2967).

All three share one failure mode: the tool reports success for work it did not
do. Provisioning mints credentials no backend ever registers and logs
``"success"``; the Terraform path builds a shell-composite command that
``shlex.split`` cannot execute; the setup script writes secrets through an
unescaped ``sed`` that either aborts the run or silently corrupts the value.
"""
from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import uuid
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[2]
_ORCH = _REPO / "launch_orchestrator" / "orchestrator.py"
_SETUP = _REPO / "launch_orchestrator" / "scripts" / "setup_environment.sh"


def _load_orchestrator_module():
    spec = importlib.util.spec_from_file_location("launch_orchestrator_mod", _ORCH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


mod = _load_orchestrator_module()


@pytest.fixture()
def orchestrator(tmp_path, monkeypatch):
    """A non-dry-run orchestrator whose base_dir is a scratch directory."""
    config = {
        "orchestrator": {"name": "test"},
        "environment": {"name": "test"},
        "design_partners": {"max_partners": 2, "max_docs_per_partner": 100},
        "infrastructure": {"terraform": {"root_module_path": "infra/terraform"}},
    }
    config_path = tmp_path / "spec.yaml"
    config_path.write_text(yaml.safe_dump(config))
    monkeypatch.setenv("REGENGINE_ENV", "production")
    return mod.LaunchOrchestrator(
        str(config_path), mod.OrchestrationMode.FULL_LAUNCH, dry_run=False
    )


def _events(orch):
    return orch.result.events


# --- #2958: minted credentials must not be written, and must not read "success" ---


def test_provisioning_writes_no_plaintext_api_key_to_disk(orchestrator, tmp_path):
    """No file under the working tree may contain a full sk_test_ credential."""
    phase = list(mod.OrchestrationPhase)[0]
    orchestrator._provision_sandbox(phase, "dp-sandbox-1", {"max_docs_per_partner": 10})

    leaked = []
    for path in tmp_path.rglob("*"):
        if not path.is_file():
            continue
        try:
            body = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        # A prefix like "sk_test_abc..." is fine; a full 32-char key is not.
        if re.search(r"sk_test_[A-Za-z0-9]{32}", body):
            leaked.append(str(path.relative_to(tmp_path)))

    assert leaked == [], f"full API key written to disk: {leaked}"


def test_provisioning_does_not_claim_success_without_registering(orchestrator):
    """Nothing in this module can reach the platform, so 'success' is a lie."""
    phase = list(mod.OrchestrationPhase)[0]
    orchestrator._provision_sandbox(phase, "dp-sandbox-1", {})

    provision_events = [e for e in _events(orchestrator) if "provision_sandbox" in e.action]
    assert provision_events, "expected a provisioning event"
    for event in provision_events:
        assert event.status != "success", (
            "provisioning recorded 'success' although no API call registers the "
            "tenant or the key -- the module imports no HTTP client at all"
        )


def test_generated_tenant_id_is_a_uuid(orchestrator, tmp_path):
    phase = list(mod.OrchestrationPhase)[0]
    orchestrator._provision_sandbox(phase, "dp-sandbox-1", {})

    configs = list((tmp_path / "generated" / "tenants").glob("*.json")) if (
        tmp_path / "generated" / "tenants"
    ).exists() else []
    for config_path in configs:
        import json

        tenant_id = json.loads(config_path.read_text())["tenant_id"]
        uuid.UUID(tenant_id)  # raises if not a UUID


def test_generated_directory_is_gitignored():
    """README.md:90 promises `generated/` is gitignored -- make that true."""
    for candidate in (
        "launch_orchestrator/generated/sandbox_keys.txt",
        "launch_orchestrator/generated/tenants/dp-sandbox-1.json",
    ):
        result = subprocess.run(
            ["git", "check-ignore", "-q", candidate], cwd=_REPO, capture_output=True
        )
        assert result.returncode == 0, f"{candidate} is NOT gitignored"


# --- #2961: the Terraform command must be executable ---------------------------


def test_terraform_command_is_not_a_shell_composite(orchestrator):
    """`shlex.split` does not interpret `&&`; it becomes a literal argv entry."""
    phase = list(mod.OrchestrationPhase)[0]
    recorded: list[str] = []

    def _capture(_phase, action, command, details):
        recorded.append(command)

    orchestrator._execute_deployment = _capture
    orchestrator._deploy_terraform_workspace(phase, "infra/terraform", "demo")

    for command in recorded:
        assert "&&" not in command, (
            "composite command passed to a shlex.split executor: terraform would "
            f"receive '&&' as a positional argument -- {command!r}"
        )


def test_missing_terraform_root_is_reported_as_failure(orchestrator):
    """`infra/terraform` does not exist in this repo; do not report success."""
    phase = list(mod.OrchestrationPhase)[0]
    orchestrator._deploy_terraform_workspace(phase, "definitely/not/here", "demo")

    events = [e for e in _events(orchestrator) if "terraform" in e.action]
    assert events, "expected a terraform event"
    assert all(e.status != "success" for e in events), (
        "reported success for a Terraform root that does not exist"
    )


# --- #2967: the setup script must not mangle secrets ---------------------------


@pytest.mark.parametrize(
    "secret",
    [
        "ab/cd+efGH12345",   # '/' -- routine in base64 S3 secret access keys
        "ab&cd",             # '&' -- expands to the whole matched line in sed
        "a/b&c/d",           # both
        "plain_value_123",   # control
    ],
)
def test_setup_script_writes_secret_values_verbatim(tmp_path, secret):
    """The value written must be byte-identical to what the operator typed."""
    env_file = tmp_path / ".env"
    env_file.write_text("OBJECT_STORAGE_SECRET_ACCESS_KEY=placeholder\nOTHER=keepme\n")

    script = f"""
    set -euo pipefail
    source '{_SETUP}' --source-only
    set_env_var OBJECT_STORAGE_SECRET_ACCESS_KEY {secret!r} '{env_file}'
    """
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, f"helper failed: {result.stderr}"

    lines = dict(
        line.split("=", 1) for line in env_file.read_text().splitlines() if "=" in line
    )
    assert lines["OBJECT_STORAGE_SECRET_ACCESS_KEY"] == secret
    assert lines["OTHER"] == "keepme", "unrelated line was corrupted"


def test_every_credential_prompt_suppresses_terminal_echo():
    """`read -p` echoes; secrets must use `read -s`."""
    body = _SETUP.read_text()
    echoing = [
        line.strip()
        for line in body.splitlines()
        if re.search(r"\bread\s+-p\b", line)
        and re.search(r"key|token|secret|password|webhook", line, re.IGNORECASE)
        # `read -p "... token? (y/N): " -n 1 -r` is a yes/no question ABOUT a
        # credential, not a prompt that captures one. Reading a single
        # character is the tell, and suppressing its echo would be wrong.
        and not re.search(r"-n\s+1\b", line)
    ]
    assert echoing == [], f"credential prompts echo to the terminal: {echoing}"


def test_setup_script_does_not_touch_the_repo_root_env():
    """Run from anywhere, it must operate on launch_orchestrator/.env."""
    body = _SETUP.read_text()
    assert 'cd "$(dirname "${BASH_SOURCE[0]}")/.."' in body or 'cd "$SCRIPT_DIR/.."' in body, (
        "script never anchors its CWD, so `cp .env.example .env` from the repo "
        "root overwrites the developer's real root .env"
    )


def test_admin_master_key_is_not_collected():
    """No code reads REGENGINE_ADMIN_MASTER_KEY; do not put it on disk."""
    for path in (
        _REPO / "launch_orchestrator" / ".env.example",
        _SETUP,
    ):
        if not path.exists():
            continue
        # The contract is that the key is not COLLECTED. Naming it in a comment
        # that explains why it was removed is fine and worth keeping.
        collected = [
            line
            for line in path.read_text().splitlines()
            if re.match(r"\s*REGENGINE_ADMIN_MASTER_KEY\s*=", line)
            or re.search(r"set_env_var\s+REGENGINE_ADMIN_MASTER_KEY", line)
        ]
        assert collected == [], (
            f"{path.name} still collects a production admin master key that "
            f"nothing in the repo reads: {collected}"
        )
