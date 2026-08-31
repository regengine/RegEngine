"""Embedded scheduler — runs SchedulerService inside the consolidated monolith.

Closes the production wiring gap where scheduler jobs (FDA recall /
warning-letter / import-alert scrapers, recall→tenant compliance alerting,
deadline monitoring, retention/archival, the nightly FSMA source sync) ran
nowhere: production is a single Railway container serving
``gunicorn server.main:app``, and the standalone
``services/scheduler/main.py`` entrypoint refuses to boot there
(``assert_legacy_entrypoint_not_in_production``).

Multi-worker safety: gunicorn runs ``WEB_CONCURRENCY`` (default 4) Uvicorn
workers, and every worker's lifespan starts this runner. Exactly one
worker across all workers AND replicas wins the PostgreSQL advisory lock
(``services/scheduler/app/distributed.py``, lock id 4294967295) and runs
the jobs; the rest hold a one-connection standby poll (5s interval). When
the leader dies, PostgreSQL releases the lock at session end and a standby
is promoted.

Enabled by default only when ``shared.env.is_production()`` is true;
override either way with ``SCHEDULER_EMBEDDED=1/0``. Dev and pytest stay
off by default so a local API run never starts scraping FDA — local dev
keeps using the standalone entrypoint.
"""

from __future__ import annotations

import os
import threading
from typing import Optional

import structlog

logger = structlog.get_logger("server.embedded_scheduler")


def embedded_scheduler_enabled() -> bool:
    """SCHEDULER_EMBEDDED env flag, defaulting to on in production only."""
    raw = os.getenv("SCHEDULER_EMBEDDED")
    if raw is not None:
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    from shared.env import is_production

    return is_production()


class EmbeddedSchedulerRunner:
    """Owns the daemon thread running leadership election + the job loop."""

    # Pause before re-entering leadership election after the workload
    # returns unexpectedly (leadership lost via the #1142 heartbeat, or a
    # crash). Standalone mode relies on Railway restarting the process for
    # this; embedded, the runner re-enters election itself.
    _REELECTION_DELAY_SECONDS = 30.0

    def __init__(self) -> None:
        self._service = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            name="embedded-scheduler",
            daemon=True,
        )
        self._thread.start()

    # SchedulerService attributes that own a SQLAlchemy Engine. Each
    # engine holds its own pool, so a service that is dropped without
    # ``dispose()`` leaks those connections until the process exits
    # (#2882): DistributedContext at pool_size=2/max_overflow=1 and
    # StateManager at pool_size=5/max_overflow=10 — up to 18 connections
    # stranded per leadership flap, per gunicorn worker.
    _ENGINE_OWNING_ATTRS = ("state_manager", "distributed_context")

    @classmethod
    def _dispose_engines(cls, service) -> None:
        """Dispose every SQLAlchemy pool a retired service owns (#2882).

        ``SchedulerService.shutdown()`` closes the APScheduler, the Kafka
        producer and the webhook HTTP session, but nothing disposes its
        two engines — and those files are outside this module. Reach in
        from here rather than leaking the pools.
        """
        for attr in cls._ENGINE_OWNING_ATTRS:
            engine = getattr(getattr(service, attr, None), "engine", None)
            if engine is None:
                continue
            try:
                engine.dispose()
                logger.info("embedded_scheduler_engine_disposed", component=attr)
            except Exception as exc:  # noqa: BLE001 — teardown must not raise
                logger.warning(
                    "embedded_scheduler_engine_dispose_failed",
                    component=attr,
                    error=str(exc),
                )

    def _retire_service(self) -> None:
        """Fully tear down the current service before it is replaced (#2882).

        Called at the top of every election pass. A no-op on the first
        pass; on every re-election it shuts the previous service down and
        disposes its pools.

        Why replace rather than reuse: a ``SchedulerService`` owns a
        ``BlockingScheduler`` whose ``ThreadPoolExecutor`` is built once
        in ``__init__``. Restarting a shut-down APScheduler *appears* to
        work (``scheduler.running`` flips back to True) but every job
        submission then dies with ``RuntimeError: cannot schedule new
        futures after shutdown`` — a re-elected leader would hold the
        advisory lock and silently run zero jobs. Rebuilding is correct;
        the leak was only ever the missing teardown of the old one.
        """
        service = self._service
        if service is None:
            return
        # Clear first: `current_service` / `is_leader` must not hand out a
        # service that is mid-teardown.
        self._service = None
        try:
            service.shutdown()
        except Exception as exc:  # noqa: BLE001 — teardown must not raise
            logger.warning("embedded_scheduler_service_shutdown_failed", error=str(exc))
        self._dispose_engines(service)
        logger.info("embedded_scheduler_service_retired")

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                from services.scheduler.service import SchedulerService

                # #2882: release the previous pass's service (engines,
                # Kafka producer, HTTP session) before building its
                # replacement. No-op on the first pass.
                self._retire_service()
                self._service = SchedulerService()
            except Exception:
                # Misconfiguration (e.g. SCHEDULER_API_KEY unset while
                # REGENGINE_ENV=production — see services/scheduler/app/
                # config.py S-3 guard) must never take down the API.
                # Loud log + Sentry, API keeps serving; retrying won't fix
                # a config error, so exit the thread.
                logger.exception("embedded_scheduler_init_failed")
                return
            try:
                # Blocks: standby poll until the advisory lock is won, then
                # BlockingScheduler.start() for as long as we stay leader.
                self._service.start()
            except Exception:
                logger.exception("embedded_scheduler_crashed")
            if self._stop_event.is_set():
                return
            # start() returned without a stop request: leadership was lost
            # (#1142 heartbeat shut the scheduler down) or the workload
            # crashed. Rejoin the standby pool after a pause — otherwise
            # this worker would permanently stop being a leader candidate.
            logger.warning(
                "embedded_scheduler_reentering_election",
                delay_seconds=self._REELECTION_DELAY_SECONDS,
            )
            self._stop_event.wait(self._REELECTION_DELAY_SECONDS)

    @property
    def current_service(self):
        """The ``SchedulerService`` this worker constructed, or None.

        NOTE: a non-None value does NOT imply this worker is the leader —
        every worker constructs a service then blocks on the standby poll.
        Use :pyattr:`is_leader` to tell whether the live circuit-breaker /
        last-scrape state on the service is actually being driven here.
        """
        return self._service

    @property
    def thread_alive(self) -> bool:
        """True while the runner's daemon thread is running (#2697).

        The thread exits permanently on an init/config failure (see
        ``_run``); /readiness uses this to surface a dead scheduler thread
        instead of reporting ``ok`` forever off the start-time success.
        """
        thread = self._thread
        return bool(thread is not None and thread.is_alive())

    @property
    def is_leader(self) -> bool:
        """True only when this worker holds the advisory lock and its
        APScheduler is running (i.e. it is the one driving the jobs)."""
        service = self._service
        if service is None:
            return False
        return bool(getattr(getattr(service, "scheduler", None), "running", False))

    def stop(self) -> None:
        """Best-effort teardown on lifespan shutdown.

        Only the leader has a running APScheduler to stop. A standby
        thread is parked in the advisory-lock poll loop with no stop
        signal — it is a daemon thread and dies with the process, and
        PostgreSQL releases the advisory lock when its session ends.
        """
        self._stop_event.set()
        service = self._service
        if service is None:
            return
        try:
            if getattr(service.scheduler, "running", False):
                # wait=False: don't block gunicorn's graceful-timeout window
                # on in-flight scrapes; jobs are emit-then-ack idempotent.
                service.scheduler.shutdown(wait=False)
        except Exception as exc:
            logger.warning("embedded_scheduler_stop_failed", error=str(exc))
        # #2882: hand the connection pools back on the way out. Note this
        # deliberately does NOT call ``service.shutdown()`` — that waits
        # for in-flight jobs and would eat the graceful-timeout window.
        # ``dispose()`` only closes *idle* pooled connections, so a
        # connection the standby-poll thread still holds is untouched.
        self._dispose_engines(service)


def start_embedded_scheduler() -> Optional[EmbeddedSchedulerRunner]:
    """Start the embedded scheduler if enabled; returns the runner or None."""
    if not embedded_scheduler_enabled():
        logger.info("embedded_scheduler_disabled")
        return None
    runner = EmbeddedSchedulerRunner()
    runner.start()
    logger.info("embedded_scheduler_started")
    return runner
