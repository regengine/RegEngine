"""State management for deduplication and tracking.

Persists seen items to PostgreSQL to prevent duplicate processing
across scheduler restarts.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import List, Optional, Set

import structlog
from sqlalchemy import Column, DateTime, String, Text, create_engine, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from .config import get_settings

logger = structlog.get_logger("scheduler.state")

Base = declarative_base()


class SeenItem(Base):
    """Record of a previously processed enforcement item."""

    __tablename__ = "scheduler_seen_items"

    source_id = Column(String(255), primary_key=True)
    source_type = Column(String(100), nullable=False)
    content_hash = Column(String(64), nullable=False)
    title = Column(Text)
    url = Column(Text)
    first_seen_at = Column(DateTime(timezone=True), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), nullable=False)


class StateManager:
    """Manages deduplication state in PostgreSQL.

    Uses a combination of source_id and content_hash to detect:
    1. New items (never seen before)
    2. Updated items (same source_id, different content)
    3. Unchanged items (same source_id and content)
    """

    def __init__(self, database_url: Optional[str] = None):
        settings = get_settings()
        self.database_url = database_url or settings.database_url
        self.engine = None
        self.SessionLocal = None
        self._initialized = False

    def initialize(self) -> None:
        """Initialize database connection and create tables."""
        if self._initialized:
            return

        try:
            self.engine = create_engine(
                self.database_url,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10,
            )
            self.SessionLocal = sessionmaker(bind=self.engine)

            # Create table if not exists
            with self.engine.connect() as conn:
                conn.execute(
                    text(
                        """
                    CREATE TABLE IF NOT EXISTS scheduler_seen_items (
                        source_id VARCHAR(255) PRIMARY KEY,
                        source_type VARCHAR(100) NOT NULL,
                        content_hash VARCHAR(64) NOT NULL,
                        title TEXT,
                        url TEXT,
                        first_seen_at TIMESTAMP WITH TIME ZONE NOT NULL,
                        last_seen_at TIMESTAMP WITH TIME ZONE NOT NULL
                    )
                """
                    )
                )
                conn.execute(
                    text(
                        """
                    CREATE INDEX IF NOT EXISTS idx_seen_items_source_type
                    ON scheduler_seen_items(source_type)
                """
                    )
                )
                conn.execute(
                    text(
                        """
                    CREATE INDEX IF NOT EXISTS idx_seen_items_last_seen
                    ON scheduler_seen_items(last_seen_at)
                """
                    )
                )

                # #1144 — persistent per-job last-run tracking. Held as
                # CREATE IF NOT EXISTS so this initializer is safe to call
                # repeatedly and survives a fresh DB / rolling deploy.
                conn.execute(
                    text(
                        """
                    CREATE TABLE IF NOT EXISTS scheduler_job_runs (
                        job_id         VARCHAR(128) PRIMARY KEY,
                        last_run_at    TIMESTAMP WITH TIME ZONE,
                        last_success_at TIMESTAMP WITH TIME ZONE,
                        last_status    VARCHAR(32),
                        last_error     TEXT
                    )
                    """
                    )
                )
                conn.commit()

            self._initialized = True
            logger.info("state_manager_initialized")

        except Exception as e:
            logger.error("state_manager_init_failed", error=str(e))
            raise

    def _get_session(self) -> Session:
        """Get a database session."""
        if not self._initialized:
            self.initialize()
        return self.SessionLocal()

    @staticmethod
    def compute_hash(content: str) -> str:
        """Compute SHA-256 hash of content for change detection."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def is_new(self, source_id: str, content: str) -> bool:
        """Check if an item has been seen before.

        Identity model (as of #1158): an item is identified by its
        ``source_id`` only. Once an item has been marked seen, it is
        never treated as new again — even if FDA edits the title,
        summary, or classification of the recall, the same
        ``source_id`` (e.g. ``fda_recall:D-0123-2026``) is a
        duplicate.

        The previous implementation hashed ``title|summary|url`` and
        treated any change as a new event, which caused duplicate
        alerts every time FDA corrected a firm name, upgraded a
        classification (II → I), or edited the product description.

        The ``content`` argument is retained for backwards compatibility
        with callers that still compute and pass a hash; it is ignored
        for the has-been-seen determination but still used to refresh
        ``last_seen_at`` so the cleanup cursor moves forward.

        Returns True only when the source_id has never been stored.
        """
        session = self._get_session()

        try:
            existing = session.query(SeenItem).filter_by(source_id=source_id).first()

            if existing is None:
                return True

            # Seen before. Refresh last_seen_at so we track that the
            # item is still live (keeps retention cleanup honest).
            existing.last_seen_at = datetime.now(timezone.utc)
            session.commit()
            return False

        finally:
            session.close()

    def mark_seen(
        self,
        source_id: str,
        source_type: str,
        content: str,
        title: Optional[str] = None,
        url: Optional[str] = None,
    ) -> None:
        """Mark an item as seen."""
        content_hash = self.compute_hash(content)
        now = datetime.now(timezone.utc)
        session = self._get_session()

        try:
            existing = session.query(SeenItem).filter_by(source_id=source_id).first()

            if existing:
                existing.content_hash = content_hash
                existing.last_seen_at = now
                if title:
                    existing.title = title
                if url:
                    existing.url = url
            else:
                session.add(
                    SeenItem(
                        source_id=source_id,
                        source_type=source_type,
                        content_hash=content_hash,
                        title=title,
                        url=url,
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                )

            session.commit()
            logger.debug("item_marked_seen", source_id=source_id, source_type=source_type)

        except Exception as e:
            session.rollback()
            logger.error("mark_seen_failed", source_id=source_id, error=str(e))
            raise
        finally:
            session.close()

    def get_seen_ids(self, source_type: str) -> Set[str]:
        """Get all seen source IDs for a source type."""
        session = self._get_session()

        try:
            results = (
                session.query(SeenItem.source_id)
                .filter_by(source_type=source_type)
                .all()
            )
            return {r.source_id for r in results}

        finally:
            session.close()

    def cleanup_old_items(self, days: int = 90) -> int:
        """Remove items not seen in the specified number of days."""
        session = self._get_session()
        cutoff = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        try:
            from datetime import timedelta

            cutoff = cutoff - timedelta(days=days)
            result = (
                session.query(SeenItem)
                .filter(SeenItem.last_seen_at < cutoff)
                .delete()
            )
            session.commit()
            logger.info("old_items_cleaned", count=result, days=days)
            return result

        except Exception as e:
            session.rollback()
            logger.error("cleanup_failed", error=str(e))
            raise
        finally:
            session.close()

    def record_job_run(
        self,
        job_id: str,
        success: bool,
        error: Optional[str] = None,
    ) -> None:
        """Record the outcome of a scheduler job run to scheduler_job_runs.

        Writes (or upserts) a single row keyed on ``job_id``:

        * ``last_run_at``      — bumped on every call
        * ``last_success_at``  — bumped only on success=True
        * ``last_status``      — ``"ok"`` or ``"error"``
        * ``last_error``       — truncated to 2000 chars on error

        Used by the APScheduler event listener (#1144) so drift can be
        detected across process restarts.
        """
        session = self._get_session()
        status = "ok" if success else "error"
        err = (error or "")[:2000] if not success else None
        try:
            session.execute(
                text(
                    """
                    INSERT INTO scheduler_job_runs
                        (job_id, last_run_at, last_success_at, last_status, last_error)
                    VALUES
                        (:job_id, NOW(),
                         CASE WHEN :success THEN NOW() ELSE NULL END,
                         :status, :err)
                    ON CONFLICT (job_id) DO UPDATE SET
                        last_run_at = NOW(),
                        last_success_at = CASE
                            WHEN :success THEN NOW()
                            ELSE scheduler_job_runs.last_success_at
                        END,
                        last_status = :status,
                        last_error = :err
                    """
                ),
                {
                    "job_id": job_id,
                    "success": success,
                    "status": status,
                    "err": err,
                },
            )
            session.commit()
        except Exception as exc:  # pragma: no cover — best-effort telemetry
            session.rollback()
            logger.error("record_job_run_failed", job_id=job_id, error=str(exc))
        finally:
            session.close()

    def get_stats(self) -> dict:
        """Get state manager statistics."""
        session = self._get_session()

        try:
            total = session.query(SeenItem).count()
            by_type = (
                session.execute(
                    text(
                        """
                    SELECT source_type, COUNT(*) as count 
                    FROM scheduler_seen_items 
                    GROUP BY source_type
                """
                    )
                )
                .fetchall()
            )

            return {
                "total_items": total,
                "by_source_type": {row[0]: row[1] for row in by_type},
            }

        finally:
            session.close()
