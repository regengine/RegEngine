"""Regression tests for the low audit bundle — ``leadership_claim`` standby path.

``leadership_claim`` is a ``@contextlib.contextmanager``. The old
implementation looped and yielded once per poll while in standby, but a
context manager may only yield once: exiting the ``with`` block after a
standby yield raised ``RuntimeError: generator didn't stop``. The standby
loop was dead code that crashed on use.
"""

from __future__ import annotations

from unittest.mock import MagicMock

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


class TestLeadershipClaim:
    def test_standby_yields_false_and_exits_cleanly(self):
        ctx = _make_ctx_with_fake_engine(lock_returns=False)

        with ctx.leadership_claim(poll_interval=0) as is_leader:
            assert is_leader is False
            assert ctx._is_leader is False

        # Exiting the with-block must not raise, and the flag stays False.
        assert ctx._is_leader is False

    def test_leader_yields_true_and_releases_on_exit(self):
        ctx = _make_ctx_with_fake_engine(lock_returns=True)

        with ctx.leadership_claim(poll_interval=0) as is_leader:
            assert is_leader is True
            assert ctx._is_leader is True

        assert ctx._is_leader is False
