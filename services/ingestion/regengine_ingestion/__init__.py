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

from .engine import IngestionEngine, create_engine_local, create_engine_production
from .config import IngestionConfig, SourceType, VerticalConfig, FrameworkConfig
from .models import (
    Document,
    IngestionJob,
    IngestionResult,
    DocumentHash,
    SourceMetadata
)

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
