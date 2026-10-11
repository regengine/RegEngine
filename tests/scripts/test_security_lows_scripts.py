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


def _load_module():
    """Import the scenario without letting it touch the process env.

    The script must not copy .env into os.environ at import (#3230), so
    importing it here is safe for the rest of the pytest process.
    """
    spec = importlib.util.spec_from_file_location("_e2e_brutal_scenario_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_committed_password_reset_sql_is_gone():
    """scripts/utilities/fix_password.sql carried a live argon2id hash for
    admin@example.com. It must not come back."""
    assert not (REPO_ROOT / "scripts" / "utilities" / "fix_password.sql").exists()


def test_e2e_scenario_has_no_fallback_internal_secret():
    """No default secret may be committed next to the env lookup."""
    source = SCRIPT.read_text()
    assert "trusted-internal-v1" not in source


def test_e2e_import_does_not_write_dotenv_into_process_env():
    """Importing the script must not assign .env keys into os.environ.

    The loader used to run at import time, leaking REGENGINE_INTERNAL_SECRET
    and DATABASE_URL into any pytest process that collected this module.
    The write may only happen inside a function body now.
    """
    import ast

    tree = ast.parse(SCRIPT.read_text())
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        assert "environ" not in ast.dump(node), (
            "top-level statement touches os.environ; .env loading must stay inside a function"
        )


def test_e2e_headers_use_env_secret(monkeypatch):
    module = _load_module()
    monkeypatch.setenv("REGENGINE_INTERNAL_SECRET", "sentinel-internal-secret")
    headers = module.build_headers()
    assert headers["X-RegEngine-Internal-Secret"] == "sentinel-internal-secret"


def test_e2e_headers_refuse_to_run_without_env_secret(monkeypatch):
    module = _load_module()
    monkeypatch.delenv("REGENGINE_INTERNAL_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="REGENGINE_INTERNAL_SECRET"):
        module.build_headers()
