"""Hygiene guard for the SDK CI workflow (audit finding re-platform-2-ops #96).

sdk-ci.yml once had no concurrency block (overlapping runs piled up) and
installed its test libraries unpinned (``pip install pytest
pytest-asyncio httpx requests``), so CI resolved whatever was newest at
run time. These tests pin the fixed behavior on the real workflow file,
plus synthetic cases proving each check can actually fail.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "sdk-ci.yml"

_PINNED_INSTALL = re.compile(r"pip install\s+(?P<specs>[^\n#]+)")


def _pip_specs(workflow: dict) -> list[str]:
    """Every package spec passed to a bare ``pip install`` in ``run:`` steps."""
    specs: list[str] = []
    jobs = workflow.get("jobs", {})
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps", []) or []:
            if not isinstance(step, dict):
                continue
            run = step.get("run", "")
            if not isinstance(run, str) or "pip install" not in run:
                continue
            for match in _PINNED_INSTALL.finditer(run):
                for token in match.group("specs").split():
                    token = token.strip().strip("\\").strip(";")
                    if not token or token.startswith("-") or token.startswith("$"):
                        continue
                    if token in ("--upgrade", "pip"):
                        # `--upgrade pip` is the pip self-bootstrap, not a library install.
                        continue
                    specs.append(token)
    return specs


def check_concurrency(workflow: dict) -> None:
    concurrency = workflow.get("concurrency", {})
    assert isinstance(concurrency, dict), "sdk-ci.yml has no top-level concurrency block"
    assert concurrency.get("cancel-in-progress") is True, (
        "concurrency must set cancel-in-progress: true so overlapping runs cancel"
    )
    assert concurrency.get("group"), "concurrency must name a shared group"


def check_installs_pinned(workflow: dict) -> None:
    unpinned = [
        spec
        for spec in _pip_specs(workflow)
        if "==" not in spec
        and not spec.startswith(("./", "../", "$"))
        and not spec.endswith((".whl", ".tar.gz"))
        and "/" not in spec
    ]
    assert not unpinned, f"unpinned pip installs drift between runs: {sorted(set(unpinned))}"


def check_job_timeouts(workflow: dict) -> None:
    missing = [
        job_id
        for job_id, job in (workflow.get("jobs", {}) or {}).items()
        if isinstance(job, dict) and "timeout-minutes" not in job
    ]
    assert not missing, f"jobs without an explicit timeout can hang CI forever: {missing}"


def _load_real() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


class TestSdkCiRealWorkflow:
    def test_concurrency_cancels_overlapping_runs(self):
        check_concurrency(_load_real())

    def test_test_libraries_are_pinned(self):
        check_installs_pinned(_load_real())

    def test_every_job_has_a_timeout(self):
        check_job_timeouts(_load_real())


class TestChecksCanFail:
    def test_missing_concurrency_fails(self):
        with pytest.raises(AssertionError, match="concurrency"):
            check_concurrency({"jobs": {}})

    def test_concurrency_without_cancellation_fails(self):
        with pytest.raises(AssertionError, match="cancel-in-progress"):
            check_concurrency({"concurrency": {"group": "sdk", "cancel-in-progress": False}})

    def test_unpinned_install_fails(self):
        workflow = {"jobs": {"sdk": {"steps": [{"run": "python -m pip install pytest pytest-asyncio httpx requests"}]}}}
        with pytest.raises(AssertionError, match="unpinned"):
            check_installs_pinned(workflow)

    def test_pinned_install_passes(self):
        workflow = {
            "jobs": {
                "sdk": {
                    "steps": [
                        {
                            "run": "python -m pip install "
                            "pytest==9.1.1 pytest-asyncio==1.4.0 httpx==0.28.1 requests==2.34.2"
                        }
                    ]
                }
            }
        }
        check_installs_pinned(workflow)

    def test_job_without_timeout_fails(self):
        with pytest.raises(AssertionError, match="timeout"):
            check_job_timeouts({"jobs": {"report": {"runs-on": "ubuntu-latest"}}})
