from __future__ import annotations

import argparse
import asyncio
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

from regengine.swarm import cli


def test_run_refuses_without_legacy_swarm_opt_in(monkeypatch, capsys):
    monkeypatch.delenv("REGENGINE_ENABLE_LEGACY_SWARM", raising=False)

    args = argparse.Namespace(
        task="Audit PR #123 for auth regressions",
        dry_run=True,
        max_iterations=1,
        agent="security",
        output_file=None,
    )

    with pytest.raises(SystemExit) as exc_info:
        cli.cmd_run(args)

    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "disabled by default" in err
    assert "scripts/summon_agent.py --list" in err


def test_status_reports_small_scale_model_when_legacy_swarm_disabled(monkeypatch, capsys):
    monkeypatch.delenv("REGENGINE_ENABLE_LEGACY_SWARM", raising=False)

    cli.cmd_status(argparse.Namespace())

    out = capsys.readouterr().out
    assert "Legacy autonomous swarm: disabled" in out
    assert "planner, implementer, security_review" in out


def test_agent_swarm_constructor_requires_legacy_opt_in(monkeypatch):
    monkeypatch.delenv("REGENGINE_ENABLE_LEGACY_SWARM", raising=False)

    from regengine.swarm.coordinator import AgentSwarm, LegacySwarmDisabledError

    with pytest.raises(LegacySwarmDisabledError):
        AgentSwarm()


def test_security_agent_ci_branch_can_read_os_env(monkeypatch, capsys):
    """Regression: a local ``import os`` made ``os.getenv`` crash in CI."""

    agent = MagicMock()
    agent.run = AsyncMock(
        return_value={
            "result": {
                "verdict": "pass",
                "summary": "ok",
                "score": 1.0,
                "vulnerabilities": [],
            }
        }
    )

    class FakeSwarm:
        def __init__(self, llm_client, max_iterations):
            self.agents = {"security": agent}

    fake_coordinator = types.ModuleType("regengine.swarm.coordinator")
    fake_coordinator.AgentSwarm = FakeSwarm

    fake_llm = types.ModuleType("regengine.swarm.llm")
    fake_llm.MockLLMClient = lambda responses: object()
    fake_llm.LLMClientFactory = MagicMock()

    gh_client = MagicMock()
    fake_github = types.ModuleType("regengine.swarm.github_integration")
    fake_github.GitHubClient = lambda: gh_client

    monkeypatch.setitem(sys.modules, "regengine.swarm.coordinator", fake_coordinator)
    monkeypatch.setitem(sys.modules, "regengine.swarm.llm", fake_llm)
    monkeypatch.setitem(
        sys.modules,
        "regengine.swarm.github_integration",
        fake_github,
    )
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("REGENGINE_ENABLE_LEGACY_SWARM", "1")

    args = argparse.Namespace(
        task="Audit PR #123 for auth regressions",
        dry_run=True,
        max_iterations=1,
        agent="security",
        output_file=None,
    )

    try:
        cli.cmd_run(args)
    finally:
        # ``cmd_run`` uses ``asyncio.run``. On Python 3.12 that leaves later
        # legacy tests that call ``asyncio.get_event_loop()`` without a default
        # loop, so restore one before this regression test exits.
        asyncio.set_event_loop(asyncio.new_event_loop())

    gh_client.comment_on_issue.assert_called_once()
    assert "Security report posted to PR #123" in capsys.readouterr().out


def _install_fake_swarm_modules(monkeypatch, agent):
    class FakeSwarm:
        def __init__(self, *args, **kwargs):
            self.agents = {"security": agent}

        async def troubleshoot(self, logs):
            FakeSwarm.last_logs = logs
            result = MagicMock()
            result.status = "diagnosed"
            result.plan = {"root_cause": "boom", "immediate_fix": "fix it"}
            result.agents_used = ["troubleshooter"]
            result.duration_seconds = 0.1
            return result

    FakeSwarm.last_logs = None

    fake_coordinator = types.ModuleType("regengine.swarm.coordinator")
    fake_coordinator.AgentSwarm = FakeSwarm
    monkeypatch.setitem(sys.modules, "regengine.swarm.coordinator", fake_coordinator)
    return FakeSwarm


def test_troubleshoot_rejects_absolute_log_file_outside_cwd(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("REGENGINE_ENABLE_LEGACY_SWARM", "1")
    monkeypatch.chdir(tmp_path)
    outside = tmp_path.parent / "outside-secret.log"
    outside.write_text("top secret log contents")

    args = argparse.Namespace(log_file=str(outside), logs=None)
    with pytest.raises(SystemExit) as exc_info:
        cli.cmd_troubleshoot(args)

    assert exc_info.value.code == 1
    assert "working directory" in capsys.readouterr().out


def test_troubleshoot_rejects_parent_traversal_log_file(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("REGENGINE_ENABLE_LEGACY_SWARM", "1")
    monkeypatch.chdir(tmp_path)
    (tmp_path.parent / "escape.log").write_text("top secret log contents")

    args = argparse.Namespace(log_file="../escape.log", logs=None)
    with pytest.raises(SystemExit) as exc_info:
        cli.cmd_troubleshoot(args)

    assert exc_info.value.code == 1
    assert "working directory" in capsys.readouterr().out


def test_troubleshoot_missing_log_file_exits_cleanly(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("REGENGINE_ENABLE_LEGACY_SWARM", "1")
    monkeypatch.chdir(tmp_path)

    args = argparse.Namespace(log_file="does-not-exist.log", logs=None)
    with pytest.raises(SystemExit) as exc_info:
        cli.cmd_troubleshoot(args)

    assert exc_info.value.code == 1
    assert "not found" in capsys.readouterr().out


def test_troubleshoot_reads_log_file_inside_cwd(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("REGENGINE_ENABLE_LEGACY_SWARM", "1")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ci.log").write_text("FAILED: boom")
    FakeSwarm = _install_fake_swarm_modules(monkeypatch, MagicMock())

    args = argparse.Namespace(log_file="ci.log", logs=None)
    try:
        cli.cmd_troubleshoot(args)
    finally:
        asyncio.set_event_loop(asyncio.new_event_loop())

    assert FakeSwarm.last_logs == "FAILED: boom"
    assert "diagnosed" in capsys.readouterr().out


def test_security_comment_tolerates_malformed_llm_findings(monkeypatch, capsys):
    """LLM finding entries with missing keys or wrong types must not crash the comment."""

    agent = MagicMock()
    agent.run = AsyncMock(
        return_value={
            "result": {
                "verdict": "fail",
                "summary": "bad",
                "score": "high",
                "vulnerabilities": [
                    {"issue": "SQLi somewhere"},
                    "not-a-dict",
                    {
                        "severity": "high",
                        "issue": "XSS",
                        "file": "app.py",
                        "remediation": "escape output",
                    },
                ],
            }
        }
    )

    class FakeSwarm:
        def __init__(self, llm_client, max_iterations):
            self.agents = {"security": agent}

    fake_coordinator = types.ModuleType("regengine.swarm.coordinator")
    fake_coordinator.AgentSwarm = FakeSwarm

    fake_llm = types.ModuleType("regengine.swarm.llm")
    fake_llm.MockLLMClient = lambda responses: object()
    fake_llm.LLMClientFactory = MagicMock()

    gh_client = MagicMock()
    fake_github = types.ModuleType("regengine.swarm.github_integration")
    fake_github.GitHubClient = lambda: gh_client

    monkeypatch.setitem(sys.modules, "regengine.swarm.coordinator", fake_coordinator)
    monkeypatch.setitem(sys.modules, "regengine.swarm.llm", fake_llm)
    monkeypatch.setitem(
        sys.modules,
        "regengine.swarm.github_integration",
        fake_github,
    )
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("REGENGINE_ENABLE_LEGACY_SWARM", "1")

    args = argparse.Namespace(
        task="Audit PR #7 for regressions",
        dry_run=True,
        max_iterations=1,
        agent="security",
        output_file=None,
    )

    try:
        cli.cmd_run(args)
    finally:
        asyncio.set_event_loop(asyncio.new_event_loop())

    gh_client.comment_on_issue.assert_called_once()
    _pr_num, comment = gh_client.comment_on_issue.call_args[0]
    assert _pr_num == 7
    assert "SQLi somewhere" in comment
    assert "XSS" in comment
    assert "Security report posted to PR #7" in capsys.readouterr().out
