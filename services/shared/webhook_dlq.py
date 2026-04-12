"""
Webhook Dead Letter Queue (DLQ) System.

Manages failed webhook deliveries with exponential backoff retry logic.
Failed webhooks are persisted to a Postgres table (dlq.webhook_failures) and
re-attempted on a configurable schedule using exponential backoff.

Schema:
    dlq.webhook_failures:
        id (UUID, primary key)
        payload (JSONB) — original webhook payload
        error_message (TEXT) — last error details
        retry_count (INTEGER) — number of attempted retries
        max_retries (INTEGER) — max allowed retries (default 5)
        next_retry_at (TIMESTAMP) — when next retry is scheduled
        status (VARCHAR) — pending/retrying/dead
        created_at (TIMESTAMP) — when DLQ entry was created
        updated_at (TIMESTAMP) — when entry was last modified
        tenant_id (UUID) — for multi-tenant isolation
        source (VARCHAR) — source system identifier

Retry Schedule (exponential backoff with constant max):
    Attempt 1: 1 second
    Attempt 2: 5 seconds
    Attempt 3: 30 seconds
    Attempt 4: 5 minutes (300 seconds)
    Attempt 5: 30 minutes (1800 seconds)
    After max retries: marked as "dead"

Usage:
    from shared.webhook_dlq import WebhookDLQ
    from shared.database import SessionLocal

    db_session = SessionLocal()
    dlq = WebhookDLQ(db_session, tenant_id="org-123")

    # Handle a failed webhook delivery
    dlq.enqueue_failed_webhook(
        payload={"event": "push", "repository": "myrepo"},
        error_message="HTTP 500: Internal Server Error",
        source="github"
    )

    # Process retries (call from a background scheduler)
    import asyncio
    await dlq.process_retries()

    # Replay a dead webhook
    dlq.replay_dead_webhook(webhook_id="123e4567-e89b-12d3-a456-426614174000")
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Any
from enum import Enum

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
    text,
    select,
    and_,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import declarative_base

logger = logging.getLogger("webhook_dlq")

Base = declarative_base()


class WebhookFailureStatus(str, Enum):
    """Status of a webhook DLQ entry."""
    PENDING = "pending"
    RETRYING = "retrying"
    DEAD = "dead"


class WebhookFailureModel(Base):
    """SQLAlchemy model for failed webhook deliveries."""

    __tablename__ = "webhook_failures"
    __table_args__ = (
        # Index on status and next_retry_at for efficient query of due retries
        # Index on tenant_id for multi-tenant isolation
        # Index on created_at for time-series analysis
    )

    id = Column(UUID(as_uuid=True), primary_key=True)

    # Webhook payload and error details
    payload = Column(JSONB, nullable=False)
    error_message = Column(Text, nullable=False)

    # Retry tracking
    retry_count = Column(Integer, default=0, nullable=False)
    max_retries = Column(Integer, default=5, nullable=False)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)

    # Status tracking
    status = Column(String(20), default=WebhookFailureStatus.PENDING.value, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Tenant and source tracking
    tenant_id = Column(String(36), nullable=True, index=True)  # UUID string
    source = Column(String(50), nullable=True)  # e.g., "github", "stripe", "custom"


# Exponential backoff schedule (in seconds)
RETRY_SCHEDULE = [1, 5, 30, 300, 1800]  # 1s, 5s, 30s, 5m, 30m


class WebhookDLQ:
    """
    Manages dead-letter queue for failed webhook deliveries.

    Provides methods to:
    - Enqueue failed webhooks with error details
    - Process retries on a schedule (exponential backoff)
    - Replay dead webhooks manually
    - Query DLQ status
    """

    def __init__(self, db_session, tenant_id: Optional[str] = None):
        """
        Initialize WebhookDLQ.

        Args:
            db_session: SQLAlchemy session for database operations
            tenant_id: Optional tenant ID for multi-tenant isolation
        """
        self.db_session = db_session
        self.tenant_id = tenant_id
        logger.debug(
            "dlq_initialized",
            tenant_id=tenant_id,
        )

    def enqueue_failed_webhook(
        self,
        webhook_id: str,
        payload: dict[str, Any],
        error_message: str,
        source: Optional[str] = None,
        max_retries: int = 5,
    ) -> str:
        """
        Enqueue a failed webhook delivery to the DLQ.

        This should be called when a webhook delivery attempt fails.
        The entry is initialized with status=pending and next_retry_at set
        to the first retry time (1 second from now).

        Args:
            webhook_id: Unique identifier for this webhook delivery
            payload: The webhook payload (dict, will be JSON-encoded)
            error_message: Human-readable error description
            source: Source system identifier (e.g., "github", "stripe")
            max_retries: Maximum number of retry attempts (default 5)

        Returns:
            The webhook_id as a string for reference

        Raises:
            SQLAlchemyError: If database write fails
        """
        try:
            now = datetime.now(timezone.utc)
            next_retry_at = now + timedelta(seconds=RETRY_SCHEDULE[0])

            stmt = text("""
                INSERT INTO dlq.webhook_failures
                (id, payload, error_message, retry_count, max_retries,
                 next_retry_at, status, created_at, updated_at, tenant_id, source)
                VALUES
                (CAST(:id AS uuid), :payload::jsonb, :error_msg, 0, :max_retries,
                 :next_retry, :status, :created, :updated, :tenant, :source)
                ON CONFLICT (id) DO UPDATE SET
                    error_message = :error_msg,
                    updated_at = :updated,
                    status = :status
            """)

            self.db_session.execute(stmt, {
                "id": webhook_id,
                "payload": json.dumps(payload),
                "error_msg": error_message,
                "max_retries": max_retries,
                "next_retry": next_retry_at,
                "status": WebhookFailureStatus.PENDING.value,
                "created": now,
                "updated": now,
                "tenant": self.tenant_id,
                "source": source,
            })
            self.db_session.commit()

            logger.info(
                "webhook_enqueued_to_dlq",
                webhook_id=webhook_id,
                error_message=error_message,
                tenant_id=self.tenant_id,
                source=source,
            )
            return webhook_id

        except SQLAlchemyError as e:
            self.db_session.rollback()
            logger.error(
                "dlq_enqueue_failed",
                webhook_id=webhook_id,
                error=str(e),
                tenant_id=self.tenant_id,
            )
            raise

    def get_pending_retries(self, limit: int = 100) -> list[dict[str, Any]]:
        """
        Fetch webhooks due for retry from the DLQ.

        Returns entries where:
        - status is PENDING or RETRYING
        - next_retry_at <= NOW
        - retry_count < max_retries

        Args:
            limit: Maximum number of entries to fetch (default 100)

        Returns:
            List of webhook failure records (dicts)
        """
        try:
            now = datetime.now(timezone.utc)

            # Build tenant filter if tenant_id is set
            tenant_filter = ""
            params = {"now": now, "limit": min(limit, 1000)}

            if self.tenant_id:
                tenant_filter = "AND tenant_id = :tenant_id"
                params["tenant_id"] = self.tenant_id

            stmt = text(f"""
                SELECT id, payload, error_message, retry_count, max_retries,
                       next_retry_at, status, source, created_at, updated_at, tenant_id
                FROM dlq.webhook_failures
                WHERE (status = :status_pending OR status = :status_retrying)
                  AND next_retry_at <= :now
                  AND retry_count < max_retries
                  {tenant_filter}
                ORDER BY next_retry_at ASC
                LIMIT :limit
            """)

            params["status_pending"] = WebhookFailureStatus.PENDING.value
            params["status_retrying"] = WebhookFailureStatus.RETRYING.value

            rows = self.db_session.execute(stmt, params).fetchall()

            results = []
            for row in rows:
                results.append({
                    "id": str(row[0]),
                    "payload": json.loads(row[1]) if isinstance(row[1], str) else row[1],
                    "error_message": row[2],
                    "retry_count": row[3],
                    "max_retries": row[4],
                    "next_retry_at": row[5],
                    "status": row[6],
                    "source": row[7],
                    "created_at": row[8],
                    "updated_at": row[9],
                    "tenant_id": row[10],
                })

            if results:
                logger.debug(
                    "pending_retries_fetched",
                    count=len(results),
                    tenant_id=self.tenant_id,
                )

            return results

        except SQLAlchemyError as e:
            logger.error(
                "dlq_fetch_failed",
                error=str(e),
                tenant_id=self.tenant_id,
            )
            return []

    def mark_retry_attempt(
        self,
        webhook_id: str,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        Mark a webhook as having been retried and schedule the next attempt.

        Updates:
        - retry_count += 1
        - error_message (if provided)
        - status (RETRYING if more retries remain, DEAD otherwise)
        - next_retry_at (based on exponential backoff schedule)
        - updated_at (current timestamp)

        Args:
            webhook_id: The webhook ID to update
            error_message: Optional new error message to record

        Returns:
            True if update succeeded, False if webhook not found or max retries exceeded
        """
        try:
            now = datetime.now(timezone.utc)

            # Fetch current state
            fetch_stmt = text("""
                SELECT retry_count, max_retries, status
                FROM dlq.webhook_failures
                WHERE id = CAST(:id AS uuid)
            """)

            row = self.db_session.execute(fetch_stmt, {"id": webhook_id}).fetchone()
            if not row:
                logger.warning(
                    "webhook_not_found_in_dlq",
                    webhook_id=webhook_id,
                    tenant_id=self.tenant_id,
                )
                return False

            retry_count, max_retries, current_status = row
            new_retry_count = retry_count + 1

            # Determine next status and retry time
            if new_retry_count >= max_retries:
                new_status = WebhookFailureStatus.DEAD.value
                next_retry_at = None
                logger.warning(
                    "webhook_marked_dead",
                    webhook_id=webhook_id,
                    retry_count=new_retry_count,
                    max_retries=max_retries,
                    tenant_id=self.tenant_id,
                )
            else:
                new_status = WebhookFailureStatus.RETRYING.value
                # Schedule next retry based on retry count
                backoff_seconds = RETRY_SCHEDULE[min(new_retry_count - 1, len(RETRY_SCHEDULE) - 1)]
                next_retry_at = now + timedelta(seconds=backoff_seconds)
                logger.info(
                    "webhook_retry_scheduled",
                    webhook_id=webhook_id,
                    retry_count=new_retry_count,
                    backoff_seconds=backoff_seconds,
                    next_retry_at=next_retry_at.isoformat(),
                    tenant_id=self.tenant_id,
                )

            # Update webhook entry
            update_stmt = text("""
                UPDATE dlq.webhook_failures
                SET retry_count = :retry_count,
                    status = :status,
                    next_retry_at = :next_retry,
                    error_message = COALESCE(:error_msg, error_message),
                    updated_at = :updated
                WHERE id = CAST(:id AS uuid)
            """)

            self.db_session.execute(update_stmt, {
                "id": webhook_id,
                "retry_count": new_retry_count,
                "status": new_status,
                "next_retry": next_retry_at,
                "error_msg": error_message,
                "updated": now,
            })
            self.db_session.commit()

            return True

        except SQLAlchemyError as e:
            self.db_session.rollback()
            logger.error(
                "dlq_retry_mark_failed",
                webhook_id=webhook_id,
                error=str(e),
                tenant_id=self.tenant_id,
            )
            return False

    async def process_retries(self) -> dict[str, int]:
        """
        Process pending webhook retries.

        This is the main background task that should be called by a scheduler
        (e.g., APScheduler, Celery, or a cron job every 10 seconds).

        For each webhook due for retry:
        1. Fetch the webhook from DLQ
        2. Attempt delivery (via callback function)
        3. If successful: delete from DLQ
        4. If failed: call mark_retry_attempt() and update error message

        Returns:
            Dict with processing stats:
            {
                "processed": int (total processed),
                "succeeded": int (removed from DLQ),
                "failed": int (rescheduled),
                "dead": int (marked as dead/exhausted),
            }

        Note:
            This method requires a webhook delivery function to be injected.
            In a real implementation, you would either:
            - Pass a callback function to the constructor
            - Emit events to a job queue (Redis, Kafka)
            - Delegate to a retry service
        """
        stats = {
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "dead": 0,
        }

        try:
            pending = self.get_pending_retries(limit=100)

            for webhook_entry in pending:
                webhook_id = webhook_entry["id"]
                stats["processed"] += 1

                try:
                    # Attempt delivery (placeholder — this would be implemented
                    # by the caller or by delegating to a retry service)
                    # For now, we just reschedule.
                    success = False
                    error_msg = "Retry processing deferred to application layer"

                    if not success:
                        # Failed — mark for retry or dead
                        marked = self.mark_retry_attempt(webhook_id, error_msg)
                        if marked:
                            # Check if now dead
                            check_stmt = text("""
                                SELECT status FROM dlq.webhook_failures
                                WHERE id = CAST(:id AS uuid)
                            """)
                            status_row = self.db_session.execute(
                                check_stmt, {"id": webhook_id}
                            ).fetchone()
                            if status_row and status_row[0] == WebhookFailureStatus.DEAD.value:
                                stats["dead"] += 1
                            else:
                                stats["failed"] += 1
                        else:
                            stats["failed"] += 1
                    else:
                        stats["succeeded"] += 1

                except Exception as e:
                    logger.error(
                        "retry_processing_error",
                        webhook_id=webhook_id,
                        error=str(e),
                        tenant_id=self.tenant_id,
                    )
                    stats["failed"] += 1

            logger.info(
                "retry_processing_complete",
                stats=stats,
                tenant_id=self.tenant_id,
            )
            return stats

        except Exception as e:
            logger.error(
                "retry_processing_failed",
                error=str(e),
                tenant_id=self.tenant_id,
            )
            return stats

    def replay_dead_webhook(self, webhook_id: str) -> bool:
        """
        Move a dead (exhausted) webhook back to pending for manual replay.

        Sets status=PENDING, retry_count=0, next_retry_at=NOW so it will
        be picked up by the next process_retries() run immediately.

        Args:
            webhook_id: The webhook ID to replay

        Returns:
            True if replay succeeded, False if webhook not found
        """
        try:
            now = datetime.now(timezone.utc)

            update_stmt = text("""
                UPDATE dlq.webhook_failures
                SET status = :status,
                    retry_count = 0,
                    next_retry_at = :next_retry,
                    updated_at = :updated
                WHERE id = CAST(:id AS uuid)
            """)

            result = self.db_session.execute(update_stmt, {
                "id": webhook_id,
                "status": WebhookFailureStatus.PENDING.value,
                "next_retry": now,
                "updated": now,
            })
            self.db_session.commit()

            if result.rowcount == 0:
                logger.warning(
                    "webhook_not_found_for_replay",
                    webhook_id=webhook_id,
                    tenant_id=self.tenant_id,
                )
                return False

            logger.info(
                "webhook_replayed",
                webhook_id=webhook_id,
                tenant_id=self.tenant_id,
            )
            return True

        except SQLAlchemyError as e:
            self.db_session.rollback()
            logger.error(
                "dlq_replay_failed",
                webhook_id=webhook_id,
                error=str(e),
                tenant_id=self.tenant_id,
            )
            return False

    def get_dlq_stats(self) -> dict[str, int]:
        """
        Get summary statistics for the DLQ.

        Returns a dict with counts of pending, retrying, and dead webhooks.

        Returns:
            {
                "pending": int,
                "retrying": int,
                "dead": int,
                "total": int,
            }
        """
        try:
            tenant_filter = ""
            params = {}

            if self.tenant_id:
                tenant_filter = "WHERE tenant_id = :tenant_id"
                params["tenant_id"] = self.tenant_id

            stmt = text(f"""
                SELECT status, COUNT(*) as count
                FROM dlq.webhook_failures
                {tenant_filter}
                GROUP BY status
            """)

            rows = self.db_session.execute(stmt, params).fetchall()

            stats = {
                "pending": 0,
                "retrying": 0,
                "dead": 0,
                "total": 0,
            }

            for status, count in rows:
                stats[status] = count
                stats["total"] += count

            logger.debug(
                "dlq_stats_retrieved",
                stats=stats,
                tenant_id=self.tenant_id,
            )
            return stats

        except SQLAlchemyError as e:
            logger.error(
                "dlq_stats_failed",
                error=str(e),
                tenant_id=self.tenant_id,
            )
            return {"pending": 0, "retrying": 0, "dead": 0, "total": 0}

    def delete_webhook(self, webhook_id: str) -> bool:
        """
        Permanently delete a webhook entry from the DLQ.

        Use with caution — this removes all record of the failed delivery.

        Args:
            webhook_id: The webhook ID to delete

        Returns:
            True if deleted, False if not found
        """
        try:
            delete_stmt = text("""
                DELETE FROM dlq.webhook_failures
                WHERE id = CAST(:id AS uuid)
            """)

            result = self.db_session.execute(delete_stmt, {"id": webhook_id})
            self.db_session.commit()

            if result.rowcount == 0:
                logger.warning(
                    "webhook_not_found_for_delete",
                    webhook_id=webhook_id,
                    tenant_id=self.tenant_id,
                )
                return False

            logger.info(
                "webhook_deleted_from_dlq",
                webhook_id=webhook_id,
                tenant_id=self.tenant_id,
            )
            return True

        except SQLAlchemyError as e:
            self.db_session.rollback()
            logger.error(
                "dlq_delete_failed",
                webhook_id=webhook_id,
                error=str(e),
                tenant_id=self.tenant_id,
            )
            return False
