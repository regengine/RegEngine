"""Regression tests: setup_environment.sh must create a mode-600 .env and must
not append-duplicate variables on re-run.

Finding: a fresh `.env` copied from `.env.example` inherited a world-readable
mode, and SALESFORCE_INSTANCE_URL / MAILCHIMP_LIST_ID were written with
`echo "..." >> .env`, so every re-run appended a second copy of the line.
The fix runs `chmod 600` after the copy and routes both variables through
the existing `set_env_var` helper, which replaces in place.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

_SETUP = Path(__file__).resolve().parents[2] / "launch_orchestrator" / "scripts" / "setup_environment.sh"


def _body() -> str:
    return _SETUP.read_text()


def test_copy_of_env_example_is_followed_by_chmod_600():
    """The fresh .env holds secrets, so it must not stay world-readable."""
    lines = _body().splitlines()
    copy_at = next(i for i, line in enumerate(lines) if line.strip() == "cp .env.example .env")
    window = "\n".join(lines[copy_at : copy_at + 4])
    assert re.search(r"chmod\s+600\s+\.env\b", window), (
        "no `chmod 600 .env` right after `cp .env.example .env`; the new .env keeps whatever mode .env.example has"
    )


def test_no_direct_append_redirect_to_dotenv():
    """Every KEY=value write must go through set_env_var, which replaces."""
    offenders = [line.strip() for line in _body().splitlines() if re.search(r">>\s*\.env\b", line)]
    assert offenders == [], (
        f"direct `>> .env` appends duplicate the variable on re-run; use set_env_var instead: {offenders}"
    )


def test_both_repeatable_variables_use_the_setter():
    """SALESFORCE_INSTANCE_URL and MAILCHIMP_LIST_ID must be idempotent."""
    body = _body()
    for key in ("SALESFORCE_INSTANCE_URL", "MAILCHIMP_LIST_ID"):
        assert re.search(rf"set_env_var\s+{key}\b", body), f"{key} is not written through set_env_var"


def test_copy_then_chmod_produces_mode_600(tmp_path):
    """End to end: cp + chmod 600 under a permissive umask yields 0o600."""
    src = tmp_path / ".env.example"
    src.write_text("PLACEHOLDER=1\n")
    dst = tmp_path / ".env"
    old_umask = os.umask(0o022)
    try:
        script = f"set -e\ncp '{src}' '{dst}'\nchmod 600 '{dst}'\n"
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    finally:
        os.umask(old_umask)
    assert result.returncode == 0, result.stderr
    mode = stat.S_IMODE(dst.stat().st_mode)
    assert mode == 0o600, f"expected mode 600, got {oct(mode)}"


def test_setter_does_not_duplicate_on_rerun(tmp_path):
    """Calling the setter twice (a re-run) leaves exactly one line per key."""
    env_file = tmp_path / ".env"
    env_file.write_text("SALESFORCE_INSTANCE_URL=https://old.example\nMAILCHIMP_LIST_ID=old-list\n")
    script = f"""
    set -euo pipefail
    source '{_SETUP}' --source-only
    set_env_var SALESFORCE_INSTANCE_URL "https://new.example" '{env_file}'
    set_env_var SALESFORCE_INSTANCE_URL "https://new.example" '{env_file}'
    set_env_var MAILCHIMP_LIST_ID "new-list" '{env_file}'
    set_env_var MAILCHIMP_LIST_ID "new-list" '{env_file}'
    """
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, f"helper failed: {result.stderr}"
    text = env_file.read_text()
    for key, value in (
        ("SALESFORCE_INSTANCE_URL", "https://new.example"),
        ("MAILCHIMP_LIST_ID", "new-list"),
    ):
        assert text.splitlines().count(f"{key}={value}") == 1, f"{key} duplicated on re-run:\n{text}"
