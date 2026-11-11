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
# Faithful minimal PyGithub fakes.
#
# PyGithub is NOT installed in the shared venv (verified: `import github`
# raises ModuleNotFoundError; do not install). These fakes mirror the
# official PyGithub 2.10.0 surface verified via documentation:
# - Repository.get_pull(number) / Repository.get_commit(sha)
# - Commit.get_combined_status() (no args) -> .state + .statuses
# - Commit.get_check_runs(check_name, status, filter) -> iterable of runs
#   with .status + .conclusion
# - PullRequest.merge(..., sha=...) accepts the head SHA for an atomic guard
# Refs:
# https://pygithub.readthedocs.io/en/stable/github_objects/Commit.html
# https://pygithub.readthedocs.io/en/stable/github_objects/PullRequest.html
# Live library integration unavailable; see
# test_pygithub_signatures_when_available (skips when `github` missing).
#
# Repository.get_combined_status does NOT exist on real Repository and is
# intentionally absent here; any use would fail loudly instead of passing
# against a fake unsupported API.


class _FakeCheckRun:
    """Minimal stand-in for github.CheckRun.CheckRun (status + conclusion)."""

    def __init__(self, status: str = "completed", conclusion: str | None = "success") -> None:
        self.status = status
        self.conclusion = conclusion


class _FakeCombinedStatus:
    """Minimal stand-in for github.CombinedStatus.CombinedStatus."""

    def __init__(self, state: str, statuses: list) -> None:
        self.state = state
        self.statuses = statuses


class _FakeCommit:
    """Minimal stand-in for github.Commit.Commit.

    Real signature: get_check_runs(check_name=NotSet, status=NotSet,
    filter=NotSet). Production calls it with no args; the fake keeps the
    same parameter names with None defaults (NotSet unavailable without
    PyGithub installed).
    """

    def __init__(
        self,
        combined_state: str = "success",
        statuses: list | None = None,
        check_runs: list | None = None,
        raise_combined: bool = False,
        raise_checks: bool = False,
    ) -> None:
        if statuses is None:
            statuses = [SimpleNamespace(state=combined_state)]
        if check_runs is None:
            check_runs = []
        self._combined_state = combined_state
        self._statuses = statuses
        self._check_runs = check_runs
        self._raise_combined = raise_combined
        self._raise_checks = raise_checks

    def get_combined_status(self):
        if self._raise_combined:
            raise RuntimeError("combined status unavailable")
        return _FakeCombinedStatus(state=self._combined_state, statuses=self._statuses)

    def get_check_runs(self, check_name=None, status=None, filter=None):
        if self._raise_checks:
            raise RuntimeError("check runs unavailable")
        return list(self._check_runs)


class _FakePR:
    """Minimal stand-in for github.PullRequest.PullRequest (head/sha + merge)."""

    def __init__(
        self,
        head_sha: str = "abc123",
        mergeable: bool = True,
        merge_result: bool = True,
        enforce_atomic: bool = False,
    ) -> None:
        self.head = SimpleNamespace(sha=head_sha)
        self.mergeable = mergeable
        self._merge_result = merge_result
        self._enforce_atomic = enforce_atomic
        self.merge_called = False
        self.merge_kwargs = None

    def merge(self, commit_message: str = "", sha=None):
        self.merge_called = True
        self.merge_kwargs = {"commit_message": commit_message, "sha": sha}
        if self._enforce_atomic and sha != self.head.sha:
            return SimpleNamespace(merged=False)
        return SimpleNamespace(merged=self._merge_result)


class _FakeRepo:
    """Minimal stand-in for github.Repository.Repository.

    Intentionally has no get_combined_status (nonexistent on real Repository).
    """

    def __init__(
        self,
        pr: _FakePR,
        commit=None,
        raise_pull: bool = False,
        raise_commit: bool = False,
        commit_side_effect=None,
    ) -> None:
        self._pr = pr
        self._commit = commit
        self._raise_pull = raise_pull
        self._raise_commit = raise_commit
        self._commit_side_effect = commit_side_effect
        self.get_pull_calls: list = []
        self.get_commit_calls: list = []

    def get_pull(self, number: int) -> _FakePR:
        self.get_pull_calls.append(number)
        if self._raise_pull:
            raise RuntimeError("pull unavailable")
        return self._pr

    def get_commit(self, sha: str):
        self.get_commit_calls.append(sha)
        if self._commit_side_effect is not None:
            self._commit_side_effect()
        if self._raise_commit:
            raise RuntimeError("commit unavailable")
        return self._commit


def _client(pr: _FakePR, commit=None, **repo_kwargs) -> GitHubClient:
    client = GitHubClient(repo_name="owner/repo", token="test-token")
    if commit is None:
        commit = _FakeCommit(combined_state="success")
    client._repo = _FakeRepo(pr, commit, **repo_kwargs)
    return client


def test_merge_pr_blocked_without_human_approval() -> None:
    pr = _FakePR(mergeable=True)
    client = _client(pr)

    assert client.merge_pr(1) is False
    assert pr.merge_called is False
    # No network on the no-approval path: no PR/commit reads.
    assert client._repo.get_pull_calls == []
    assert client._repo.get_commit_calls == []


def test_merge_pr_blocked_when_checks_not_green() -> None:
    for state in ("failure", "pending", "error"):
        pr = _FakePR(mergeable=True)
        commit = _FakeCommit(combined_state=state)
        client = _client(pr, commit)

        assert client.merge_pr(1, human_approved=True) is False
        assert pr.merge_called is False
        assert client._repo.get_commit_calls == ["abc123"]


def test_merge_pr_blocked_when_checks_unavailable() -> None:
    pr = _FakePR(mergeable=True)
    client = _client(pr, raise_commit=True)
    assert client.merge_pr(1, human_approved=True) is False
    assert pr.merge_called is False

    pr = _FakePR(mergeable=True)
    client = _client(pr, _FakeCommit(raise_combined=True))
    assert client.merge_pr(1, human_approved=True) is False
    assert pr.merge_called is False

    pr = _FakePR(mergeable=True)
    client = _client(pr, _FakeCommit(combined_state="success", raise_checks=True))
    assert client.merge_pr(1, human_approved=True) is False
    assert pr.merge_called is False

    pr = _FakePR(mergeable=True)
    client = _client(pr, raise_pull=True)
    assert client.merge_pr(1, human_approved=True) is False
    assert pr.merge_called is False


def test_merge_pr_blocked_when_not_mergeable() -> None:
    pr = _FakePR(mergeable=False)
    commit = _FakeCommit(combined_state="success", check_runs=[_FakeCheckRun()])
    client = _client(pr, commit)

    assert client.merge_pr(1, human_approved=True) is False
    assert pr.merge_called is False


def test_merge_pr_merges_when_approved_and_green() -> None:
    pr = _FakePR(mergeable=True, head_sha="abc123")
    commit = _FakeCommit(
        combined_state="success",
        statuses=[SimpleNamespace(state="success")],
        check_runs=[_FakeCheckRun(status="completed", conclusion="success")],
    )
    client = _client(pr, commit)

    assert client.merge_pr(1, human_approved=True) is True
    assert pr.merge_called is True
    assert pr.merge_kwargs["sha"] == "abc123"
    assert client._repo.get_commit_calls == ["abc123"]
    assert client._repo.get_pull_calls == [1]


def test_merge_pr_status_only_success() -> None:
    pr = _FakePR(head_sha="status-sha")
    commit = _FakeCommit(
        combined_state="success",
        statuses=[SimpleNamespace(state="success")],
        check_runs=[],
    )
    client = _client(pr, commit)

    assert client.merge_pr(1, human_approved=True) is True
    assert pr.merge_kwargs["sha"] == "status-sha"


def test_merge_pr_check_only_success() -> None:
    # GitHub represents empty combined as pending; with no statuses, green
    # check runs alone are success.
    pr = _FakePR(head_sha="checks-sha")
    commit = _FakeCommit(
        combined_state="pending",
        statuses=[],
        check_runs=[
            _FakeCheckRun(status="completed", conclusion="success"),
            _FakeCheckRun(status="completed", conclusion="success"),
        ],
    )
    client = _client(pr, commit)

    assert client.merge_pr(1, human_approved=True) is True
    assert pr.merge_kwargs["sha"] == "checks-sha"


@pytest.mark.parametrize(
    "combined",
    [None, SimpleNamespace(state="pending"), SimpleNamespace(state="pending", statuses=None)],
)
def test_missing_legacy_response_does_not_allow_check_only_merge(monkeypatch, combined):
    pr = _FakePR()
    commit = _FakeCommit(check_runs=[_FakeCheckRun()])
    monkeypatch.setattr(commit, "get_combined_status", lambda: combined)

    assert _client(pr, commit).merge_pr(1, human_approved=True) is False
    assert pr.merge_called is False


def test_merge_pr_blocked_when_check_runs_pending_despite_success_statuses() -> None:
    for run_status in ("queued", "in_progress", "requested", "waiting"):
        pr = _FakePR(mergeable=True)
        commit = _FakeCommit(
            combined_state="success",
            statuses=[SimpleNamespace(state="success")],
            check_runs=[_FakeCheckRun(status=run_status, conclusion=None)],
        )
        client = _client(pr, commit)

        assert client.merge_pr(1, human_approved=True) is False
        assert pr.merge_called is False

    pr = _FakePR(mergeable=True)
    commit = _FakeCommit(
        combined_state="success",
        statuses=[SimpleNamespace(state="success")],
        check_runs=[_FakeCheckRun(status="completed", conclusion=None)],
    )
    client = _client(pr, commit)

    assert client.merge_pr(1, human_approved=True) is False
    assert pr.merge_called is False


def test_merge_pr_blocked_when_check_runs_failing_despite_success_statuses() -> None:
    for conclusion in ("failure", "cancelled", "timed_out", "action_required", "stale"):
        pr = _FakePR(mergeable=True)
        commit = _FakeCommit(
            combined_state="success",
            statuses=[SimpleNamespace(state="success")],
            check_runs=[_FakeCheckRun(status="completed", conclusion=conclusion)],
        )
        client = _client(pr, commit)

        assert client.merge_pr(1, human_approved=True) is False
        assert pr.merge_called is False


def test_merge_pr_treats_neutral_and_skipped_as_green() -> None:
    """GitHub counts skipped and neutral conclusions as green for merging.

    This repo skips workflow jobs on pull requests via conditionals, so a
    normal green PR carries skipped check runs. Treating them as failure
    blocked every janitor auto-merge even with approval and green checks.
    """
    for conclusion in ("neutral", "skipped"):
        pr_status = _FakePR()
        commit_status = _FakeCommit(
            combined_state="success",
            statuses=[SimpleNamespace(state="success")],
            check_runs=[_FakeCheckRun(status="completed", conclusion=conclusion)],
        )
        assert _client(pr_status, commit_status).get_pr_checks_status(1) == "success"

        pr = _FakePR(mergeable=True)
        commit = _FakeCommit(
            combined_state="success",
            statuses=[SimpleNamespace(state="success")],
            check_runs=[_FakeCheckRun(status="completed", conclusion=conclusion)],
        )
        client = _client(pr, commit)

        assert client.merge_pr(1, human_approved=True) is True
        assert pr.merge_called is True


def test_merge_pr_blocked_when_no_checks() -> None:
    pr = _FakePR()
    commit = _FakeCommit(combined_state="pending", statuses=[], check_runs=[])
    assert _client(pr, commit).get_pr_checks_status(1) == "pending"

    pr = _FakePR(mergeable=True)
    commit = _FakeCommit(combined_state="pending", statuses=[], check_runs=[])
    client = _client(pr, commit)

    assert client.merge_pr(1, human_approved=True) is False
    assert pr.merge_called is False


def test_merge_pr_passes_exact_checked_sha() -> None:
    pr = _FakePR(head_sha="deadbeef", mergeable=True)
    commit = _FakeCommit(combined_state="success", check_runs=[_FakeCheckRun()])
    client = _client(pr, commit)

    assert client.merge_pr(1, human_approved=True) is True
    assert client._repo.get_pull_calls == [1]
    assert client._repo.get_commit_calls == ["deadbeef"]
    assert pr.merge_kwargs is not None
    assert pr.merge_kwargs["sha"] == "deadbeef"


def test_merge_pr_concurrent_head_change_rejected() -> None:
    pr = _FakePR(head_sha="sha-old", mergeable=True, enforce_atomic=True)
    commit = _FakeCommit(combined_state="success", check_runs=[_FakeCheckRun()])

    def advance_head() -> None:
        pr.head.sha = "sha-new"

    client = _client(pr, commit, commit_side_effect=advance_head)

    assert client.merge_pr(1, human_approved=True) is False
    assert pr.merge_called is True
    assert pr.merge_kwargs["sha"] == "sha-old"
    assert client._repo.get_commit_calls == ["sha-old"]


def test_merge_pr_disable_checks_bypasses_gate_but_uses_atomic_sha() -> None:
    pr = _FakePR(head_sha="bypass-sha", mergeable=True)
    commit = _FakeCommit(combined_state="failure")
    client = _client(pr, commit)

    assert client.merge_pr(1, human_approved=True, require_green_checks=False) is True
    assert pr.merge_called is True
    assert pr.merge_kwargs["sha"] == "bypass-sha"
    assert client._repo.get_commit_calls == []
    assert client._repo.get_pull_calls == [1]


def test_get_pr_checks_status_uses_commit_api() -> None:
    pr = _FakePR(head_sha="commit-sha")
    commit = _FakeCommit(combined_state="success", check_runs=[_FakeCheckRun()])
    client = _client(pr, commit)

    assert client.get_pr_checks_status(1) == "success"
    assert client._repo.get_pull_calls == [1]
    assert client._repo.get_commit_calls == ["commit-sha"]


def test_get_pr_checks_status_propagates_api_errors() -> None:
    pr = _FakePR()
    with pytest.raises(RuntimeError):
        _client(pr, raise_commit=True).get_pr_checks_status(1)

    pr = _FakePR()
    with pytest.raises(RuntimeError):
        _client(pr, _FakeCommit(raise_combined=True)).get_pr_checks_status(1)

    pr = _FakePR()
    with pytest.raises(RuntimeError):
        _client(pr, _FakeCommit(raise_checks=True)).get_pr_checks_status(1)


def test_fake_repo_has_no_combined_status_method() -> None:
    """Guards against reintroducing the nonexistent Repository.get_combined_status."""
    assert not hasattr(_FakeRepo, "get_combined_status")
    pr = _FakePR()
    client = _client(pr)
    assert not hasattr(client._repo, "get_combined_status")


def test_pygithub_signatures_when_available() -> None:
    """When PyGithub is installed, verify our usage matches its real surface.

    Skips (documents unavailable) in the shared venv, which lacks `github`.
    """
    try:
        import inspect

        from github.Commit import Commit
        from github.PullRequest import PullRequest
        from github.Repository import Repository
    except ImportError:
        pytest.skip("PyGithub not installed; fakes verified against 2.10.0 docs (see header)")
    assert hasattr(Repository, "get_commit")
    assert hasattr(Repository, "get_pull")
    assert not hasattr(Repository, "get_combined_status")
    assert hasattr(Commit, "get_combined_status")
    assert hasattr(Commit, "get_check_runs")
    assert "sha" in inspect.signature(PullRequest.merge).parameters
    assert "commit_message" in inspect.signature(PullRequest.merge).parameters


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
    asyncio.run(
        swarm._create_auto_fix_pr(
            "task",
            {"files_written": [{"path": "app.py", "action": "modify"}]},
            human_approved=True,
        )
    )

    assert any("push" in cmd for cmd in git_calls)
    assert len(pr_calls) == 1
    add_cmds = [cmd for cmd in git_calls if "add" in cmd]
    assert len(add_cmds) == 1
    assert "app.py" in add_cmds[0]
    assert "." not in add_cmds[0]
    for cmd in git_calls:
        assert "core.hooksPath=/dev/null" in cmd


def test_auto_fix_pr_blocked_when_no_stageable_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Even with approval, nothing is pushed when the coder produced no safe files."""
    monkeypatch.setenv("REGENGINE_ENABLE_LEGACY_SWARM", "1")
    monkeypatch.delenv("REGENGINE_SWARM_AUTO_PR_APPROVED", raising=False)
    monkeypatch.chdir(tmp_path)
    calls: list = []
    monkeypatch.setattr("subprocess.run", lambda *a, **k: calls.append(a) or SimpleNamespace(returncode=0))
    import regengine.swarm.github_integration as gh_mod

    monkeypatch.setattr(gh_mod, "GitHubClient", lambda *a, **k: calls.append("github") or None)

    swarm = _swarm()
    result = asyncio.run(swarm._create_auto_fix_pr("task", {"files_written": []}, human_approved=True))

    assert result is None
    assert calls == []


def test_auto_fix_pr_runs_on_approval_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The approval env var alone authorizes the push path without the flag."""
    monkeypatch.setenv("REGENGINE_ENABLE_LEGACY_SWARM", "1")
    monkeypatch.setenv("REGENGINE_SWARM_AUTO_PR_APPROVED", "true")
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
    asyncio.run(swarm._create_auto_fix_pr("task", {"files_written": [{"path": "app.py", "action": "modify"}]}))

    assert any("push" in cmd for cmd in git_calls)
    assert len(pr_calls) == 1


def test_auto_fix_pr_skips_sensitive_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Model output naming .git or workflow files stages only the safe remainder."""
    monkeypatch.setenv("REGENGINE_ENABLE_LEGACY_SWARM", "1")
    monkeypatch.delenv("REGENGINE_SWARM_AUTO_PR_APPROVED", raising=False)
    monkeypatch.chdir(tmp_path)
    git_calls: list = []
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: git_calls.append(a[0]) or SimpleNamespace(returncode=0),
    )

    class _FakeGH:
        def create_pr(self, **kwargs):
            return {"number": 1}

    import regengine.swarm.github_integration as gh_mod

    monkeypatch.setattr(gh_mod, "GitHubClient", lambda *a, **k: _FakeGH())

    swarm = _swarm()
    asyncio.run(
        swarm._create_auto_fix_pr(
            "task",
            {
                "files_written": [
                    {"path": ".git/hooks/pre-commit", "action": "create"},
                    {"path": ".github/workflows/evil.yml", "action": "create"},
                    {"path": "app.py", "action": "modify"},
                ]
            },
            human_approved=True,
        )
    )

    add_cmds = [cmd for cmd in git_calls if "add" in cmd]
    assert len(add_cmds) == 1
    staged = add_cmds[0][add_cmds[0].index("--") + 1 :]
    assert staged == ["app.py"]


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

    assert result.status == "completed_with_warnings"
    assert any("missing human approval" in err for err in result.errors)
    assert calls == []


# ── Write guard: sensitive paths and unresolved traversal ────


def test_is_path_within_base_rejects_unresolved_traversal() -> None:
    from regengine.swarm.agents import is_path_within_base as check

    assert not check(Path("/repo"), Path("/repo/foo/../../etc/passwd"))
    assert check(Path("/repo"), Path("/repo/sub/../ok.py"))


def test_coder_act_blocks_git_and_workflow_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Model output naming .git config or workflow files must not be written."""
    workdir = tmp_path / "repo"
    workdir.mkdir()
    monkeypatch.chdir(workdir)

    agent = _coder(tmp_path)
    result = asyncio.run(
        agent.act(
            {
                "files": [
                    {"path": ".git/config", "action": "create", "content": "[core]\n"},
                    {
                        "path": ".github/workflows/nightly.yml",
                        "action": "create",
                        "content": "run: evil\n",
                    },
                    {"path": "pkg/ok.py", "action": "create", "content": "x = 1\n"},
                ]
            }
        )
    )

    assert result["file_count"] == 1
    assert not (workdir / ".git" / "config").exists()
    assert not (workdir / ".github" / "workflows" / "nightly.yml").exists()
    assert (workdir / "pkg" / "ok.py").read_text() == "x = 1\n"


# ── PR body redaction ─────────────────────────────────────────


def test_redact_for_pr_body_strips_secrets() -> None:
    from regengine.swarm.coordinator import redact_for_pr_body

    body = redact_for_pr_body("deploy with api_key: hunter2 and password= s3cret")
    assert "hunter2" not in body
    assert "s3cret" not in body
    assert "plain task text stays" in redact_for_pr_body("plain task text stays")


# ── Approval forwarding ───────────────────────────────────────


def test_sweep_forwards_human_approved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGENGINE_ENABLE_LEGACY_SWARM", "1")
    swarm = _swarm()
    seen: list = []

    async def fake_solve(task_item, context=None, human_approved=False):
        seen.append((task_item, human_approved))
        return SimpleNamespace(status="completed", errors=[])

    monkeypatch.setattr(swarm, "solve", fake_solve)
    asyncio.run(swarm.sweep(["a", "b"], human_approved=True))

    assert [flag for _, flag in seen] == [True, True]


def test_troubleshoot_forwards_human_approved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGENGINE_ENABLE_LEGACY_SWARM", "1")
    swarm = _swarm()
    seen: dict = {}

    async def fake_sre_run(task, context=None):
        return {
            "result": {
                "analysis": {"root_cause": "boom"},
                "remediation": {"immediate_fix": "fix it"},
            }
        }

    async def fake_solve(task, context=None, human_approved=False):
        seen["task"] = task
        seen["human_approved"] = human_approved
        return swarm._build_result(task, "completed", ["SRE"], 0, 0.0)

    monkeypatch.setattr(swarm.sre, "run", fake_sre_run)
    monkeypatch.setattr(swarm, "solve", fake_solve)
    asyncio.run(swarm.troubleshoot("some logs", human_approved=True))

    assert seen["human_approved"] is True
    assert "boom" in seen["task"]


# ── Janitor CLI approval gate ─────────────────────────────────


class _FakeJanitorAgent:
    def __init__(self, decision: str = "merge") -> None:
        self.decision = decision
        self.evaluated: list = []

    async def run(self, task: str, context=None):
        self.evaluated.append(task)
        return {"result": {"decision": self.decision, "reasoning": "tests green"}}


class _FakeJanitorPR:
    def __init__(self, number: int, fail_scan: bool = False) -> None:
        self.number = number
        self.title = f"PR {number}"
        self._fail_scan = fail_scan

    def get_issue_comments(self):
        if self._fail_scan:
            raise RuntimeError("comments unavailable")
        return [SimpleNamespace(body="Security Audit: pass")]


class _FakeJanitorGH:
    instances: list = []

    def __init__(self, prs, fail_status_for=()) -> None:
        self._prs = prs
        self._fail_status_for = set(fail_status_for)
        self.status_calls: list = []
        self.merge_calls: list = []
        _FakeJanitorGH.instances.append(self)

    @property
    def repo(self):
        outer = self

        class _Pulls:
            totalCount = len(outer._prs)

            def __iter__(self):
                return iter(outer._prs)

        return SimpleNamespace(get_pulls=lambda state="open": _Pulls())

    def get_pr_checks_status(self, number: int) -> str:
        self.status_calls.append(number)
        if number in self._fail_status_for:
            raise RuntimeError("checks unavailable")
        return "success"

    def merge_pr(self, number: int, human_approved: bool = False) -> bool:
        self.merge_calls.append((number, human_approved))
        return True


def _janitor_args(**overrides):
    args = {
        "task": "janitor sweep",
        "dry_run": True,
        "agent": "janitor",
        "approve_merges": False,
        "prs": None,
        "approve_pr": False,
        "max_iterations": 3,
        "output_file": None,
    }
    args.update(overrides)
    return SimpleNamespace(**args)


def _run_janitor(monkeypatch: pytest.MonkeyPatch, pr_list, decision="merge", fail_status_for=(), **arg_overrides):
    from regengine.swarm import cli as cli_mod

    janitor = _FakeJanitorAgent(decision=decision)

    class _FakeSwarm:
        def __init__(self, *a, **k) -> None:
            self.agents = {"janitor": janitor}

    _FakeJanitorGH.instances.clear()
    monkeypatch.setenv("REGENGINE_ENABLE_LEGACY_SWARM", "1")
    monkeypatch.setattr("regengine.swarm.coordinator.AgentSwarm", _FakeSwarm)
    monkeypatch.setattr(
        "regengine.swarm.github_integration.GitHubClient",
        lambda *a, **k: _FakeJanitorGH(pr_list, fail_status_for=fail_status_for),
    )
    cli_mod.cmd_run(_janitor_args(**arg_overrides))
    gh = _FakeJanitorGH.instances[-1]
    return janitor, gh


def test_janitor_skips_merge_without_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    janitor, gh = _run_janitor(monkeypatch, [_FakeJanitorPR(7)], approve_merges=False)

    assert janitor.evaluated != []
    assert gh.merge_calls == []


def test_janitor_merges_only_with_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    janitor, gh = _run_janitor(monkeypatch, [_FakeJanitorPR(7)], approve_merges=True)

    assert gh.merge_calls == [(7, True)]


def test_janitor_continues_after_single_pr_scan_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _, gh = _run_janitor(
        monkeypatch,
        [_FakeJanitorPR(1, fail_scan=True), _FakeJanitorPR(2)],
        approve_merges=True,
        fail_status_for=(),
    )

    assert gh.merge_calls == [(2, True)]


def test_janitor_prs_filter_limits_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    janitor, gh = _run_janitor(
        monkeypatch,
        [_FakeJanitorPR(1), _FakeJanitorPR(2), _FakeJanitorPR(3)],
        approve_merges=True,
        prs="2",
    )

    assert gh.merge_calls == [(2, True)]
    assert janitor.evaluated == ["Evaluate PR #2"]


# ── Compliance sweep forwarding ───────────────────────────────


def test_compliance_sweep_forwards_env_approval(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import importlib.util

    script_path = Path(__file__).resolve().parents[2] / "scripts" / "compliance_sweep.py"
    spec = importlib.util.spec_from_file_location("compliance_sweep_under_test", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setenv("REGENGINE_ENABLE_LEGACY_SWARM", "1")
    monkeypatch.setenv("REGENGINE_SWARM_AUTO_PR_APPROVED", "true")
    monkeypatch.delenv("REGENGINE_CI_AUTO_FIX", raising=False)

    seen: dict = {}

    class _FakeSweepSwarm:
        def __init__(self, *a, **k) -> None:
            pass

        async def sweep(self, tasks, concurrency=5, human_approved=False):
            seen["count"] = len(tasks)
            seen["human_approved"] = human_approved
            return [SimpleNamespace(status="completed_with_warnings", errors=["blocked"]) for _ in tasks]

    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "AgentSwarm", _FakeSweepSwarm)
    asyncio.run(module.roll_out_compliance("FSMA-204"))
    os.environ.pop("REGENGINE_CI_AUTO_FIX", None)

    assert seen["count"] == len(module.SERVICES)
    assert seen["human_approved"] is True
