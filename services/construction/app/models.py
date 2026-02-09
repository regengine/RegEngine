"""
SQLAlchemy models for Construction compliance service.
BIM version control and OSHA safety tracking.
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, ForeignKey, Index, CheckConstraint, Boolean
from sqlalchemy.dialects.postgresql import UUID
import uuid
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class BIMChangeRecord(Base):
    """
    BIM (Building Information Modeling) change tracking per ISO 19650.
    Immutable version control for construction document changes.
    """
    __tablename__ = "bim_change_records"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # Multi-tenant isolation
    project_id = Column(String(100), nullable=False, index=True)
    project_name = Column(String(255), nullable=False)
    
    # Change details
    change_number = Column(String(100), nullable=False, unique=True, index=True)
    change_type = Column(String(100), nullable=False)  # RFI | SUBMITTAL | CHANGE_ORDER | DESIGN_REVISION
    description = Column(Text, nullable=False)
    
    # BIM file tracking
    file_name = Column(String(500), nullable=False)
    file_version = Column(String(50), nullable=False)
    file_hash = Column(String(64), nullable=False)  # SHA-256
    previous_version_id = Column(Integer, ForeignKey('bim_change_records.id', ondelete='SET NULL'), nullable=True)
    
    # Stakeholders
    submitted_by = Column(String(255), nullable=False)
    submission_date = Column(DateTime, nullable=False, index=True)
    reviewed_by = Column(String(255), nullable=True)
    review_date = Column(DateTime, nullable=True)
    
    # Approval workflow
    status = Column(String(50), nullable=False, default="PENDING")  # PENDING | APPROVED | REJECTED | SUPERSEDED
    approval_notes = Column(Text, nullable=True)
    
    # ISO 19650 compliance
    cde_level = Column(String(50), nullable=True)  # WIP | SHARED | PUBLISHED | ARCHIVED (Common Data Environment)
    
    metadata_ = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_bim_project_version', 'project_id', 'file_version'),
        Index('idx_bim_submission_date', 'submission_date'),
        CheckConstraint(
            "change_type IN ('RFI', 'SUBMITTAL', 'CHANGE_ORDER', 'DESIGN_REVISION')", 
            name='check_change_type'
        ),
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED', 'SUPERSEDED')", 
            name='check_bim_status'
        ),
    )
    
    def __repr__(self):
        return f"<BIMChange(id={self.id}, number={self.change_number}, version={self.file_version}, status={self.status})>"


class OSHASafetyInspection(Base):
    """
    OSHA safety inspection tracking per 29 CFR 1926.
    """
    __tablename__ = "osha_safety_inspections"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # Multi-tenant isolation
    project_id = Column(String(100), nullable=False, index=True)
    
    # Inspection details
    inspection_date = Column(DateTime, nullable=False, index=True)
    inspector_name = Column(String(255), nullable=False)
    inspection_type = Column(String(100), nullable=False)  # WEEKLY | MONTHLY | INCIDENT | OSHA_VISIT
    
    # OSHA 1926 subpart reference
    osha_subpart = Column(String(50), nullable=True)  # e.g., "Subpart M" (Fall Protection)
    
    # Findings
    violations_found = Column(Integer, nullable=False, default=0)
    violation_severity = Column(String(50), nullable=True)  # SERIOUS | WILLFUL | REPEAT | OTHER
    violation_description = Column(Text, nullable=True)
    
    # Corrective action
    corrective_action_required = Column(Boolean, default=False)
    corrective_action_description = Column(Text, nullable=True)
    corrective_action_due_date = Column(DateTime, nullable=True)
    corrective_action_completed = Column(Boolean, default=False)
    
    # Status
    status = Column(String(50), nullable=False, default="OPEN")  # OPEN | CORRECTIVE_ACTION | CLOSED
    
    metadata_ = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_osha_project_date', 'project_id', 'inspection_date'),
        CheckConstraint(
            "inspection_type IN ('WEEKLY', 'MONTHLY', 'INCIDENT', 'OSHA_VISIT')", 
            name='check_inspection_type'
        ),
        CheckConstraint(
            "status IN ('OPEN', 'CORRECTIVE_ACTION', 'CLOSED')", 
            name='check_osha_status'
        ),
    )
    
    def __repr__(self):
        return f"<OSHAInspection(id={self.id}, project={self.project_id}, date={self.inspection_date}, violations={self.violations_found})>"


class SubcontractorCertification(Base):
    """
    Subcontractor qualification and certification tracking.
    """
    __tablename__ = "subcontractor_certifications"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # Multi-tenant isolation
    subcontractor_name = Column(String(255), nullable=False, index=True)
    subcontractor_code = Column(String(100), nullable=True)
    
    # Certification details
    certification_type = Column(String(100), nullable=False)  # INSURANCE | LICENSE | OSHA_10 | OSHA_30 | TRADE_CERT
    certification_number = Column(String(100), nullable=True)
    issue_date = Column(DateTime, nullable=False)
    expiration_date = Column(DateTime, nullable=False, index=True)
    
    # Document tracking
    document_hash = Column(String(64), nullable=True)  # SHA-256 of cert document
    
    # Status
    is_active = Column(Boolean, default=True)
    verification_status = Column(String(50), nullable=False, default="PENDING")  # PENDING | VERIFIED | EXPIRED
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_subcontractor_exp_date', 'subcontractor_name', 'expiration_date'),
    )
    
    def __repr__(self):
        return f"<SubcontractorCert(id={self.id}, name={self.subcontractor_name}, type={self.certification_type})>"
