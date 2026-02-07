"""Main ingestion engine."""

import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from .audit import AuditLogger
from .config import FrameworkConfig, IngestionConfig, SourceType
from .models import (
    Document,
    DocumentHash,
    DocumentType,
    IngestionJob,
    IngestionResult,
    JobStatus,
)
from .parsers import create_default_registry
from .sources import FederalRegisterAdapter, SourceAdapter, ECFRAdapter, FDAAdapter
from .storage import StorageManager
from .utils import hash_content, hash_text, generate_document_id


class IngestionEngine:
    """
    Main ingestion engine orchestrating the complete pipeline.
    
    Coordinates:
    - Source adapters for fetching
    - Storage for persistence
    - Audit logging for provenance
    - Deduplication
    """
    
    def __init__(
        self,
        framework_config: FrameworkConfig,
        storage_manager: StorageManager,
    ):
        """
        Initialize ingestion engine.
        
        Args:
            framework_config: Framework configuration
            storage_manager: Storage manager instance
        """
        self.config = framework_config
        self.storage = storage_manager
        self.parser_registry = create_default_registry()
    
    def run_job(self, ingestion_config: IngestionConfig) -> IngestionResult:
        """
        Run an ingestion job.
        
        Args:
            ingestion_config: Ingestion job configuration
            
        Returns:
            IngestionResult with job status and documents
        """
        # Create job
        job = IngestionJob(
            job_id=str(uuid.uuid4()),
            vertical=ingestion_config.vertical,
            source_type=ingestion_config.source_type.value,
            status=JobStatus.PENDING,
            config=vars(ingestion_config)
        )
        
        # Initialize audit logger
        audit_dir = self.storage.base_path / "audit"
        audit_logger = AuditLogger(job.job_id, audit_dir)
        
        # Create source adapter
        adapter = self._create_adapter(ingestion_config, audit_logger)
        
        # Start job
        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        
        documents = []
        errors = []
        
        try:
            # Fetch and process documents
            for content, source_metadata, doc_metadata in adapter.fetch_documents(
                vertical=ingestion_config.vertical,
                max_documents=ingestion_config.max_documents,
                date_from=ingestion_config.date_from,
                date_to=ingestion_config.date_to,
                **ingestion_config.source_config
            ):
                job.documents_processed += 1
                
                try:
                    # Hash content
                    content_sha256, content_sha512 = hash_content(content)
                    
                    # Check for duplicates
                    if self.storage.document_exists(content_sha256, ingestion_config.vertical):
                        audit_logger.log_skip(content_sha256[:16], "duplicate")
                        job.documents_skipped += 1
                        continue
                    
                    # Store document
                    document_id, storage_key, _ = self.storage.store_document(
                        content,
                        ingestion_config.vertical,
                    )
                    
                    audit_logger.log_store(document_id, "success", storage_key)
                    
                    # Extract text using parser registry
                    content_type = source_metadata.http_headers.get("Content-Type", "text/plain")
                    try:
                        text, parser_name = self.parser_registry.parse(
                            content,
                            content_type,
                            doc_metadata
                        )
                        text_sha256, text_sha512 = hash_text(text)
                        audit_logger.log_parse(document_id, "success", parser_name)
                    except Exception as e:
                        text = ""
                        text_sha256 = text_sha512 = None
                        audit_logger.log_parse(document_id, "failure", "unknown", str(e))
                    
                    # Create document record
                    document = Document(
                        id=document_id,
                        title=doc_metadata.get("title", "Untitled"),
                        source_type=ingestion_config.source_type.value,
                        document_type=DocumentType(doc_metadata.get("document_type", "other")),
                        vertical=ingestion_config.vertical,
                        hash=DocumentHash(
                            content_sha256=content_sha256,
                            content_sha512=content_sha512,
                            text_sha256=text_sha256,
                            text_sha512=text_sha512,
                        ),
                        source_metadata=source_metadata,
                        publication_date=self._parse_date(doc_metadata.get("publication_date")),
                        agencies=doc_metadata.get("agencies", []),
                        cfr_references=doc_metadata.get("cfr_references", []),
                        text=text,
                        text_length=len(text),
                        storage_key=storage_key,
                        content_length=len(content),
                    )
                    
                    documents.append(document)
                    job.documents_succeeded += 1
                    
                except Exception as e:
                    job.documents_failed += 1
                    error_info = {
                        "document": doc_metadata.get("title", "unknown"),
                        "error": str(e),
                    }
                    errors.append(error_info)
                    audit_logger.log("process", "document", status="failure", error=str(e))
            
            # Job completed
            job.status = JobStatus.COMPLETED
            
        except Exception as e:
            # Job failed
            job.status = JobStatus.FAILED
            job.error_message = str(e)
            job.error_details = {"exception": type(e).__name__}
        
        finally:
            job.completed_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
        
        return IngestionResult(
            job=job,
            documents=documents,
            errors=errors
        )
    
    def _create_adapter(
        self,
        config: IngestionConfig,
        audit_logger: AuditLogger
    ) -> SourceAdapter:
        """Create source adapter based on config."""
        if config.source_type == SourceType.FEDERAL_REGISTER:
            return FederalRegisterAdapter(
                audit_logger=audit_logger,
                user_agent=config.user_agent
            )
        elif config.source_type == SourceType.ECFR:
            return ECFRAdapter(
                audit_logger=audit_logger,
                user_agent=config.user_agent
            )
        elif config.source_type == SourceType.FDA:
            return FDAAdapter(
                api_key=self.config.fda_api_key,
                audit_logger=audit_logger,
                user_agent=config.user_agent
            )
        else:
            raise ValueError(f"Unsupported source type: {config.source_type}")
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse date string to datetime."""
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except Exception:
            return None
    
    def ingest_federal_register(
        self,
        vertical: str,
        max_documents: int = 100,
        date_from: Optional[datetime] = None,
        agencies: Optional[list] = None
    ) -> IngestionResult:
        """
        Convenience method to ingest from Federal Register.
        
        Args:
            vertical: Regulatory vertical
            max_documents: Maximum documents to fetch
            date_from: Start date
            agencies: List of agency slugs
            
        Returns:
            IngestionResult
        """
        config = IngestionConfig(
            source_type=SourceType.FEDERAL_REGISTER,
            vertical=vertical,
            max_documents=max_documents,
            date_from=date_from,
            source_config={"agencies": agencies} if agencies else {}
        )
        return self.run_job(config)

    def ingest_ecfr(
        self,
        vertical: str,
        cfr_title: int,
        cfr_part: int
    ) -> IngestionResult:
        """
        Convenience method to ingest from eCFR.
        
        Args:
            vertical: Regulatory vertical
            cfr_title: CFR Title number
            cfr_part: CFR Part number
            
        Returns:
            IngestionResult
        """
        config = IngestionConfig(
            source_type=SourceType.ECFR,
            vertical=vertical,
            source_config={"cfr_title": cfr_title, "cfr_part": cfr_part}
        )
        return self.run_job(config)

    def ingest_fda(
        self,
        vertical: str,
        max_documents: int = 100
    ) -> IngestionResult:
        """
        Convenience method to ingest from FDA.
        
        Args:
            vertical: Regulatory vertical
            max_documents: Maximum documents to fetch
            
        Returns:
            IngestionResult
        """
        config = IngestionConfig(
            source_type=SourceType.FDA,
            vertical=vertical,
            max_documents=max_documents
        )
        return self.run_job(config)


def create_engine_local(
    data_path: str = "./data",
    **kwargs
) -> IngestionEngine:
    """
    Create an ingestion engine with local filesystem storage.
    
    Args:
        data_path: Path to local data directory
        **kwargs: Additional framework config parameters
        
    Returns:
        IngestionEngine instance
    """
    framework_config = FrameworkConfig.default()
    framework_config.storage.filesystem_path = Path(data_path)
    
    storage_manager = StorageManager(Path(data_path))
    
    return IngestionEngine(framework_config, storage_manager)


def create_engine_production(
    s3_bucket: str,
    db_host: str,
    db_name: str,
    db_user: str,
    db_password: str
) -> IngestionEngine:
    """
    Create an ingestion engine for production with S3 storage.
    
    Args:
        s3_bucket: S3 bucket name
        db_host: Database host
        db_name: Database name
        db_user: Database user
        db_password: Database password
        
    Returns:
        IngestionEngine instance
    """
    # This would integrate with S3 and database
    raise NotImplementedError("Production engine with S3 not yet implemented")
