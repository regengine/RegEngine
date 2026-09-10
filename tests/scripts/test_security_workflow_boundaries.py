"""Guard disposable PR database targets and fail-closed live audit preflight."""

import os
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def jobs():
    return yaml.safe_load((ROOT / ".github/workflows/security.yml").read_text())["jobs"]


def test_tenant_job_is_unconditional_and_uses_only_disposable_role_targets():
    job = jobs()["tenant-isolation"]
    assert "if" not in job
    assert "secrets." not in str(job)
    assert job["services"]["postgres"]["ports"] == ["5432:5432"]
    step = next(s for s in job["steps"] if s.get("name") == "Run tenant isolation tests")
    env = step["env"]
    names = ("MIGRATIONS_DATABASE_URL", "DATABASE_URL", "ADMIN_DATABASE_URL", "ROLE_ADMIN_DATABASE_URL")
    urls = [urlsplit(env[name]) for name in names]
    assert {(u.hostname, u.port, u.path) for u in urls} == {("localhost", 5432, "/live_suite")}
    assert len({u.username for u in urls}) == 4
    assert env["REMEDIATION_TEST_APP_DSN"] == env["DATABASE_URL"]
    assert env["REGENGINE_REQUIRE_DB"] == "1"
    assert "--source" in step["run"]


@pytest.mark.parametrize(
    "base,token,success",
    [
        ("", "", False),
        ("https://example.invalid", "", False),
        ("", "test-token", False),
        ("https://example.invalid", "test-token", True),
    ],
)
def test_audit_preflight_requires_both_settings(tmp_path, base, token, success):
    job = jobs()["audit-integrity-preflight"]
    assert job["if"] == "github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'"
    output = tmp_path / "output"
    check = next(s for s in job["steps"] if s.get("id") == "check")
    result = subprocess.run(
        ["bash", "-eu", "-c", check["run"]],
        env={**os.environ, "AUDIT_API_BASE": base, "AUDIT_TOKEN": token, "GITHUB_OUTPUT": str(output)},
        capture_output=True,
        text=True,
    )
    assert (result.returncode == 0) is success
    assert output.read_text().strip() == f"configured={str(success).lower()}"
    assert "test-token" not in result.stdout + result.stderr
