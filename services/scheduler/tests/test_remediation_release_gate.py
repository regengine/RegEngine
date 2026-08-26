"""Fail-closed release gate for remediation notification delivery."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from services.scheduler.service import SchedulerService


def _service_stub():
    service = SchedulerService.__new__(SchedulerService)
    service.settings = SimpleNamespace(remediation_outbox_drain_interval_seconds=30)
    scheduled = []
    service._add_tracked_job = lambda *args, **kwargs: scheduled.append((args, kwargs))
    return service, scheduled


def test_disabled_router_does_not_schedule_remediation_delivery(monkeypatch):
    monkeypatch.delenv("ENABLED_ROUTERS", raising=False)
    service, scheduled = _service_stub()

    service._schedule_remediation_notification_drain()

    assert scheduled == []


def test_enabled_router_registers_remediation_delivery(monkeypatch):
    monkeypatch.setenv("ENABLED_ROUTERS", "admin,remediation")
    service, scheduled = _service_stub()

    service._schedule_remediation_notification_drain()

    assert len(scheduled) == 1
    assert scheduled[0][1]["job_id"] == "remediation_notification_drain"


def test_disabled_router_refuses_direct_drain_execution(monkeypatch):
    monkeypatch.delenv("ENABLED_ROUTERS", raising=False)
    delivery = SimpleNamespace(
        drain_all_tenants=lambda _db: pytest.fail(
            "disabled remediation delivery must not reach its database drainer"
        )
    )
    monkeypatch.setitem(
        sys.modules,
        "services.ingestion.app.remediation.delivery",
        delivery,
    )
    service, _scheduled = _service_stub()

    service.drain_remediation_notifications()
