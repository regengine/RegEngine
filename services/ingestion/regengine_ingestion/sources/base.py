"""Base source adapter interface."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Iterator, List, Optional

from ..models import Document, DocumentType, SourceMetadata
from ..audit.logger import AuditLogger


class SourceAdapter(ABC):
    """
    Base class for all source adapters.
    
    Adapters fetch documents from external sources and normalize them
    into the RegEngine document format.
    """
    
    def __init__(
        self,
        audit_logger: Optional[AuditLogger] = None,
        user_agent: str = "RegEngine Ingestion Bot/1.0"
    ):
        """
        Initialize source adapter.
        
        Args:
            audit_logger: Logger for audit trail
            user_agent: User agent string for HTTP requests
        """
        self.audit_logger = audit_logger
        self.user_agent = user_agent
    
    @abstractmethod
    def fetch_documents(
        self,
        vertical: str,
        max_documents: int = 100,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        **kwargs
    ) -> Iterator[tuple[bytes, SourceMetadata, Dict]]:
        """
        Fetch documents from the source.
        
        Args:
            vertical: Regulatory vertical
            max_documents: Maximum number of documents to fetch
            date_from: Start date filter
            date_to: End date filter
            **kwargs: Source-specific parameters
            
        Yields:
            Tuples of (raw_content, source_metadata, document_metadata)
        """
        pass
    
    @abstractmethod
    def get_source_name(self) -> str:
        """Get the source name/type."""
        pass
    
    def log_fetch(self, url: str, status: str, http_status: Optional[int] = None, error: Optional[str] = None) -> None:
        """Helper to log fetch operations."""
        if self.audit_logger:
            self.audit_logger.log_fetch(url, status, http_status, error)
