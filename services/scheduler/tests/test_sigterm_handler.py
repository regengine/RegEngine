"""Regression test for #1255 — scheduler must trap SIGTERM on Railway deploys.

Railway and Kubernetes send SIGTERM (not SIGINT) when rolling a deploy.
Python's default SIGTERM disposition terminates the process without
running `finally` clauses, so the existing `try/except KeyboardInterrupt`
shutdown path in `SchedulerService.start` never got a chance to:
  - cancel in-flight APScheduler jobs (BlockingScheduler.shutdown)
  - flush the Kafka producer buffer
  - release the advisory lock

Installing a SIGTERM handler that raises KeyboardInterrupt lets the
existing shutdown path run on deploy.
"""

from __future__ import annotations

import os
import signal
import threading


def test_install_graceful_shutdown_handlers_registers_sigterm():
    """The main-thread SIGTERM handler must raise KeyboardInterrupt."""
    if threading.current_thread() is not threading.main_thread():
        # signal.signal() only works on the main thread; skip if we're not there.
        import pytest
        pytest.skip("signal.signal() requires main thread")

    import main as scheduler_main

    original_sigterm = signal.getsignal(signal.SIGTERM)
    original_sigint = signal.getsignal(signal.SIGINT)

    try:
        scheduler_main._install_graceful_shutdown_handlers()

        # After install, the SIGTERM handler must be the scheduler's own
        # function (not SIG_DFL / SIG_IGN / the original).
        new_sigterm = signal.getsignal(signal.SIGTERM)
        assert callable(new_sigterm), (
            "#1255: SIGTERM must be handled by a callable after "
            "_install_graceful_shutdown_handlers runs"
        )
        assert new_sigterm is not signal.SIG_DFL
        assert new_sigterm is not signal.SIG_IGN

        # Handler must translate into KeyboardInterrupt.
        import pytest
        with pytest.raises(KeyboardInterrupt):
            new_sigterm(signal.SIGTERM, None)
    finally:
        signal.signal(signal.SIGTERM, original_sigterm)
        signal.signal(signal.SIGINT, original_sigint)
