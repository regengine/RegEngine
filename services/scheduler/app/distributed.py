"""Distributed coordination for high-availability scheduler components.

Implements Leader Election pattern using PostgreSQL Advisory Locks to ensure
only one scheduler instance is active at a time (Active-Standby).
"""

import contextlib
import time
import structlog
from typing import Generator, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from .config import get_settings

logger = structlog.get_logger("scheduler.distributed")

# Constant lock ID for the scheduler leader (arbitrary large integer)
# ensuring it doesn't collide with other application locks.
SCHEDULER_LEADER_LOCK_ID = 4294967295  # Max uint32

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

    def wait_for_leadership(self, callback, poll_interval: int = 5):
        """Blocking call that waits for leadership then runs callback.

        Sets ``self._is_leader`` to True for the duration of ``callback``
        and clears it in the ``finally`` block, so ``app.leadership.is_leader()``
        (which reads the same flag) returns accurate values from inside
        callback-driven jobs. Without this (#1162), every ``is_leader()``
        guard in the module-level scheduled jobs silently skipped because
        the flag was only ever set by :meth:`leadership_claim`.
        """
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
                        logger.info("leadership_acquired_running_scheduler")
                        # #1162 — publish our leader state BEFORE running the
                        # callback so any is_leader() gates inside the
                        # callback see True.
                        self._is_leader = True
                        try:
                            # Run the actual scheduler workload
                            # This callback should block (e.g. valid for BlockingScheduler)
                            # If it returns, we release lock (or maybe we lost connection?)
                            callback()
                        except Exception as e:
                            logger.error("scheduler_crashed", error=str(e))
                            raise e
                        finally:
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
