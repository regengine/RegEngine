"""
Type definitions and Pydantic models for Energy SDK.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, field_validator, ConfigDict


class SystemStatus(str, Enum):
    """System compliance status."""
    NOMINAL = "NOMINAL"
    DEGRADED = "DEGRADED"
    NON_COMPLIANT = "NON_COMPLIANT"


class AssetInfo(BaseModel):
    """Asset information for snapshot."""
    id: str = Field(..., description="Unique asset identifier")
    type: str = Field(..., description="Asset type (e.g., TRANSFORMER, RELAY)")
    firmware_version: Optional[str] = Field(None, description="Current firmware version")
    last_verified: str = Field(..., description="ISO 8601 timestamp of last verification")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional asset metadata")


class ESPConfig(BaseModel):
    """Electronic Security Perimeter configuration."""
    firewall_version: str = Field(..., description="Firewall software version")
    ids_enabled: bool = Field(..., description="Intrusion detection system status")
    patch_level: str = Field(..., description="Current patch level")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional ESP metadata")


class RegulatoryInfo(BaseModel):
    """Regulatory compliance information."""
    standard: str = Field(default="NERC-CIP-013-1", description="Regulatory standard")
    audit_ready: bool = Field(default=True, description="Audit readiness status")


class SnapshotCreateRequest(BaseModel):
    """Request to create a compliance snapshot."""
    
    substation_id: str = Field(..., min_length=1, description="Substation identifier")
    facility_name: str = Field(..., min_length=1, description="Facility name")
    system_status: SystemStatus = Field(..., description="Current system status")
    assets: List[AssetInfo] = Field(..., min_length=1, description="List of assets")
    esp_config: ESPConfig = Field(..., description="ESP configuration")
    patch_metrics: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Patch metrics data")
    regulatory: Optional[RegulatoryInfo] = Field(default_factory=RegulatoryInfo, description="Regulatory info")
    trigger_reason: Optional[str] = Field(None, description="Human-readable reason for snapshot")
    
    @field_validator('assets')
    @classmethod
    def validate_assets(cls, v):
        if not v:
            raise ValueError("At least one asset required")
        return v


class SnapshotResponse(BaseModel):
    """Response from snapshot creation."""
    
    snapshot_id: str = Field(..., description="Unique snapshot ID")
    snapshot_time: str = Field(..., description="ISO 8601 timestamp")
    system_status: str = Field(..., description="System status at snapshot time")
    content_hash: str = Field(..., description="SHA-256 content hash")
    signature_hash: Optional[str] = Field(None, description="Cryptographic signature")
    asset_summary: Dict[str, Any] = Field(..., description="Asset state summary")
    chain_status: Optional[str] = Field(None, description="Chain integrity status")
    
    model_config = ConfigDict(extra="allow")


class VerificationResult(BaseModel):
    """Result of chain integrity verification."""
    
    verified: bool = Field(..., description="Whether verification passed")
    snapshot_id: str = Field(..., description="Verified snapshot ID")
    content_hash_valid: bool = Field(..., description="Content hash validity")
    signature_valid: Optional[bool] = Field(None, description="Signature validity")
    chain_intact: bool = Field(..., description="Chain integrity status")
    total_snapshots: Optional[int] = Field(None, description="Total snapshots in chain")
    broken_links: Optional[int] = Field(None, description="Number of broken chain links")
    errors: List[str] = Field(default_factory=list, description="Verification errors")
    
    model_config = ConfigDict(extra="allow")


class SnapshotListResponse(BaseModel):
    """Paginated list of snapshots."""
    
    snapshots: List[SnapshotResponse] = Field(..., description="List of snapshots")
    total: int = Field(..., description="Total count")
    limit: int = Field(..., description="Page size")
    offset: int = Field(..., description="Pagination offset")
    
    model_config = ConfigDict(extra="allow")
