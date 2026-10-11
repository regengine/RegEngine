"""QA deep-pass tests for launch_orchestrator/orchestrator.py.

Covers result accounting, config validation, environment gating, mode
dispatch, deployment execution, and honest status reporting. All tests are
fast and deterministic: no sleeps, no network, subprocess use is limited to
the local Python interpreter and echo.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[2]
_ORCH = _REPO / "launch_orchestrator" / "orchestrator.py"


def _load_orchestrator_module():
    spec = importlib.util.spec_from_file_location("launch_orchestrator_qa4", _ORCH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


mod = _load_orchestrator_module()


def _write_config(tmp_path, config) -> str:
    path = tmp_path / "spec.yaml"
    path.write_text(yaml.safe_dump(config))
    return str(path)


@pytest.fixture()
def minimal_config_path(tmp_path):
    return _write_config(
        tmp_path,
        {
            "orchestrator": {"name": "test"},
            "environment": {"name": "test"},
        },
    )


@pytest.fixture()
def orch(minimal_config_path):
    """Dry-run orchestrator rooted at a scratch directory."""
    return mod.LaunchOrchestrator(minimal_config_path, mod.OrchestrationMode.DRY_RUN, dry_run=True)


def _events_by_action(orchestrator, action):
    return [e for e in orchestrator.result.events if e.action == action]


# --- OrchestrationResult accounting ------------------------------------------


def test_failure_event_flips_success_and_records_error(orch):
    orch.result.add_event(mod.OrchestrationPhase.INIT, "probe", "failure", error="boom")
    assert orch.result.success is False
    assert orch.result.errors == ["initialization/probe: boom"]


def test_success_event_keeps_success_true(orch):
    orch.result.add_event(mod.OrchestrationPhase.INIT, "probe", "success")
    assert orch.result.success is True
    assert orch.result.errors == []


def test_add_artifact_hashes_literal_content(orch):
    orch.result.add_artifact("greeting", "hello")
    assert orch.result.artifacts["greeting"] == hashlib.sha256(b"hello").hexdigest()


def test_add_artifact_hashes_file_bytes(orch, tmp_path):
    target = tmp_path / "blob.bin"
    target.write_bytes(b"\x00\x01binary")
    orch.result.add_artifact("blob", str(target))
    assert orch.result.artifacts["blob"] == hashlib.sha256(b"\x00\x01binary").hexdigest()


def test_to_dict_serializes_events_and_artifacts(orch):
    orch.result.add_event(mod.OrchestrationPhase.INIT, "probe", "success", details={"n": 1})
    orch.result.add_artifact("greeting", "hello")
    body = orch.result.to_dict()
    assert body["mode"] == "dry_run"
    assert body["success"] is True
    assert body["events"][0]["action"] == "probe"
    assert body["events"][0]["details"] == {"n": 1}
    assert body["artifacts"]["greeting"] == hashlib.sha256(b"hello").hexdigest()


# --- Config loading -----------------------------------------------------------


def test_missing_config_key_raises_value_error(tmp_path):
    path = _write_config(tmp_path, {"orchestrator": {"name": "test"}})
    with pytest.raises(ValueError, match="Missing required config key: environment"):
        mod.LaunchOrchestrator(path, mod.OrchestrationMode.DRY_RUN, dry_run=True)


def test_empty_config_file_raises_value_error_not_type_error(tmp_path):
    """An empty yaml file loads as None; the caller deserves a ValueError."""
    path = tmp_path / "spec.yaml"
    path.write_text("")
    with pytest.raises(ValueError, match="not a mapping"):
        mod.LaunchOrchestrator(path, mod.OrchestrationMode.DRY_RUN, dry_run=True)


def test_non_dry_run_requires_production_env(tmp_path, monkeypatch):
    path = _write_config(tmp_path, {"orchestrator": {}, "environment": {}})
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    with pytest.raises(RuntimeError, match="REGENGINE_ENV=production"):
        mod.LaunchOrchestrator(path, mod.OrchestrationMode.FULL_LAUNCH, dry_run=False)


def test_non_dry_run_allowed_in_production_env(tmp_path, monkeypatch):
    path = _write_config(tmp_path, {"orchestrator": {}, "environment": {}})
    monkeypatch.setenv("REGENGINE_ENV", "production")
    instance = mod.LaunchOrchestrator(path, mod.OrchestrationMode.FULL_LAUNCH, dry_run=False)
    assert instance.dry_run is False


def test_dry_run_mode_forces_dry_run(minimal_config_path):
    instance = mod.LaunchOrchestrator(minimal_config_path, mod.OrchestrationMode.DRY_RUN, dry_run=False)
    assert instance.dry_run is True


# --- Environment validation ----------------------------------------------------


def test_validate_environment_reports_missing_vars(orch, monkeypatch):
    orch.config["environment"] = {"required_env_vars": ["DEFINITELY_NOT_SET_QA4_A"]}
    monkeypatch.delenv("DEFINITELY_NOT_SET_QA4_A", raising=False)
    assert orch._validate_environment() is False
    events = _events_by_action(orch, "validate_environment")
    assert len(events) == 1
    assert events[0].status == "failure"
    assert orch.result.success is False


def test_validate_environment_passes_when_all_set(orch, monkeypatch):
    orch.config["environment"] = {"required_env_vars": ["QA4_PRESENT"]}
    monkeypatch.setenv("QA4_PRESENT", "1")
    assert orch._validate_environment() is True
    assert _events_by_action(orch, "validate_environment")[0].status == "success"


def test_validate_environment_tolerates_null_environment_block(orch):
    """`environment:` with no mapping must not crash with AttributeError."""
    orch.config["environment"] = None
    assert orch._validate_environment() is True


def test_full_launch_dry_run_tolerates_null_blocks(tmp_path):
    """Every optional mapping block may be explicitly null in yaml."""
    path = _write_config(
        tmp_path,
        {
            "orchestrator": {"name": "test"},
            "environment": None,
            "public_surface": None,
            "sales": None,
            "design_partner_program": None,
            "investor_readiness": None,
            "infrastructure": None,
        },
    )
    instance = mod.LaunchOrchestrator(path, mod.OrchestrationMode.FULL_LAUNCH, dry_run=True)
    result = instance.run()
    assert result.success is True
    assert any(e.action == "generate_summary" for e in result.events)


def test_dry_run_continues_past_failed_environment(orch, monkeypatch):
    orch.config["environment"] = {"required_env_vars": ["DEFINITELY_NOT_SET_QA4_B"]}
    monkeypatch.delenv("DEFINITELY_NOT_SET_QA4_B", raising=False)
    result = orch.run()
    assert result.end_time is not None
    actions = {e.action for e in result.events}
    assert "validate_environment" in actions
    assert "generate_summary" in actions


# --- Mode dispatch --------------------------------------------------------------


def test_sales_only_runs_sales_phase_alone(tmp_path):
    path = _write_config(
        tmp_path,
        {
            "orchestrator": {"name": "test"},
            "environment": {},
            "sales": {
                "personas": [{"id": "p1", "title": "P1"}],
                "outbound_campaigns": {"sequences": []},
            },
        },
    )
    instance = mod.LaunchOrchestrator(path, mod.OrchestrationMode.SALES_ONLY, dry_run=True)
    result = instance.run()
    assert result.success is True
    phases = {e.phase for e in result.events}
    assert mod.OrchestrationPhase.SALES_GTM in phases
    assert mod.OrchestrationPhase.INFRA not in phases
    assert mod.OrchestrationPhase.PUBLIC_SURFACE not in phases


def test_infra_only_skips_sales_and_reports_missing_terraform(tmp_path, monkeypatch):
    path = _write_config(
        tmp_path,
        {
            "orchestrator": {"name": "test"},
            "environment": {},
            "infrastructure": {"terraform": {"root_module_path": "definitely/not/here"}},
        },
    )
    monkeypatch.setenv("REGENGINE_ENV", "production")
    instance = mod.LaunchOrchestrator(path, mod.OrchestrationMode.INFRA_ONLY, dry_run=False)
    result = instance.run()
    assert result.success is False
    assert any("terraform" in e.action and e.status == "failure" for e in result.events)


# --- Deployment execution --------------------------------------------------------


def test_execute_deployment_dry_run_records_command(orch):
    orch._execute_deployment(mod.OrchestrationPhase.INFRA, "probe", "echo hi", {"k": "v"})
    (event,) = _events_by_action(orch, "probe")
    assert event.status == "success"
    assert event.details["dry_run"] is True
    assert event.details["command"] == "echo hi"


def test_execute_deployment_real_command_success(tmp_path, monkeypatch):
    path = _write_config(tmp_path, {"orchestrator": {}, "environment": {}})
    monkeypatch.setenv("REGENGINE_ENV", "production")
    instance = mod.LaunchOrchestrator(path, mod.OrchestrationMode.INFRA_ONLY, dry_run=False)
    instance._execute_deployment(mod.OrchestrationPhase.INFRA, "probe", "echo hi", {})
    (event,) = _events_by_action(instance, "probe")
    assert event.status == "success"
    assert event.details["stdout"] == "hi"


def test_execute_deployment_real_command_failure(tmp_path, monkeypatch):
    path = _write_config(tmp_path, {"orchestrator": {}, "environment": {}})
    monkeypatch.setenv("REGENGINE_ENV", "production")
    instance = mod.LaunchOrchestrator(path, mod.OrchestrationMode.INFRA_ONLY, dry_run=False)
    command = f'{sys.executable} -c "import sys; sys.exit(1)"'
    instance._execute_deployment(mod.OrchestrationPhase.INFRA, "probe", command, {})
    (event,) = _events_by_action(instance, "probe")
    assert event.status == "failure"
    assert instance.result.success is False


# --- Honest status reporting -------------------------------------------------------


def test_status_page_skipped_event_names_a_reason(tmp_path, monkeypatch):
    """A production run configures no status page; the skip must say why."""
    path = _write_config(
        tmp_path,
        {
            "orchestrator": {"name": "test"},
            "environment": {},
            "public_surface": {"status_page": {"components": [{"name": "API"}]}},
        },
    )
    monkeypatch.setenv("REGENGINE_ENV", "production")
    instance = mod.LaunchOrchestrator(path, mod.OrchestrationMode.FULL_LAUNCH, dry_run=False)
    instance._deploy_public_surface()
    (event,) = _events_by_action(instance, "configure_status_page")
    assert event.status == "skipped"
    assert "reason" in event.details


def test_missing_legal_template_records_skipped_not_crash(orch):
    """No legal_template_ref configured: previously crashed with IsADirectoryError."""
    orch.config["design_partner_program"] = {"max_partners": 1, "sandbox": {}}
    orch._provision_design_partners()
    events = _events_by_action(orch, "validate_legal_template")
    assert len(events) == 1
    assert events[0].status == "skipped"


def test_missing_investor_memo_records_skipped_not_crash(orch):
    """No memo_template_ref configured: previously crashed with IsADirectoryError."""
    orch.config["investor_readiness"] = {"slides_required": ["vision"]}
    orch._prepare_investor_materials()
    events = _events_by_action(orch, "validate_investor_memo")
    assert len(events) == 1
    assert events[0].status == "skipped"


# --- Sales collateral ---------------------------------------------------------------


def test_persona_collateral_registers_artifact_and_writes_nothing(orch):
    persona = {
        "id": "qa_persona",
        "title": "QA Persona",
        "pains": ["pain one"],
        "desired_outcomes": ["outcome one"],
    }
    orch._generate_persona_collateral(mod.OrchestrationPhase.SALES_GTM, persona)
    assert "qa_persona_one_pager" in orch.result.artifacts
    assert not (Path(orch.config_path).parent / "generated").exists()


def test_outbound_sequence_derives_channels(orch):
    campaign = {
        "id": "seq1",
        "persona": "qa_persona",
        "steps": [
            {"channel": "email"},
            {"channel": "email"},
            {"channel": "linkedin"},
        ],
    }
    orch._initialize_outbound_sequence(mod.OrchestrationPhase.SALES_GTM, campaign)
    (event,) = _events_by_action(orch, "initialize_sequence_seq1")
    assert event.status == "success"
    assert event.details["num_steps"] == 3
    assert sorted(event.details["channels"]) == ["email", "linkedin"]


# --- Summary and finalize --------------------------------------------------------------


def test_summary_counts_match_events(orch):
    orch.result.add_event(mod.OrchestrationPhase.INIT, "a", "success")
    orch.result.add_event(mod.OrchestrationPhase.INIT, "b", "failure", error="x")
    orch._generate_summary()
    (event,) = _events_by_action(orch, "generate_summary")
    assert event.details["total_events"] == 2
    assert event.details["successful_events"] == 1
    assert event.details["failed_events"] == 1


def test_finalize_writes_result_file(tmp_path, minimal_config_path):
    instance = mod.LaunchOrchestrator(minimal_config_path, mod.OrchestrationMode.DRY_RUN, dry_run=True)
    result = instance.run()
    result_file = tmp_path / "orchestration_result.json"
    assert result_file.exists()
    body = json.loads(result_file.read_text())
    assert body["success"] is result.success
    assert body["mode"] == "dry_run"


def test_main_exits_zero_on_success(tmp_path, monkeypatch, capsys):
    path = _write_config(
        tmp_path,
        {
            "orchestrator": {"name": "test"},
            "environment": {"required_env_vars": []},
            "sales": {"personas": [], "outbound_campaigns": {"sequences": []}},
        },
    )
    monkeypatch.setattr(sys, "argv", ["orchestrator.py", "--mode", "sales_only", "--config", path, "--dry-run"])
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 0
