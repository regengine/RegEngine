"""Root pytest configuration.

Historically this file carried a per-test-module import flipper that evicted
and rebound ``app``/``main``/``shared`` modules so bare service imports
resolved during multi-service collection. That machinery is deleted: test
imports are canonical (``services.<svc>.app.*``), so one module identity
exists per service tree and no runtime switching is needed. Static
per-service ``sys.path`` inserts live in each service's tests/conftest.py
for the remaining bare-import stragglers and for
``--import-mode=importlib`` collection races.

One narrow guard remains: tests may install synthetic ``shared.*`` modules
into ``sys.modules`` (e.g. a stubbed ``shared.database``) for their own
import-time wiring. Without cleanup those stubs leak into later-collected
test modules. We evict any ``shared.*`` entry that is not the real module
cached at startup. ``app``/``main`` identity is deliberately NOT touched —
that is the whole point of the static-unified experiment.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent
_SERVICES_DIR = _REPO_ROOT / "services"
_SHARED_DIR = _SERVICES_DIR / "shared"


def _remember_real_shared_modules() -> dict[str, object]:
    """Snapshot the real ``shared`` package modules for later restore."""
    cache: dict[str, object] = {}
    try:
        import importlib

        for name in list(sys.modules):
            if name == "shared" or name.startswith("shared."):
                mod = sys.modules.get(name)
                mod_file = str(getattr(mod, "__file__", "") or "")
                if mod_file and str(_SHARED_DIR) in mod_file:
                    cache[name] = mod
        importlib.import_module("shared")
        for name in list(sys.modules):
            if (name == "shared" or name.startswith("shared.")) and name not in cache:
                mod = sys.modules.get(name)
                mod_file = str(getattr(mod, "__file__", "") or "")
                if mod_file and str(_SHARED_DIR) in mod_file:
                    cache[name] = mod
    except Exception:
        pass
    return cache


_REAL_SHARED_MODULES = _remember_real_shared_modules()


def _is_real_shared_module(mod: object) -> bool:
    """True when ``mod`` is the on-disk package under ``services/shared``.

    Synthetic stubs installed by tests have no ``__file__`` or point
    elsewhere. Real modules must NEVER be evicted: test modules bind
    ``shared.*`` objects at import time and monkeypatch them at run time:
    evicting a real module between those two moments splits module identity
    (patch lands on the test's binding, the handler lazy-imports a fresh
    unpatched object — the 1342-family 404s on the exp branch).
    """
    mod_file = str(getattr(mod, "__file__", "") or "")
    return bool(mod_file) and str(_SHARED_DIR) in mod_file


def _purge_synthetic_shared_modules() -> None:
    """Evict synthetic ``shared.*`` stubs; keep every real module's identity.

    Real-ness is anchored to the on-disk path, not startup-snapshot
    membership: a real module imported after the snapshot (e.g. at test-module
    import) is still real and must survive, or monkeypatch-by-object breaks.
    """
    for name in list(sys.modules):
        if name == "shared" or name.startswith("shared."):
            mod = sys.modules.get(name)
            if mod is None:
                continue
            if _is_real_shared_module(mod):
                continue
            if name in _REAL_SHARED_MODULES and _REAL_SHARED_MODULES[name] is mod:
                continue
            sys.modules.pop(name, None)
    for name, mod in _REAL_SHARED_MODULES.items():
        current = sys.modules.get(name)
        if current is mod:
            continue
        if current is None or not _is_real_shared_module(current):
            sys.modules[name] = mod  # type: ignore[assignment]


def _ensure_default_event_loop() -> None:
    """Keep legacy sync tests that call ``asyncio.get_event_loop()`` stable."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
        return

    if loop.is_closed():
        asyncio.set_event_loop(asyncio.new_event_loop())


@pytest.fixture(autouse=True)
def _reset_in_process_tenant_rate_limit_bucket():
    """Keep broad pytest runs from sharing anonymous TestClient rate buckets.

    Individual rate-limit tests still exercise blocking behavior inside a
    single test. This only clears state between tests, matching how isolated
    test processes behaved before the full-suite runner was wired up.
    """
    try:
        import shared.tenant_rate_limiting as tenant_rate_limiting

        tenant_rate_limiting._bucket = tenant_rate_limiting._InMemoryBucket()
    except Exception:
        pass


def pytest_collectstart(collector):  # type: ignore[no-untyped-def]
    _purge_synthetic_shared_modules()


def pytest_runtest_setup(item):  # type: ignore[no-untyped-def]
    _purge_synthetic_shared_modules()
    _ensure_default_event_loop()
