"""Regression tests for the production deploy gate.

The defect: `.github/workflows/deploy.yml` auto-deployed production on
every push to main with no protected-environment approver, so a merged
PR shipped to production with no human release approval. These tests pin
the `production` environment binding on the deploy job (which is what
lets the repo settings gate releases with required reviewers) and the
existing wait-for-CI ordering.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_PATH = REPO_ROOT / ".github" / "workflows" / "deploy.yml"
CODEOWNERS_PATH = REPO_ROOT / ".github" / "CODEOWNERS"


def _deploy():
    data = yaml.safe_load(DEPLOY_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{DEPLOY_PATH} did not parse as a mapping"
    return data


def test_deploy_job_targets_production_environment():
    """Fails on the old workflow, whose deploy job named no environment."""
    jobs = _deploy().get("jobs", {})
    assert "deploy" in jobs, "deploy.yml has no deploy job"
    environment = jobs["deploy"].get("environment")
    if isinstance(environment, dict):
        environment = environment.get("name")
    assert environment == "production", (
        "deploy job must target the production environment so release "
        "approvers can gate it; found no environment binding"
    )


def test_deploy_still_waits_for_green_backend_ci():
    """The environment gate adds approval; it must not replace the CI gate."""
    jobs = _deploy().get("jobs", {})
    needs = jobs["deploy"].get("needs", [])
    if isinstance(needs, str):
        needs = [needs]
    assert "wait-for-ci" in needs, "deploy job must still wait for backend CI"


def test_push_to_main_remains_the_deploy_trigger():
    """Documents the auto-deploy shape the environment gate now guards."""
    data = _deploy()
    on = data.get("on", data.get(True))
    assert isinstance(on, dict) and "push" in on, "deploy must trigger on push"
    assert "main" in on["push"].get("branches", [])


def test_codeowners_security_paths_keep_an_owner():
    """Security-sensitive paths must keep at least one named owner.

    A second human owner is still needed (see reviewer notes); this test
    pins the entries so they cannot be dropped silently in the meantime.
    """
    lines = [line.split("#", 1)[0].strip() for line in CODEOWNERS_PATH.read_text(encoding="utf-8").splitlines()]
    entries = [line for line in lines if line and not line.startswith("*")]
    security_markers = ("SECURITY.md", "services/shared/auth.py", "services/ingestion/app/authz.py")
    for marker in security_markers:
        matches = [entry for entry in entries if entry.startswith(marker)]
        assert matches, f"CODEOWNERS lost its entry for {marker}"
        for entry in matches:
            owners = [part for part in entry.split() if part.startswith("@")]
            assert owners, f"CODEOWNERS entry has no owner: {entry!r}"
