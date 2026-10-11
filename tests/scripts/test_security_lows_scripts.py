"""Security lows batch: committed credential file stays gone, and the brutal
E2E scenario requires its internal secret from the environment.

Every credential-looking value below is a sentinel, never a real secret.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "e2e_brutal_scenario.py"

_SPEC = importlib.util.spec_from_file_location("_e2e_brutal_scenario_under_test", SCRIPT)
assert _SPEC and _SPEC.loader
_module = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _module
_SPEC.loader.exec_module(_module)


def test_committed_password_reset_sql_is_gone():
    """scripts/utilities/fix_password.sql carried a live argon2id hash for
    admin@example.com. It must not come back."""
    assert not (REPO_ROOT / "scripts" / "utilities" / "fix_password.sql").exists()


def test_e2e_scenario_has_no_fallback_internal_secret():
    """No default secret may be committed next to the env lookup."""
    source = SCRIPT.read_text()
    assert "trusted-internal-v1" not in source


def test_e2e_headers_use_env_secret(monkeypatch):
    monkeypatch.setenv("REGENGINE_INTERNAL_SECRET", "sentinel-internal-secret")
    headers = _module.build_headers()
    assert headers["X-RegEngine-Internal-Secret"] == "sentinel-internal-secret"


def test_e2e_headers_refuse_to_run_without_env_secret(monkeypatch):
    monkeypatch.delenv("REGENGINE_INTERNAL_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="REGENGINE_INTERNAL_SECRET"):
        _module.build_headers()
