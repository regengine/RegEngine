"""Legacy compliance sweep must not arm CI auto-fix without explicit opt-in."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"

AUTO_FIX_ENV = "REGENGINE_CI_AUTO_FIX"


def _load():
    name = "compliance_sweep_under_test"
    if name in sys.modules:
        del sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / "compliance_sweep.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class _FakeSwarm:
    """Minimal stand-in for AgentSwarm that records auto-fix state at sweep time."""

    def __init__(self, seen: dict) -> None:
        self._seen = seen

    async def sweep(self, tasks, concurrency: int = 10):  # noqa: ANN001, ANN201, ARG002
        import os

        self._seen["auto_fix_at_sweep"] = os.environ.get(AUTO_FIX_ENV)
        self._seen["task_count"] = len(tasks)
        return []


def _install_fakes(monkeypatch, mod, seen: dict):
    monkeypatch.setattr(mod, "AgentSwarm", lambda *args, **kwargs: _FakeSwarm(seen))
    monkeypatch.setattr(mod, "legacy_swarm_enabled", lambda: True)


def test_default_run_does_not_enable_auto_fix(monkeypatch) -> None:
    mod = _load()
    seen: dict = {}
    _install_fakes(monkeypatch, mod, seen)
    monkeypatch.delenv(AUTO_FIX_ENV, raising=False)

    asyncio.run(mod.roll_out_compliance())

    import os

    assert os.environ.get(AUTO_FIX_ENV) != "true"
    assert seen["auto_fix_at_sweep"] != "true"
    assert seen["task_count"] == len(mod.SERVICES)


def test_explicit_opt_in_enables_auto_fix(monkeypatch) -> None:
    mod = _load()
    seen: dict = {}
    _install_fakes(monkeypatch, mod, seen)
    monkeypatch.delenv(AUTO_FIX_ENV, raising=False)

    asyncio.run(mod.roll_out_compliance(auto_fix=True))

    import os

    assert os.environ.get(AUTO_FIX_ENV) == "true"
    assert seen["auto_fix_at_sweep"] == "true"
