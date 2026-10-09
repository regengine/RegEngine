"""Regression tests for scripts/generate_redis_certs.sh (audit medium #50).

The defect: every openssl invocation ended in `2>/dev/null`, so a failed
certificate generation looked fine until Redis refused to start, and nothing
stopped unencrypted private keys from landing in a tracked, committable
directory (the default `./certs/redis` is only safe because of the `certs/`
rule in .gitignore).

The fix: openssl errors are surfaced (no silenced stderr), the generated
artifacts are verified before the script reports success, and the script
refuses to write to any in-repo location that is not gitignored.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "generate_redis_certs.sh"


def _run_script(cert_dir: Path, *, cwd: Path, path_prefix: str | None = None, timeout: int = 300):
    env = dict(os.environ)
    env["CERT_DIR"] = str(cert_dir)
    if path_prefix is not None:
        env["PATH"] = f"{path_prefix}{os.pathsep}{env['PATH']}"
    return subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        cwd=str(cwd),
        timeout=timeout,
    )


def test_openssl_stderr_is_not_silenced():
    """No openssl invocation may discard its error output.

    Fails against the pre-fix script, which appended `2>/dev/null` to
    every openssl command.
    """
    openssl_lines = [
        line for line in SCRIPT.read_text().splitlines() if "openssl" in line and not line.lstrip().startswith("#")
    ]
    assert openssl_lines, "script no longer invokes openssl?"
    for line in openssl_lines:
        assert "2>/dev/null" not in line, f"openssl error output is hidden, failed certs look fine: {line.strip()}"


def test_failing_openssl_aborts_with_a_visible_error(tmp_path):
    """A failing openssl must exit non-zero AND say why on stderr.

    Runs with a stub openssl that always fails. Fails against the pre-fix
    script: `set -e` still aborted, but `2>/dev/null` swallowed the reason
    so stderr was empty.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "openssl"
    stub.write_text('#!/usr/bin/env bash\necho "openssl stub: req: error: simulated failure" >&2\nexit 1\n')
    stub.chmod(0o755)

    proc = _run_script(tmp_path / "certs", cwd=tmp_path, path_prefix=str(bin_dir))

    assert proc.returncode != 0, "script reported success despite openssl failing"
    assert proc.stderr.strip() != "", "script hid the openssl failure; nothing on stderr explains the abort"
    assert "simulated failure" in proc.stderr


def test_refuses_an_in_repo_location_that_is_not_gitignored():
    """Unencrypted keys must never land in a tracked directory.

    Fails against the pre-fix script, which wrote wherever CERT_DIR
    pointed with no gitignore check. Uses a scratch dir inside the repo
    (removed afterwards) that .gitignore does not cover.
    """
    probe = REPO_ROOT / ".tmp-redis-certs-guard-probe"
    if probe.exists():
        shutil.rmtree(probe)
    try:
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", str(probe / "redis.key")],
            cwd=str(REPO_ROOT),
            capture_output=True,
            timeout=60,
        )
        assert ignored.returncode != 0, "probe dir is unexpectedly gitignored"

        proc = _run_script(probe, cwd=REPO_ROOT)
        assert proc.returncode != 0, "script wrote unencrypted keys to a tracked in-repo location"
        assert "gitignored" in proc.stderr, f"refusal should explain the gitignore problem:\n{proc.stderr}"
    finally:
        if probe.exists():
            shutil.rmtree(probe)


def test_default_cert_dir_stays_gitignored():
    """The default ./certs/redis must remain covered by .gitignore."""
    proc = subprocess.run(
        ["git", "check-ignore", "-q", "certs/redis/redis.key"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        timeout=60,
    )
    assert proc.returncode == 0, "default CERT_DIR ./certs/redis is not gitignored; generated keys could be committed"


def test_happy_path_generates_verifiable_certs_with_private_keys(tmp_path):
    """End-to-end with the real openssl: certs verify and keys are 0600."""
    if shutil.which("openssl") is None:
        import pytest

        pytest.skip("openssl not available")
    cert_dir = tmp_path / "certs"
    proc = _run_script(cert_dir, cwd=tmp_path)
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    for name in ("ca.crt", "ca.key", "redis.crt", "redis.key"):
        assert (cert_dir / name).exists(), f"missing {name}:\n{proc.stdout}\n{proc.stderr}"
    for name in ("ca.key", "redis.key"):
        mode = stat.S_IMODE((cert_dir / name).stat().st_mode)
        assert mode == 0o600, f"{name} has mode {oct(mode)}, expected 0o600"

    verify = subprocess.run(
        ["openssl", "verify", "-CAfile", str(cert_dir / "ca.crt"), str(cert_dir / "redis.crt")],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert verify.returncode == 0, verify.stderr
    assert "OK" in verify.stdout
