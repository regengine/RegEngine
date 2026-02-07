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
        """Check if an item is new or has changed.

        Returns True if:
        - Item has never been seen
        - Item content has changed since last seen
        """
        content_hash = self.compute_hash(content)
        session = self._get_session()

        try:
            existing = session.query(SeenItem).filter_by(source_id=source_id).first()

            if existing is None:
                return True

            if existing.content_hash != content_hash:
                # Content has changed
                return True

            # Update last_seen_at even if unchanged
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
