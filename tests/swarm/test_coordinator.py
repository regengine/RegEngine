"""Focused tests for regengine.swarm.coordinator (AgentSwarm orchestration).

Covers the coordinator's main public behavior: the legacy opt-in gate,
auto-PR approval parsing, SwarmResult serialization, the message bus,
the solve chain (happy path, planner/coder/tester failures, reviewer
reject, the request-changes feedback loop, max iterations, and the
completed_with_warnings status), batch sweep, troubleshoot, and status
reporting.

One test runs a real end-to-end solve with MockLLMClient. The rest stub
the sub-agents' run() methods with canned envelopes, so they exercise
the coordinator's own orchestration (chaining, verdict branching,
iteration counting, error aggregation) without paying for full agent
runs. No network, no real external services. Agent file writes and
memory directories land in tmp_path via the shared fixture.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from regengine.swarm.base import AgentMemory, AgentMessage, MessageType
from regengine.swarm.coordinator import (
    AgentSwarm,
    LegacySwarmDisabledError,
    SwarmResult,
    legacy_swarm_enabled,
    swarm_auto_pr_approved,
)
from regengine.swarm.llm import MockLLMClient

LEGACY_ENV = "REGENGINE_ENABLE_LEGACY_SWARM"
APPROVAL_ENV = "REGENGINE_SWARM_AUTO_PR_APPROVED"
AUTO_FIX_ENV = "REGENGINE_CI_AUTO_FIX"

PLAN_JSON = json.dumps(
    {
        "steps": [
            {
                "id": 1,
                "action": "Implement",
                "files": ["app.py"],
                "details": "Write code",
                "acceptance_criteria": "Done",
            }
        ],
        "risks": [],
        "estimated_complexity": "low",
    }
)
CODE_JSON = json.dumps(
    {
        "files": [
            {"path": "app.py", "action": "create", "content": "x = 1\n", "language": "python"},
        ],
        "summary": "did it",
        "dependencies_added": [],
    }
)
APPROVE_JSON = json.dumps(
    {"verdict": "approve", "score": 0.9, "issues": [], "strengths": ["ok"], "summary": "good"},
)
TESTS_JSON = json.dumps(
    {
        "test_files": [],
        "scenarios_covered": ["happy_path", "edge_case", "error_handling"],
        "coverage_estimate": "80%",
        "summary": "tests",
    }
)

_PLAN_ENVELOPE = {"result": {"plan": {"steps": [{"id": 1}]}, "step_count": 1}}
_CODE_ENVELOPE = {
    "result": {"files_written": [{"path": "app.py", "status": "written"}], "file_count": 1, "summary": "did it"},
}
_TESTS_ENVELOPE = {"result": {"test_files": [], "scenarios_covered": []}}
_SRE_ENVELOPE = {
    "result": {
        "analysis": {"root_cause": "flaky test", "category": "test"},
        "remediation": {"immediate_fix": "quarantine it", "long_term_fix": "fix race", "files_to_modify": []},
    },
}


def _review_envelope(verdict, critical_issues=None):
    return {
        "result": {
            "verdict": verdict,
            "score": 0.9,
            "review": {"notes": "looks fine"},
            "critical_issues": critical_issues or [],
        },
    }


@pytest.fixture
def swarm_env(tmp_path, monkeypatch):
    """Opt into the legacy runtime, isolate the cwd, and disable CI auto-fix."""
    monkeypatch.setenv(LEGACY_ENV, "1")
    monkeypatch.delenv(APPROVAL_ENV, raising=False)
    monkeypatch.delenv(AUTO_FIX_ENV, raising=False)
    monkeypatch.chdir(tmp_path)
    # AgentMemory append-log writes are slow on shared fleet disks and
    # unrelated to coordinator orchestration, so silence them here.
    # Every agent think/act/reflect step and LLM call stays real.
    monkeypatch.setattr(AgentMemory, "record", lambda self, *args, **kwargs: None)
    return tmp_path


def _stubbed_swarm(monkeypatch, reviewer="approve", **overrides):
    """Build a swarm whose sub-agent run() methods return canned envelopes."""
    swarm = AgentSwarm(llm_client=MockLLMClient())
    stubs = {
        "planner": _PLAN_ENVELOPE,
        "coder": _CODE_ENVELOPE,
        "reviewer": _review_envelope(reviewer) if isinstance(reviewer, str) else reviewer,
        "tester": _TESTS_ENVELOPE,
        "sre": _SRE_ENVELOPE,
    }
    stubs.update(overrides)
    for name, envelope in stubs.items():
        mock = AsyncMock(return_value=envelope) if not isinstance(envelope, AsyncMock) else envelope
        monkeypatch.setattr(getattr(swarm, name), "run", mock)
    return swarm


# ── Gate and approval parsing ─────────────────────────────


def test_legacy_gate_and_pr_approval_parsing(monkeypatch):
    for value in ("1", "true", "TRUE", "yes", "on", "  On  "):
        monkeypatch.setenv(LEGACY_ENV, value)
        assert legacy_swarm_enabled() is True
    for value in ("", "0", "false", "no", "off", "2"):
        monkeypatch.setenv(LEGACY_ENV, value)
        assert legacy_swarm_enabled() is False
    monkeypatch.delenv(LEGACY_ENV, raising=False)
    assert legacy_swarm_enabled() is False

    for value in ("1", "true", "yes", "on"):
        monkeypatch.setenv(APPROVAL_ENV, value)
        assert swarm_auto_pr_approved() is True
    monkeypatch.delenv(APPROVAL_ENV, raising=False)
    assert swarm_auto_pr_approved() is False
    assert swarm_auto_pr_approved(explicit=True) is True


def test_constructor_requires_legacy_opt_in(monkeypatch):
    monkeypatch.delenv(LEGACY_ENV, raising=False)
    with pytest.raises(LegacySwarmDisabledError):
        AgentSwarm(llm_client=MockLLMClient())


# ── SwarmResult serialization ─────────────────────────────


def test_swarm_result_to_dict_and_json():
    result = SwarmResult(
        task="Add rate limiting",
        status="completed",
        agents_used=["PlannerAgent"],
        iterations=1,
        duration_seconds=1.23,
    )
    payload = result.to_dict()
    assert payload["task"] == "Add rate limiting"
    assert payload["status"] == "completed"
    assert payload["message_count"] == 0
    assert payload["errors"] == []
    assert "timestamp" in payload
    assert json.loads(result.to_json())["agents_used"] == ["PlannerAgent"]


# ── Message bus and status ──────────────────────────────────


def test_message_bus_and_status(swarm_env):
    swarm = AgentSwarm(llm_client=MockLLMClient())
    swarm._post_message(
        AgentMessage(
            sender="PlannerAgent",
            receiver="CoderAgent",
            message_type=MessageType.PLAN,
            content={"plan": "x"},
        )
    )
    swarm._post_message(
        AgentMessage(
            sender="CoderAgent",
            receiver="ReviewerAgent",
            message_type=MessageType.CODE,
            content={"code": "y"},
        )
    )
    assert [m.sender for m in swarm._get_messages_for("CoderAgent")] == ["PlannerAgent"]
    assert swarm._get_messages_for("Nobody") == []

    status = swarm.status()
    assert set(status["agents"]) == {
        "planner",
        "coder",
        "reviewer",
        "tester",
        "sre",
        "security",
        "janitor",
    }
    assert status["llm_provider"] == "mock"
    assert status["message_bus_size"] == 2


# ── solve chain ─────────────────────────────────────────────


def test_solve_happy_path_completed(swarm_env):
    """The single real end-to-end solve: plan, code, approve, test."""
    responses = [PLAN_JSON, CODE_JSON, APPROVE_JSON, TESTS_JSON]
    swarm = AgentSwarm(llm_client=MockLLMClient(responses=responses))
    result = asyncio.run(swarm.solve("Add a trivial thing"))

    assert result.status == "completed"
    assert result.errors == []
    assert result.agents_used == ["PlannerAgent", "CoderAgent", "ReviewerAgent", "TesterAgent"]
    assert result.iterations == 1
    assert result.plan is not None
    assert result.code is not None
    assert result.review is not None
    assert result.tests is not None
    assert len(swarm.message_bus) >= 2


def test_solve_planner_failure_returns_failed(swarm_env, monkeypatch):
    swarm = _stubbed_swarm(monkeypatch)
    monkeypatch.setattr(swarm.planner, "run", AsyncMock(side_effect=RuntimeError("llm down")))
    result = asyncio.run(swarm.solve("Anything"))

    assert result.status == "failed"
    assert any("PlannerAgent failed" in e for e in result.errors)
    assert result.agents_used == []


def test_solve_reviewer_reject_fails_without_tests(swarm_env, monkeypatch):
    swarm = _stubbed_swarm(monkeypatch, reviewer="reject")
    result = asyncio.run(swarm.solve("Add a thing"))

    assert result.status == "failed"
    assert any("rejected" in e for e in result.errors)
    assert "TesterAgent" not in result.agents_used
    assert result.tests is None
    assert swarm.tester.run.await_count == 0


def test_solve_feedback_loop_retries_then_approves(swarm_env, monkeypatch):
    swarm = _stubbed_swarm(monkeypatch)
    monkeypatch.setattr(
        swarm.reviewer,
        "run",
        AsyncMock(side_effect=[_review_envelope("request_changes"), _review_envelope("approve")]),
    )
    result = asyncio.run(swarm.solve("Add a thing"))

    assert result.status == "completed"
    assert result.iterations == 2
    assert swarm.coder.run.await_count == 2
    assert any(m.message_type == MessageType.FEEDBACK for m in swarm.message_bus)


def test_solve_max_iterations_records_error(swarm_env, monkeypatch):
    swarm = _stubbed_swarm(monkeypatch, reviewer="request_changes")
    swarm.max_iterations = 1
    result = asyncio.run(swarm.solve("Add a thing"))

    assert result.status == "failed"
    assert any("Max feedback iterations (1) reached" in e for e in result.errors)
    assert result.iterations == 1


def test_solve_coder_failure_mid_loop(swarm_env, monkeypatch):
    swarm = _stubbed_swarm(monkeypatch)
    monkeypatch.setattr(
        swarm.reviewer,
        "run",
        AsyncMock(side_effect=[_review_envelope("request_changes"), _review_envelope("approve")]),
    )
    monkeypatch.setattr(
        swarm.coder,
        "run",
        AsyncMock(side_effect=[_CODE_ENVELOPE, RuntimeError("disk full")]),
    )
    result = asyncio.run(swarm.solve("Add a thing"))

    assert result.status == "failed"
    assert any("CoderAgent failed (iteration 2)" in e for e in result.errors)
    assert result.tests is None


def test_solve_tester_failure_marks_failed(swarm_env, monkeypatch):
    swarm = _stubbed_swarm(monkeypatch)
    monkeypatch.setattr(swarm.tester, "run", AsyncMock(side_effect=RuntimeError("no pytest")))
    result = asyncio.run(swarm.solve("Add a thing"))

    assert result.status == "failed"
    assert any("TesterAgent failed" in e for e in result.errors)


def test_solve_completed_with_warnings_on_critical_issues(swarm_env, monkeypatch):
    critical = [{"severity": "critical", "description": "tenant id not scoped"}]
    swarm = _stubbed_swarm(monkeypatch, reviewer=_review_envelope("approve", critical_issues=critical))
    result = asyncio.run(swarm.solve("Add a thing"))

    assert result.status == "completed_with_warnings"
    assert result.errors == []


# ── sweep and troubleshoot ──────────────────────────────────


def test_sweep_runs_batch(swarm_env, monkeypatch):
    swarm = _stubbed_swarm(monkeypatch)
    results = asyncio.run(swarm.sweep(["task a", "task b"], concurrency=2))

    assert len(results) == 2
    assert all(r.status == "completed" for r in results)
    assert {r.task for r in results} == {"task a", "task b"}
    assert swarm.tester.run.await_count == 2


def test_troubleshoot_runs_sre_then_solve(swarm_env, monkeypatch):
    swarm = _stubbed_swarm(monkeypatch)
    result = asyncio.run(swarm.troubleshoot("FAILED test_x (flaky)"))

    assert result.status == "completed"
    assert result.task.startswith("Fix CI failure:")
    assert "PlannerAgent" in result.agents_used
    assert swarm.sre.run.await_count == 1


def test_troubleshoot_sre_failure_returns_failed(swarm_env, monkeypatch):
    swarm = _stubbed_swarm(monkeypatch)
    monkeypatch.setattr(swarm.sre, "run", AsyncMock(side_effect=RuntimeError("sre down")))
    result = asyncio.run(swarm.troubleshoot("FAILED everything"))

    assert result.status == "failed"
    assert any("CIResilienceAgent failed" in e for e in result.errors)
