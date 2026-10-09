"""Exit-code regression tests for ``scripts/drain_graph_outbox.py``.

The audit found the drain script returned 0 (success) when Neo4j was
down, so cron reported a healthy drain that moved zero rows. The fix
splits the old combined early-return:

* sync intentionally disabled (no Neo4j configured) -> 0, nothing to do.
* sync enabled but the driver is unavailable (Neo4j down) -> non-zero
  so cron alerting fires and pending rows wait for the next cycle.

The ``driver unavailable`` case is the test that fails on the old code
(old code returned 0) and passes on the new code.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "drain_graph_outbox.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("drain_graph_outbox_exit_codes_under_test", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _install_stubs(monkeypatch, *, enabled, driver, summary):
    """Stub the delayed imports inside ``main`` so no DB or Neo4j is touched."""
    session = MagicMock(name="db_session")
    session_class = MagicMock(name="SessionLocal", return_value=session)

    drainer = MagicMock(name="drainer")
    drainer.drain_once.return_value = summary
    drainer_class = MagicMock(name="GraphOutboxDrainer", return_value=drainer)

    sync = MagicMock(name="supplier_graph_sync")
    sync.enabled = enabled
    sync.current_driver.return_value = driver

    database_mod = types.ModuleType("app.database")
    database_mod.SessionLocal = session_class
    graph_outbox_mod = types.ModuleType("app.graph_outbox")
    graph_outbox_mod.GraphOutboxDrainer = drainer_class
    sync_mod = types.ModuleType("app.supplier_graph_sync")
    sync_mod.supplier_graph_sync = sync
    tenant_ctx_mod = types.ModuleType("shared.neo4j_tenant_context")
    tenant_ctx_mod.session_with_tenant = MagicMock(name="session_with_tenant")

    monkeypatch.setitem(sys.modules, "app", types.ModuleType("app"))
    monkeypatch.setitem(sys.modules, "app.database", database_mod)
    monkeypatch.setitem(sys.modules, "app.graph_outbox", graph_outbox_mod)
    monkeypatch.setitem(sys.modules, "app.supplier_graph_sync", sync_mod)
    monkeypatch.setitem(sys.modules, "shared", types.ModuleType("shared"))
    monkeypatch.setitem(sys.modules, "shared.neo4j_tenant_context", tenant_ctx_mod)
    return {
        "session_class": session_class,
        "drainer_class": drainer_class,
        "drainer": drainer,
        "sync": sync,
    }


def test_driver_unavailable_exits_nonzero(monkeypatch):
    """Neo4j configured but down: must NOT exit 0 (fails on old code)."""
    module = _load_script_module()
    stubs = _install_stubs(
        monkeypatch,
        enabled=True,
        driver=None,
        summary={"claimed": 0, "drained": 0, "failed": 0, "rescheduled": 0},
    )
    assert module.main([]) != 0
    stubs["drainer_class"].assert_not_called()


def test_sync_disabled_still_exits_zero(monkeypatch):
    """No Neo4j configured on purpose: exit 0, nothing to drain."""
    module = _load_script_module()
    stubs = _install_stubs(
        monkeypatch,
        enabled=False,
        driver=None,
        summary={"claimed": 0, "drained": 0, "failed": 0, "rescheduled": 0},
    )
    assert module.main([]) == 0
    stubs["drainer_class"].assert_not_called()


def test_successful_drain_exits_zero(monkeypatch):
    module = _load_script_module()
    _install_stubs(
        monkeypatch,
        enabled=True,
        driver=object(),
        summary={"claimed": 2, "drained": 2, "failed": 0, "rescheduled": 0},
    )
    assert module.main([]) == 0


def test_failed_rows_exit_nonzero(monkeypatch):
    module = _load_script_module()
    _install_stubs(
        monkeypatch,
        enabled=True,
        driver=object(),
        summary={"claimed": 2, "drained": 1, "failed": 1, "rescheduled": 0},
    )
    assert module.main([]) == 2
