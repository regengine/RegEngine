"""Break-it regression tests for launch_orchestrator (bad spec YAML, missing
templates, dry-run safety).

Each test names the probe it came from. Most fail on the pre-fix code: either
the constructor raised the wrong error (TypeError, KeyError, AttributeError),
the run crashed mid-phase (IsADirectoryError, IndexError, FileNotFoundError),
or it reported success for work it never did. Two tests are pins: they pass on
the old code too and exist to lock in behavior that must not regress
(shell metacharacters stay inert, concurrent dry runs leave valid JSON).

Set LAUNCH_ORCHESTRATOR_UNDER_TEST to point at another copy of
orchestrator.py (for example the pre-fix version) to confirm the fail-before
behavior without touching git.
"""

from __future__ import annotations

import importlib.util
import json
import os
import threading
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[2]
_ORCH = Path(
    os.environ.get(
        "LAUNCH_ORCHESTRATOR_UNDER_TEST",
        _REPO / "launch_orchestrator" / "orchestrator.py",
    )
)


def _load_orchestrator_module():
    spec = importlib.util.spec_from_file_location("launch_orchestrator_breakit_mod", _ORCH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


mod = _load_orchestrator_module()


def _write_spec(tmp_path: Path, config: dict) -> str:
    path = tmp_path / "spec.yaml"
    path.write_text(yaml.safe_dump(config))
    return str(path)


def _base_config(**overrides) -> dict:
    config = {"orchestrator": {"name": "test"}, "environment": {}}
    config.update(overrides)
    return config


@pytest.fixture()
def dry(tmp_path, monkeypatch):
    """Dry-run orchestrator on a scratch spec."""
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    path = _write_spec(tmp_path, _base_config())
    return mod.LaunchOrchestrator(str(path), mod.OrchestrationMode.DRY_RUN, dry_run=True)


@pytest.fixture()
def live(tmp_path, monkeypatch):
    """Non-dry-run orchestrator. Commands used in tests are bare `echo` and
    the base dir is a scratch directory, so nothing real can happen."""
    monkeypatch.setenv("REGENGINE_ENV", "production")
    path = _write_spec(tmp_path, _base_config())
    return mod.LaunchOrchestrator(str(path), mod.OrchestrationMode.FULL_LAUNCH, dry_run=False)


def _make(tmp_path, monkeypatch, config: dict, mode=None, dry_run=True):
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    path = _write_spec(tmp_path, config)
    return mod.LaunchOrchestrator(str(path), mode or mod.OrchestrationMode.DRY_RUN, dry_run=dry_run)


# --- Bad spec YAML: empty, wrong top-level type, wrong environment type ---


def test_empty_spec_file_raises_value_error(tmp_path, monkeypatch):
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    path = tmp_path / "empty.yaml"
    path.write_text("")
    with pytest.raises(ValueError, match="Empty configuration"):
        mod.LaunchOrchestrator(str(path), mod.OrchestrationMode.DRY_RUN, dry_run=True)


def test_list_top_level_spec_raises_value_error(tmp_path, monkeypatch):
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    path = tmp_path / "spec.yaml"
    path.write_text("- just\n- a\n- list\n")
    with pytest.raises(ValueError, match="must be a mapping"):
        mod.LaunchOrchestrator(str(path), mod.OrchestrationMode.DRY_RUN, dry_run=True)


def test_string_environment_raises_value_error(tmp_path, monkeypatch):
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    path = _write_spec(tmp_path, {"orchestrator": {"n": 1}, "environment": "prod"})
    with pytest.raises(ValueError, match="environment.*must be a mapping"):
        mod.LaunchOrchestrator(str(path), mod.OrchestrationMode.DRY_RUN, dry_run=True)


def test_string_required_env_vars_raises_value_error(tmp_path, monkeypatch):
    """A string is iterable, so without validation the check degrades into
    per-character variable names (missing_vars ['F', 'O', 'O'])."""
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    path = _write_spec(tmp_path, {"orchestrator": {"n": 1}, "environment": {"required_env_vars": "FOO"}})
    with pytest.raises(ValueError, match="required_env_vars.*must be a list of strings"):
        mod.LaunchOrchestrator(str(path), mod.OrchestrationMode.DRY_RUN, dry_run=True)


def test_null_required_env_vars_is_treated_as_empty(tmp_path, monkeypatch):
    """`required_env_vars:` with no value parses as None; that means no
    requirements, not a crash."""
    orch = _make(tmp_path, monkeypatch, {"orchestrator": {"n": 1}, "environment": {"required_env_vars": None}})
    assert orch.run().success is True


def test_non_string_env_var_entry_raises_value_error(tmp_path, monkeypatch):
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    path = _write_spec(tmp_path, {"orchestrator": {"n": 1}, "environment": {"required_env_vars": ["OK_VAR", 42]}})
    with pytest.raises(ValueError, match="required_env_vars.*must be a list of strings"):
        mod.LaunchOrchestrator(str(path), mod.OrchestrationMode.DRY_RUN, dry_run=True)


# --- Bad spec YAML: shapes the run indexes into must be validated at load ---


def test_step_missing_channel_raises_at_load(tmp_path, monkeypatch):
    config = _base_config(
        sales={"outbound_campaigns": {"sequences": [{"id": "s1", "persona": "p", "steps": [{"day_offset": 0}]}]}}
    )
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    path = _write_spec(tmp_path, config)
    with pytest.raises(ValueError, match=r"sequences\[0\]\.steps\[0\]\.channel"):
        mod.LaunchOrchestrator(str(path), mod.OrchestrationMode.SALES_ONLY, dry_run=True)


def test_persona_missing_id_raises_at_load(tmp_path, monkeypatch):
    config = _base_config(sales={"personas": [{"title": "No Id"}]})
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    path = _write_spec(tmp_path, config)
    with pytest.raises(ValueError, match=r"personas\[0\]\.id"):
        mod.LaunchOrchestrator(str(path), mod.OrchestrationMode.SALES_ONLY, dry_run=True)


def test_status_component_missing_name_raises_at_load(tmp_path, monkeypatch):
    config = _base_config(public_surface={"status_page": {"components": [{"id": "api"}]}})
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    path = _write_spec(tmp_path, config)
    with pytest.raises(ValueError, match=r"components\[0\]\.name"):
        mod.LaunchOrchestrator(str(path), mod.OrchestrationMode.DRY_RUN, dry_run=True)


def test_string_max_partners_raises_at_load(tmp_path, monkeypatch):
    config = _base_config(design_partner_program={"max_partners": "five"})
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    path = _write_spec(tmp_path, config)
    with pytest.raises(ValueError, match="max_partners.*non-negative integer"):
        mod.LaunchOrchestrator(str(path), mod.OrchestrationMode.DRY_RUN, dry_run=True)


def test_negative_max_partners_raises_at_load(tmp_path, monkeypatch):
    config = _base_config(design_partner_program={"max_partners": -1})
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    path = _write_spec(tmp_path, config)
    with pytest.raises(ValueError, match="max_partners.*non-negative integer"):
        mod.LaunchOrchestrator(str(path), mod.OrchestrationMode.DRY_RUN, dry_run=True)


def test_string_workspaces_raises_at_load(tmp_path, monkeypatch):
    config = _base_config(infrastructure={"terraform": {"root_module_path": "x", "workspaces": "demo"}})
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    path = _write_spec(tmp_path, config)
    with pytest.raises(ValueError, match="workspaces.*must be a list of strings"):
        mod.LaunchOrchestrator(str(path), mod.OrchestrationMode.DRY_RUN, dry_run=True)


# --- Missing templates: never crash, never claim success ---


def test_minimal_spec_dry_run_skips_optional_templates(dry):
    """A spec with no design-partner or investor sections used to crash with
    IsADirectoryError (base_dir / "" resolves to the base dir itself)."""
    result = dry.run()
    assert result.success is True
    by_action = {e.action: e.status for e in result.events}
    assert by_action.get("validate_legal_template") == "skipped"
    assert by_action.get("validate_investor_memo") == "skipped"


def test_missing_legal_template_records_failure(tmp_path, monkeypatch):
    config = _base_config(design_partner_program={"legal_template_ref": "legal/NOPE_missing.md", "max_partners": 0})
    orch = _make(tmp_path, monkeypatch, config)
    result = orch.run()
    assert result.success is False
    event = next(e for e in result.events if e.action == "validate_legal_template")
    assert event.status == "failure"
    assert "NOPE_missing.md" in (event.error or "")


def test_missing_investor_memo_records_failure(tmp_path, monkeypatch):
    config = _base_config(investor_readiness={"memo_template_ref": "investors/NOPE_missing.md"})
    orch = _make(tmp_path, monkeypatch, config)
    result = orch.run()
    assert result.success is False
    event = next(e for e in result.events if e.action == "validate_investor_memo")
    assert event.status == "failure"


def test_missing_sequence_template_records_failure(tmp_path, monkeypatch):
    """A campaign whose template files do not exist cannot run; the old code
    recorded success anyway."""
    config = _base_config(
        sales={
            "outbound_campaigns": {
                "sequences": [
                    {
                        "id": "s1",
                        "persona": "p",
                        "steps": [
                            {"day_offset": 0, "channel": "email", "template_ref": "templates/email/NOPE_missing.md"}
                        ],
                    }
                ]
            }
        }
    )
    orch = _make(tmp_path, monkeypatch, config, mode=mod.OrchestrationMode.SALES_ONLY)
    result = orch.run()
    event = next(e for e in result.events if e.action == "initialize_sequence_s1")
    assert event.status == "failure"
    assert "NOPE_missing.md" in (event.error or "")
    assert result.success is False


def test_present_sequence_template_records_success(tmp_path, monkeypatch):
    template = tmp_path / "hello.md"
    template.write_text("# hi")
    config = _base_config(
        sales={
            "outbound_campaigns": {
                "sequences": [
                    {
                        "id": "s1",
                        "persona": "p",
                        "steps": [{"day_offset": 0, "channel": "email", "template_ref": "hello.md"}],
                    }
                ]
            }
        }
    )
    # Spec must sit beside the template: base_dir is the spec's parent.
    orch = _make(tmp_path, monkeypatch, config, mode=mod.OrchestrationMode.SALES_ONLY)
    result = orch.run()
    event = next(e for e in result.events if e.action == "initialize_sequence_s1")
    assert event.status == "success"
    assert result.success is True


# --- Deployment execution: per-action failure, bounded time, live guard ---


def test_bogus_binary_records_failure_and_run_continues(tmp_path, monkeypatch):
    """A missing binary used to escape as FileNotFoundError and abort every
    remaining phase. Now it is one failure event and the run continues."""
    monkeypatch.setenv("REGENGINE_ENV", "production")
    config = _base_config(
        public_surface={"marketing_site": {"deploy_command": "definitely-not-a-real-binary-xyz deploy"}}
    )
    path = _write_spec(tmp_path, config)
    orch = mod.LaunchOrchestrator(str(path), mod.OrchestrationMode.FULL_LAUNCH, dry_run=False)
    result = orch.run()
    event = next(e for e in result.events if e.action == "deploy_marketing_site")
    assert event.status == "failure"
    assert "FileNotFoundError" in (event.error or "")
    # The run continued past the bad command instead of aborting.
    assert any(e.action == "generate_summary" for e in result.events)
    assert not any(e.action == "orchestration_execution" for e in result.events)


def test_empty_deploy_command_records_failure(live):
    live._execute_deployment(mod.OrchestrationPhase.INFRA, "probe", "   ", {})
    event = next(e for e in live.result.events if e.action == "probe")
    assert event.status == "failure"
    assert "empty" in (event.error or "").lower()


def test_flipped_dry_run_still_requires_production_guard(tmp_path, monkeypatch):
    """dry_run is a plain attribute; flipping it after construction used to
    run live commands with no guard at all."""
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    orch = _make(tmp_path, monkeypatch, _base_config())
    orch.dry_run = False
    with pytest.raises(RuntimeError, match="REGENGINE_ENV=production"):
        orch._execute_deployment(mod.OrchestrationPhase.INFRA, "probe", 'echo "LIVE"', {})


def test_live_write_paths_require_production_guard(tmp_path, monkeypatch):
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    orch = _make(tmp_path, monkeypatch, _base_config())
    orch.dry_run = False
    phase = mod.OrchestrationPhase.DESIGN_PARTNERS
    with pytest.raises(RuntimeError, match="REGENGINE_ENV=production"):
        orch._provision_sandbox(phase, "dp-sandbox-1", {})
    assert not (tmp_path / "generated").exists()


def test_shell_metacharacters_are_not_interpreted(live, tmp_path):
    """Pin: shlex.split without shell=True must keep this passing. The marker
    file must never be created."""
    marker = tmp_path / "pwned_marker"
    live._execute_deployment(mod.OrchestrationPhase.INFRA, "probe", f"echo hi; touch {marker}", {})
    assert not marker.exists()


def test_deploy_passes_a_timeout(live, monkeypatch):
    seen: dict = {}
    real_run = mod.subprocess.run

    def _spy(*args, **kwargs):
        seen.update(kwargs)
        return real_run(*args, **kwargs)

    monkeypatch.setattr(mod.subprocess, "run", _spy)
    live._execute_deployment(mod.OrchestrationPhase.INFRA, "probe", "echo hi", {})
    assert seen.get("timeout") == mod._DEPLOY_TIMEOUT_SECONDS


def test_deploy_timeout_records_failure(live, monkeypatch):
    def _hang(*args, **kwargs):
        raise mod.subprocess.TimeoutExpired(cmd="sleep 1000", timeout=1)

    monkeypatch.setattr(mod.subprocess, "run", _hang)
    live._execute_deployment(mod.OrchestrationPhase.INFRA, "probe", "sleep 1000", {})
    event = next(e for e in live.result.events if e.action == "probe")
    assert event.status == "failure"
    assert "TimeoutExpired" in (event.error or "")


# --- Result file: atomic write, concurrent dry runs ---


def test_failed_result_write_keeps_previous_file(dry, monkeypatch):
    """A crash mid-write must leave the previous complete file, not a
    truncated one. The old code truncated first via open("w")."""
    result_file = dry.base_dir / "orchestration_result.json"
    result_file.write_text('{"sentinel": true}')
    stray = list(dry.base_dir.glob(".orchestration_result.json.*.tmp"))
    assert stray == []

    def _boom(*args, **kwargs):
        raise RuntimeError("disk exploded")

    monkeypatch.setattr(mod.json, "dump", _boom)
    with pytest.raises(RuntimeError, match="disk exploded"):
        dry._finalize_result()
    assert result_file.read_text() == '{"sentinel": true}'
    for leftover in dry.base_dir.glob(".orchestration_result.json.*.tmp"):
        leftover.unlink()


def test_concurrent_dry_runs_leave_valid_result_json(tmp_path, monkeypatch):
    """Pin: parallel dry runs against one spec dir must leave parseable JSON
    and no stray temp files."""
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    path = _write_spec(tmp_path, _base_config())
    errors: list = []

    def _run():
        try:
            orch = mod.LaunchOrchestrator(str(path), mod.OrchestrationMode.DRY_RUN, dry_run=True)
            orch.run()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=_run) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert errors == []
    assert json.loads((tmp_path / "orchestration_result.json").read_text())["mode"] == "dry_run"
    assert list(tmp_path.glob(".orchestration_result.json.*.tmp")) == []
