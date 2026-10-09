"""Redaction of deployment command output in the launch orchestrator.

Deploy command stdout/stderr is stored on orchestration events and persisted
to orchestration_result.json. If a deploy tool echoes a credential, the raw
value must not be kept verbatim. These tests prove secrets are redacted
before they reach the stored event details.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_ORCHESTRATOR_PATH = Path(__file__).resolve().parent.parent / "launch_orchestrator" / "orchestrator.py"


def _load_orchestrator():
    spec = importlib.util.spec_from_file_location("launch_orchestrator_orchestrator", _ORCHESTRATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def module():
    return _load_orchestrator()


@pytest.fixture()
def orchestrator(module, tmp_path, monkeypatch):
    monkeypatch.setenv("REGENGINE_ENV", "production")
    config = tmp_path / "spec.yaml"
    config.write_text("orchestrator: {}\nenvironment: {}\n")
    return module.LaunchOrchestrator(
        config_path=str(config),
        mode=module.OrchestrationMode.INFRA_ONLY,
        dry_run=False,
    )


def test_redact_secrets_covers_common_token_shapes(module):
    cases = [
        "key sk-abcDEF1234567890seed",
        "Authorization: Bearer abcdefgh12345678",
        "api_key=supersecretvalue",
        "password: hunter2-hunter2",
        "AKIAIOSFODNN7EXAMPLE",
    ]
    for raw in cases:
        redacted = module.redact_secrets(raw)
        assert raw not in redacted
        assert "[REDACTED" in redacted


def test_redact_secrets_leaves_plain_output_alone(module):
    plain = "terraform apply complete: 3 added, 0 changed, 0 destroyed"
    assert module.redact_secrets(plain) == plain
    assert module.redact_secrets(None) is None


def test_execute_deployment_redacts_success_output(module, orchestrator, monkeypatch):
    leaked_stdout = "created api token api_key=topsecret-deploy-token-123\nall good"
    leaked_stderr = "warning: password=hunter2-hunter2 used default\n"

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=leaked_stdout, stderr=leaked_stderr)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    orchestrator._execute_deployment(module.OrchestrationPhase.INFRA, "deploy_test", "echo hi", {})

    details = orchestrator.result.events[-1].details
    assert "topsecret-deploy-token-123" not in details["stdout"]
    assert "hunter2-hunter2" not in details["stderr"]
    assert "[REDACTED" in details["stdout"]
    assert "[REDACTED" in details["stderr"]


def test_execute_deployment_redacts_failure_output(module, orchestrator, monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=args[0],
            output="failed with token sk-abcDEF1234567890seed",
            stderr="Bearer abcdefgh12345678 rejected",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    orchestrator._execute_deployment(module.OrchestrationPhase.INFRA, "deploy_test", "echo hi", {})

    event = orchestrator.result.events[-1]
    assert event.status == "failure"
    assert "sk-abcDEF1234567890seed" not in str(event.details["stdout"])
    assert "abcdefgh12345678" not in str(event.details["stderr"])
    assert "sk-abcDEF1234567890seed" not in str(event.error)
