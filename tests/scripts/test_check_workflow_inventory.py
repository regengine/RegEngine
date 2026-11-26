"""Tests for the workflow / branch-protection contract guard.

The guard exists because branch protection requires status-check contexts
by bare string, with no link back to the job that emits them. Two silent
failure modes follow, both of which actually happened on this repo:

  * a required context that no job emits (``CI Status Gate`` between
    #2551 and 2026-07-31), and
  * a required context emitted only by a path-filtered workflow, so a
    docs-only PR could never satisfy it (``security.yml``'s six gates).

Both were merged past with admin overrides. These tests pin the guard's
behavior on synthetic workflow trees, plus one test against the REAL
repo so the live contract cannot drift.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_workflow_inventory.py"

_spec = importlib.util.spec_from_file_location("check_workflow_inventory", SCRIPT)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def _write_workflow(dir_path: Path, filename: str, body: str) -> Path:
    path = dir_path / filename
    path.write_text(body, encoding="utf-8")
    return path


def _inventory(workflows: list[str], contexts: list[str]) -> str:
    lines = ["[workflows]", *workflows, "", "[required-contexts]", *contexts, ""]
    return "\n".join(lines)


_GOOD_WORKFLOW = """\
name: gate
on:
  merge_group:
    types: [checks_requested]
  pull_request:
jobs:
  gate:
    name: "CI Status Gate"
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
"""

_FILTERED_WORKFLOW = """\
name: gate
on:
  merge_group:
    types: [checks_requested]
  pull_request:
    paths-ignore:
      - 'docs/**'
jobs:
  gate:
    name: "CI Status Gate"
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
"""


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Point the guard at a synthetic repo tree."""
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    inventory = tmp_path / "workflow_inventory.txt"
    monkeypatch.setattr(_mod, "ROOT", tmp_path)
    monkeypatch.setattr(_mod, "WORKFLOW_DIR", workflow_dir)
    monkeypatch.setattr(_mod, "INVENTORY_FILE", inventory)
    return workflow_dir, inventory


class TestWorkflowInventorySync:
    def test_matching_tree_passes(self, sandbox, capsys):
        workflow_dir, inventory = sandbox
        _write_workflow(workflow_dir, "gate.yml", _GOOD_WORKFLOW)
        inventory.write_text(_inventory(["gate.yml"], ["CI Status Gate"]))

        assert _mod.main() == 0
        assert "OK" in capsys.readouterr().out

    def test_unlisted_new_workflow_fails(self, sandbox, capsys):
        workflow_dir, inventory = sandbox
        _write_workflow(workflow_dir, "gate.yml", _GOOD_WORKFLOW)
        _write_workflow(workflow_dir, "sneaky.yml", _GOOD_WORKFLOW.replace("CI Status Gate", "Other"))
        inventory.write_text(_inventory(["gate.yml"], ["CI Status Gate"]))

        assert _mod.main() == 1
        out = capsys.readouterr().out
        assert "UNLISTED" in out
        assert "sneaky.yml" in out

    def test_deleted_or_renamed_workflow_fails(self, sandbox, capsys):
        """The rename/delete case the guard was asked for: the inventory
        still lists a workflow that no longer exists."""
        workflow_dir, inventory = sandbox
        _write_workflow(workflow_dir, "gate-renamed.yml", _GOOD_WORKFLOW)
        inventory.write_text(_inventory(["gate.yml", "gate-renamed.yml"], ["CI Status Gate"]))

        assert _mod.main() == 1
        out = capsys.readouterr().out
        assert "MISSING" in out
        assert "gate.yml" in out


class TestRequiredContextContract:
    def test_phantom_context_fails(self, sandbox, capsys):
        """The real 2026-07-31 bug: the required context is 'CI Status
        Gate' but the only jobs are 'Backend/Frontend CI Status Gate'."""
        workflow_dir, inventory = sandbox
        _write_workflow(
            workflow_dir,
            "gate.yml",
            _GOOD_WORKFLOW.replace("CI Status Gate", "Backend CI Status Gate"),
        )
        inventory.write_text(_inventory(["gate.yml"], ["CI Status Gate"]))

        assert _mod.main() == 1
        out = capsys.readouterr().out
        assert "PHANTOM" in out
        # The near-miss hint makes the fix obvious.
        assert "Backend CI Status Gate" in out

    def test_path_filtered_emitter_fails(self, sandbox, capsys):
        """The security.yml bug: emitted, but unreachable on PRs that miss
        the filter (docs-only PRs), so they can never be merged cleanly."""
        workflow_dir, inventory = sandbox
        _write_workflow(workflow_dir, "gate.yml", _FILTERED_WORKFLOW)
        inventory.write_text(_inventory(["gate.yml"], ["CI Status Gate"]))

        assert _mod.main() == 1
        out = capsys.readouterr().out
        assert "UNREACHABLE" in out
        assert "paths-ignore" in out

    def test_paths_allowlist_filter_also_fails(self, sandbox, capsys):
        workflow_dir, inventory = sandbox
        _write_workflow(
            workflow_dir,
            "gate.yml",
            _FILTERED_WORKFLOW.replace("paths-ignore:", "paths:"),
        )
        inventory.write_text(_inventory(["gate.yml"], ["CI Status Gate"]))

        assert _mod.main() == 1
        assert "UNREACHABLE" in capsys.readouterr().out

    def test_push_only_workflow_fails(self, sandbox, capsys):
        workflow_dir, inventory = sandbox
        _write_workflow(
            workflow_dir,
            "gate.yml",
            _GOOD_WORKFLOW.replace("  pull_request:\n", "  push:\n    branches: [main]\n"),
        )
        inventory.write_text(_inventory(["gate.yml"], ["CI Status Gate"]))

        assert _mod.main() == 1
        assert "no `pull_request:` trigger" in capsys.readouterr().out

    def test_job_id_used_when_job_has_no_name(self, sandbox, capsys):
        """A job without `name:` posts its job ID as the context."""
        workflow_dir, inventory = sandbox
        _write_workflow(
            workflow_dir,
            "gate.yml",
            "name: gate\non:\n  merge_group:\n  pull_request:\njobs:\n  ci-status-gate:\n"
            "    runs-on: ubuntu-latest\n    steps:\n      - run: echo ok\n",
        )
        inventory.write_text(_inventory(["gate.yml"], ["ci-status-gate"]))

        assert _mod.main() == 0

    def test_one_reachable_emitter_is_enough(self, sandbox, capsys):
        """If two workflows emit the same context and at least one is
        unfiltered, the requirement is satisfiable."""
        workflow_dir, inventory = sandbox
        _write_workflow(workflow_dir, "gate.yml", _GOOD_WORKFLOW)
        _write_workflow(workflow_dir, "gate-filtered.yml", _FILTERED_WORKFLOW)
        inventory.write_text(_inventory(["gate.yml", "gate-filtered.yml"], ["CI Status Gate"]))

        assert _mod.main() == 0


class TestMergeQueueContract:
    def test_required_emitter_without_merge_group_fails(self, sandbox, capsys):
        workflow_dir, inventory = sandbox
        _write_workflow(
            workflow_dir,
            "gate.yml",
            _GOOD_WORKFLOW.replace("  merge_group:\n    types: [checks_requested]\n", ""),
        )
        inventory.write_text(_inventory(["gate.yml"], ["CI Status Gate"]))

        assert _mod.main() == 1
        out = capsys.readouterr().out
        assert "MERGE QUEUE" in out
        assert "deadlock" in out

    def test_every_required_emitter_needs_merge_group(self, sandbox, capsys):
        workflow_dir, inventory = sandbox
        _write_workflow(workflow_dir, "gate.yml", _GOOD_WORKFLOW)
        _write_workflow(
            workflow_dir,
            "other-gate.yml",
            _GOOD_WORKFLOW.replace("  merge_group:\n    types: [checks_requested]\n", ""),
        )
        inventory.write_text(_inventory(["gate.yml", "other-gate.yml"], ["CI Status Gate"]))

        assert _mod.main() == 1
        assert "other-gate.yml" in capsys.readouterr().out

    @pytest.mark.parametrize("filename", ["backend-ci.yml", "frontend-ci.yml"])
    @pytest.mark.parametrize("merge_group", [True, False])
    def test_mirrored_gate_requires_merge_group(self, sandbox, capsys, filename, merge_group):
        workflow_dir, inventory = sandbox
        _write_workflow(workflow_dir, "gate.yml", _GOOD_WORKFLOW)
        body = _GOOD_WORKFLOW.replace("CI Status Gate", "Mirrored gate")
        if not merge_group:
            body = body.replace("  merge_group:\n    types: [checks_requested]\n", "")
        _write_workflow(workflow_dir, filename, body)
        inventory.write_text(_inventory(["gate.yml", filename], ["CI Status Gate"]))

        assert _mod.main() == (0 if merge_group else 1)
        out = capsys.readouterr().out
        assert ("MERGE QUEUE" in out) == (not merge_group)


class TestRealRepositoryContract:
    def test_live_repo_satisfies_the_contract(self, capsys):
        """Runs against the REAL .github/workflows and inventory. Fails if
        anyone renames a workflow, drops a required-context emitter, or
        re-adds a path filter to one."""
        assert _mod.main() == 0
        assert "OK" in capsys.readouterr().out
