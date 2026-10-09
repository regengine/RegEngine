"""Regression tests for the scheduler split-brain finding.

After a database failover PostgreSQL releases the old leader's advisory
lock server-side and a standby acquires it, while the old leader keeps
running scrapers until its heartbeat notices. Two fixes bound that
window:

1. The heartbeat default is shortened so a lost lock is noticed within
   about 15s instead of up to ~45s (interval x max failures).
2. ``SchedulerService._process_new_items`` re-checks leadership
   synchronously (``DistributedContext.verify_leadership``) before any
   emission and skips the batch when the lock is gone, leaving items
   un-marked so the true leader emits them on its next tick.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from app.distributed import (
    _DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    _DEFAULT_HEARTBEAT_MAX_FAILURES,
    DistributedContext,
)

from services.scheduler.app.models import (
    EnforcementItem,
    EnforcementSeverity,
    SourceType,
)


def test_heartbeat_worst_case_detection_window_bounded():
    """The async detection window must stay well under the old ~45s."""
    window = _DEFAULT_HEARTBEAT_INTERVAL_SECONDS * _DEFAULT_HEARTBEAT_MAX_FAILURES
    assert window <= 15, (
        f"heartbeat worst-case detection window is {window}s "
        "(interval x max failures); a deposed leader can double-emit "
        "for that whole window"
    )


# ---------------------------------------------------------------------------
# verify_leadership unit tests (scripted engine, no database needed).
# ---------------------------------------------------------------------------


class _ProbeConn:
    def __init__(self, scalar_value):
        self._value = scalar_value

    def execution_options(self, **_kw):
        return self

    def execute(self, _query, _params=None):
        result = MagicMock()
        result.scalar.return_value = self._value
        return result

    def close(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _ProbeEngine:
    def __init__(self, entry):
        self._entry = entry
        self.connects = 0

    def connect(self):
        self.connects += 1
        if isinstance(self._entry, BaseException):
            raise self._entry
        return _ProbeConn(self._entry)


def _ctx(is_leader: bool, pid, probe_entry) -> DistributedContext:
    ctx = DistributedContext.__new__(DistributedContext)
    ctx._is_leader = is_leader
    ctx._leader_pid = pid
    ctx.engine = _ProbeEngine(probe_entry)
    return ctx


class TestVerifyLeadership:
    def test_lock_held_returns_true(self):
        ctx = _ctx(True, 1234, 1)
        assert ctx.verify_leadership() is True

    def test_lock_missing_returns_false(self):
        ctx = _ctx(True, 1234, None)
        assert ctx.verify_leadership() is False

    def test_database_error_fails_closed_without_raising(self):
        ctx = _ctx(True, 1234, ConnectionError("db unreachable"))
        assert ctx.verify_leadership() is False

    def test_not_leader_returns_false_without_touching_db(self):
        ctx = _ctx(False, 1234, 1)
        assert ctx.verify_leadership() is False
        assert ctx.engine.connects == 0

    def test_claim_without_pid_trusts_flag(self):
        # leadership_claim records no backend pid; nothing to re-verify.
        ctx = _ctx(True, None, ConnectionError("must not be called"))
        assert ctx.verify_leadership() is True
        assert ctx.engine.connects == 0


# ---------------------------------------------------------------------------
# Pre-emit guard tests (full SchedulerService with stubbed dependencies).
# ---------------------------------------------------------------------------


def _item(source_id: str = "split-brain:001") -> EnforcementItem:
    return EnforcementItem(
        source_type=SourceType.FDA_WARNING_LETTER,
        source_id=source_id,
        title="Warning letter",
        url="https://example.com/wl/001",
        published_date=datetime(2026, 4, 17, tzinfo=timezone.utc),
        severity=EnforcementSeverity.HIGH,
    )


def _svc():
    from services.scheduler import service as scheduler_service

    with (
        patch.object(scheduler_service, "get_kafka_producer", return_value=MagicMock()),
        patch.object(scheduler_service, "WebhookNotifier", return_value=MagicMock()),
        patch.object(scheduler_service, "DistributedContext", return_value=MagicMock()),
        patch.object(scheduler_service, "StateManager", return_value=MagicMock()),
        patch.object(scheduler_service, "FDAImportAlertsScraper", return_value=MagicMock()),
        patch.object(scheduler_service, "FDARecallsScraper", return_value=MagicMock()),
        patch.object(scheduler_service, "FDAWarningLettersScraper", return_value=MagicMock()),
        patch.object(scheduler_service, "BlockingScheduler", return_value=MagicMock()),
    ):
        svc = scheduler_service.SchedulerService()
    return svc


@pytest.fixture(autouse=True)
def kafka_backbone(monkeypatch):
    """Exercise the Kafka emission path these tests assert about."""
    monkeypatch.setenv("EVENT_BACKBONE", "kafka")


class TestPreEmitGuard:
    def test_deposed_leader_skips_emission(self):
        """The core split-brain case: pid recorded, lock gone in pg_locks."""
        svc = _svc()
        svc.distributed_context = _ctx(True, 1234, None)
        svc.kafka_producer.emit_batch.return_value = (1, 0)
        svc.kafka_producer.emit_fsma_batch.return_value = (0, 0)
        svc.notifier.notify.return_value = []

        svc._process_new_items([_item()], SourceType.FDA_WARNING_LETTER)

        svc.kafka_producer.emit_batch.assert_not_called()
        svc.notifier.notify.assert_not_called()
        svc.state_manager.mark_seen.assert_not_called()

    def test_healthy_leader_emits_normally(self):
        svc = _svc()
        svc.distributed_context = _ctx(True, 1234, 1)
        svc.kafka_producer.emit_batch.return_value = (1, 0)
        svc.kafka_producer.emit_fsma_batch.return_value = (0, 0)
        svc.notifier.notify.return_value = []

        svc._process_new_items([_item()], SourceType.FDA_WARNING_LETTER)

        svc.kafka_producer.emit_batch.assert_called_once()
        svc.state_manager.mark_seen.assert_called_once()

    def test_no_election_never_blocks(self):
        """Standalone runs and unit-test setups (no pid recorded) behave
        exactly as before: no database probe, emission proceeds."""
        svc = _svc()
        ctx = _ctx(False, None, ConnectionError("must not be called"))
        svc.distributed_context = ctx
        svc.kafka_producer.emit_batch.return_value = (1, 0)
        svc.kafka_producer.emit_fsma_batch.return_value = (0, 0)
        svc.notifier.notify.return_value = []

        svc._process_new_items([_item()], SourceType.FDA_WARNING_LETTER)

        svc.kafka_producer.emit_batch.assert_called_once()
        assert ctx.engine.connects == 0
