"""
kernel.obligation.routes was retired in #1366 (Option B).

The router had zero FastAPI ``include_router`` callers in-tree and carried
hardening defects documented in #1319. Tests that exercised it are replaced
by a single import-not-present guard here so the file doesn't silently
succeed or silently fail to collect.
"""

import importlib


def test_obligation_routes_module_does_not_exist() -> None:
    """Confirms kernel.obligation.routes was deleted as part of #1366."""
    try:
        importlib.import_module("kernel.obligation.routes")
        raise AssertionError(
            "kernel.obligation.routes still exists — it should have been "
            "deleted as part of #1366 (retire orphaned obligation router)."
        )
    except ModuleNotFoundError:
        pass  # expected
