"""Regression tests for scripts/demo_mvp_flow.sh API key handling.

The defect: the script took the API key as a command-line argument
(`API_KEY="${1:-}"`), so the key was retained in shell history and stayed
visible in process lists. The fix reads the key only from the
REGENGINE_API_KEY environment variable or from a secure interactive prompt,
and refuses command-line arguments outright.

Every value that looks like a key below is a sentinel, never a real secret.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "demo_mvp_flow.sh"


def _executable_lines():
    """Non-comment, non-empty lines of the script."""
    return [line for line in SCRIPT.read_text().splitlines() if line.strip() and not line.lstrip().startswith("#")]


def _run_script(*args, env_extra=None, stdin_data=None):
    env = dict(os.environ)
    env.pop("REGENGINE_API_KEY", None)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        ["bash", str(SCRIPT), *args],
        env=env,
        input=stdin_data,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc


def test_api_key_never_comes_from_positional_params():
    """No executable line may assign the API key from $1, $* or $@.

    Fails against the pre-fix script, which contained API_KEY="${1:-}".
    The $1 uses that remain (echo helpers) never feed API_KEY.
    """
    for line in _executable_lines():
        if "API_KEY" in line:
            assert not re.search(r"\$(1|\*|@)", line), f"API key taken from a command-line argument: {line!r}"


def test_help_text_no_longer_advertises_a_key_argument():
    """Usage must point at the env var, not at a positional argument."""
    source = SCRIPT.read_text()
    assert "REGENGINE_API_KEY" in source
    assert "[API_KEY]" not in source
    assert "demo_mvp_flow.sh <tenant-scoped-api-key>" not in source


def test_key_falls_back_to_a_silent_prompt():
    """With no env var, an interactive run must prompt without echoing."""
    source = SCRIPT.read_text()
    assert "read -rsp" in source or "read -rs" in source, (
        "expected a silent (read -s) interactive prompt for the API key"
    )


def test_positional_api_key_is_rejected_before_any_network_use():
    """Passing the key as an argument must fail fast with guidance.

    Fails against the pre-fix script, which accepted $1 as the key and
    proceeded to the Step 0 health checks.
    """
    proc = _run_script(
        "sentinel-arg-key",
        env_extra={"ADMIN_URL": "http://127.0.0.1:1", "INGEST_URL": "http://127.0.0.1:1"},
        stdin_data="",
    )
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0
    assert "command-line argument" in combined
    assert "REGENGINE_API_KEY" in combined
    assert "Checking service health" not in combined


def test_missing_key_error_points_at_env_or_prompt():
    """Without any key, the error must not mention passing one as an argument."""
    source = SCRIPT.read_text()
    assert "Usage: ./scripts/demo_mvp_flow.sh <tenant-scoped-api-key>" not in source
