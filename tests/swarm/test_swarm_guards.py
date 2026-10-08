"""Regression tests for swarm file-write guard and auto-merge guards."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from regengine.swarm.agents import CoderAgent, is_path_within_base
from regengine.swarm.coordinator import AgentSwarm
from regengine.swarm.github_integration import GitHubClient
from regengine.swarm.llm import MockLLMClient


def _coder(tmp_path: Path) -> CoderAgent:
    return CoderAgent(llm_client=MockLLMClient(), memory_dir=tmp_path / "mem")


# ── File-write guard ────────────────────────────────────────


def test_is_path_within_base_rejects_sibling_prefix() -> None:
    base = Path("/repo")
    sibling = Path("/repo-backup/evil.py")

    assert not is_path_within_base(base, sibling)
    assert is_path_within_base(base, base / "ok.py")
    assert is_path_within_base(base, base)


def test_coder_act_blocks_sibling_prefix_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A symlink inside the workdir pointing at a sibling folder that shares
    a text prefix must not let the coder write outside the workdir."""
    workdir = tmp_path / "repo"
    workdir.mkdir()
    outside = tmp_path / "repo-backup"
    outside.mkdir()
    os.symlink(outside, workdir / "sibling-link", target_is_directory=True)

    monkeypatch.chdir(workdir)
    agent = _coder(tmp_path)
    result = asyncio.run(
        agent.act(
            {
                "files": [
                    {
                        "path": "sibling-link/evil.py",
                        "action": "create",
                        "content": "pwned\n",
                    }
                ]
            }
        )
    )

    assert result["file_count"] == 0
    assert not (outside / "evil.py").exists()


def test_coder_act_still_writes_inside_workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workdir = tmp_path / "repo"
    workdir.mkdir()
    monkeypatch.chdir(workdir)

    agent = _coder(tmp_path)
    result = asyncio.run(
        agent.act(
            {
                "files": [
                    {"path": "pkg/ok.py", "action": "create", "content": "x = 1\n"},
                ]
            }
        )
    )

    assert result["file_count"] == 1
    assert (workdir / "pkg" / "ok.py").read_text() == "x = 1\n"


# ── merge_pr guards ─────────────────────────────────────────


class _FakePR:
    def __init__(self, mergeable: bool = True) -> None:
        self.mergeable = mergeable
        self.merge_called = False
        self.head = SimpleNamespace(sha="abc123")

    def merge(self, commit_message: str = ""):
        self.merge_called = True
        return SimpleNamespace(merged=True)


class _FakeRepo:
    def __init__(self, pr: _FakePR, state: str = "success", raise_checks: bool = False) -> None:
        self._pr = pr
        self._state = state
        self._raise_checks = raise_checks

    def get_pull(self, number: int) -> _FakePR:
        return self._pr

    def get_combined_status(self, ref: str):
        if self._raise_checks:
            raise RuntimeError("checks unavailable")
        return SimpleNamespace(state=self._state)


def _client(pr: _FakePR, **kwargs) -> GitHubClient:
    client = GitHubClient(repo_name="owner/repo", token="test-token")
    client._repo = _FakeRepo(pr, **kwargs)
    return client


def test_merge_pr_blocked_without_human_approval() -> None:
    pr = _FakePR(mergeable=True)

    assert _client(pr).merge_pr(1) is False
    assert pr.merge_called is False


def test_merge_pr_blocked_when_checks_not_green() -> None:
    for state in ("failure", "pending", "error"):
        pr = _FakePR(mergeable=True)

        assert _client(pr, state=state).merge_pr(1, human_approved=True) is False
        assert pr.merge_called is False


def test_merge_pr_blocked_when_checks_unavailable() -> None:
    pr = _FakePR(mergeable=True)

    assert _client(pr, raise_checks=True).merge_pr(1, human_approved=True) is False
    assert pr.merge_called is False


def test_merge_pr_blocked_when_not_mergeable() -> None:
    pr = _FakePR(mergeable=False)

    assert _client(pr).merge_pr(1, human_approved=True) is False
    assert pr.merge_called is False


def test_merge_pr_merges_when_approved_and_green() -> None:
    pr = _FakePR(mergeable=True)

    assert _client(pr).merge_pr(1, human_approved=True) is True
    assert pr.merge_called is True


# ── Coordinator auto-PR approval ────────────────────────────


def _swarm() -> AgentSwarm:
    return AgentSwarm(llm_client=MockLLMClient())


def test_auto_fix_pr_blocked_without_approval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGENGINE_ENABLE_LEGACY_SWARM", "1")
    monkeypatch.delenv("REGENGINE_SWARM_AUTO_PR_APPROVED", raising=False)
    monkeypatch.chdir(tmp_path)
    calls: list = []
    monkeypatch.setattr("subprocess.run", lambda *a, **k: calls.append(a) or SimpleNamespace(returncode=0))
    import regengine.swarm.github_integration as gh_mod

    monkeypatch.setattr(gh_mod, "GitHubClient", lambda *a, **k: calls.append("github") or None)

    swarm = _swarm()
    result = asyncio.run(swarm._create_auto_fix_pr("task", {"files_written": []}))

    assert result is None
    assert calls == []


def test_auto_fix_pr_runs_with_explicit_approval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGENGINE_ENABLE_LEGACY_SWARM", "1")
    monkeypatch.delenv("REGENGINE_SWARM_AUTO_PR_APPROVED", raising=False)
    monkeypatch.chdir(tmp_path)
    git_calls: list = []
    pr_calls: list = []
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: git_calls.append(a[0]) or SimpleNamespace(returncode=0),
    )

    class _FakeGH:
        def create_pr(self, **kwargs):
            pr_calls.append(kwargs)
            return {"number": 1}

    import regengine.swarm.github_integration as gh_mod

    monkeypatch.setattr(gh_mod, "GitHubClient", lambda *a, **k: _FakeGH())

    swarm = _swarm()
    asyncio.run(swarm._create_auto_fix_pr("task", {"files_written": []}, human_approved=True))

    assert any("push" in cmd for cmd in git_calls)
    assert len(pr_calls) == 1


def test_solve_does_not_push_or_open_pr_without_approval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Full solve() with CI auto-fix on but no human approval must not push or open a PR."""
    monkeypatch.setenv("REGENGINE_ENABLE_LEGACY_SWARM", "1")
    monkeypatch.setenv("REGENGINE_CI_AUTO_FIX", "true")
    monkeypatch.delenv("REGENGINE_SWARM_AUTO_PR_APPROVED", raising=False)
    monkeypatch.chdir(tmp_path)
    calls: list = []
    monkeypatch.setattr("subprocess.run", lambda *a, **k: calls.append(a) or SimpleNamespace(returncode=0))
    import regengine.swarm.github_integration as gh_mod

    monkeypatch.setattr(gh_mod, "GitHubClient", lambda *a, **k: calls.append("github") or None)

    responses = [
        (
            '{"steps": [{"id": 1, "action": "Implement", "files": ["app.py"], '
            '"details": "Write code", "acceptance_criteria": "Done"}], '
            '"risks": [], "estimated_complexity": "low"}'
        ),
        (
            '{"files": [{"path": "app.py", "action": "create", '
            '"content": "x = 1\\n", "language": "python"}], '
            '"summary": "did it", "dependencies_added": []}'
        ),
        '{"verdict": "approve", "score": 0.9, "issues": [], "strengths": ["ok"], "summary": "good"}',
        (
            '{"test_files": [], "scenarios_covered": ["happy_path", "edge_case", "error_handling"], '
            '"coverage_estimate": "80%", "summary": "tests"}'
        ),
    ]
    swarm = AgentSwarm(llm_client=MockLLMClient(responses=responses))
    result = asyncio.run(swarm.solve("Add a trivial thing"))

    assert result.status == "completed"
    assert calls == []
