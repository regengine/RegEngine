"""Fail-closed release gate for the graph audit-buffer writer."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from services.scheduler.service import SchedulerService


def _service_stub():
    service = SchedulerService.__new__(SchedulerService)
    scheduled = []
    service._add_tracked_job = lambda *args, **kwargs: scheduled.append((args, kwargs))
    return service, scheduled


def test_disabled_graph_does_not_schedule_audit_replay(monkeypatch):
    monkeypatch.setenv("ENABLED_ROUTERS", "admin,fsma_compliance")
    reconciler = SimpleNamespace(
        get_interval_seconds=lambda: pytest.fail(
            "disabled graph audit replay must not import scheduler configuration"
        )
    )
    monkeypatch.setitem(
        sys.modules,
        "services.graph.app.audit_buffer_reconciler",
        reconciler,
    )
    service, scheduled = _service_stub()

    service._schedule_audit_buffer_reconcile()

    assert scheduled == []


def test_enabled_graph_registers_guarded_audit_replay(monkeypatch):
    monkeypatch.setenv("ENABLED_ROUTERS", "admin,graph")
    reconciler = SimpleNamespace(get_interval_seconds=lambda: 17)
    monkeypatch.setitem(
        sys.modules,
        "services.graph.app.audit_buffer_reconciler",
        reconciler,
    )
    service, scheduled = _service_stub()

    service._schedule_audit_buffer_reconcile()

    assert len(scheduled) == 1
    args, kwargs = scheduled[0]
    assert args[0] == service.reconcile_audit_buffer
    assert kwargs["job_id"] == "audit_buffer_reconcile"


def test_disabled_graph_refuses_direct_audit_replay(monkeypatch):
    monkeypatch.setenv("ENABLED_ROUTERS", "admin,fsma_compliance")
    reconciler = SimpleNamespace(
        run_reconcile_tick=lambda: pytest.fail(
            "disabled graph audit replay must not reach the primary writer"
        )
    )
    monkeypatch.setitem(
        sys.modules,
        "services.graph.app.audit_buffer_reconciler",
        reconciler,
    )
    service, _scheduled = _service_stub()

    service.reconcile_audit_buffer()


def test_enabled_graph_executes_audit_replay(monkeypatch):
    monkeypatch.setenv("ENABLED_ROUTERS", "graph")
    calls = []
    reconciler = SimpleNamespace(run_reconcile_tick=lambda: calls.append("tick"))
    monkeypatch.setitem(
        sys.modules,
        "services.graph.app.audit_buffer_reconciler",
        reconciler,
    )
    service, _scheduled = _service_stub()

    service.reconcile_audit_buffer()

    assert calls == ["tick"]
