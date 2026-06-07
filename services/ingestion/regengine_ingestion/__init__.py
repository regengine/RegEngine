"""
RegEngine Ingestion Framework

A production-grade regulatory document ingestion system with:
- Multi-source adapters (Federal Register, eCFR, FDA, web crawling)
- Cryptographic verification (SHA-256/SHA-512)
- Complete audit trails
- Multi-vertical support
- Deduplication
- Rate limiting
"""

from .config import FrameworkConfig, IngestionConfig, SourceType, VerticalConfig
from .engine import IngestionEngine, create_engine_local, create_engine_production
from .models import Document, DocumentHash, IngestionJob, IngestionResult, SourceMetadata

__version__ = "1.0.0"

__all__ = [
    "IngestionEngine",
    "create_engine_local",
    "create_engine_production",
    "IngestionConfig",
    "SourceType",
    "VerticalConfig",
    "Document",
    "IngestionJob",
    "IngestionResult",
    "DocumentHash",
    "SourceMetadata",
]
