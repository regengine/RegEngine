"""
SQLAlchemy models for Gaming compliance service.
Immutable transaction logs and self-exclusion records.
"""

from sqlalchemy import Column, Integer, String, DateTime, BigInteger, JSON, Index, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
import uuid
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class TransactionLog(Base):
    """
    Immutable transaction log for gaming activities.
    Required for Gaming Commission audits and AML/FinCEN reporting.
    
    Retention: 5+ years per most gaming jurisdictions.
    """
    __tablename__ = "transaction_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # Multi-tenant isolation
    player_id = Column(String(255), nullable=False, index=True)
    transaction_type = Column(String(50), nullable=False)  # WAGER | PAYOUT | JACKPOT | DEPOSIT | WITHDRAWAL
    amount_cents = Column(BigInteger, nullable=False)  # Store in cents to avoid float precision issues
    game_id = Column(String(255), nullable=False, index=True)
    jurisdiction = Column(String(100), nullable=False)  # "NEVADA" | "NEW_JERSEY" | "TRIBAL"
    timestamp = Column(DateTime, nullable=False, index=True)
    content_hash = Column(String(64), nullable=False, unique=True)  # SHA-256 for immutability
    metadata_ = Column("metadata", JSON, nullable=True)  # Additional jurisdiction-specific fields
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_player_timestamp', 'player_id', 'timestamp'),
        Index('idx_jurisdiction_timestamp', 'jurisdiction', 'timestamp'),
        CheckConstraint('amount_cents >= 0', name='check_positive_amount'),
    )
    
    def __repr__(self):
        return f"<TransactionLog(id={self.id}, player={self.player_id}, type={self.transaction_type}, hash={self.content_hash[:16]}...)>"


class SelfExclusionRecord(Base):
    """
    Player self-exclusion for responsible gaming compliance.
    Required by most gaming regulators (e.g., Nevada Reg 5.011).
    """
    __tablename__ = "self_exclusion_records"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # Multi-tenant isolation
    player_id = Column(String(255), nullable=False, unique=True, index=True)
    duration_days = Column(Integer, nullable=False)  # Common: 30, 90, 365, or 0 (permanent)
    reason = Column(String(500), nullable=True)
    effective_date = Column(DateTime, nullable=False, index=True)
    expiration_date = Column(DateTime, nullable=True)  # NULL = permanent
    status = Column(String(50), nullable=False, default="ACTIVE")  # ACTIVE | EXPIRED | REVOKED
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        CheckConstraint('duration_days >= 0', name='check_positive_duration'),
    )
    
    def __repr__(self):
        return f"<SelfExclusion(player={self.player_id}, status={self.status}, expires={self.expiration_date})>"


class ResponsibleGamingAlert(Base):
    """
    Automated alerts for problem gambling detection.
    Tracks behavioral signals for intervention.
    """
    __tablename__ = "responsible_gaming_alerts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # Multi-tenant isolation
    player_id = Column(String(255), nullable=False, index=True)
    alert_type = Column(String(100), nullable=False)  # "HIGH_FREQUENCY" | "LOSS_CHASING" | "AFTER_HOURS"
    risk_score = Column(Integer, nullable=False)  # 0-100
    detection_data = Column(JSON, nullable=False)  # Metrics that triggered the alert
    triggered_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by = Column(String(255), nullable=True)
    intervention_action = Column(String(500), nullable=True)  # What action was taken
    status = Column(String(50), nullable=False, default="PENDING")  # PENDING | REVIEWED | ESCALATED
    
    __table_args__ = (
        Index('idx_player_status', 'player_id', 'status'),
        CheckConstraint('risk_score >= 0 AND risk_score <= 100', name='check_risk_score_range'),
    )
    
    def __repr__(self):
        return f"<RGAlert(player={self.player_id}, type={self.alert_type}, risk={self.risk_score})>"
