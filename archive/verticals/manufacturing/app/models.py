"""
SQLAlchemy models for Manufacturing compliance service.
NCR (Non-Conformance Report) engine and CAPA tracking.
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, ForeignKey, Index, CheckConstraint, Boolean
from sqlalchemy.dialects.postgresql import UUID
import uuid
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class NonConformanceReport(Base):
    """
    Non-Conformance Report (NCR) tracking for ISO 9001 compliance.
    
    NCR Lifecycle:
    1. Detection - Issue identified
    2. Containment - Immediate action to prevent further issues
    3. Root Cause Analysis - 5 Whys, Fishbone, etc.
    4. CAPA - Corrective/Preventive actions
    5. Verification - Effectiveness check
    6. Closure - Sign-off
    """
    __tablename__ = "non_conformance_reports"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # Multi-tenant isolation
    ncr_number = Column(String(100), nullable=False, unique=True, index=True)
    
    # Detection
    detected_date = Column(DateTime, nullable=False, index=True)
    detected_by = Column(String(255), nullable=False)
    detection_source = Column(String(100), nullable=False)  # INTERNAL_AUDIT | CUSTOMER_COMPLAINT | PROCESS_MONITORING | SUPPLIER_ISSUE
    
    # Affected items
    part_number = Column(String(100), nullable=True, index=True)
    lot_number = Column(String(100), nullable=True)
    quantity_affected = Column(Integer, nullable=True)
    
    # Description
    description = Column(Text, nullable=False)
    severity = Column(String(50), nullable=False)  # CRITICAL | MAJOR | MINOR
    
    # Containment
    containment_action = Column(Text, nullable=True)
    containment_date = Column(DateTime, nullable=True)
    
    # Root Cause Analysis
    root_cause = Column(Text, nullable=True)
    rca_method = Column(String(100), nullable=True)  # 5_WHYS | FISHBONE | FAULT_TREE | PARETO
    rca_completed_date = Column(DateTime, nullable=True)
    
    # Status tracking
    status = Column(String(50), nullable=False, default="OPEN")  # OPEN | CAPA_IN_PROGRESS | VERIFICATION | CLOSED
    
    # ISO certification relevance
    iso_9001_relevant = Column(Boolean, default=True)  # Quality
    iso_14001_relevant = Column(Boolean, default=False)  # Environmental
    iso_45001_relevant = Column(Boolean, default=False)  # Safety
    
    # Closure
    closed_date = Column(DateTime, nullable=True)
    closed_by = Column(String(255), nullable=True)
    
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    capas = relationship("CorrectiveAction", back_populates="ncr")
    
    __table_args__ = (
        Index('idx_ncr_status_date', 'status', 'detected_date'),
        Index('idx_ncr_part_lot', 'part_number', 'lot_number'),
        CheckConstraint(
            "detection_source IN ('INTERNAL_AUDIT', 'CUSTOMER_COMPLAINT', 'PROCESS_MONITORING', 'SUPPLIER_ISSUE')", 
            name='check_detection_source'
        ),
        CheckConstraint(
            "severity IN ('CRITICAL', 'MAJOR', 'MINOR')", 
            name='check_severity'
        ),
        CheckConstraint(
            "status IN ('OPEN', 'CAPA_IN_PROGRESS', 'VERIFICATION', 'CLOSED')", 
            name='check_ncr_status'
        ),
    )
    
    def __repr__(self):
        return f"<NCR(id={self.id}, number={self.ncr_number}, severity={self.severity}, status={self.status})>"


class CorrectiveAction(Base):
    """
    CAPA (Corrective and Preventive Action) tracking.
    
    Corrective = Fix the problem
    Preventive = Prevent recurrence
    """
    __tablename__ = "corrective_actions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # Multi-tenant isolation
    ncr_id = Column(Integer, ForeignKey('non_conformance_reports.id', ondelete='CASCADE'), nullable=False, index=True)
    
    action_type = Column(String(50), nullable=False)  # CORRECTIVE | PREVENTIVE
    description = Column(Text, nullable=False)
    
    # Assignment
    assigned_to = Column(String(255), nullable=False)
    assigned_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    due_date = Column(DateTime, nullable=False, index=True)
    
    # Implementation
    implementation_status = Column(String(50), nullable=False, default="PENDING")  # PENDING | IN_PROGRESS | COMPLETE | VERIFIED
    implementation_date = Column(DateTime, nullable=True)
    implementation_notes = Column(Text, nullable=True)
    
    # Effectiveness verification (ISO requirement)
    verification_required = Column(Boolean, default=True)
    verification_date = Column(DateTime, nullable=True)
    verification_result = Column(String(50), nullable=True)  # EFFECTIVE | NOT_EFFECTIVE | PARTIALLY_EFFECTIVE
    verified_by = Column(String(255), nullable=True)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    ncr = relationship("NonConformanceReport", back_populates="capas")
    
    __table_args__ = (
        Index('idx_capa_ncr_status', 'ncr_id', 'implementation_status'),
        Index('idx_capa_assigned_due', 'assigned_to', 'due_date'),
        CheckConstraint(
            "action_type IN ('CORRECTIVE', 'PREVENTIVE')", 
            name='check_action_type'
        ),
        CheckConstraint(
            "implementation_status IN ('PENDING', 'IN_PROGRESS', 'COMPLETE', 'VERIFIED')", 
            name='check_implementation_status'
        ),
    )
    
    def __repr__(self):
        return f"<CAPA(id={self.id}, type={self.action_type}, status={self.implementation_status})>"


class SupplierQualityIssue(Base):
    """
    Supplier quality tracking for external NCRs.
    
    8D (Eight Disciplines) problem solving for supplier issues.
    """
    __tablename__ = "supplier_quality_issues"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # Multi-tenant isolation
    supplier_name = Column(String(255), nullable=False, index=True)
    supplier_code = Column(String(100), nullable=True)
    
    # Issue details
    issue_date = Column(DateTime, nullable=False, index=True)
    part_number = Column(String(100), nullable=False, index=True)
    lot_number = Column(String(100), nullable=True)
    defect_description = Column(Text, nullable=False)
    
    # 8D Process tracking
    d0_preparation = Column(JSON, nullable=True)  # Team formation
    d1_team = Column(JSON, nullable=True)  # Cross-functional team
    d2_problem_description = Column(Text, nullable=True)
    d3_interim_containment = Column(Text, nullable=True)
    d4_root_cause = Column(Text, nullable=True)
    d5_permanent_corrective_action = Column(Text, nullable=True)
    d6_implementation = Column(Text, nullable=True)
    d7_preventive_measures = Column(Text, nullable=True)
    d8_team_recognition = Column(Text, nullable=True)
    
    # Status
    status = Column(String(50), nullable=False, default="OPEN")  # OPEN | IN_PROGRESS | RESOLVED | CLOSED
    resolution_date = Column(DateTime, nullable=True)
    
    # Link to NCR if applicable
    ncr_id = Column(Integer, ForeignKey('non_conformance_reports.id', ondelete='SET NULL'), nullable=True)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_supplier_issue_date', 'supplier_name', 'issue_date'),
        Index('idx_supplier_part', 'supplier_name', 'part_number'),
        CheckConstraint(
            "status IN ('OPEN', 'IN_PROGRESS', 'RESOLVED', 'CLOSED')", 
            name='check_supplier_status'
        ),
    )
    
    def __repr__(self):
        return f"<SupplierQualityIssue(id={self.id}, supplier={self.supplier_name}, status={self.status})>"


class AuditFinding(Base):
    """
    Internal and external audit findings for ISO certification compliance.
    """
    __tablename__ = "audit_findings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # Multi-tenant isolation
    
    # Audit information
    audit_type = Column(String(100), nullable=False)  # INTERNAL | EXTERNAL_ISO_9001 | EXTERNAL_ISO_14001 | EXTERNAL_ISO_45001 | CUSTOMER
    audit_date = Column(DateTime, nullable=False, index=True)
    auditor_name = Column(String(255), nullable=False)
    
    # Finding details
    finding_number = Column(String(100), nullable=False, unique=True, index=True)
    clause_reference = Column(String(100), nullable=True)  # ISO clause (e.g., "8.5.1")
    finding_type = Column(String(50), nullable=False)  # MAJOR_NC | MINOR_NC | OFI (Opportunity for Improvement)
    description = Column(Text, nullable=False)
    
    # Response
    corrective_action_plan = Column(Text, nullable=True)
    target_closure_date = Column(DateTime, nullable=True, index=True)
    actual_closure_date = Column(DateTime, nullable=True)
    
    # Status
    status = Column(String(50), nullable=False, default="OPEN")  # OPEN | ACTION_PLAN_SUBMITTED | VERIFICATION_PENDING | CLOSED
    
    # Link to NCR if generated
    ncr_id = Column(Integer, ForeignKey('non_conformance_reports.id', ondelete='SET NULL'), nullable=True)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_audit_type_date', 'audit_type', 'audit_date'),
        Index('idx_audit_finding_status', 'finding_type', 'status'),
        CheckConstraint(
            "finding_type IN ('MAJOR_NC', 'MINOR_NC', 'OFI')", 
            name='check_finding_type'
        ),
        CheckConstraint(
            "status IN ('OPEN', 'ACTION_PLAN_SUBMITTED', 'VERIFICATION_PENDING', 'CLOSED')", 
            name='check_audit_status'
        ),
    )
    
    def __repr__(self):
        return f"<AuditFinding(id={self.id}, number={self.finding_number}, type={self.finding_type}, status={self.status})>"
