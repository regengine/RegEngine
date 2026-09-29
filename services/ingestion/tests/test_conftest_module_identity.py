"""Keep shared module identities stable across service-local test collection."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_LOAD_CONFTEST = """
import importlib.util
import sys
from pathlib import Path

root = Path.cwd()
spec = importlib.util.spec_from_file_location(
    "ingestion_conftest_probe", root / "services/ingestion/tests/conftest.py"
)
conftest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(conftest)
"""


def _run_probe(script: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr


def test_admin_shared_symlink_preserves_exception_identity() -> None:
    _run_probe(
        """
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "services/admin"))
import shared.url_validation as original

assert "/admin/shared/" in original.__file__
original_error = original.SSRFError
"""
        + _LOAD_CONFTEST
        + """
import shared.url_validation as restored

assert restored is original, "cleanup replaced a genuine shared module"
assert restored.SSRFError is original_error
"""
    )


def test_cleanup_still_evicts_foreign_and_synthetic_modules() -> None:
    _run_probe(
        _LOAD_CONFTEST
        + """
from importlib.machinery import ModuleSpec
from types import ModuleType

foreign = ModuleType("app.foreign_probe")
foreign.__file__ = str(root / "services/admin/app/foreign_probe.py")
foreign.__spec__ = ModuleSpec(foreign.__name__, loader=None)
synthetic = ModuleType("app.synthetic_probe")
sys.modules[foreign.__name__] = foreign
sys.modules[synthetic.__name__] = synthetic

conftest._purge_stale_modules()

assert foreign.__name__ not in sys.modules
assert synthetic.__name__ not in sys.modules
"""
    )
