"""Data models for the ingestion framework."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class JobStatus(str, Enum):
    """Job execution status."""
    
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DocumentType(str, Enum):
    """Document type classification."""
    
    REGULATION = "regulation"
    GUIDANCE = "guidance"
    NOTICE = "notice"
    RULE = "rule"
    ORDER = "order"
    ADVISORY = "advisory"
    REPORT = "report"
    OTHER = "other"


@dataclass
class DocumentHash:
    """Cryptographic hashes for a document."""
    
    content_sha256: str
    content_sha512: str
    text_sha256: Optional[str] = None
    text_sha512: Optional[str] = None


@dataclass
class SourceMetadata:
    """Metadata about the document source."""
    
    source_url: str
    fetch_timestamp: datetime
    http_status: Optional[int] = None
    http_headers: Dict[str, str] = field(default_factory=dict)
    etag: Optional[str] = None
    last_modified: Optional[datetime] = None


@dataclass
class Document:
    """A regulatory document with complete metadata."""
    
    # Identifiers
    id: str  # Content-based ID (hash prefix)
    title: str
    tenant_id: str
    
    # Classification
    source_type: str
    document_type: DocumentType
    vertical: str
    
    # Cryptographic verification
    hash: DocumentHash
    
    # Source information
    source_metadata: SourceMetadata
    
    # Document metadata
    effective_date: Optional[datetime] = None
    publication_date: Optional[datetime] = None
    agencies: List[str] = field(default_factory=list)
    cfr_references: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    
    # Content
    text: Optional[str] = None
    text_length: int = 0
    
    # Storage
    storage_key: str = ""
    content_type: str = "application/octet-stream"
    content_length: int = 0
    
    # Audit
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class IngestionJob:
    """Ingestion job tracking."""
    
    # Identifiers
    job_id: str
    vertical: str
    source_type: str
    
    # Status
    status: JobStatus = JobStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Progress
    documents_processed: int = 0
    documents_succeeded: int = 0
    documents_failed: int = 0
    documents_skipped: int = 0  # Duplicates
    
    # Configuration snapshot
    config: Dict = field(default_factory=dict)
    
    # Results
    error_message: Optional[str] = None
    error_details: Dict = field(default_factory=dict)
    
    # Audit
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class IngestionResult:
    """Result of an ingestion operation."""
    
    job: IngestionJob
    documents: List[Document] = field(default_factory=list)
    errors: List[Dict] = field(default_factory=list)
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        total = self.job.documents_processed
        if total == 0:
            return 0.0
        return (self.job.documents_succeeded / total) * 100


@dataclass
class AuditEntry:
    """Audit log entry."""
    
    timestamp: datetime
    job_id: str
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    status: str = "success"
    details: Dict = field(default_factory=dict)
    error: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "job_id": self.job_id,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "status": self.status,
            "details": self.details,
            "error": self.error,
        }
