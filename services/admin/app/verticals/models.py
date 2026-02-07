"""
Vertical Compliance Domain Models.

Generic models to support expansion into Healthcare, Finance, Gaming, Energy, and Technology.
Designed to run parallel to the film-specific PCOS models.
"""

from __future__ import annotations

import uuid as uuid_module
from enum import Enum
from datetime import datetime
from typing import Any, Dict

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship
from ..sqlalchemy_models import Base, GUID, JSONType


class VerticalType(str, Enum):
    """Supported industry verticals."""
    HEALTHCARE = "healthcare"
    FINANCE = "finance"
    GAMING = "gaming"
    ENERGY = "energy"
    TECHNOLOGY = "technology"
    # Legacy/Core support
    MEDIA_PRODUCTION = "media_production"


class VerticalProjectModel(Base):
    """
    Generic compliance project/scope for any vertical.
    
    Examples:
    - Healthcare: "Q1 Facility Audit - West Wing"
    - Finance: "2026 SOC 2 Type II Readiness"
    - Gaming: "NJ DGE Launch Prep"
    """
    __tablename__ = "vertical_projects"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)

    name = Column(String(255), nullable=False)
    description = Column(Text)
    
    # Core discriminator
    vertical = Column(String(50), nullable=False) # e.g. "healthcare"
    
    # Flexible metadata for vertical-specific fields
    # e.g. Healthcare: { "facility_type": "hospital", "patient_volume": 5000 }
    # e.g. Finance: { "audit_standard": "soc2", "cpa_firm": "PwC" }
    vertical_metadata = Column(JSONType(), nullable=False, default=dict)

    status = Column(String(50), nullable=False, default="active")
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(GUID(), ForeignKey("users.id"))

    # Relationships
    rule_instances = relationship("VerticalRuleInstanceModel", back_populates="project", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_vertical_projects_tenant", "tenant_id"),
        Index("idx_vertical_projects_vertical", "vertical"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "tenant_id": str(self.tenant_id),
            "name": self.name,
            "description": self.description,
            "vertical": self.vertical,
            "vertical_metadata": self.vertical_metadata,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "created_by": str(self.created_by) if self.created_by else None,
        }


class VerticalRuleInstanceModel(Base):
    """
    Instance of a specific rule applied to a project.
    
    Links back to the static definitions in the JSON RulePacks.
    """
    __tablename__ = "vertical_rule_instances"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(GUID(), ForeignKey("vertical_projects.id", ondelete="CASCADE"), nullable=False)

    # Link to JSON definition
    rule_pack_id = Column(String(100), nullable=False) # e.g. "healthcare_hipaa_v1"
    rule_id = Column(String(100), nullable=False)      # e.g. "HIPAA-ADM-01"

    # Status tracking
    status = Column(String(50), nullable=False, default="pending") # pending, compliant, non_compliant, not_applicable
    
    # Evidence / Findings
    evidence_links = Column(JSONType(), default=list) # List of S3 keys or URLs
    auditor_notes = Column(Text)
    
    assigned_to = Column(GUID(), ForeignKey("users.id"))
    due_date = Column(DateTime(timezone=True))
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    project = relationship("VerticalProjectModel", back_populates="rule_instances")

    __table_args__ = (
        Index("idx_vertical_rules_project", "project_id"),
        Index("idx_vertical_rules_status", "status"),
        Index("idx_vertical_rules_lookup", "rule_pack_id", "rule_id"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "project_id": str(self.project_id),
            "rule_pack_id": self.rule_pack_id,
            "rule_id": self.rule_id,
            "status": self.status,
            "evidence_links": self.evidence_links,
            "auditor_notes": self.auditor_notes,
            "assigned_to": str(self.assigned_to) if self.assigned_to else None,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
