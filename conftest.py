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
from pathlib import Path
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
}


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


def _switch_to_service(service: str) -> None:
    """Make ``services/<service>/`` the active site for the ``app`` package.

    Python caches imported packages in ``sys.modules``. If ``app`` was
    imported earlier from a sibling service, subsequent ``from app.X``
    imports will resolve against that stale package. Evict the cache and
    reorder ``sys.path`` so the fresh import resolves correctly.
    """
    service_dir = _SERVICES_DIR / service
    service_dir_str = str(service_dir)

    # Drop any cached ``app`` (and its submodules) so reimport uses the
    # correct service's app/ directory. Only evict entries that don't belong
    # to the current service (would be wasteful to reload things that are
    # already correct).
    stale = [name for name in sys.modules if name == "app" or name.startswith("app.")]
    for name in stale:
        mod = sys.modules.get(name)
        mod_file = getattr(mod, "__file__", None) or ""
        if mod_file and str(service_dir) in mod_file:
            continue
        sys.modules.pop(name, None)

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
    path = Path(str(fspath))
    service = _service_for_path(path)
    if service is not None:
        _switch_to_service(service)
