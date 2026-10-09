"""Focused unit tests for regengine.swarm.agents.

Covers the main public behavior of every agent class (init defaults,
think/act/reflect) plus path-safety edge cases. All LLM calls use
MockLLMClient; no network or external services.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from regengine.swarm.agents import (
    CIResilienceAgent,
    CoderAgent,
    JanitorAgent,
    PlannerAgent,
    ReviewerAgent,
    SecurityAgent,
    TesterAgent,
    is_path_within_base,
)
from regengine.swarm.llm import MockLLMClient


def _memory(tmp_path: Path) -> Path:
    mem = tmp_path / "mem"
    mem.mkdir(exist_ok=True)
    return mem


# ── is_path_within_base ─────────────────────────────────────


def test_is_path_within_base_accepts_inside_and_base_itself() -> None:
    base = Path("/repo")
    assert is_path_within_base(base, base / "pkg" / "ok.py")
    assert is_path_within_base(base, base)


def test_is_path_within_base_rejects_sibling_sharing_text_prefix() -> None:
    assert not is_path_within_base(Path("/repo"), Path("/repo-backup/evil.py"))


# ── Agent init defaults ─────────────────────────────────────


@pytest.mark.parametrize(
    ("cls", "name", "role"),
    [
        (PlannerAgent, "PlannerAgent", "planner"),
        (CoderAgent, "CoderAgent", "coder"),
        (ReviewerAgent, "ReviewerAgent", "reviewer"),
        (TesterAgent, "TesterAgent", "tester"),
        (CIResilienceAgent, "CIResilienceAgent", "sre"),
        (SecurityAgent, "SecurityAgent", "security"),
        (JanitorAgent, "JanitorAgent", "janitor"),
    ],
)
def test_agent_init_defaults_name_and_role(tmp_path, cls, name, role) -> None:
    agent = cls(llm_client=MockLLMClient(), memory_dir=_memory(tmp_path))
    assert agent.name == name
    assert agent.role == role
    assert agent.system_prompt


# ── PlannerAgent ────────────────────────────────────────────


async def test_planner_think_returns_llm_json(tmp_path: Path) -> None:
    plan = {"steps": [{"id": 1, "action": "add", "files": ["a.py"]}], "risks": []}
    agent = PlannerAgent(
        llm_client=MockLLMClient(responses=[json.dumps(plan)]),
        memory_dir=_memory(tmp_path),
    )
    assert await agent.think("Add a thing") == plan


async def test_planner_act_summarizes_steps(tmp_path: Path) -> None:
    agent = PlannerAgent(llm_client=MockLLMClient(), memory_dir=_memory(tmp_path))
    plan = {
        "steps": [
            {"id": 1, "action": "a", "files": ["a.py", "b.py"]},
            {"id": 2, "action": "b", "files": ["b.py"]},
        ],
        "estimated_complexity": "low",
    }
    result = await agent.act(plan)
    assert result["step_count"] == 2
    assert sorted(result["files_targeted"]) == ["a.py", "b.py"]
    assert result["estimated_complexity"] == "low"


async def test_planner_act_empty_plan_is_zero_steps(tmp_path: Path) -> None:
    agent = PlannerAgent(llm_client=MockLLMClient(), memory_dir=_memory(tmp_path))
    result = await agent.act({})
    assert result["step_count"] == 0
    assert result["files_targeted"] == []


async def test_planner_reflect_passes_good_plan(tmp_path: Path) -> None:
    agent = PlannerAgent(llm_client=MockLLMClient(), memory_dir=_memory(tmp_path))
    plan = {
        "steps": [
            {"id": 1, "action": "a", "files": ["a.py"], "acceptance_criteria": "done"},
        ]
    }
    assessment = await agent.reflect({"plan": plan})
    assert assessment["status"] == "pass"


async def test_planner_reflect_flags_empty_and_incomplete_steps(tmp_path: Path) -> None:
    agent = PlannerAgent(llm_client=MockLLMClient(), memory_dir=_memory(tmp_path))
    assert (await agent.reflect({"plan": {}}))["status"] == "needs_improvement"
    assessment = await agent.reflect({"plan": {"steps": [{"id": 1, "action": "a"}]}})
    assert assessment["status"] == "needs_improvement"
    assert any("acceptance criteria" in i for i in assessment["issues"])
    assert any("target files" in i for i in assessment["issues"])


# ── CoderAgent ──────────────────────────────────────────────


async def test_coder_act_writes_file_inside_workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workdir = tmp_path / "repo"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    agent = CoderAgent(llm_client=MockLLMClient(), memory_dir=_memory(tmp_path))

    result = await agent.act(
        {
            "files": [{"path": "pkg/ok.py", "action": "create", "content": "x = 1\n"}],
            "summary": "add ok",
        }
    )

    assert result["file_count"] == 1
    assert (workdir / "pkg" / "ok.py").read_text() == "x = 1\n"
    assert result["summary"] == "add ok"


@pytest.mark.parametrize("evil", ["../evil.py", "/abs/evil.py", "..\\evil.py"])
async def test_coder_act_blocks_path_traversal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, evil: str) -> None:
    workdir = tmp_path / "repo"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    agent = CoderAgent(llm_client=MockLLMClient(), memory_dir=_memory(tmp_path))

    result = await agent.act({"files": [{"path": evil, "action": "create", "content": "pwned\n"}]})

    assert result["file_count"] == 0
    assert not (tmp_path / "evil.py").exists()


async def test_coder_reflect_flags_print_credential_and_empty(tmp_path: Path) -> None:
    agent = CoderAgent(llm_client=MockLLMClient(), memory_dir=_memory(tmp_path))
    assessment = await agent.reflect(
        {
            "files_written": [
                {"path": "a.py", "content": "print('hi')\n"},
                {"path": "b.py", "content": "password = 'x'\n"},
                {"path": "c.py", "content": "  \n"},
            ]
        }
    )
    assert assessment["status"] == "needs_improvement"
    assert len(assessment["issues"]) == 3


async def test_coder_reflect_passes_clean_file(tmp_path: Path) -> None:
    agent = CoderAgent(llm_client=MockLLMClient(), memory_dir=_memory(tmp_path))
    assessment = await agent.reflect({"files_written": [{"path": "a.py", "content": "import structlog\n"}]})
    assert assessment["status"] == "pass"


@pytest.mark.xfail(strict=True, reason="CoderAgent.reflect reads content key that CoderAgent.act never writes")
async def test_coder_reflect_passes_on_own_act_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workdir = tmp_path / "repo"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    agent = CoderAgent(llm_client=MockLLMClient(), memory_dir=_memory(tmp_path))
    result = await agent.act({"files": [{"path": "pkg/ok.py", "action": "create", "content": "x = 1\n"}]})
    assert result["file_count"] == 1
    assessment = await agent.reflect(result)
    assert assessment["status"] == "pass"


# ── ReviewerAgent ───────────────────────────────────────────


async def test_reviewer_act_summarizes_review(tmp_path: Path) -> None:
    agent = ReviewerAgent(llm_client=MockLLMClient(), memory_dir=_memory(tmp_path))
    review = {
        "verdict": "request_changes",
        "score": 0.4,
        "issues": [{"severity": "critical", "file": "a.py"}],
    }
    result = await agent.act(review)
    assert result["verdict"] == "request_changes"
    assert result["score"] == 0.4
    assert result["issue_count"] == 1
    assert len(result["critical_issues"]) == 1


async def test_reviewer_reflect_flags_approve_with_critical_issues(tmp_path: Path) -> None:
    agent = ReviewerAgent(llm_client=MockLLMClient(), memory_dir=_memory(tmp_path))
    assessment = await agent.reflect(
        {
            "review": {"verdict": "approve"},
            "verdict": "approve",
            "critical_issues": [{"severity": "critical"}],
        }
    )
    assert assessment["status"] == "needs_improvement"


async def test_reviewer_reflect_flags_empty_review(tmp_path: Path) -> None:
    agent = ReviewerAgent(llm_client=MockLLMClient(), memory_dir=_memory(tmp_path))
    assessment = await agent.reflect({"review": {}, "verdict": "unknown"})
    assert assessment["status"] == "needs_improvement"


# ── TesterAgent ─────────────────────────────────────────────


async def test_tester_act_counts_tests(tmp_path: Path) -> None:
    agent = TesterAgent(llm_client=MockLLMClient(), memory_dir=_memory(tmp_path))
    result = await agent.act(
        {
            "test_files": [
                {"path": "test_a.py", "content": "...", "test_count": 2},
                {"path": "test_b.py", "content": "...", "test_count": 3},
            ],
            "scenarios_covered": ["happy_path", "edge_case", "error_handling"],
            "coverage_estimate": "high",
        }
    )
    assert result["test_file_count"] == 2
    assert result["total_tests"] == 5


async def test_tester_reflect_requires_tests_and_scenarios(tmp_path: Path) -> None:
    agent = TesterAgent(llm_client=MockLLMClient(), memory_dir=_memory(tmp_path))
    assert (await agent.reflect({"total_tests": 0}))["status"] == "needs_improvement"
    few = await agent.reflect({"total_tests": 2, "scenarios_covered": ["happy_path", "edge_case", "error_handling"]})
    assert few["status"] == "needs_improvement"
    missing = await agent.reflect({"total_tests": 5, "scenarios_covered": ["happy_path"]})
    assert missing["status"] == "needs_improvement"
    full = await agent.reflect({"total_tests": 4, "scenarios_covered": ["happy_path", "edge_case", "error_handling"]})
    assert full["status"] == "pass"


# ── CIResilienceAgent ───────────────────────────────────────


async def test_ci_resilience_act_extracts_remediation(tmp_path: Path) -> None:
    agent = CIResilienceAgent(llm_client=MockLLMClient(), memory_dir=_memory(tmp_path))
    result = await agent.act(
        {
            "analysis": {"root_cause": "missing env var", "category": "env"},
            "remediation": {"immediate_fix": "set VAR", "files_to_modify": ["ci.yml"]},
            "confidence": 0.9,
        }
    )
    assert result["root_cause"] == "missing env var"
    assert result["category"] == "env"
    assert result["files_to_modify"] == ["ci.yml"]
    assert result["confidence"] == 0.9


async def test_ci_resilience_reflect_flags_missing_cause_and_low_confidence(
    tmp_path: Path,
) -> None:
    agent = CIResilienceAgent(llm_client=MockLLMClient(), memory_dir=_memory(tmp_path))
    assert (await agent.reflect({"confidence": 0.9}))["status"] == "needs_improvement"
    low = await agent.reflect({"root_cause": "x", "confidence": 0.1})
    assert low["status"] == "needs_improvement"
    good = await agent.reflect({"root_cause": "x", "confidence": 0.9})
    assert good["status"] == "pass"


# ── SecurityAgent ───────────────────────────────────────────


async def test_security_act_builds_scorecard(tmp_path: Path) -> None:
    agent = SecurityAgent(llm_client=MockLLMClient(), memory_dir=_memory(tmp_path))
    result = await agent.act(
        {
            "vulnerabilities": [{"issue": "sqli", "severity": "high"}],
            "verdict": "fail",
            "score": 0.2,
            "summary": "bad",
        }
    )
    assert result["vulnerability_count"] == 1
    assert result["verdict"] == "fail"


async def test_security_reflect_flags_pass_with_vulnerabilities(tmp_path: Path) -> None:
    agent = SecurityAgent(llm_client=MockLLMClient(), memory_dir=_memory(tmp_path))
    bad = await agent.reflect({"vulnerability_count": 1, "verdict": "pass", "vulnerabilities": [{"severity": "high"}]})
    assert bad["status"] == "needs_improvement"
    assert bad["critical_vulnerabilities"] == 1
    good = await agent.reflect({"vulnerability_count": 0, "verdict": "pass", "vulnerabilities": []})
    assert good["status"] == "pass"


# ── JanitorAgent ────────────────────────────────────────────


async def test_janitor_act_returns_decision_without_merging(tmp_path: Path) -> None:
    agent = JanitorAgent(llm_client=MockLLMClient(), memory_dir=_memory(tmp_path))
    result = await agent.act({"decision": "merge", "reasoning": "tests green", "cleanup_actions": ["delete branch"]})
    assert result["decision"] == "merge"
    assert result["merged"] is False


async def test_janitor_reflect_requires_tests_in_merge_reasoning(tmp_path: Path) -> None:
    agent = JanitorAgent(llm_client=MockLLMClient(), memory_dir=_memory(tmp_path))
    bad = await agent.reflect({"decision": "merge", "reasoning": "looks good"})
    assert bad["status"] == "needs_improvement"
    good = await agent.reflect({"decision": "merge", "reasoning": "all tests green"})
    assert good["status"] == "pass"
    assert (await agent.reflect({"decision": "hold", "reasoning": ""}))["status"] == "pass"
