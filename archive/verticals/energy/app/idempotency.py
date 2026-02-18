"""
Idempotency Management

Prevents duplicate snapshot creation via deduplication window.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import Column, String, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Session

from app.database import Base


class SnapshotIdempotencyModel(Base):
    """
    Idempotency records for snapshot deduplication.
    
    Retention: 5 minutes (matching deduplication window)
    Cleanup: Cron job DELETE WHERE expires_at < NOW()
    """
    __tablename__ = "snapshot_idempotency"
    
    idempotency_key = Column(String(64), primary_key=True)
    snapshot_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey('compliance_snapshots.id'),
        nullable=True
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    
    __table_args__ = (
        Index(
            'idx_idempotency_expires',
            'expires_at',
            postgresql_where=Column('expires_at') > datetime.utcnow()
        ),
    )


class IdempotencyManager:
    """Manages snapshot deduplication."""
    
    DEDUP_WINDOW_MINUTES = 5
    
    def __init__(self, db_session: Session):
        self.db = db_session
    
    def generate_key(
        self,
        substation_id: str,
        trigger_event: str,
        timestamp: Optional[datetime] = None,
        tenant_id: Optional[UUID] = None
    ) -> str:
        """
        Generate idempotency key from request content.
        
        Key is stable within 5-minute window for same trigger.
        Scoped by tenant_id if provided.
        """
        if not timestamp:
            timestamp = datetime.now(timezone.utc)
        
        # Round to 5-minute window
        window = self._timestamp_window(timestamp)
        
        key_data = {
            "substation_id": substation_id,
            "trigger_event": trigger_event,
            "timestamp_window": window,
            "tenant_id": str(tenant_id) if tenant_id else "default"
        }
        
        return hashlib.sha256(
            json.dumps(key_data, sort_keys=True).encode()
        ).hexdigest()
    
    def find_recent_snapshot(
        self,
        idempotency_key: str
    ) -> Optional[UUID]:
        """
        Check if snapshot exists within dedup window.
        
        Returns snapshot_id if found, None otherwise.
        """
        record = (
            self.db.query(SnapshotIdempotencyModel)
            .filter(SnapshotIdempotencyModel.idempotency_key == idempotency_key)
            .filter(SnapshotIdempotencyModel.expires_at > datetime.now(timezone.utc))
            .first()
        )
        
        return record.snapshot_id if record else None
    
    def store_record(
        self,
        idempotency_key: str,
        snapshot_id: UUID
    ):
        """Store idempotency record with expiration."""
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=self.DEDUP_WINDOW_MINUTES
        )
        
        record = SnapshotIdempotencyModel(
            idempotency_key=idempotency_key,
            snapshot_id=snapshot_id,
            expires_at=expires_at
        )
        
        self.db.add(record)
        # Commit handled by caller
    
    def cleanup_expired(self) -> int:
        """
        Remove expired idempotency records.
        
        Should be called by cron job every minute.
        Returns count of deleted records.
        """
        deleted = (
            self.db.query(SnapshotIdempotencyModel)
            .filter(SnapshotIdempotencyModel.expires_at < datetime.now(timezone.utc))
            .delete()
        )
        
        self.db.commit()
        return deleted
    
    def _timestamp_window(self, dt: datetime) -> str:
        """Round to 5-minute window for deduplication."""
        minutes = (dt.minute // 5) * 5
        window_dt = dt.replace(minute=minutes, second=0, microsecond=0)
        return window_dt.isoformat()
