"""Ensure ``services/ingestion`` is on sys.path so bare ``from app.X`` imports
resolve correctly when pytest collects from the repo root.

The root conftest.py provides a ``pytest_collectstart`` hook for this, but
``--import-mode=importlib`` can race ahead of the hook when conftest files are
imported.  Placing an explicit sys.path insert here runs at conftest-import
time, which is guaranteed to precede any test-module import in this directory.
"""
from __future__ import annotations

import sys
from contextlib import suppress
from pathlib import Path
from types import ModuleType

_service_dir = str(Path(__file__).resolve().parents[1])  # services/ingestion
if _service_dir not in sys.path:
    sys.path.insert(0, _service_dir)

_shared_dir = str(Path(__file__).resolve().parents[2] / "shared")
_regengine_ingestion_dir = str(Path(_service_dir) / "regengine_ingestion")
_REAL_MODULES: dict[str, ModuleType] = {}
_MODULE_ROOTS = (
    ("app", _service_dir),
    ("shared", _shared_dir),
    ("regengine_ingestion", _regengine_ingestion_dir),
    ("redis", ""),
)


def _evict_module(name: str) -> None:
    """Remove a module and detach it from its parent package, if any."""
    sys.modules.pop(name, None)

    parent_name, _, child_name = name.rpartition(".")
    if not parent_name:
        return

    parent = sys.modules.get(parent_name)
    if parent is None or not hasattr(parent, child_name):
        return

    with suppress(AttributeError):
        delattr(parent, child_name)


def _bind_module(name: str, module: ModuleType) -> None:
    """Install a module into sys.modules and reattach it to its parent."""
    sys.modules[name] = module

    parent_name, _, child_name = name.rpartition(".")
    if not parent_name:
        return

    parent = sys.modules.get(parent_name)
    if parent is not None:
        setattr(parent, child_name, module)


def _remember_real_module(name: str, module: ModuleType | None, expected_root: str) -> bool:
    """Cache real service/shared modules so we can restore them after stubs."""
    mod_file = str(getattr(module, "__file__", "") or "")
    mod_spec = getattr(module, "__spec__", None)
    if module is None or mod_spec is None:
        return False
    if expected_root and expected_root not in mod_file:
        return False
    _REAL_MODULES[name] = module
    return True


def _repair_package_links(prefix: str) -> None:
    """Reattach live submodules to their parent packages."""
    names = sorted(
        [k for k in sys.modules if k == prefix or k.startswith(f"{prefix}.")],
        key=lambda value: value.count("."),
    )
    for name in names:
        if "." not in name:
            continue
        parent_name, _, child_name = name.rpartition(".")
        parent = sys.modules.get(parent_name)
        child = sys.modules.get(name)
        if parent is not None and child is not None:
            setattr(parent, child_name, child)


def _purge_stale_modules() -> None:
    """Keep ingestion tests bound to the real ingestion ``app`` package.

    Some ingestion tests install synthetic ``app.*`` modules into sys.modules
    at import time. Those stubs are fine for the test module that created them,
    but they can poison later tests that expect the real ingestion package.
    We evict:
    - any ``app`` / ``shared`` module imported from outside the expected tree
    - synthetic stubs with no import spec
    """
    for prefix, expected_root in _MODULE_ROOTS:
        names = sorted(
            [k for k in sys.modules if k == prefix or k.startswith(f"{prefix}.")],
            key=lambda value: value.count("."),
            reverse=True,
        )
        for name in names:
            mod = sys.modules.get(name)
            if _remember_real_module(name, mod, expected_root):
                continue

            cached = _REAL_MODULES.get(name)
            if cached is not None:
                _bind_module(name, cached)
                continue

            _evict_module(name)

    for prefix, _expected_root in _MODULE_ROOTS:
        cached = _REAL_MODULES.get(prefix)
        if prefix not in sys.modules and cached is not None:
            _bind_module(prefix, cached)
        _repair_package_links(prefix)


_purge_stale_modules()


def pytest_runtest_setup(item):  # type: ignore[no-untyped-def]
    _purge_stale_modules()
