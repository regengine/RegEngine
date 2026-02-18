"""
Database Models - SQLAlchemy ORM

Maps to compliance snapshot schema with immutability enforcement.
"""
from uuid import UUID as StdUUID
from uuid_extensions import uuid7  # Time-ordered UUIDs (uuid7 v0.1.0 installs as uuid_extensions)
from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, Enum, JSON, ForeignKey,
    CheckConstraint, UniqueConstraint, Text, Index
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

from app.models import (
    SystemStatus, SnapshotGenerator, SnapshotTriggerEvent,
    MismatchSeverity
)

Base = declarative_base()


class ComplianceSnapshotModel(Base):
    """
    Immutable compliance snapshot - database model.
    
    CRITICAL: Never UPDATE or DELETE. Append-only.
    """
    __tablename__ = "compliance_snapshots"
    
    # Identity
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    tenant_id = Column(PGUUID(as_uuid=True), nullable=False, index=True)  # Multi-tenant isolation
    
    # Temporal
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    snapshot_time = Column(DateTime(timezone=True), nullable=False)
    
    # Scope
    substation_id = Column(String(255), nullable=False, index=True)
    facility_name = Column(String(500), nullable=False)
    
    # System State
    system_status = Column(Enum(SystemStatus), nullable=False)
    
    # Denormalized State (JSONB)
    asset_states = Column(JSON, nullable=False)
    esp_config = Column(JSON, nullable=False)
    patch_metrics = Column(JSON, nullable=False)
    active_mismatches = Column(JSON, nullable=False, default=list)
    
    # Generation Metadata
    generated_by = Column(Enum(SnapshotGenerator), nullable=False)
    trigger_event = Column(Enum(SnapshotTriggerEvent))
    generator_user_id = Column(PGUUID(as_uuid=True))
    
    # Integrity
    content_hash = Column(String(64), nullable=False)
    signature_hash = Column(String(64))
    previous_snapshot_id = Column(PGUUID(as_uuid=True), ForeignKey('compliance_snapshots.id'))
    
    # Compliance
    regulatory_version = Column(String(50), default='CIP-013-1')
    
    # Relationships
    previous_snapshot = relationship(
        "ComplianceSnapshotModel",
        remote_side=[id],
        backref="next_snapshots"
    )
    
    __table_args__ = (
        CheckConstraint(
            "length(content_hash) = 64",
            name="valid_content_hash_length"
        ),
        CheckConstraint(
            "(generated_by = 'USER_MANUAL' AND generator_user_id IS NOT NULL) OR "
            "(generated_by != 'USER_MANUAL')",
            name="manual_requires_user_id"
        ),
        Index('idx_snapshots_substation_time', 'substation_id', 'snapshot_time'),
        Index('idx_snapshots_status', 'system_status', postgresql_where=Column('system_status') != 'NOMINAL'),
    )


class MismatchModel(Base):
    """Mismatch (first-class risk object) - database model."""
    __tablename__ = "mismatches"
    
    # Identity
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    tenant_id = Column(PGUUID(as_uuid=True), nullable=False, index=True)  # Multi-tenant isolation
    
    # Discovery
    detected_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    detection_snapshot_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey('compliance_snapshots.id'),
        nullable=False
    )
    
    # Asset Context
    asset_id = Column(String(255), nullable=False, index=True)
    asset_name = Column(String(500), nullable=False)
    vendor = Column(String(255))
    
    # Integrity Violation
    mismatch_type = Column(String(50), nullable=False)
    
    # State Deltas
    hash_expected = Column(String(64))
    hash_actual = Column(String(64))
    version_expected = Column(String(100))
    version_actual = Column(String(100))
    last_known_good_snapshot_id = Column(PGUUID(as_uuid=True), ForeignKey('compliance_snapshots.id'))
    
    # Risk Assessment
    severity = Column(Enum(MismatchSeverity), nullable=False)
    
    # Regulatory Mapping
    regulatory_refs = Column(JSON, default=list)
    
    # Resolution State
    status = Column(String(20), nullable=False, default='OPEN')
    resolved_at = Column(DateTime(timezone=True))
    resolution_snapshot_id = Column(PGUUID(as_uuid=True), ForeignKey('compliance_snapshots.id'))
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    detection_snapshot = relationship("ComplianceSnapshotModel", foreign_keys=[detection_snapshot_id])
    resolution_snapshot = relationship("ComplianceSnapshotModel", foreign_keys=[resolution_snapshot_id])
    
    __table_args__ = (
        CheckConstraint(
            "(status IN ('RESOLVED', 'RISK_ACCEPTED') AND resolved_at IS NOT NULL) OR "
            "(status IN ('OPEN', 'UNDER_REVIEW') AND resolved_at IS NULL)",
            name="resolved_requires_timestamp"
        ),
        CheckConstraint(
            "(status IN ('RESOLVED', 'RISK_ACCEPTED') AND resolution_snapshot_id IS NOT NULL) OR "
            "(status IN ('OPEN', 'UNDER_REVIEW'))",
            name="resolved_requires_snapshot"
        ),
        Index('idx_mismatches_status', 'status', postgresql_where=Column('status').in_(['OPEN', 'UNDER_REVIEW'])),
        Index('idx_mismatches_severity', 'severity', postgresql_where=Column('severity').in_(['HIGH', 'CRITICAL'])),
    )


class AttestationModel(Base):
    """Attestation (human accountability) - database model."""
    __tablename__ = "attestations"
    
    # Identity
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    tenant_id = Column(PGUUID(as_uuid=True), nullable=False, index=True)  # Multi-tenant isolation
    
    # Linkage (REQUIRED)
    mismatch_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey('mismatches.id'),
        nullable=False,
        unique=True  # One attestation per mismatch
    )
    
    # Accountability
    attestor_user_id = Column(PGUUID(as_uuid=True), nullable=False)
    attestor_name = Column(String(500), nullable=False)
    attestor_role = Column(String(100))
    
    # Resolution Classification
    resolution_type = Column(String(50), nullable=False)
    
    # Justification (REQUIRED, min 50 chars)
    justification = Column(Text, nullable=False)
    
    # Supporting Evidence
    evidence_urls = Column(JSON, default=list)
    
    # Cryptographic Integrity
    signed_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    signature_fingerprint = Column(String(128))
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    
    # Relationships
    mismatch = relationship("MismatchModel", back_populates="attestation")
    
    __table_args__ = (
        CheckConstraint(
            "length(justification) >= 50",
            name="justification_min_length"
        ),
    )


# Add back-reference to MismatchModel
MismatchModel.attestation = relationship(
    "AttestationModel",
    back_populates="mismatch",
    uselist=False  # One-to-one
)
