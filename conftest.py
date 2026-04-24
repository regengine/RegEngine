"""Root pytest configuration.

This conftest exists to solve the multi-service ``app/`` collision problem:
the repo has multiple service packages under ``services/<svc>/`` each with an
``app/`` subpackage. When pytest collects tests across services, only one
``app`` can live in ``sys.modules`` at a time, so tests from the "other"
service fail with ``ModuleNotFoundError: No module named 'app.X'``.

The fix: hook into pytest's collection so that immediately before we import a
test module, we detect which service owns it and (a) invalidate the cached
``app`` module, (b) reorder ``sys.path`` so that service's directory wins.

This keeps feature code untouched while letting the full test suite collect
in a single ``pytest`` run.
"""
from __future__ import annotations

import re
import sys
from contextlib import suppress
from pathlib import Path
from types import ModuleType
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parent
_SERVICES_DIR = _REPO_ROOT / "services"

# Known services that expose their own top-level ``app/`` package.
_APP_BEARING_SERVICES = ("admin", "graph", "ingestion", "nlp", "scheduler")

# Tests under top-level ``tests/`` that reach into a specific service via
# bare ``from app.X`` imports. The conftest flips sys.path to the named
# service before the test module is imported so ``app`` resolves correctly.
# Keys are path suffixes (as shipped, always POSIX); values are service
# names from ``_APP_BEARING_SERVICES``.
_TEST_TO_SERVICE_OVERRIDES = {
    "tests/billing/test_stripe_billing.py": "ingestion",
    "tests/billing/test_stripe_webhook_ordering_1196.py": "ingestion",
    "tests/security/test_audit_integrity.py": "admin",
    "tests/security/test_strict_ciam_compliance.py": "admin",
    "tests/test_trace_engine.py": "ingestion",
    "tests/test_compliance_control_plane_e2e.py": "ingestion",
    "tests/test_rules_engine.py": "ingestion",
    "tests/test_rules_engine_unit.py": "ingestion",
    "tests/graph/test_hierarchy_builder_global_scope.py": "graph",
}
_KNOWN_SERVICE_MODULES: dict[str, dict[str, ModuleType]] = {
    service: {} for service in _APP_BEARING_SERVICES
}
_KNOWN_SHARED_MODULES: dict[str, ModuleType] = {}


def _evict_module(name: str) -> None:
    """Remove a module and detach any lingering package attribute."""
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
    """Install a cached real module and reattach it to its parent package."""
    sys.modules[name] = module

    parent_name, _, child_name = name.rpartition(".")
    if not parent_name:
        return

    parent = sys.modules.get(parent_name)
    if parent is not None:
        setattr(parent, child_name, module)


def _remember_real_module(
    cache: dict[str, ModuleType],
    name: str,
    module: ModuleType | None,
    expected_root: str,
) -> bool:
    """Cache real modules so later stub cleanup can restore them."""
    mod_file = str(getattr(module, "__file__", "") or "")
    mod_spec = getattr(module, "__spec__", None)
    if module is None or mod_spec is None:
        return False
    if expected_root and expected_root not in mod_file:
        return False
    cache[name] = module
    return True


def _repair_package_links(prefix: str) -> None:
    """Reattach submodules to their live parent packages."""
    names = sorted(
        [name for name in sys.modules if name == prefix or name.startswith(f"{prefix}.")],
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


def _service_for_path(path: Path) -> Optional[str]:
    """Return the service name owning ``path``, or ``None`` if unowned."""
    try:
        rel = path.resolve().relative_to(_SERVICES_DIR)
    except ValueError:
        rel = None

    if rel is not None:
        parts = rel.parts
        if parts and parts[0] in _APP_BEARING_SERVICES:
            return parts[0]

    # Check top-level tests/* overrides.
    try:
        rel_root = path.resolve().relative_to(_REPO_ROOT)
    except ValueError:
        return None
    key = rel_root.as_posix()
    return _TEST_TO_SERVICE_OVERRIDES.get(key)


def _activate_service_for_path(path: Path) -> None:
    """Flip import context for any test path owned by a service."""
    service = _service_for_path(path)
    if service is not None:
        _switch_to_service(service)


def _switch_to_service(service: str) -> None:
    """Make ``services/<service>/`` the active site for the ``app`` package.

    Python caches imported packages in ``sys.modules``. If ``app`` was
    imported earlier from a sibling service, subsequent ``from app.X``
    imports will resolve against that stale package. Evict the cache and
    reorder ``sys.path`` so the fresh import resolves correctly.
    """
    service_dir = _SERVICES_DIR / service
    service_dir_str = str(service_dir)
    service_cache = _KNOWN_SERVICE_MODULES.setdefault(service, {})

    # Drop any cached ``app`` (and its submodules) so reimport uses the
    # correct service's app/ directory. Only evict entries that don't belong
    # to the current service (would be wasteful to reload things that are
    # already correct).
    stale = sorted(
        [name for name in sys.modules if name == "app" or name.startswith("app.")],
        key=lambda value: value.count("."),
        reverse=True,
    )
    for name in stale:
        mod = sys.modules.get(name)
        if _remember_real_module(service_cache, name, mod, str(service_dir)):
            continue

        cached = service_cache.get(name)
        if cached is not None:
            _bind_module(name, cached)
            continue

        _evict_module(name)

    # Also evict ``shared.*`` entries that resolved from an unknown/stale
    # location (e.g. loaded before sys.path was correct).  If the module
    # file is not under the current services dir, evict it so it re-resolves.
    _shared_dir = str(_SERVICES_DIR / "shared")
    stale_shared = sorted(
        [name for name in sys.modules if name == "shared" or name.startswith("shared.")],
        key=lambda value: value.count("."),
        reverse=True,
    )
    for name in stale_shared:
        mod = sys.modules.get(name)
        if _remember_real_module(_KNOWN_SHARED_MODULES, name, mod, _shared_dir):
            continue  # already correct

        cached = _KNOWN_SHARED_MODULES.get(name)
        if cached is not None:
            _bind_module(name, cached)
            continue

        _evict_module(name)

    if "app" not in sys.modules and (cached_app := service_cache.get("app")) is not None:
        _bind_module("app", cached_app)
    if "shared" not in sys.modules and (cached_shared := _KNOWN_SHARED_MODULES.get("shared")) is not None:
        _bind_module("shared", cached_shared)

    for prefix in ("app", "shared"):
        _repair_package_links(prefix)

    # Remove other service dirs from sys.path so only the current one wins
    # when ``app`` is (re-)imported.
    sys.path[:] = [
        p for p in sys.path
        if not any(
            p == str(_SERVICES_DIR / s) for s in _APP_BEARING_SERVICES if s != service
        )
    ]

    # Place this service's dir at position 0.
    if service_dir_str in sys.path:
        sys.path.remove(service_dir_str)
    sys.path.insert(0, service_dir_str)


def pytest_collectstart(collector):  # type: ignore[no-untyped-def]
    """Pytest hook: called before each collector (module/file) runs.

    For test modules under ``services/<svc>/`` or in the overrides table,
    flip sys.path/sys.modules so ``from app.X`` resolves inside that
    service's ``app/`` tree.
    """
    fspath = getattr(collector, "path", None) or getattr(collector, "fspath", None)
    if fspath is None:
        return
    _activate_service_for_path(Path(str(fspath)))


def pytest_collect_file(file_path, path, parent):  # type: ignore[no-untyped-def]
    """Switch service import context before pytest creates a file collector."""
    _activate_service_for_path(Path(str(file_path)))
    return None


def pytest_pycollect_makemodule(module_path, path, parent):  # type: ignore[no-untyped-def]
    """Switch service import context immediately before module import."""
    _activate_service_for_path(Path(str(module_path)))
    return None
