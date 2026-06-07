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

import asyncio
import os
import re
import sys
from contextlib import suppress
from pathlib import Path
from types import ModuleType
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parent
_SERVICES_DIR = _REPO_ROOT / "services"

# Known services that expose their own top-level ``app/`` package.
_APP_BEARING_SERVICES = ("admin", "compliance", "graph", "ingestion", "nlp", "scheduler")

# Tests under top-level ``tests/`` that reach into a specific service via
# bare ``from app.X`` imports. The conftest flips sys.path to the named
# service before the test module is imported so ``app`` resolves correctly.
# Keys are path suffixes (as shipped, always POSIX); values are service
# names from ``_APP_BEARING_SERVICES``.
_TEST_TO_SERVICE_OVERRIDES = {
    "tests/billing/test_stripe_billing.py": "ingestion",
    "tests/billing/test_stripe_webhook_ordering_1196.py": "ingestion",
    "tests/contract/test_admin_api_contract.py": "admin",
    "tests/ingestion/test_ingest_url.py": "ingestion",
    "tests/security/test_audit_integrity.py": "admin",
    "tests/security/test_strict_ciam_compliance.py": "admin",
    "tests/test_trace_engine.py": "ingestion",
    "tests/test_compliance_control_plane_e2e.py": "ingestion",
    "tests/test_rules_engine.py": "ingestion",
    "tests/test_rules_engine_unit.py": "ingestion",
    "tests/graph/test_hierarchy_builder_global_scope.py": "graph",
}
_KNOWN_SERVICE_MODULES: dict[str, dict[str, ModuleType]] = {service: {} for service in _APP_BEARING_SERVICES}
_KNOWN_SHARED_MODULES: dict[str, ModuleType] = {}


def _service_from_module_file(module: ModuleType | None) -> Optional[str]:
    """Infer which service owns an imported ``app`` module."""
    mod_file = str(getattr(module, "__file__", "") or "")
    if not mod_file:
        return None

    for service in _APP_BEARING_SERVICES:
        service_root = str(_SERVICES_DIR / service)
        if service_root and service_root in mod_file:
            return service
    return None


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
    _prepare_service_test_environment(service)

    # Drop any cached bare ``main`` and ``app`` (plus app submodules) so
    # reimport uses the correct service. Several service-local tests import
    # ``from main import app`` at module scope, so only evicting ``app.*`` is
    # not enough during full-suite collection.
    stale = sorted(
        [name for name in sys.modules if name == "main" or name == "app" or name.startswith("app.")],
        key=lambda value: value.count("."),
        reverse=True,
    )
    for name in stale:
        mod = sys.modules.get(name)
        owner_service = _service_from_module_file(mod)
        owner_cache = _KNOWN_SERVICE_MODULES.setdefault(owner_service, {}) if owner_service else None
        if owner_cache is not None:
            remembered = _remember_real_module(
                owner_cache,
                name,
                mod,
                str(_SERVICES_DIR / owner_service),
            )
            if remembered and owner_service == service:
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

    if "main" not in sys.modules and (cached_main := service_cache.get("main")) is not None:
        _bind_module("main", cached_main)
    if "app" not in sys.modules and (cached_app := service_cache.get("app")) is not None:
        _bind_module("app", cached_app)
    if "shared" not in sys.modules and (cached_shared := _KNOWN_SHARED_MODULES.get("shared")) is not None:
        _bind_module("shared", cached_shared)

    # Restore the full cached module tree for the active service, not just
    # names that happened to overlap with the previously active service.
    # Without this, switching from e.g. scheduler -> admin restores ``app``
    # but not deeper admin-only modules like ``app.erasure_routes``;
    # a later import rebuilds those as fresh module objects, so test-time
    # patches hit a different module identity than the already-collected
    # router/handler objects.
    for name, cached in sorted(service_cache.items(), key=lambda item: item[0].count(".")):
        _bind_module(name, cached)

    for prefix in ("app", "shared"):
        _repair_package_links(prefix)

    # Remove other service dirs from sys.path so only the current one wins
    # when ``app`` is (re-)imported.
    sys.path[:] = [
        p for p in sys.path if not any(p == str(_SERVICES_DIR / s) for s in _APP_BEARING_SERVICES if s != service)
    ]

    # Place this service's dir at position 0.
    if service_dir_str in sys.path:
        sys.path.remove(service_dir_str)
    sys.path.insert(0, service_dir_str)


def _prepare_service_test_environment(service: str) -> None:
    """Reset env that service-local tests expect before module import.

    Some suites mutate process-wide env with plain ``os.environ`` assignments.
    When pytest collects multiple services in one process, those mutations can
    leak into later service imports. Compliance tests import ``main.app`` at
    module scope and rely on test-mode API-key bypass, so pin its import-time
    environment whenever the compliance service becomes active.
    """
    if service != "compliance":
        return

    os.environ["REGENGINE_ENV"] = "test"
    os.environ["ENVIRONMENT"] = "test"
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    os.environ.setdefault("AUTH_TEST_BYPASS_TOKEN", "test-bypass-token-for-pytest")
    os.environ.setdefault("AUTH_SECRET_KEY", "test-secret-key-for-pytest")


def _ensure_default_event_loop() -> None:
    """Keep legacy sync tests that call ``asyncio.get_event_loop()`` stable."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
        return

    if loop.is_closed():
        asyncio.set_event_loop(asyncio.new_event_loop())


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


def pytest_runtest_setup(item):  # type: ignore[no-untyped-def]
    """Switch service import context again before each test executes.

    Collection-time switching is not sufficient because many tests perform
    ``from app.X import ...`` imports inside the test body or fixture setup.
    Without a runtime refresh, the final collected service can leave a stale
    ``app`` package active in ``sys.modules``/``sys.path`` and poison later
    tests that pass in isolation.
    """
    item_path = getattr(item, "path", None) or getattr(item, "fspath", None)
    if item_path is None:
        return
    _activate_service_for_path(Path(str(item_path)))
    _ensure_default_event_loop()
