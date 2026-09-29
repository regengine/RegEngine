"""Shared fixtures for contract tests."""

import sys

import pytest


@pytest.fixture(autouse=True)
def _clear_admin_brute_force_state(monkeypatch):
    """Isolate local auth counters without reading or deleting Redis data."""
    for module_name in ("app.privileged_auth", "services.admin.app.privileged_auth"):
        module = sys.modules.get(module_name)
        throttle = getattr(module, "_privileged_auth_throttle", None) if module else None
        if throttle is None:
            continue
        monkeypatch.setattr(module, "_privileged_auth_throttle", module.PrivilegedAuthThrottle(redis_client=None))
