"""Regression tests for the multi-service pytest import switcher."""

import importlib.util
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType


def test_shared_module_loaded_through_admin_symlink_keeps_one_identity() -> None:
    """A symlinked shared module is real, not a stale module to re-import.

    Re-importing ``shared.tenant_context`` leaves already-imported functions
    holding an older ContextVar, which can make tenant-worker tests observe an
    unset tenant even though dispatch entered ``tenant_scope``.
    """

    repo_root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("regengine_root_conftest", repo_root / "conftest.py")
    assert spec and spec.loader
    root_conftest = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(root_conftest)
    module = ModuleType("shared.tenant_context")
    module.__file__ = str(repo_root / "services/admin/shared/tenant_context.py")
    module.__spec__ = ModuleSpec(module.__name__, loader=None)
    cache: dict[str, ModuleType] = {}

    remembered = root_conftest._remember_real_module(
        cache,
        module.__name__,
        module,
        str(repo_root / "services/shared"),
    )

    assert remembered is True
    assert cache[module.__name__] is module
