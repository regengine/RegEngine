"""
SQLAlchemy models for Aerospace compliance service.
AS9102 FAI vault and configuration baseline tracking.
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, ForeignKey, Index, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
import uuid
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class FAIReport(Base):
    """
    First Article Inspection (FAI) report per AS9102 Rev B.
    
    AS9102 consists of three forms:
    - Form 1: Part Number Accountability
    - Form 2: Product Accountability  
    - Form 3: Characteristic Accountability
    
    Retention: 30+ years for aerospace (part lifecycle + traceability)
    """
    __tablename__ = "fai_reports"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # Multi-tenant isolation
    part_number = Column(String(100), nullable=False, index=True)
    part_name = Column(String(255), nullable=False)
    drawing_number = Column(String(100), nullable=False, index=True)
    drawing_revision = Column(String(50), nullable=False)
    customer_name = Column(String(255), nullable=False, index=True)
    customer_part_number = Column(String(100), nullable=True)
    
    # AS9102 Form 1 - Part Number Accountability
    form1_data = Column(JSON, nullable=False)  # Serialized Form 1
    
    # AS9102 Form 2 - Product Accountability (can be multiple)
    form2_data = Column(JSON, nullable=False)  # Array of Form 2s
    
    # AS9102 Form 3 - Characteristic Accountability (can be multiple)
    form3_data = Column(JSON, nullable=False)  # Array of Form 3s
    
    inspection_method = Column(String(100), nullable=False)  # ACTUAL | DELTA | BASELINE
    inspection_date = Column(DateTime, nullable=False, index=True)
    inspector_name = Column(String(255), nullable=False)
    
    # Cryptographic integrity
    content_hash = Column(String(64), nullable=False, unique=True)  # SHA-256 of all forms
    
    # Approval tracking
    approval_status = Column(String(50), nullable=False, default="PENDING")  # PENDING | APPROVED | REJECTED
    approval_date = Column(DateTime, nullable=True)
    approval_notes = Column(Text, nullable=True)
    
    fai_metadata = Column(JSON, nullable=True)  # NADCAP, customer-specific requirements
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    baselines = relationship("ConfigurationBaseline", back_populates="fai_report")
    
    __table_args__ = (
        Index('idx_fai_part_drawing', 'part_number', 'drawing_revision'),
        Index('idx_fai_customer_date', 'customer_name', 'inspection_date'),
        CheckConstraint(
            "inspection_method IN ('ACTUAL', 'DELTA', 'BASELINE')", 
            name='check_inspection_method'
        ),
        CheckConstraint(
            "approval_status IN ('PENDING', 'APPROVED', 'REJECTED')", 
            name='check_approval_status'
        ),
    )
    
    def __repr__(self):
        return f"<FAIReport(id={self.id}, part={self.part_number}, rev={self.drawing_revision}, status={self.approval_status})>"


class ConfigurationBaseline(Base):
    """
    Configuration baseline tracking for 30-year lifecycle management.
    
    Critical for aerospace where parts may be serviced decades after production.
    Tracks exact component revisions used in each assembly.
    """
    __tablename__ = "configuration_baselines"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # Multi-tenant isolation
    assembly_id = Column(String(100), nullable=False, index=True)
    assembly_name = Column(String(255), nullable=False)
    serial_number = Column(String(100), nullable=True, index=True)
    
    # Configuration data (list of components with part numbers, revisions, serial numbers)
    baseline_data = Column(JSON, nullable=False)
    
    # Cryptographic integrity
    baseline_hash = Column(String(64), nullable=False, unique=True)  # SHA-256 of configuration
    
    # Link to FAI if applicable
    fai_report_id = Column(Integer, ForeignKey('fai_reports.id', ondelete='SET NULL'), nullable=True)
    
    # Lifecycle metadata
    manufacturing_date = Column(DateTime, nullable=False, index=True)
    end_of_life_date = Column(DateTime, nullable=True)
    lifecycle_status = Column(String(50), nullable=False, default="ACTIVE")  # ACTIVE | MAINTENANCE | RETIRED
    
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    fai_report = relationship("FAIReport", back_populates="baselines")
    
    __table_args__ = (
        Index('idx_baseline_assembly_serial', 'assembly_id', 'serial_number'),
        Index('idx_baseline_mfg_date', 'manufacturing_date'),
        CheckConstraint(
            "lifecycle_status IN ('ACTIVE', 'MAINTENANCE', 'RETIRED')", 
            name='check_lifecycle_status'
        ),
    )
    
    def __repr__(self):
        return f"<ConfigurationBaseline(id={self.id}, assembly={self.assembly_id}, sn={self.serial_number}, status={self.lifecycle_status})>"


class NADCAPEvidence(Base):
    """
    NADCAP special process evidence vault.
    
    NADCAP (National Aerospace and Defense Contractors Accreditation Program)
    requires special process documentation for:
    - Heat treat
    - Welding
    - Non-destructive testing (NDT)
    - Chemical processing
    """
    __tablename__ = "nadcap_evidence"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # Multi-tenant isolation
    process_type = Column(String(100), nullable=False, index=True)  # HEAT_TREAT | WELDING | NDT | CHEMICAL
    part_number = Column(String(100), nullable=False, index=True)
    lot_number = Column(String(100), nullable=True)
    
    # Process parameters (e.g., temperature, time, atmosphere for heat treat)
    process_parameters = Column(JSON, nullable=False)
    
    # Process results (e.g., hardness, pyrometry logs)
    process_results = Column(JSON, nullable=False)
    
    # Operator and equipment
    operator_name = Column(String(255), nullable=False)
    equipment_id = Column(String(100), nullable=False)
    calibration_due_date = Column(DateTime, nullable=True)
    
    process_date = Column(DateTime, nullable=False, index=True)
    
    # Cryptographic integrity
    content_hash = Column(String(64), nullable=False, unique=True)
    
    # Certification tracking
    nadcap_certification_number = Column(String(100), nullable=True)
    certification_expiry = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_nadcap_part_process', 'part_number', 'process_type'),
        Index('idx_nadcap_process_date', 'process_date'),
    )
    
    def __repr__(self):
        return f"<NADCAPEvidence(id={self.id}, type={self.process_type}, part={self.part_number})>"
