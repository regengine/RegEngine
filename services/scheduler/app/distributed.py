"""Distributed coordination for high-availability scheduler components.

Implements Leader Election pattern using PostgreSQL Advisory Locks to ensure
only one scheduler instance is active at a time (Active-Standby).
"""

import contextlib
import threading
import time
from typing import Callable, Generator, Optional

import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from .config import get_settings

logger = structlog.get_logger("scheduler.distributed")

# Constant lock ID for the scheduler leader (arbitrary large integer)
# ensuring it doesn't collide with other application locks.
SCHEDULER_LEADER_LOCK_ID = 4294967295  # Max uint32

# ── #1142: heartbeat defaults ────────────────────────────────────────────────
# Without a heartbeat, `wait_for_leadership` acquires the advisory lock,
# starts the scheduler callback, and never re-checks the lock. If the
# connection dies server-side (network partition, DB failover, proxy reset,
# long GC pause) PostgreSQL auto-releases the lock at session end — a standby
# can then acquire it while the old "leader" still runs scrapers. That's a
# double-leader window with duplicate emissions.
#
# The heartbeat runs in a daemon thread on a SEPARATE short-lived connection
# and verifies our backend pid still holds the lock via ``pg_locks``. On
# three consecutive failures (either the lock is gone OR we can't reach the
# DB) we invoke ``on_leadership_lost`` so the caller can gracefully shut the
# scheduler down and let the orchestrator restart us.
_DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 15.0
_DEFAULT_HEARTBEAT_MAX_FAILURES = 3
_HEARTBEAT_SHUTDOWN_JOIN_TIMEOUT_SECONDS = 5.0


class DistributedContext:
    """Manages distributed leadership via database locks."""

    def __init__(self, database_url: Optional[str] = None):
        settings = get_settings()
        self.database_url = database_url or settings.database_url
        self.engine = create_engine(
            self.database_url,
            pool_pre_ping=True,
            # We use a separate pool for the lock to ensure the connection
            # stays open as long as we hold leadership.
            pool_size=1,
            max_overflow=0,
            connect_args={"keepalives": 1, "keepalives_idle": 30}
        )
        self._is_leader = False
        # #1142: heartbeat state. ``_leader_pid`` is the backend pid we
        # recorded at acquisition time — the heartbeat checks pg_locks
        # for exactly that pid. ``_heartbeat_stop`` is an Event the main
        # thread sets to tell the heartbeat thread to exit.
        self._leader_pid: Optional[int] = None
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None

    @contextlib.contextmanager
    def leadership_claim(self, poll_interval: int = 5) -> Generator[bool, None, None]:
        """Attempt to acquire and hold leadership.

        Yields True if leader, False otherwise. This is a blocking context manager
        that runs a keep-alive loop.

        Args:
            poll_interval: Seconds to wait between lock acquisition attempts.
        """
        connection = None
        try:
            while True:
                try:
                    if not connection:
                        connection = self.engine.connect()
                        # Set autocommit isolation to ensure lock acquisition is immediate
                        connection.execution_options(isolation_level="AUTOCOMMIT")

                    # Try to acquire advisory lock (non-blocking)
                    # pg_try_advisory_lock returns true if lock obtained, false otherwise
                    result = connection.execute(
                        text("SELECT pg_try_advisory_lock(:lock_id)"),
                        {"lock_id": SCHEDULER_LEADER_LOCK_ID}
                    ).scalar()

                    if result:
                        if not self._is_leader:
                            logger.info("leadership_acquired", lock_id=SCHEDULER_LEADER_LOCK_ID)
                            self._is_leader = True

                        yield True
                        return

                    else:
                        if self._is_leader:
                            logger.warn("leadership_lost", lock_id=SCHEDULER_LEADER_LOCK_ID)
                            self._is_leader = False

                        logger.debug("leadership_poll_standby", lock_id=SCHEDULER_LEADER_LOCK_ID)
                        yield False

                        # Wait before retrying (effectively creating a standby loop)
                        time.sleep(poll_interval)

                except SQLAlchemyError as e:
                    logger.error("database_connection_error", error=str(e))
                    if connection:
                        try:
                            connection.close()
                        except Exception as close_error:
                            logger.error("connection_close_failed", error=str(close_error))
                        connection = None
                    time.sleep(poll_interval)

        finally:
            if connection:
                try:
                    # Release lock if we held it
                    if self._is_leader:
                         connection.execute(
                            text("SELECT pg_advisory_unlock(:lock_id)"),
                            {"lock_id": SCHEDULER_LEADER_LOCK_ID}
                        )
                         logger.info("leadership_released", lock_id=SCHEDULER_LEADER_LOCK_ID)
                    connection.close()
                except Exception as e:
                    logger.error("error_releasing_lock", error=str(e))
                self._is_leader = False

    def wait_for_leadership(
        self,
        callback: Callable[[], None],
        poll_interval: int = 5,
        *,
        on_leadership_lost: Optional[Callable[[], None]] = None,
        heartbeat_interval_seconds: float = _DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        heartbeat_max_failures: int = _DEFAULT_HEARTBEAT_MAX_FAILURES,
    ) -> None:
        """Blocking call that waits for leadership then runs ``callback``.

        Sets ``self._is_leader`` to True for the duration of ``callback``
        and clears it in the ``finally`` block, so ``app.leadership.is_leader()``
        (which reads the same flag) returns accurate values from inside
        callback-driven jobs. Without this (#1162), every ``is_leader()``
        guard in the module-level scheduled jobs silently skipped because
        the flag was only ever set by :meth:`leadership_claim`.

        #1142 — while ``callback`` is running we also spawn a daemon
        heartbeat thread that periodically verifies our PostgreSQL
        backend pid still holds the advisory lock. If that check fails
        (the DB session died, a failover released our lock, or we can't
        reach the DB) after ``heartbeat_max_failures`` consecutive
        attempts, we:
            1. Clear ``self._is_leader`` (so any concurrent
               ``is_leader()`` readers see False immediately).
            2. Call ``on_leadership_lost`` — typically a
               ``BlockingScheduler.shutdown(wait=False)`` wrapper — so
               the main thread can unwind the callback cleanly.
            3. Exit the heartbeat thread.

        Parameters
        ----------
        callback:
            Blocking function to run while we hold leadership.
        poll_interval:
            Seconds between lock-acquisition attempts when in standby.
        on_leadership_lost:
            Called from the heartbeat thread when we detect leadership
            loss. Expected to arrange a clean shutdown of the callback.
            If ``None``, heartbeat failure still clears ``_is_leader``
            and logs loudly but does not signal the main thread — the
            callback will continue until it exits on its own.
        heartbeat_interval_seconds:
            Polling cadence of the heartbeat. Default 15s — every 30s
            check wastes cycles; every 5s could add meaningful DB load
            in a large cluster.
        heartbeat_max_failures:
            Consecutive heartbeat failures tolerated before declaring
            leadership lost. Default 3 — tolerates transient blips.
        """
        # #1142: defensive lazy init — older code paths construct the
        # context via ``DistributedContext.__new__`` (e.g. the #1162 test
        # helper) which skips ``__init__``. Keep the heartbeat wiring
        # self-healing so we don't crash on a missing attribute.
        if not hasattr(self, "_heartbeat_stop"):
            self._heartbeat_stop = threading.Event()
        if not hasattr(self, "_heartbeat_thread"):
            self._heartbeat_thread = None
        if not hasattr(self, "_leader_pid"):
            self._leader_pid = None

        logger.info("entering_leadership_election_loop")

        # We need a dedicated connection that stays open
        while True:
            conn = None
            try:
                conn = self.engine.connect()
                conn.execution_options(isolation_level="AUTOCOMMIT")

                while True:
                    # Try to get lock
                    got_lock = conn.execute(
                        text("SELECT pg_try_advisory_lock(:lock_id)"),
                        {"lock_id": SCHEDULER_LEADER_LOCK_ID}
                    ).scalar()

                    if got_lock:
                        # #1142: stash our backend pid so the heartbeat
                        # thread can verify the lock still belongs to us.
                        try:
                            self._leader_pid = conn.execute(
                                text("SELECT pg_backend_pid()")
                            ).scalar()
                        except Exception as pid_err:
                            # If we can't get our pid, the heartbeat
                            # can't do its job reliably. Log loudly but
                            # continue — skipping heartbeat is strictly
                            # worse than no-heartbeat (this PR's prior
                            # state). We log and proceed; op will see
                            # the warning.
                            logger.warning(
                                "leader_pid_fetch_failed_heartbeat_disabled",
                                error=str(pid_err),
                            )
                            self._leader_pid = None

                        logger.info(
                            "leadership_acquired_running_scheduler",
                            leader_pid=self._leader_pid,
                        )
                        # #1162 — publish our leader state BEFORE running the
                        # callback so any is_leader() gates inside the
                        # callback see True.
                        self._is_leader = True

                        # #1142: start heartbeat thread.
                        self._heartbeat_stop.clear()
                        if self._leader_pid is not None:
                            self._heartbeat_thread = threading.Thread(
                                target=self._run_heartbeat,
                                args=(
                                    self._leader_pid,
                                    heartbeat_interval_seconds,
                                    heartbeat_max_failures,
                                    on_leadership_lost,
                                ),
                                name="scheduler-leader-heartbeat",
                                daemon=True,
                            )
                            self._heartbeat_thread.start()
                        else:
                            self._heartbeat_thread = None

                        try:
                            # Run the actual scheduler workload
                            # This callback should block (e.g. valid for BlockingScheduler)
                            # If it returns, we release lock (or maybe we lost connection?)
                            callback()
                        except Exception as e:
                            logger.error("scheduler_crashed", error=str(e))
                            raise e
                        finally:
                            # #1142: stop heartbeat BEFORE clearing state
                            # so the heartbeat thread doesn't race with a
                            # tear-down that would look like "lock lost".
                            self._heartbeat_stop.set()
                            if self._heartbeat_thread is not None:
                                self._heartbeat_thread.join(
                                    timeout=_HEARTBEAT_SHUTDOWN_JOIN_TIMEOUT_SECONDS
                                )
                                if self._heartbeat_thread.is_alive():
                                    # Daemon thread — OK to leave behind,
                                    # but log so we don't silently leak.
                                    logger.warning(
                                        "heartbeat_thread_did_not_exit_in_time",
                                    )
                                self._heartbeat_thread = None
                            self._leader_pid = None
                            # Clear the flag first — even if unlock fails or
                            # raises, no subsequent is_leader() call should
                            # incorrectly report True.
                            self._is_leader = False
                            # If callback finishes, we unlock
                            try:
                                conn.execute(
                                    text("SELECT pg_advisory_unlock(:lock_id)"),
                                    {"lock_id": SCHEDULER_LEADER_LOCK_ID}
                                )
                                logger.info("leadership_released_callback_finished")
                            except Exception as unlock_err:
                                logger.error(
                                    "leadership_unlock_failed",
                                    error=str(unlock_err),
                                )
                            return  # Exit loop if callback finishes intentionally

                    else:
                        logger.info("standby_mode_waiting_for_lock")
                        # Keep _is_leader honest even during poll periods.
                        self._is_leader = False
                        time.sleep(poll_interval)
                        # Connection is still open, we loop and retry

            except SQLAlchemyError as e:
                logger.error("db_connection_lost_retrying", error=str(e))
                self._is_leader = False
                if conn:
                    try:
                        conn.close()
                    except Exception as close_error:
                        logger.error("leadership_conn_close_failed", error=str(close_error))
                # Exponential backoff?
                time.sleep(poll_interval)
            except Exception as e:
                logger.exception("unexpected_error_in_election", error=str(e))
                self._is_leader = False
                # Avoid tight loop on crash
                time.sleep(poll_interval)

    # ── #1142: heartbeat implementation ────────────────────────────────────
    def _run_heartbeat(
        self,
        leader_pid: int,
        interval_seconds: float,
        max_failures: int,
        on_leadership_lost: Optional[Callable[[], None]],
    ) -> None:
        """Daemon-thread loop that verifies we still hold the advisory lock.

        Uses a SEPARATE short-lived engine connection for each probe — the
        leader's own connection is not thread-safe and is tied up with
        scheduler queries. Querying ``pg_locks`` for our ``leader_pid``
        tells us whether PG still recognizes the session that acquired
        the lock. If that session died (network partition, failover), the
        row is gone, and we know we've lost leadership even though the
        main thread hasn't noticed yet.

        Exits when ``self._heartbeat_stop`` is set OR after ``max_failures``
        consecutive failures, whichever comes first.
        """
        consecutive_failures = 0
        logger.info(
            "leadership_heartbeat_started",
            leader_pid=leader_pid,
            interval_seconds=interval_seconds,
            max_failures=max_failures,
        )

        while not self._heartbeat_stop.wait(interval_seconds):
            try:
                with self.engine.connect() as hb_conn:
                    hb_conn.execution_options(isolation_level="AUTOCOMMIT")
                    result = hb_conn.execute(
                        text(
                            """
                            SELECT 1 FROM pg_locks
                            WHERE locktype = 'advisory'
                              AND pid = :leader_pid
                              AND objid = :lock_id
                              AND classid = 0
                            LIMIT 1
                            """
                        ),
                        {
                            "leader_pid": leader_pid,
                            "lock_id": SCHEDULER_LEADER_LOCK_ID,
                        },
                    ).scalar()
            except Exception as exc:  # noqa: BLE001 - intentional catch-all
                consecutive_failures += 1
                logger.warning(
                    "leadership_heartbeat_query_failed",
                    leader_pid=leader_pid,
                    error=str(exc),
                    consecutive_failures=consecutive_failures,
                    max_failures=max_failures,
                )
                if consecutive_failures >= max_failures:
                    logger.error(
                        "leadership_heartbeat_exhausted_declaring_lost",
                        leader_pid=leader_pid,
                        consecutive_failures=consecutive_failures,
                    )
                    self._signal_leadership_lost(on_leadership_lost, leader_pid)
                    return
                continue

            if result == 1:
                if consecutive_failures > 0:
                    logger.info(
                        "leadership_heartbeat_recovered",
                        leader_pid=leader_pid,
                        prior_failures=consecutive_failures,
                    )
                consecutive_failures = 0
                logger.debug(
                    "leadership_heartbeat_ok",
                    leader_pid=leader_pid,
                )
                continue

            consecutive_failures += 1
            logger.warning(
                "leadership_heartbeat_lock_missing",
                leader_pid=leader_pid,
                consecutive_failures=consecutive_failures,
                max_failures=max_failures,
                note=(
                    "pg_locks shows no advisory lock for our backend pid — "
                    "session may have been dropped by the DB"
                ),
            )
            if consecutive_failures >= max_failures:
                logger.error(
                    "leadership_heartbeat_lost_lock_declaring_shutdown",
                    leader_pid=leader_pid,
                    consecutive_failures=consecutive_failures,
                )
                self._signal_leadership_lost(on_leadership_lost, leader_pid)
                return

        logger.info(
            "leadership_heartbeat_stopped_normally",
            leader_pid=leader_pid,
        )

    def _signal_leadership_lost(
        self,
        on_leadership_lost: Optional[Callable[[], None]],
        leader_pid: int,
    ) -> None:
        """Clear leader flag + invoke shutdown callback.

        Called from the heartbeat thread only. ``_is_leader`` is cleared
        FIRST so any concurrent ``is_leader()`` readers see the updated
        value before the shutdown callback runs its own work.
        """
        self._is_leader = False
        if on_leadership_lost is None:
            logger.warning(
                "leadership_lost_no_shutdown_callback_registered",
                leader_pid=leader_pid,
                note=(
                    "heartbeat detected leadership loss but no "
                    "on_leadership_lost callback was provided; the "
                    "scheduler callback will continue running until it "
                    "exits on its own — consider wiring a shutdown hook"
                ),
            )
            return
        try:
            on_leadership_lost()
        except Exception as cb_err:  # noqa: BLE001
            logger.error(
                "on_leadership_lost_callback_failed",
                error=str(cb_err),
                leader_pid=leader_pid,
            )
