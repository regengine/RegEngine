"""
Pydantic models for framework arbitrage and compliance analysis
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from enum import Enum


class Effort(str, Enum):
    """Effort level enumeration"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Priority(str, Enum):
    """Priority level enumeration"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Control(BaseModel):
    """Individual compliance control"""

    control_id: str = Field(..., description="Unique control identifier")
    requirement: str = Field(..., description="Control requirement description")
    description: Optional[str] = Field(None, description="Detailed description")
    effort_hours: float = Field(default=4.0, description="Estimated effort in hours")
    category: Optional[str] = Field(None, description="Control category")

    class Config:
        json_schema_extra = {
            "example": {
                "control_id": "SOC2-CC6.1",
                "requirement": "Logical access controls",
                "description": "The entity implements logical access security software...",
                "effort_hours": 4.0,
                "category": "Access Control",
            }
        }


class Framework(BaseModel):
    """Compliance framework"""

    id: str = Field(..., description="Framework unique identifier")
    name: str = Field(..., description="Framework name")
    version: str = Field(..., description="Framework version")
    category: str = Field(..., description="Framework category (e.g., Security, Privacy)")
    description: Optional[str] = Field(None, description="Framework description")
    controls: List[Control] = Field(default_factory=list, description="Framework controls")
    last_updated: Optional[datetime] = Field(None, description="Last update timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "soc2",
                "name": "SOC 2",
                "version": "2017",
                "category": "Security",
                "description": "AICPA's SOC 2 framework for service organizations",
                "last_updated": "2023-01-15T10:00:00Z",
            }
        }


class ControlMapping(BaseModel):
    """Mapping between two controls"""

    control_from: str = Field(..., description="Source control ID")
    control_to: str = Field(..., description="Target control ID")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Mapping confidence")
    requirement_from: Optional[str] = Field(None, description="Source requirement text")
    requirement_to: Optional[str] = Field(None, description="Target requirement text")

    class Config:
        json_schema_extra = {
            "example": {
                "control_from": "SOC2-CC6.1",
                "control_to": "ISO-A.9.2.1",
                "confidence": 0.95,
            }
        }


class ArbitrageOpportunity(BaseModel):
    """Framework arbitrage opportunity"""

    id: str = Field(..., description="Opportunity identifier")
    from_framework: str = Field(..., description="Source framework")
    to_framework: str = Field(..., description="Target framework")
    overlap_controls: int = Field(..., description="Number of overlapping controls")
    total_controls: int = Field(..., description="Total controls in target framework")
    overlap_percentage: float = Field(..., description="Overlap percentage")
    estimated_savings_hours: float = Field(..., description="Estimated time savings in hours")
    path: List[ControlMapping] = Field(
        default_factory=list, description="Control mappings showing overlap"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "id": "arb-soc2-iso27001",
                "from_framework": "SOC2",
                "to_framework": "ISO27001",
                "overlap_controls": 45,
                "total_controls": 114,
                "overlap_percentage": 39.5,
                "estimated_savings_hours": 180.0,
            }
        }


class ComplianceGap(BaseModel):
    """Compliance gap identification"""

    control_id: str = Field(..., description="Missing control ID")
    control_name: str = Field(..., description="Control name/requirement")
    missing_in: str = Field(..., description="Framework where control is missing")
    description: Optional[str] = Field(None, description="Gap description")
    remediation_effort: Effort = Field(..., description="Effort to remediate")
    priority: Priority = Field(..., description="Remediation priority")
    estimated_hours: float = Field(default=4.0, description="Estimated remediation hours")

    class Config:
        json_schema_extra = {
            "example": {
                "control_id": "HIPAA-164.308",
                "control_name": "Administrative Safeguards",
                "missing_in": "SOC2",
                "remediation_effort": "medium",
                "priority": "high",
                "estimated_hours": 12.0,
            }
        }


class FrameworkRelationship(BaseModel):
    """Relationship between two frameworks"""

    framework_id: str = Field(..., description="Related framework ID")
    framework_name: str = Field(..., description="Related framework name")
    relationship_type: str = Field(..., description="Type: maps_to, aligns_with, etc.")
    strength: float = Field(..., ge=0.0, le=1.0, description="Relationship strength")
    control_overlap: int = Field(..., description="Number of overlapping controls")

    class Config:
        json_schema_extra = {
            "example": {
                "framework_id": "iso27001",
                "framework_name": "ISO 27001",
                "relationship_type": "maps_to",
                "strength": 0.85,
                "control_overlap": 45,
            }
        }


class FrameworkRelationshipsResponse(BaseModel):
    """Response for framework relationships endpoint"""

    framework: str = Field(..., description="Source framework")
    related_frameworks: List[FrameworkRelationship] = Field(
        default_factory=list, description="List of related frameworks"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "framework": "SOC2",
                "related_frameworks": [
                    {
                        "framework_id": "iso27001",
                        "framework_name": "ISO 27001",
                        "relationship_type": "maps_to",
                        "strength": 0.85,
                        "control_overlap": 45,
                    }
                ],
            }
        }


class ArbitrageResponse(BaseModel):
    """Response for arbitrage endpoint"""

    opportunities: List[ArbitrageOpportunity] = Field(
        default_factory=list, description="List of arbitrage opportunities"
    )


class GapAnalysisResponse(BaseModel):
    """Response for gap analysis endpoint"""

    gaps: List[ComplianceGap] = Field(default_factory=list, description="Identified compliance gaps")
    coverage_percentage: float = Field(..., description="Current coverage percentage")
    total_gaps: int = Field(..., description="Total number of gaps")
    estimated_total_hours: float = Field(..., description="Total estimated remediation hours")

    class Config:
        json_schema_extra = {
            "example": {
                "gaps": [],
                "coverage_percentage": 67.3,
                "total_gaps": 12,
                "estimated_total_hours": 48.0,
            }
        }
