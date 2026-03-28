"""
PCOS Schema Governance Models

Tracking of schema versions and analysis runs.
"""

from __future__ import annotations

import uuid as uuid_module
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB

from ..sqlalchemy_models import Base, GUID, JSONType

class SchemaVersionModel(Base):
    """
    Schema migrations registry.
    
    Every migration must self-register here. If a migration runs
    without recording itself, it is invalid by definition.
    """
    __tablename__ = "schema_migrations"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(String(50), nullable=False, unique=True)
    checksum = Column(String(64), nullable=False)  # SHA-256
    git_sha = Column(String(40))
    description = Column(Text)
    applied_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    applied_by = Column(String(100))
    execution_time_ms = Column(Integer)
    success = Column(Boolean, nullable=False, default=True)


class PCOSAnalysisRunModel(Base):
    """
    Analysis run tracking.
    
    Every analysis MUST have an AnalysisRun. This is the invariant
    that ensures all verdicts are traceable to a specific execution context.
    """
    __tablename__ = "pcos_analysis_runs"
    
    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    
    # Run identification
    run_type = Column(String(50), nullable=False)  # 'compliance_check', 'rate_validation'
    run_status = Column(String(20), nullable=False, default="pending")  # 'pending', 'running', 'completed', 'failed'
    
    # What was analyzed
    project_id = Column(GUID(), ForeignKey("pcos_projects.id"))
    entity_type = Column(String(50))
    entity_id = Column(GUID())
    
    # Run context (immutable snapshot)
    run_parameters = Column(JSONB, nullable=False, default=dict)
    rule_pack_version = Column(String(50))
    fact_snapshot_time = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    
    # Results
    total_evaluations = Column(Integer, default=0)
    pass_count = Column(Integer, default=0)
    fail_count = Column(Integer, default=0)
    warning_count = Column(Integer, default=0)
    indeterminate_count = Column(Integer, default=0)
    
    # Execution metadata
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    execution_time_ms = Column(Integer)
    error_message = Column(Text)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    
    # Relationships
    project = relationship("PCOSProjectModel")
    evaluations = relationship("PCOSRuleEvaluationModel", back_populates="analysis_run")
    
    def mark_running(self):
        """Mark the run as started."""
        if self.run_status != "pending":
            raise ValueError("Can only start a pending run")
        self.run_status = "running"
        self.started_at = datetime.now(timezone.utc)
    
    def mark_completed(self, pass_count: int, fail_count: int, warning_count: int, indeterminate_count: int):
        """Mark the run as completed with results."""
        if self.run_status not in ("pending", "running"):
            raise ValueError("Can only complete a pending/running run")
        self.run_status = "completed"
        self.completed_at = datetime.now(timezone.utc)
        self.pass_count = pass_count
        self.fail_count = fail_count
        self.warning_count = warning_count
        self.indeterminate_count = indeterminate_count
        self.total_evaluations = pass_count + fail_count + warning_count + indeterminate_count
        if self.started_at:
            self.execution_time_ms = int((self.completed_at - self.started_at).total_seconds() * 1000)
    
    def mark_failed(self, error: str):
        """Mark the run as failed."""
        if self.run_status not in ("pending", "running"):
            raise ValueError("Can only fail a pending/running run")
        self.run_status = "failed"
        self.completed_at = datetime.now(timezone.utc)
        self.error_message = error
        if self.started_at:
            self.execution_time_ms = int((self.completed_at - self.started_at).total_seconds() * 1000)


