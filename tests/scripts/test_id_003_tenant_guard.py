"""Regression tests for scripts/test_id_003.sh tenant handling.

The defect: the script hardcoded DEMO and ADVERSARY tenant UUIDs with no
validation, so after fixture rotation it silently exercised the wrong
tenants instead of failing. The script must now resolve both tenant IDs
from the environment (DEMO_TENANT_ID / ADVERSARY_TENANT_ID), validate that
each is a UUID, require them to differ, and exit non-zero before touching
the database otherwise.

These tests run the real script with a stubbed `docker` on PATH, so they
need no live PostgreSQL or containers. The stub records its arguments so
the happy path can prove the script forwarded the environment-supplied
adversary tenant into the `SET app.tenant_id` statement.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "test_id_003.sh"

DEMO_UUID = "11111111-1111-1111-1111-111111111111"
ADVERSARY_UUID = "22222222-2222-2222-2222-222222222222"

# The stale IDs the script used to hardcode. They must not come back.
OLD_DEMO_UUID = "40e74bc9-4087-4612-8d94-215347138a68"
OLD_ADVERSARY_UUID = "9f6ceefc-05d6-43a3-83c6-77cd5f954a2e"

_DOCKER_STUB = """\
#!/usr/bin/env bash
# Stub docker: record arguments, pretend the query ran.
echo "$@" >> "$DOCKER_LOG"
exit 0
"""


def _run_script(tmp_path: Path, *, env_extra: dict | None = None):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "docker"
    stub.write_text(_DOCKER_STUB)
    stub.chmod(0o755)

    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["DOCKER_LOG"] = str(tmp_path / "docker.log")
    env.pop("DEMO_TENANT_ID", None)
    env.pop("ADVERSARY_TENANT_ID", None)
    # Legacy internal names must not act as a backdoor around validation.
    env.pop("DEMO_TENANT", None)
    env.pop("ADVERSARY_TENANT", None)
    if env_extra:
        env.update(env_extra)

    proc = subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        timeout=120,
    )
    return proc


def test_missing_demo_tenant_id_fails(tmp_path):
    """No DEMO_TENANT_ID: fail before touching the database.

    Fails against the old script, which ignored the environment and ran
    with its hardcoded IDs (docker stub exits 0, so it reported success).
    """
    proc = _run_script(tmp_path, env_extra={"ADVERSARY_TENANT_ID": ADVERSARY_UUID})
    assert proc.returncode != 0
    assert "DEMO_TENANT_ID" in proc.stderr
    assert not (tmp_path / "docker.log").exists()


def test_missing_adversary_tenant_id_fails(tmp_path):
    """No ADVERSARY_TENANT_ID: fail before touching the database."""
    proc = _run_script(tmp_path, env_extra={"DEMO_TENANT_ID": DEMO_UUID})
    assert proc.returncode != 0
    assert "ADVERSARY_TENANT_ID" in proc.stderr
    assert not (tmp_path / "docker.log").exists()


def test_malformed_tenant_id_fails(tmp_path):
    """A non-UUID tenant ID is rejected instead of sent to Postgres.

    Fails against the old script, which performed no validation.
    """
    proc = _run_script(
        tmp_path,
        env_extra={
            "DEMO_TENANT_ID": "not-a-uuid",
            "ADVERSARY_TENANT_ID": ADVERSARY_UUID,
        },
    )
    assert proc.returncode != 0
    assert "not a valid UUID" in proc.stderr
    assert not (tmp_path / "docker.log").exists()


def test_identical_tenant_ids_fail(tmp_path):
    """Same tenant twice makes the bypass check vacuous, so it must fail."""
    proc = _run_script(
        tmp_path,
        env_extra={
            "DEMO_TENANT_ID": DEMO_UUID,
            "ADVERSARY_TENANT_ID": DEMO_UUID,
        },
    )
    assert proc.returncode != 0
    assert "must differ" in proc.stderr
    assert not (tmp_path / "docker.log").exists()


def test_valid_env_tenants_reach_the_query(tmp_path):
    """With valid env tenants the script poses as the adversary tenant."""
    proc = _run_script(
        tmp_path,
        env_extra={
            "DEMO_TENANT_ID": DEMO_UUID,
            "ADVERSARY_TENANT_ID": ADVERSARY_UUID,
        },
    )
    assert proc.returncode == 0, proc.stderr

    logged = (tmp_path / "docker.log").read_text()
    assert f"SET app.tenant_id = '{ADVERSARY_UUID}'" in logged
    assert OLD_DEMO_UUID not in logged
    assert OLD_ADVERSARY_UUID not in logged


def test_hardcoded_tenant_ids_are_gone():
    """The stale hardcoded IDs must not reappear in the script."""
    source = SCRIPT.read_text()
    assert OLD_DEMO_UUID not in source
    assert OLD_ADVERSARY_UUID not in source
