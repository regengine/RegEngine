"""Data models for the scheduler service."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    """Types of regulatory sources."""

    FDA_WARNING_LETTER = "fda_warning_letter"
    FDA_IMPORT_ALERT = "fda_import_alert"
    FDA_RECALL = "fda_recall"
    STATE_REGISTRY = "state_registry"
    FEDERAL_REGISTER = "federal_register"
    REGULATORY_DISCOVERY = "regulatory_discovery"


class EnforcementSeverity(str, Enum):
    """Severity levels for enforcement actions."""

    CRITICAL = "critical"  # Active recall, immediate action required
    HIGH = "high"  # Warning letter, import alert
    MEDIUM = "medium"  # Regulatory update, guidance change
    LOW = "low"  # Informational update


class EnforcementItem(BaseModel):
    """A detected enforcement action or regulatory change."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    source_type: SourceType
    source_id: str = Field(..., description="Unique ID from source system")
    title: str
    summary: Optional[str] = None
    url: str
    published_date: datetime
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    severity: EnforcementSeverity = EnforcementSeverity.MEDIUM
    affected_products: List[str] = Field(default_factory=list)
    affected_companies: List[str] = Field(default_factory=list)
    jurisdiction: str = Field(default="US-FDA")
    raw_data: Dict[str, Any] = Field(default_factory=dict)


class ScrapeResult(BaseModel):
    """Result of a scraper execution."""

    source_type: SourceType
    success: bool
    items_found: int = 0
    items_new: int = 0
    items: List[EnforcementItem] = Field(default_factory=list)
    error_message: Optional[str] = None
    duration_ms: float = 0
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # #1140: soft-failure signals — the scrape didn't fail outright but
    # something looks off (e.g. parser_mismatch_suspected when the scraper
    # returns zero items from a page that clearly should have had some).
    # Alert/metrics code should treat non-empty ``warnings`` as a signal
    # alongside ``success=False``.
    warnings: List[str] = Field(default_factory=list)


class JobExecution(BaseModel):
    """Record of a scheduled job execution."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    job_id: str
    source_type: SourceType
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    success: bool = False
    items_processed: int = 0
    error_message: Optional[str] = None


class WebhookPayload(BaseModel):
    """Payload sent to webhook endpoints."""

    event_type: str = "enforcement.detected"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "regengine-scheduler"
    items: List[EnforcementItem]
    summary: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "summary": self.summary,
            "item_count": len(self.items),
            "items": [item.model_dump(mode="json") for item in self.items],
        }


class AlertEvent(BaseModel):
    """Kafka event for detected regulatory changes."""

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str = "enforcement.detected"
    source_type: SourceType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    item: EnforcementItem
    tenant_id: Optional[UUID] = None  # For tenant-specific routing

    def to_kafka_dict(self) -> Dict[str, Any]:
        """Convert to Kafka-friendly dict."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source_type": self.source_type.value,
            "timestamp": self.timestamp.isoformat(),
            "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            "item": self.item.model_dump(mode="json"),
        }
