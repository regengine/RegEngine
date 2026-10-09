"""Guards for scripts/start-e2e-backend.sh.

The starter deletes both fixture databases on every run and used to bake
in a default signing key for every environment. It must now warn before
deleting and require an explicit AUTH_SECRET_KEY or JWT_SIGNING_KEY
outside local (development/test) mode.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "start-e2e-backend.sh"


def _source() -> str:
    return SCRIPT.read_text()


def test_warns_before_deleting_fixture_databases():
    src = _source()
    assert "PLAYWRIGHT_PRESERVE_LOCAL_DB" in src
    lowered = src.lower()
    assert "warning" in lowered
    assert "playwright_preserve_local_db=1" in lowered


def test_requires_explicit_key_outside_local_mode():
    src = _source()
    assert "AUTH_SECRET_KEY" in src
    assert "JWT_SIGNING_KEY" in src
    assert "REGENGINE_ENV" in src
    # The local fixture default must not be applied unconditionally.
    assert "playwright-local-jwt-signing-key-2026" in src
    assert "requires an explicit" in src.lower()


def _make_fake_python_bin(tmp_path: Path) -> Path:
    """Fake PYTHON_BIN that records its env instead of starting uvicorn."""
    fake = tmp_path / "fake-python"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "FAKE_PYTHON_CALLED $*" >> "{tmp_path}/calls.log"\n'
        f'echo "AUTH_SECRET_KEY=$AUTH_SECRET_KEY" >> "{tmp_path}/calls.log"\n'
        f'echo "JWT_SIGNING_KEY=$JWT_SIGNING_KEY" >> "{tmp_path}/calls.log"\n'
        f'echo "REGENGINE_ENV=$REGENGINE_ENV" >> "{tmp_path}/calls.log"\n'
        "exit 0\n"
    )
    os.chmod(fake, 0o755)
    assert stat.S_IMODE(os.stat(fake).st_mode) & 0o111
    return fake


def _run_script(tmp_path: Path, extra_env: dict) -> subprocess.CompletedProcess:
    fake = _make_fake_python_bin(tmp_path)
    env = {
        **os.environ,
        "PYTHON_BIN": str(fake),
        "PLAYWRIGHT_SHARED_DB_PATH": str(tmp_path / "shared.db"),
        "PLAYWRIGHT_ADMIN_DB_PATH": str(tmp_path / "admin.db"),
        "PLAYWRIGHT_PRESERVE_LOCAL_DB": "1",
        **extra_env,
    }
    env.pop("AUTH_SECRET_KEY", None)
    env.pop("JWT_SIGNING_KEY", None)
    for key, value in extra_env.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def _fake_python_called(tmp_path: Path) -> bool:
    log = tmp_path / "calls.log"
    return log.exists() and "FAKE_PYTHON_CALLED" in log.read_text()


def test_production_without_key_refuses_to_start(tmp_path):
    proc = _run_script(tmp_path, {"REGENGINE_ENV": "production"})
    assert proc.returncode != 0
    assert "explicit" in (proc.stdout + proc.stderr).lower()
    assert not _fake_python_called(tmp_path)


def test_production_with_explicit_key_starts(tmp_path):
    proc = _run_script(
        tmp_path,
        {"REGENGINE_ENV": "production", "AUTH_SECRET_KEY": "sentinel-explicit-key"},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _fake_python_called(tmp_path)
    log = (tmp_path / "calls.log").read_text()
    assert "sentinel-explicit-key" in log
    assert "playwright-local-jwt-signing-key-2026" not in log


def test_local_mode_keeps_working_without_key(tmp_path):
    proc = _run_script(tmp_path, {"REGENGINE_ENV": "development"})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _fake_python_called(tmp_path)


def test_delete_warns_and_preserve_keeps_files(tmp_path):
    shared = tmp_path / "shared.db"
    admin = tmp_path / "admin.db"
    shared.write_text("sentinel-shared")
    admin.write_text("sentinel-admin")

    fake = _make_fake_python_bin(tmp_path)
    base_env = {
        **os.environ,
        "PYTHON_BIN": str(fake),
        "PLAYWRIGHT_SHARED_DB_PATH": str(shared),
        "PLAYWRIGHT_ADMIN_DB_PATH": str(admin),
        "REGENGINE_ENV": "development",
    }

    keep = dict(base_env, PLAYWRIGHT_PRESERVE_LOCAL_DB="1")
    proc = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env=keep, timeout=30)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert shared.read_text() == "sentinel-shared"
    assert admin.read_text() == "sentinel-admin"

    proc = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env=base_env, timeout=30)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "warning" in (proc.stdout + proc.stderr).lower()
    assert not shared.exists()
    assert not admin.exists()
