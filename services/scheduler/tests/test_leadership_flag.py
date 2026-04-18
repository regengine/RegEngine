"""Regression tests for #1162 — wait_for_leadership must set `_is_leader`.

`DistributedContext.leadership_claim` correctly sets `self._is_leader = True`
when it acquires the PostgreSQL advisory lock, so any `is_leader()` check
inside the context manager sees True.

But the other entry point — `wait_for_leadership` — only acquired the
lock and invoked `callback()` without setting `_is_leader`. Every
`is_leader()` guard inside the callback-driven scheduled jobs (the path
used by `app/jobs.py` and by `SchedulerService._run_scheduler_workload`)
therefore returned False. Jobs like the FSMA nightly sync silently
skipped even when the instance WAS the leader.

These tests drive `wait_for_leadership` with a fake engine to confirm:
1. Inside the callback, `_is_leader` is True.
2. After the callback returns, `_is_leader` is back to False.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.distributed import DistributedContext


def _make_ctx_with_fake_engine(lock_returns: bool = True) -> DistributedContext:
    """Construct a DistributedContext without touching pydantic settings."""
    ctx = DistributedContext.__new__(DistributedContext)
    ctx.database_url = "postgresql://fake"
    ctx._is_leader = False

    fake_result = MagicMock()
    fake_result.scalar.return_value = lock_returns

    fake_conn = MagicMock()
    fake_conn.execute.return_value = fake_result
    fake_conn.execution_options.return_value = fake_conn

    fake_engine = MagicMock()
    fake_engine.connect.return_value = fake_conn

    ctx.engine = fake_engine
    return ctx


class TestLeadershipFlagInWaitForLeadership:

    def test_is_leader_true_during_callback(self):
        ctx = _make_ctx_with_fake_engine(lock_returns=True)

        observed = {"leader_during_callback": None}

        def cb():
            observed["leader_during_callback"] = ctx._is_leader

        ctx.wait_for_leadership(cb, poll_interval=0)

        assert observed["leader_during_callback"] is True, (
            "#1162: wait_for_leadership must set _is_leader=True before "
            "invoking the callback"
        )

    def test_is_leader_false_after_callback(self):
        ctx = _make_ctx_with_fake_engine(lock_returns=True)

        def cb():
            pass

        ctx.wait_for_leadership(cb, poll_interval=0)

        assert ctx._is_leader is False, (
            "After the leader callback exits, _is_leader must be cleared "
            "so subsequent checks do not falsely report leadership"
        )

    def test_is_leader_false_if_callback_raises(self):
        """Even when the callback crashes, the leader flag must be cleared.

        The callback exception is logged and the function returns via the
        inner `finally` (the `return` inside the finally suppresses the
        propagating exception — an existing code-path quirk). What
        matters for #1162 is that `_is_leader` does NOT stay True after
        the callback crashes — otherwise anything else in the process
        sees a zombie leader flag.
        """
        ctx = _make_ctx_with_fake_engine(lock_returns=True)

        class Boom(Exception):
            pass

        observed = {"leader_at_raise": None}

        def cb():
            observed["leader_at_raise"] = ctx._is_leader
            raise Boom("crashed")

        # wait_for_leadership returns normally because the `finally`
        # block's `return` suppresses the propagating exception.
        ctx.wait_for_leadership(cb, poll_interval=0)

        assert observed["leader_at_raise"] is True, (
            "While callback was running, _is_leader must be True"
        )
        assert ctx._is_leader is False, (
            "After callback raises, _is_leader must be cleared "
            "in the finally block"
        )
