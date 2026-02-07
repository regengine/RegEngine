"""
SQLAlchemy models for Automotive compliance service.
PPAP (Production Part Approval Process) vault for IATF 16949.
"""

from sqlalchemy import Column, Integer, String, DateTime, BigInteger, JSON, ForeignKey, Index, CheckConstraint, Text
from sqlalchemy.dialects.postgresql import UUID
import uuid
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class PPAPSubmission(Base):
    """
    PPAP submission tracking for OEM approval process.
    
    PPAP Levels (per AIAG PPAP Manual 4th Edition):
    - Level 1: PSW only
    - Level 2: PSW + limited supporting data
    - Level 3: PSW + complete supporting data
    - Level 4: PSW + complete supporting data at supplier
    - Level 5: PSW + complete supporting data at designated location
    
    Retention: Typically lifetime of part + 1 year per OEM requirements.
    """
    __tablename__ = "ppap_submissions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # Multi-tenant isolation
    part_number = Column(String(100), nullable=False, index=True)
    part_name = Column(String(255), nullable=False)
    submission_level = Column(Integer, nullable=False)  # 1-5
    oem_customer = Column(String(255), nullable=False, index=True)
    customer_part_number = Column(String(100), nullable=True)  # OEM's part number
    submission_date = Column(DateTime, nullable=False, index=True)
    approval_status = Column(String(50), nullable=False, default="PENDING")  # PENDING | APPROVED | REJECTED | INTERIM
    approval_date = Column(DateTime, nullable=True)
    approval_notes = Column(Text, nullable=True)
    metadata_ = Column("metadata", JSON, nullable=True)  # Customer-specific requirements
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    elements = relationship("PPAPElement", back_populates="submission", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_ppap_part_customer', 'part_number', 'oem_customer'),
        Index('idx_ppap_status_date', 'approval_status', 'submission_date'),
        CheckConstraint('submission_level >= 1 AND submission_level <= 5', name='check_ppap_level'),
        CheckConstraint(
            "approval_status IN ('PENDING', 'APPROVED', 'REJECTED', 'INTERIM')", 
            name='check_approval_status'
        ),
    )
    
    def __repr__(self):
        return f"<PPAPSubmission(id={self.id}, part={self.part_number}, level={self.submission_level}, status={self.approval_status})>"


class PPAPElement(Base):
    """
    Individual PPAP elements (18 required per AIAG PPAP Manual).
    
    The 18 PPAP Elements:
    1. Design Records
    2. Engineering Change Documents
    3. Customer Engineering Approval
    4. DFMEA (Design FMEA)
    5. Process Flow Diagram
    6. PFMEA (Process FMEA)
    7. Control Plan
    8. MSA (Measurement System Analysis)
    9. Dimensional Results
    10. Material/Performance Test Results
    11. Initial Process Studies
    12. Qualified Laboratory Documentation
    13. Appearance Approval Report (AAR)
    14. Sample Production Parts
    15. Master Sample
    16. Checking Aids
    17. Customer-Specific Requirements
    18. Part Submission Warrant (PSW)
    """
    __tablename__ = "ppap_elements"
    
    # Valid element types (18 PPAP elements)
    VALID_ELEMENT_TYPES = [
        "DESIGN_RECORDS",
        "ENGINEERING_CHANGE_DOCUMENTS",
        "CUSTOMER_ENGINEERING_APPROVAL",
        "DFMEA",
        "PROCESS_FLOW_DIAGRAM",
        "PFMEA",
        "CONTROL_PLAN",
        "MSA",
        "DIMENSIONAL_RESULTS",
        "MATERIAL_TEST_RESULTS",
        "INITIAL_PROCESS_STUDIES",
        "QUALIFIED_LABORATORY_DOCUMENTATION",
        "APPEARANCE_APPROVAL_REPORT",
        "SAMPLE_PRODUCTION_PARTS",
        "MASTER_SAMPLE",
        "CHECKING_AIDS",
        "CUSTOMER_SPECIFIC_REQUIREMENTS",
        "PART_SUBMISSION_WARRANT"
    ]
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # Multi-tenant isolation
    submission_id = Column(Integer, ForeignKey('ppap_submissions.id', ondelete='CASCADE'), nullable=False, index=True)
    element_type = Column(String(100), nullable=False)
    filename = Column(String(500), nullable=False)
    content_hash = Column(String(64), nullable=False)  # SHA-256 for immutability
    file_size_bytes = Column(BigInteger, nullable=False)
    mime_type = Column(String(100), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    notes = Column(Text, nullable=True)
    uploaded_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    uploaded_by = Column(String(255), nullable=True)
    
    # Relationships
    submission = relationship("PPAPSubmission", back_populates="elements")
    
    __table_args__ = (
        Index('idx_element_submission_type', 'submission_id', 'element_type'),
        Index('idx_element_content_hash', 'content_hash'),
    )
    
    def __repr__(self):
        return f"<PPAPElement(id={self.id}, type={self.element_type}, hash={self.content_hash[:16]}...)>"


class LPAAudit(Base):
    """
    Layered Process Audit tracking for continuous compliance monitoring.
    
    LPA Strategy:
    - Multiple layers (executive, management, frontline)
    - Scheduled and random audits
    - Immediate corrective action for failures
    """
    __tablename__ = "lpa_audits"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # Multi-tenant isolation
    audit_date = Column(DateTime, nullable=False, index=True)
    layer = Column(String(50), nullable=False)  # EXECUTIVE | MANAGEMENT | FRONTLINE
    part_number = Column(String(100), nullable=True, index=True)
    process_step = Column(String(255), nullable=False)
    question = Column(Text, nullable=False)
    result = Column(String(50), nullable=False)  # PASS | FAIL | NA
    auditor_name = Column(String(255), nullable=False)
    corrective_action = Column(Text, nullable=True)
    corrective_action_due = Column(DateTime, nullable=True)
    corrective_action_status = Column(String(50), nullable=True)  # PENDING | COMPLETE
    metadata_ = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_lpa_result_date', 'result', 'audit_date'),
        Index('idx_lpa_part_date', 'part_number', 'audit_date'),
        CheckConstraint(
            "layer IN ('EXECUTIVE', 'MANAGEMENT', 'FRONTLINE')", 
            name='check_lpa_layer'
        ),
        CheckConstraint(
            "result IN ('PASS', 'FAIL', 'NA')", 
            name='check_lpa_result'
        ),
    )
    
    def __repr__(self):
        return f"<LPAAudit(id={self.id}, layer={self.layer}, result={self.result}, date={self.audit_date})>"
