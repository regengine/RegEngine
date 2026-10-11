"""QA deep-pass: embedded-scheduler pure units (no threads, no scheduler import).

Covers server/workers/embedded_scheduler.py enable-flag parsing, leader
detection, engine disposal, service retirement, and stop() teardown paths.
Threaded bootstrap and re-election are covered by
tests/test_embedded_scheduler.py. Fast and deterministic.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from server.workers.embedded_scheduler import (
    EmbeddedSchedulerRunner,
    embedded_scheduler_enabled,
)


@pytest.mark.parametrize("raw", ["1", "true", "yes", "on", " True ", "YES"])
def test_flag_truthy_variants_enable(monkeypatch, raw):
    monkeypatch.setenv("SCHEDULER_EMBEDDED", raw)
    assert embedded_scheduler_enabled() is True


@pytest.mark.parametrize("raw", ["0", "false", "no", "off", "", "  "])
def test_flag_falsy_variants_disable(monkeypatch, raw):
    monkeypatch.setenv("SCHEDULER_EMBEDDED", raw)
    assert embedded_scheduler_enabled() is False


def test_unset_flag_follows_production_only(monkeypatch):
    monkeypatch.delenv("SCHEDULER_EMBEDDED", raising=False)
    monkeypatch.setenv("REGENGINE_ENV", "production")
    assert embedded_scheduler_enabled() is True
    monkeypatch.setenv("REGENGINE_ENV", "staging")
    assert embedded_scheduler_enabled() is False


def test_current_service_defaults_to_none():
    assert EmbeddedSchedulerRunner().current_service is None


@pytest.mark.parametrize(
    ("service", "expected"),
    [
        (None, False),
        (SimpleNamespace(), False),
        (SimpleNamespace(scheduler=SimpleNamespace()), False),
        (SimpleNamespace(scheduler=SimpleNamespace(running=False)), False),
        (SimpleNamespace(scheduler=SimpleNamespace(running=True)), True),
    ],
)
def test_is_leader_matrix(service, expected):
    runner = EmbeddedSchedulerRunner()
    runner._service = service
    assert runner.is_leader is expected


def test_dispose_engines_disposes_each_pool():
    state = SimpleNamespace(engine=MagicMock())
    dist = SimpleNamespace(engine=MagicMock())
    service = SimpleNamespace(state_manager=state, distributed_context=dist)
    EmbeddedSchedulerRunner._dispose_engines(service)
    state.engine.dispose.assert_called_once_with()
    dist.engine.dispose.assert_called_once_with()


def test_dispose_engines_skips_missing_and_swallows_errors():
    broken = MagicMock()
    broken.dispose.side_effect = RuntimeError("pool gone")
    service = SimpleNamespace(state_manager=SimpleNamespace(engine=broken))
    EmbeddedSchedulerRunner._dispose_engines(service)


def test_retire_service_clears_first_and_tears_down():
    runner = EmbeddedSchedulerRunner()
    service = MagicMock()
    runner._service = service
    runner._retire_service()
    assert runner._service is None
    assert runner.current_service is None
    assert runner.is_leader is False
    service.shutdown.assert_called_once_with()


def test_retire_service_without_service_is_noop():
    EmbeddedSchedulerRunner()._retire_service()


def test_retire_service_swallows_shutdown_errors():
    runner = EmbeddedSchedulerRunner()
    service = MagicMock()
    service.shutdown.side_effect = RuntimeError("stuck")
    runner._service = service
    runner._retire_service()
    assert runner._service is None


def test_stop_without_service_is_noop():
    EmbeddedSchedulerRunner().stop()


def test_stop_disposes_engines_even_for_standby():
    runner = EmbeddedSchedulerRunner()
    engine = MagicMock()
    service = SimpleNamespace(
        scheduler=SimpleNamespace(running=False),
        state_manager=SimpleNamespace(engine=engine),
    )
    runner._service = service
    runner.stop()
    engine.dispose.assert_called_once_with()
