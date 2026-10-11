"""Break tests: leadership lost during startup must not start the scheduler.

The heartbeat clears ``_is_leader`` and asks the scheduler to shut down.
Shutdown raises SchedulerNotRunningError when ``start()`` has not been
called yet, which is the whole initial-scrape window. The exception is
swallowed and the heartbeat thread exits. If the workload then calls
``start()`` anyway, this process runs jobs with nobody left watching the
lock. A standby that already acquired the released lock runs too.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

from app.distributed import DistributedContext
from app.models import SourceType
from apscheduler.schedulers.base import SchedulerNotRunningError
from service import SchedulerService


class _Conn:
    def __init__(self, script):
        self._script = list(script)

    def execution_options(self, **_kwargs):
        return self

    def execute(self, _query, _params=None):
        result = MagicMock()
        result.scalar.return_value = self._script.pop(0) if self._script else None
        return result

    def close(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Engine:
    """Main thread gets the lock once. Heartbeat probes always see it gone."""

    def connect(self):
        if threading.current_thread().name.startswith("scheduler-leader-heartbeat"):
            return _Conn([0])
        return _Conn([True, 4242, None])


class _Scheduler:
    def __init__(self):
        self.started = False

    def shutdown(self, wait=True):
        if not self.started:
            raise SchedulerNotRunningError()
        self.started = False

    def start(self):
        self.started = True


def _context() -> DistributedContext:
    ctx = DistributedContext.__new__(DistributedContext)
    ctx.database_url = "postgresql://fake"
    ctx._is_leader = False
    ctx._leader_pid = None
    ctx._heartbeat_stop = threading.Event()
    ctx._heartbeat_thread = None
    ctx.engine = _Engine()
    return ctx


def _service(ctx: DistributedContext) -> SchedulerService:
    svc = SchedulerService.__new__(SchedulerService)
    svc.distributed_context = ctx
    svc.scheduler = _Scheduler()
    svc.schedule_jobs = lambda: None
    return svc


class TestLeadershipLostBeforeStart:
    def test_loss_during_initial_scrape_does_not_start_scheduler(self):
        ctx = _context()
        svc = _service(ctx)

        def initial_scrape():
            # The real initial scrape blocks on FDA for much longer than
            # the heartbeat. Wait until the heartbeat has declared the
            # lock gone, then return as a finished scrape would.
            for _ in range(400):
                if not ctx._is_leader:
                    return
                time.sleep(0.01)
            raise AssertionError("heartbeat never cleared leadership")

        svc.run_initial_scrape = initial_scrape

        ctx.wait_for_leadership(
            svc._run_scheduler_workload,
            on_leadership_lost=svc._on_leadership_lost,
            poll_interval=0,
            heartbeat_interval_seconds=0.01,
            heartbeat_max_failures=2,
        )

        assert svc.scheduler.started is False, (
            "scheduler.start() ran after leadership was lost during startup. "
            "shutdown() cannot stop a scheduler that is not running, so the "
            "workload must refuse to start it."
        )
        assert ctx._is_leader is False

    def test_initial_scrape_stops_when_leadership_drops(self):
        ctx = _context()
        ctx._is_leader = True
        svc = _service(ctx)
        ran: list[SourceType] = []

        def run_scraper(source_type: SourceType) -> None:
            ran.append(source_type)
            ctx._is_leader = False

        svc.run_scraper = run_scraper
        svc.scrapers = {
            SourceType.FDA_RECALL: (None, None),
            SourceType.FDA_WARNING_LETTER: (None, None),
            SourceType.FDA_IMPORT_ALERT: (None, None),
        }

        svc.run_initial_scrape()

        assert ran == [SourceType.FDA_RECALL], (
            f"after the lock is lost, later startup scrapes must not run. ran={ran!r}"
        )
