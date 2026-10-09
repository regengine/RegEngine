"""Guard workflow hygiene from audit finding 99: pinned-action version labels
must agree across files, and PR-controlled values (branch names, PR numbers)
must reach shell steps through environment variables, not direct
interpolation into ``run:`` scripts."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = ROOT / ".github" / "workflows"

USES_PIN = re.compile(r"uses:\s*\S+@(?P<sha>[0-9a-f]{40})\s*(?:#\s*(?P<label>\S+))?")
SHELL_CONTEXT = re.compile(r"\$\{\{[^}]*github\.(event\.pull_request|head_ref|base_ref)")


def _steps(doc):
    for job in (doc.get("jobs") or {}).values():
        if isinstance(job, dict):
            for step in job.get("steps") or []:
                if isinstance(step, dict):
                    yield step


def test_checkout_pin_labels_agree_for_same_sha():
    labels_by_sha: dict[str, set[str]] = {}
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        for line in path.read_text().splitlines():
            if "actions/checkout@" not in line:
                continue
            match = USES_PIN.search(line)
            assert match is not None, f"{path.name}: unparseable checkout pin: {line.strip()}"
            labels_by_sha.setdefault(match.group("sha"), set()).add(match.group("label") or "")
    assert labels_by_sha, "no checkout pins found"
    disagreeing = {sha: labels for sha, labels in labels_by_sha.items() if len(labels) > 1}
    assert not disagreeing, "same pinned SHA carries different version labels: " + ", ".join(
        f"{sha[:12]} -> {sorted(labels)}" for sha, labels in disagreeing.items()
    )


def test_pr_values_reach_shell_only_via_env():
    offenders = []
    for name in ("sentinel.yml", "pr-quality.yml"):
        doc = yaml.safe_load((WORKFLOW_DIR / name).read_text())
        for step in _steps(doc):
            run = step.get("run")
            if isinstance(run, str) and SHELL_CONTEXT.search(run):
                offenders.append(f"{name} step {step.get('name', step.get('id', '?'))!r}")
    assert not offenders, (
        f"direct ${{{{ github... }}}} interpolation inside shell run blocks (pass via env instead): {offenders}"
    )


def test_fixed_steps_still_receive_their_values():
    sentinel = yaml.safe_load((WORKFLOW_DIR / "sentinel.yml").read_text())
    fetch = next(s for s in _steps(sentinel) if isinstance(s.get("run"), str) and "git fetch origin" in s["run"])
    assert "base.ref" in str(fetch.get("env", {})), "fetch step must receive the base ref via env"

    quality = yaml.safe_load((WORKFLOW_DIR / "pr-quality.yml").read_text())
    size = next(s for s in _steps(quality) if s.get("name") == "Check PR size")
    assert "pull_request.number" in str(size.get("env", {})), "size step must receive the PR number via env"
    assert "$PR_NUMBER" in size["run"], "size step must read the PR number from the environment"
