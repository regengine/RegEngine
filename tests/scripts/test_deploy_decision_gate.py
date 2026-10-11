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
from pathlib import Path

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


def test_ai_analysis_exclusion_is_documented_as_advisory_only():
    # The decision gate deliberately ignores ai-analysis failures, so the
    # workflow source must say advisory-only is intended. Otherwise a
    # future reader cannot tell intent from accident.
    source = (_REPO / ".github" / "workflows" / "qa-pipeline.yml").read_text()
    assert "advisory-only" in source.lower()
    assert "ai-analysis" not in _workflow("qa-pipeline.yml")["jobs"]["decision"]["needs"]
    decision = _DECISION.read_text()
    assert "advisory-only" in decision.lower()


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
