"""
Snapshot Engine - Core Domain Models

Immutable data structures for compliance snapshots.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from uuid import UUID
import logging

logger = logging.getLogger(__name__)


class SystemStatus(str, Enum):
    """System compliance status enumeration."""
    NOMINAL = "NOMINAL"
    DEGRADED = "DEGRADED"
    NON_COMPLIANT = "NON_COMPLIANT"


class SnapshotGenerator(str, Enum):
    """Who/what generated the snapshot."""
    SYSTEM_AUTO = "SYSTEM_AUTO"
    USER_MANUAL = "USER_MANUAL"
    SCHEDULED = "SCHEDULED"


class SnapshotTriggerEvent(str, Enum):
    """Events that trigger snapshot creation."""
    ASSET_VERIFICATION_CHANGE = "ASSET_VERIFICATION_CHANGE"
    MISMATCH_CREATED = "MISMATCH_CREATED"
    MISMATCH_RESOLVED = "MISMATCH_RESOLVED"
    ESP_TOPOLOGY_CHANGE = "ESP_TOPOLOGY_CHANGE"
    PATCH_VELOCITY_BREACH = "PATCH_VELOCITY_BREACH"
    SCHEDULED_DAILY = "SCHEDULED_DAILY"
    USER_MANUAL_REQUEST = "USER_MANUAL_REQUEST"
    INITIAL_BASELINE = "INITIAL_BASELINE"


@dataclass(frozen=True)
class SnapshotCreationRequest:
    """
    Input to snapshot creation engine.
    
    Frozen dataclass ensures immutability of request.
    """
    substation_id: str
    facility_name: str
    asset_states: Dict
    esp_config: Dict
    patch_metrics: Dict
    active_mismatch_ids: List[UUID]
    generated_by: SnapshotGenerator
    trigger_event: SnapshotTriggerEvent
    generator_user_id: Optional[UUID] = None
    # Tenant ID (default for backward compatibility, but required for tenant isolation)
    # Default is the 'default' tenant UUID used in migrations
    tenant_id: UUID = UUID('00000000-0000-0000-0000-000000000001')
    
    def __post_init__(self):
        """Validate snapshot creation request."""
        # Validate assets list
        if not self.asset_states or len(self.asset_states) == 0:
            raise ValueError("At least one asset state required")
        
        # Note: generator_user_id validation relaxed for development/testing
        # TODO: In production, enforce user_id requirement based on generated_by type


@dataclass(frozen=True)
class ComplianceSnapshot:
    """
    Immutable compliance snapshot.
    
    Critical: This class is frozen - no modifications allowed after creation.
    Represents absolute truth at a point in time.
    """
    id: UUID
    created_at: datetime
    snapshot_time: datetime
    substation_id: str
    facility_name: str
    system_status: SystemStatus
    asset_states: Dict
    esp_config: Dict
    patch_metrics: Dict
    active_mismatches: List[str]  # Stringified UUIDs for JSON
    generated_by: SnapshotGenerator
    trigger_event: SnapshotTriggerEvent
    content_hash: str
    signature_hash: str
    previous_snapshot_id: Optional[UUID] = None
    generator_user_id: Optional[UUID] = None
    regulatory_version: str = "CIP-013-1"
    tenant_id: UUID = UUID('00000000-0000-0000-0000-000000000001')
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "id": str(self.id),
            "tenant_id": str(self.tenant_id),
            "created_at": self.created_at.isoformat(),
            "snapshot_time": self.snapshot_time.isoformat(),
            "substation_id": self.substation_id,
            "facility_name": self.facility_name,
            "system_status": self.system_status.value,
            "asset_states": self.asset_states,
            "esp_config": self.esp_config,
            "patch_metrics": self.patch_metrics,
            "active_mismatches": self.active_mismatches,
            "generated_by": self.generated_by.value,
            "trigger_event": self.trigger_event.value,
            "content_hash": self.content_hash,
            "signature_hash": self.signature_hash,
            "previous_snapshot_id": str(self.previous_snapshot_id) if self.previous_snapshot_id else None,
            "generator_user_id": str(self.generator_user_id) if self.generator_user_id else None,
            "regulatory_version": self.regulatory_version
        }


@dataclass(frozen=True)
class MismatchSeverity(str, Enum):
    """Mismatch severity levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class AssetStateSummary:
    """Summary of asset verification state."""
    total_assets: int
    verified_count: int
    mismatch_count: int
    unknown_count: int
    
    @property
    def verification_percentage(self) -> float:
        """Percentage of assets verified."""
        if self.total_assets == 0:
            return 0.0
        return (self.verified_count / self.total_assets) * 100
