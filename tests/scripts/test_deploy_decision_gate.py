"""Deploy Decision and the backend status gate must fail closed.

A newer push cancels the in-flight workflow. Those runs used to execute
their `if: always()` summary jobs anyway and post a failure for stages
that were aborted, which showed up as a red Backend CI Status Gate and
Deploy Decision on a SHA whose tests never finished.

`cancelled()` is true only when the workflow itself was cancelled. The
summary jobs skip in that case. A stage that failed, was skipped, or was
cancelled while the workflow kept running still blocks.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[2]
_DECISION = _REPO / "qa" / "decision.js"


def _workflow(name: str) -> dict:
    data = yaml.safe_load((_REPO / ".github" / "workflows" / name).read_text())
    assert isinstance(data, dict)
    return data


def _run_decision(fast: str, sim: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["FAST_GATE_RESULT"] = fast
    env["SYSTEM_SIM_RESULT"] = sim
    return subprocess.run(
        ["node", str(_DECISION)],
        cwd=_REPO,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_decision_job_skips_only_when_the_workflow_is_cancelled():
    job = _workflow("qa-pipeline.yml")["jobs"]["decision"]
    assert job["if"] == "always() && !cancelled()"
    assert job["needs"] == ["fast-gate", "system-sim"]


def test_backend_status_gate_still_requires_every_dependency_success():
    job = _workflow("backend-ci.yml")["jobs"]["ci-status"]
    assert job["name"] == "Backend CI Status Gate"
    assert job["if"] == "always() && !cancelled()"
    script = job["steps"][0]["run"]
    assert '!= "success"' in script
    assert "needs.test.result" in script
    assert "needs.ingestion-full-suite.result" in script


def test_decision_passes_only_when_both_stages_succeed():
    result = _run_decision("success", "success")
    assert result.returncode == 0, result.stderr
    assert "DEPLOY: All checks passed." in result.stdout


def test_decision_blocks_on_failure_skip_and_cancel():
    failed = _run_decision("failure", "success")
    assert failed.returncode == 1
    assert "Critical checks failed." in failed.stderr

    skipped = _run_decision("success", "skipped")
    assert skipped.returncode == 1
    assert "Required stages were skipped." in skipped.stderr

    # The state posted when system-sim is aborted but the workflow is not.
    cancelled = _run_decision("success", "cancelled")
    assert cancelled.returncode == 1
    assert "A required stage was cancelled." in cancelled.stderr
    assert "systemSim" in cancelled.stderr

    unknown = _run_decision("success", "timed_out")
    assert unknown.returncode == 1
    payload = unknown.stderr.split("Unexpected stage state — ", 1)[1].splitlines()[0]
    assert json.loads(payload) == {"fastGate": "success", "systemSim": "timed_out"}


_SHA = "a" * 40
_SECURITY_JOBS = [
    "Privileged Workflow Tool Pinning",
    "Secrets Scan (gitleaks)",
    "Secrets Audit (detect-secrets)",
    "Browser Storage PII Guard",
    "SAST (Semgrep)",
    "Dependency Audit",
    "Tenant Isolation & Auth Tests",
    "security.txt Expiry Check",
    "Generate SBOM (SPDX)",
    "Container Scan (Trivy)",
]


def _security_run(**changes):
    return {
        "id": 200,
        "name": "security",
        "path": ".github/workflows/security.yml",
        "workflow_id": 42,
        "head_sha": _SHA,
        "head_branch": "main",
        "event": "push",
        "run_number": 20,
        "run_attempt": 1,
        "status": "completed",
        "conclusion": "success",
        "repository": {"full_name": "regengine/RegEngine"},
        "head_repository": {"full_name": "regengine/RegEngine"},
        **changes,
    }


def _security_jobs():
    return [
        {
            "id": 300 + index,
            "run_id": 200,
            "run_attempt": 1,
            "head_sha": _SHA,
            "name": name,
            "status": "completed",
            "conclusion": "success",
            "steps": [],
        }
        for index, name in enumerate(_SECURITY_JOBS)
    ]


def _run_security_gate(tmp_path, runs, jobs=None, *, event="push", api_error=False, runs_after=None, environment=None):
    """Execute the workflow's real gate with only the external GH API replaced."""
    workflow = _workflow("deploy.yml")
    deploy = workflow["jobs"]["deploy"]
    gates = [workflow["jobs"][name] for name in deploy["needs"]]
    security_steps = [
        (gate, step)
        for gate in gates
        for step in gate["steps"]
        if step.get("name") == "Require security green for deployed revision"
    ]
    assert security_steps, "deployment must depend on a security evidence gate"
    gate, step = security_steps[0]
    assert "if" not in gate and "if" not in step, "manual dispatch must not bypass security"
    assert not gate.get("continue-on-error") and not step.get("continue-on-error")

    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps({"runs": runs, "jobs": jobs, "api_error": api_error, "runs_after": runs_after}))
    gh = tmp_path / "gh"
    gh.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "data = json.loads(Path(os.environ['TEST_SECURITY_EVIDENCE']).read_text())\n"
        "if data['api_error'] is True or (data['api_error'] == 'jobs' and '/jobs?' in sys.argv[4]):\n"
        "    print('API unavailable: test-gate-token', file=sys.stderr)\n"
        "    sys.exit(1)\n"
        "assert sys.argv[1:4] == ['api', '--paginate', '--slurp'], sys.argv\n"
        f"runs_endpoint = 'repos/regengine/RegEngine/actions/workflows/security.yml/runs?head_sha={_SHA}&per_page=100'\n"
        "jobs_endpoint = 'repos/regengine/RegEngine/actions/runs/200/jobs?filter=latest&per_page=100'\n"
        "if sys.argv[4] == runs_endpoint:\n"
        "    print(json.dumps(data['runs']))\n"
        "    if data['runs_after'] is not None:\n"
        "        data['runs'] = data['runs_after']\n"
        "        Path(os.environ['TEST_SECURITY_EVIDENCE']).write_text(json.dumps(data))\n"
        "elif sys.argv[4] == jobs_endpoint:\n"
        "    print(json.dumps(data['jobs']))\n"
        "else:\n"
        "    sys.exit('Unexpected GitHub endpoint: ' + sys.argv[4])\n"
    )
    gh.chmod(0o755)
    context = {
        "${{ github.sha }}": _SHA,
        "${{ github.repository }}": "regengine/RegEngine",
        "${{ secrets.GITHUB_TOKEN }}": "test-gate-token",
    }
    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "GITHUB_SHA": _SHA,
        "GITHUB_REPOSITORY": "regengine/RegEngine",
        "GITHUB_EVENT_NAME": event,
        "TEST_SECURITY_EVIDENCE": str(evidence),
        **{name: context.get(value, value) for name, value in step.get("env", {}).items()},
        **(environment or {}),
    }
    return subprocess.run(
        ["bash", "-eu", "-c", step["run"].strip() + " --timeout-seconds 0"],
        cwd=_REPO,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )


@pytest.mark.parametrize("event", ["push", "workflow_dispatch"])
def test_deployment_accepts_complete_security_evidence_for_exact_sha(tmp_path, event):
    result = _run_security_gate(
        tmp_path,
        [{"workflow_runs": [_security_run()]}],
        [{"jobs": _security_jobs()}],
        event=event,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert _SHA in result.stdout


@pytest.mark.parametrize("event", ["push", "workflow_dispatch"])
@pytest.mark.parametrize(
    "runs",
    [
        [],
        [_security_run(head_sha="b" * 40)],
        [_security_run(event="pull_request")],
        [_security_run(path=".github/workflows/backend-ci.yml")],
        [_security_run(repository={"full_name": "someone/else"})],
        [_security_run(head_repository={"full_name": "someone/else"})],
        [_security_run(status="in_progress", conclusion=None)],
        [_security_run(conclusion="failure")],
        [_security_run(conclusion="cancelled")],
        [_security_run(conclusion="skipped")],
        [_security_run(conclusion="timed_out")],
        [_security_run(conclusion="neutral")],
        [_security_run(), _security_run(id=201, run_number=21, conclusion="failure")],
        [_security_run(run_attempt=2, conclusion="failure")],
    ],
)
def test_deployment_blocks_absent_incomplete_or_untrusted_security_evidence(tmp_path, event, runs):
    result = _run_security_gate(tmp_path, [{"workflow_runs": runs}], [{"jobs": _security_jobs()}], event=event)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "security" in result.stdout.lower() + result.stderr.lower()


@pytest.mark.parametrize("name", _SECURITY_JOBS)
@pytest.mark.parametrize("conclusion", ["skipped", "failure", "cancelled", None])
def test_deployment_requires_every_release_security_job_to_succeed(tmp_path, name, conclusion):
    jobs = _security_jobs()
    next(job for job in jobs if job["name"] == name)["conclusion"] = conclusion
    result = _run_security_gate(tmp_path, [{"workflow_runs": [_security_run()]}], [{"jobs": jobs}])
    assert result.returncode == 1, result.stdout + result.stderr
    assert name in result.stdout + result.stderr


@pytest.mark.parametrize("change", ["missing", "stale_sha", "other_run", "in_progress"])
def test_deployment_rejects_missing_or_mismatched_scan_jobs(tmp_path, change):
    jobs = _security_jobs()
    container = jobs[-1]
    if change == "missing":
        jobs.pop()
    elif change == "stale_sha":
        container["head_sha"] = "b" * 40
    elif change == "other_run":
        container["run_id"] = 199
    else:
        container["status"] = "in_progress"
    result = _run_security_gate(tmp_path, [{"workflow_runs": [_security_run()]}], [{"jobs": jobs}])
    assert result.returncode == 1, result.stdout + result.stderr


def test_deployment_reads_all_run_and_job_pages(tmp_path):
    jobs = _security_jobs()
    result = _run_security_gate(
        tmp_path,
        [{"workflow_runs": [_security_run(head_sha="b" * 40)]}, {"workflow_runs": [_security_run()]}],
        [{"jobs": jobs[:-2]}, {"jobs": jobs[-2:]}],
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("api_error", [True, "jobs"])
def test_deployment_fails_closed_when_security_api_is_unavailable(tmp_path, api_error):
    result = _run_security_gate(tmp_path, [{"workflow_runs": [_security_run()]}], api_error=api_error)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "test-gate-token" not in result.stdout + result.stderr


@pytest.mark.parametrize("payload", [None, {}, [{"workflow_runs": None}], [{"workflow_runs": [{}]}]])
def test_deployment_fails_closed_on_malformed_security_evidence(tmp_path, payload):
    result = _run_security_gate(tmp_path, payload)
    assert result.returncode == 1, result.stdout + result.stderr


@pytest.mark.parametrize(
    "new_run",
    [
        _security_run(run_attempt=2, status="in_progress", conclusion=None),
        _security_run(id=201, run_number=21, conclusion="failure"),
        _security_run(run_attempt=2, conclusion="failure"),
    ],
)
def test_deployment_rechecks_security_run_after_reading_jobs(tmp_path, new_run):
    result = _run_security_gate(
        tmp_path,
        [{"workflow_runs": [_security_run()]}],
        [{"jobs": _security_jobs()}],
        runs_after=[{"workflow_runs": [new_run]}],
    )
    assert result.returncode == 1, result.stdout + result.stderr


@pytest.mark.parametrize("event", ["workflow_dispatch", "schedule"])
def test_deployment_can_use_successful_full_security_run_on_same_revision(tmp_path, event):
    jobs = _security_jobs()
    jobs[-1]["run_attempt"] = 2
    result = _run_security_gate(
        tmp_path,
        [{"workflow_runs": [_security_run(event=event, run_attempt=2)]}],
        [{"jobs": jobs}],
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("sha", ["", "aaaaaaa", "refs/heads/main"])
def test_deployment_requires_a_full_commit_sha(tmp_path, sha):
    result = _run_security_gate(tmp_path, [], environment={"RELEASE_SHA": sha})
    assert result.returncode == 1, result.stdout + result.stderr
