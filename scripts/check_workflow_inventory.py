#!/usr/bin/env python3
"""CI guard: keep workflows and branch-protection required contexts in sync.

Branch protection requires status-check CONTEXTS by name. A context is a
bare string — GitHub does not know, and cannot check, which workflow is
supposed to emit it. So two silent failure modes exist:

1. **Phantom required context.** A required context that no job emits.
   Every PR waits forever on a check that will never post; the only way
   to merge is an admin override. This is not hypothetical: between
   #2551 and 2026-07-31 the required context ``CI Status Gate`` was
   emitted by nothing (the jobs are named ``Backend CI Status Gate`` and
   ``Frontend CI Status Gate``), and merges proceeded via override.

2. **Unreachable required context.** A required context emitted by a
   path-filtered workflow. PRs that miss the filter never produce it —
   e.g. a docs-only PR against a workflow with
   ``paths-ignore: ['docs/**']`` — so that class of PR is structurally
   unmergeable without an override.

This guard fails CI when either shape appears, and when the workflow set
drifts from the checked-in inventory (a rename or delete that nobody
recorded is how phantom contexts get created in the first place).

Checks:
  A. Every ``.github/workflows/*.yml`` is listed in ``[workflows]``.
  B. Every ``[workflows]`` entry still exists on disk.
  C. Every ``[required-contexts]`` entry is emitted as a job ``name:``.
  D. The workflow emitting each required context runs on EVERY pull
     request — a ``pull_request:`` trigger with no ``paths:`` /
     ``paths-ignore:`` filter.
  E. Required-context emitters and the backend/frontend gates they mirror
     have a ``merge_group:`` trigger, or the merge queue would deadlock.

The inventory (``scripts/workflow_inventory.txt``) is the checked-in
mirror of branch-protection settings. Changing branch protection is a
settings-UI action; update the inventory in the same PR.

Usage (local): ``python3 scripts/check_workflow_inventory.py``
Usage (CI):    same. Non-zero exit fails the step.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_DIR = ROOT / ".github" / "workflows"
INVENTORY_FILE = Path(__file__).with_name("workflow_inventory.txt")

# PR Gate mirrors these gates, so they must also post on merge-group SHAs.
MIRRORED_GATE_WORKFLOWS = {"backend-ci.yml", "frontend-ci.yml"}

RUNBOOK = "docs/runbooks/BRANCH_PROTECTION.md"


def _parse_inventory() -> tuple[set[str], list[str]]:
    """Return (workflow filenames, required contexts) from the inventory."""
    if not INVENTORY_FILE.exists():
        print(f"ERROR: missing inventory file: {INVENTORY_FILE}", file=sys.stderr)
        sys.exit(2)

    workflows: set[str] = set()
    contexts: list[str] = []
    section: str | None = None
    for raw in INVENTORY_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if section == "workflows":
            workflows.add(line)
        elif section == "required-contexts":
            contexts.append(line)
    return workflows, contexts


def _load_workflow(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        print(f"ERROR: {path.name} is not valid YAML: {exc}", file=sys.stderr)
        sys.exit(2)
    return data if isinstance(data, dict) else {}


def _triggers(workflow: dict) -> dict:
    """Return the ``on:`` mapping.

    PyYAML parses the bare key ``on`` as the boolean True (YAML 1.1), so
    check both spellings.
    """
    raw = workflow.get("on", workflow.get(True))
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        return {key: None for key in raw}
    if isinstance(raw, str):
        return {raw: None}
    return {}


def _job_names(workflow: dict) -> set[str]:
    """Job display names — the strings that become status-check contexts.

    A job with no explicit ``name:`` posts its job ID as the context.
    """
    names: set[str] = set()
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict):
        return names
    for job_id, job in jobs.items():
        if isinstance(job, dict) and isinstance(job.get("name"), str):
            names.add(job["name"])
        else:
            names.add(str(job_id))
    return names


def _runs_on_every_pr(workflow: dict) -> tuple[bool, str]:
    """Does this workflow run on EVERY pull request to main?

    Returns (ok, reason-if-not).
    """
    triggers = _triggers(workflow)
    if "pull_request" not in triggers:
        return False, "has no `pull_request:` trigger"
    cfg = triggers.get("pull_request")
    if not isinstance(cfg, dict):
        return True, ""
    for filter_key in ("paths", "paths-ignore"):
        if cfg.get(filter_key):
            return False, f"its `pull_request:` trigger is filtered by `{filter_key}:`"
    return True, ""


def main() -> int:
    inventory_workflows, required_contexts = _parse_inventory()

    if not WORKFLOW_DIR.is_dir():
        print(f"ERROR: workflow directory not found: {WORKFLOW_DIR}", file=sys.stderr)
        return 2

    on_disk = {p.name for p in WORKFLOW_DIR.glob("*.yml")} | {p.name for p in WORKFLOW_DIR.glob("*.yaml")}
    failures: list[str] = []

    # Check A/B: inventory vs disk.
    for name in sorted(on_disk - inventory_workflows):
        failures.append(
            f"UNLISTED workflow '.github/workflows/{name}' — add it to "
            f"scripts/workflow_inventory.txt under [workflows]."
        )
    for name in sorted(inventory_workflows - on_disk):
        failures.append(
            f"MISSING workflow '.github/workflows/{name}' — it is listed in "
            f"scripts/workflow_inventory.txt but does not exist. If it was renamed or "
            f"deleted, update the inventory AND check whether it emitted a "
            f"branch-protection required context (see {RUNBOOK})."
        )

    # Build the context -> emitting workflow map across every workflow on disk.
    workflows: dict[str, dict] = {}
    emitters: dict[str, list[tuple[str, dict]]] = {}
    for path in sorted(WORKFLOW_DIR.glob("*.y*ml")):
        workflow = _load_workflow(path)
        workflows[path.name] = workflow
        for job_name in _job_names(workflow):
            emitters.setdefault(job_name, []).append((path.name, workflow))

    # Check C/D: required contexts are emitted, and reachable on every PR.
    for context in required_contexts:
        matches = emitters.get(context)
        if not matches:
            near = sorted(n for n in emitters if context.lower() in n.lower() or n.lower() in context.lower())
            hint = f" Closest job names: {', '.join(near)}." if near else ""
            failures.append(
                f"PHANTOM required context '{context}' — no job in .github/workflows/ "
                f"emits it, so every PR blocks on a check that can never post.{hint}"
            )
            continue
        reachable = [(fname, wf) for fname, wf in matches if _runs_on_every_pr(wf)[0]]
        if not reachable:
            fname, wf = matches[0]
            _, reason = _runs_on_every_pr(wf)
            failures.append(
                f"UNREACHABLE required context '{context}' — emitted by {fname}, but "
                f"{reason}, so PRs that miss the filter can never satisfy it."
            )

    # Check E: every emitter and mirrored gate must run for the merge queue.
    queue_workflows = MIRRORED_GATE_WORKFLOWS & on_disk
    for context in required_contexts:
        queue_workflows.update(fname for fname, _ in emitters.get(context, []))
    for fname in sorted(queue_workflows):
        if "merge_group" not in _triggers(workflows[fname]):
            failures.append(
                f"MERGE QUEUE workflow '{fname}' has no `merge_group:` trigger — "
                "the merge queue would deadlock waiting for its required or mirrored gate."
            )

    print(f"Scanned {len(on_disk)} workflow file(s) in .github/workflows/")
    print(f"Checked {len(required_contexts)} required context(s) from {INVENTORY_FILE.name}")

    if failures:
        print()
        for failure in failures:
            print(f"FAIL: {failure}")
        print(
            "\nWorkflow / branch-protection contract violated.\n"
            "\n"
            "The inventory in scripts/workflow_inventory.txt is the checked-in mirror\n"
            "of the `main` branch-protection settings. Keep them in the same PR:\n"
            "  * renamed or deleted a workflow -> update [workflows], and re-check\n"
            "    whether it emitted a required context;\n"
            "  * renamed a job that emits a required context -> either restore the\n"
            "    job name or change the required context in branch protection AND\n"
            "    update [required-contexts];\n"
            "  * a required context must come from a workflow that runs on EVERY\n"
            "    pull request, otherwise PRs that miss its path filter can never\n"
            "    satisfy it and can only be merged with an admin override.\n"
            f"\nSee {RUNBOOK}."
        )
        return 1

    print("\nOK — workflow inventory matches disk; every required context is emitted and reachable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
