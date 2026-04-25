"""Database manager for PostgreSQL operations."""

import json
from datetime import datetime
from typing import List, Optional
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ..config import DatabaseConfig
from ..models import Document, IngestionJob, AuditEntry


class DatabaseManager:
    """
    PostgreSQL database manager for ingestion framework.
    
    Handles document persistence, job tracking, and audit logging.
    """
    
    def __init__(self, config: DatabaseConfig):
        """
        Initialize database manager.
        
        Args:
            config: Database configuration
        """
        self.config = config
        self.conn = None
    
    def connect(self) -> None:
        """Establish database connection."""
        self.conn = psycopg.connect(
            host=self.config.host,
            port=self.config.port,
            dbname=self.config.database,
            user=self.config.user,
            password=self.config.password,
            row_factory=dict_row,
        )
        self.conn.autocommit = True
    
    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def set_tenant_context(self, tenant_id: str) -> None:
        """Set tenant context for RLS via the Postgres SECURITY DEFINER helper.

        Intentionally does NOT delegate to
        ``services.shared.tenant_context.set_tenant_guc`` (the Phase B
        canonical primitive, #1934). The other tenant-context callers
        in the codebase (CTEPersistence #1935, CanonicalEventStore
        #1936, ExceptionQueueService #1938) all run on top of a
        SQLAlchemy Session inside an explicit transaction, where
        ``SET LOCAL app.tenant_id = :tid`` (transaction-scoped) is the
        right shape.

        ``DatabaseManager`` is structurally different on two axes:

        1. **Raw psycopg connection, not SQLAlchemy.** The session
           parameter ``set_tenant_guc`` expects (an object with
           ``.execute(text(...), params)``) doesn't match this layer's
           ``conn.cursor().execute(sql, tuple)`` API.

        2. **``autocommit = True``** (set in ``connect()`` above).
           Every statement is its own transaction. ``SET LOCAL`` only
           takes effect within the current transaction and resets on
           COMMIT — under autocommit it would set then immediately
           reset on the implicit commit. Effectively a no-op.

        The SECURITY DEFINER function ``set_tenant_context(uuid)``
        defined in ``services/admin/migrations/V3__tenant_isolation.sql``
        uses ``set_config('app.tenant_id', ..., FALSE)`` which is
        session-scoped — the right shape under autocommit, where the
        connection is the unit of context.

        Pool-bleed safety (the reason Phase B exists) is not a concern
        here because ``DatabaseManager`` opens a per-instance dedicated
        connection in ``connect()`` and closes it in ``close()`` /
        ``__exit__``. There is no connection pool; the GUC dies with
        the connection.

        If this code path ever switches to SQLAlchemy or to a pooled
        connection model, revisit — the right migration would be the
        full set: drop autocommit, wrap requests in explicit
        transactions, switch to a SQLAlchemy session, then delegate
        to ``set_tenant_guc``. Out of scope for the Phase B per-call-
        site sweep.
        """
        if not self.conn:
            self.connect()
        with self.conn.cursor() as cur:
            cur.execute("SELECT set_tenant_context(%s)", (tenant_id,))

    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.close()
    
    # Document operations
    
    def insert_document(self, document: Document) -> None:
        """
        Insert document into database.
        
        Args:
            document: Document to insert
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ingestion.documents (
                    id, tenant_id, title, source_type, document_type, vertical,
                    content_sha256, content_sha512, text_sha256, text_sha512,
                    source_url, fetch_timestamp, http_status, etag, last_modified,
                    effective_date, publication_date, agencies, cfr_references, keywords,
                    text_length, content_length, content_type, storage_key
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                ON CONFLICT (content_sha256) DO NOTHING
            """, (
                UUID(document.id) if isinstance(document.id, str) else document.id,
                UUID(document.tenant_id) if isinstance(document.tenant_id, str) and document.tenant_id else document.tenant_id,
                document.title,
                document.source_type,
                document.document_type.value,
                document.vertical,
                document.hash.content_sha256,
                document.hash.content_sha512,
                document.hash.text_sha256,
                document.hash.text_sha512,
                document.source_metadata.source_url,
                document.source_metadata.fetch_timestamp,
                document.source_metadata.http_status,
                document.source_metadata.etag,
                document.source_metadata.last_modified,
                document.effective_date,
                document.publication_date,
                document.agencies,
                document.cfr_references,
                document.keywords,
                document.text_length,
                document.content_length,
                document.content_type,
                document.storage_key
            ))
    
    def get_document(self, document_id: str, tenant_id: str) -> Optional[dict]:
        """
        Retrieve document by ID, scoped to the calling tenant.

        Args:
            document_id: Document identifier
            tenant_id: Tenant identifier (required for isolation)

        Returns:
            Document dict or None
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM ingestion.documents
                WHERE id = %s AND tenant_id = %s
            """, (document_id, tenant_id))
            return cur.fetchone()

    def get_document_by_hash(self, content_sha256: str, tenant_id: str) -> Optional[dict]:
        """
        Retrieve document by content hash, scoped to the calling tenant.

        Args:
            content_sha256: SHA-256 hash of document content
            tenant_id: Tenant identifier (required for isolation)

        Returns:
            Document dict or None
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM ingestion.documents
                WHERE content_sha256 = %s AND tenant_id = %s
            """, (content_sha256, tenant_id))
            return cur.fetchone()
    
    def search_documents(
        self,
        tenant_id: str,
        vertical: Optional[str] = None,
        source_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[dict]:
        """
        Search documents with filters, scoped to the calling tenant.

        Args:
            tenant_id: Tenant identifier (required for isolation)
            vertical: Filter by vertical
            source_type: Filter by source type
            limit: Maximum results (capped at 500)
            offset: Pagination offset

        Returns:
            List of document dicts
        """
        limit = min(limit, 500)  # Hard cap — prevent full-table dumps
        query = "SELECT * FROM ingestion.documents WHERE tenant_id = %s"
        params = [tenant_id]

        if vertical:
            query += " AND vertical = %s"
            params.append(vertical)

        if source_type:
            query += " AND source_type = %s"
            params.append(source_type)

        query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        with self.conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()
    
    # Job operations
    
    def insert_job(self, job: IngestionJob) -> None:
        """
        Insert ingestion job.
        
        Args:
            job: Job to insert
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ingestion.jobs (
                    job_id, vertical, source_type, status,
                    created_at, started_at, completed_at, updated_at,
                    documents_processed, documents_succeeded, documents_failed, documents_skipped,
                    config, error_message, error_details
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s
                )
            """, (
                UUID(job.job_id),
                job.vertical,
                job.source_type,
                job.status.value,
                job.created_at,
                job.started_at,
                job.completed_at,
                job.updated_at,
                job.documents_processed,
                job.documents_succeeded,
                job.documents_failed,
                job.documents_skipped,
                json.dumps(job.config),
                job.error_message,
                json.dumps(job.error_details) if job.error_details else None
            ))
    
    def update_job(self, job: IngestionJob) -> None:
        """
        Update job status and metrics.
        
        Args:
            job: Job to update
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE ingestion.jobs SET
                    status = %s,
                    started_at = %s,
                    completed_at = %s,
                    updated_at = %s,
                    documents_processed = %s,
                    documents_succeeded = %s,
                    documents_failed = %s,
                    documents_skipped = %s,
                    error_message = %s,
                    error_details = %s
                WHERE job_id = %s
            """, (
                job.status.value,
                job.started_at,
                job.completed_at,
                job.updated_at,
                job.documents_processed,
                job.documents_succeeded,
                job.documents_failed,
                job.documents_skipped,
                job.error_message,
                json.dumps(job.error_details) if job.error_details else None,
                UUID(job.job_id)
            ))
    
    def get_job(self, job_id: str) -> Optional[dict]:
        """
        Retrieve job by ID.
        
        Args:
            job_id: Job identifier
            
        Returns:
            Job dict or None
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM ingestion.jobs
                WHERE job_id = %s
            """, (UUID(job_id),))
            return cur.fetchone()
    
    # Audit log operations
    
    def insert_audit_entry(self, entry: AuditEntry) -> None:
        """
        Insert audit log entry.
        
        Args:
            entry: Audit entry to insert
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ingestion.audit_log (
                    timestamp, job_id, action, resource_type, resource_id,
                    status, details, error
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s
                )
            """, (
                entry.timestamp,
                UUID(entry.job_id),
                entry.action,
                entry.resource_type,
                entry.resource_id,
                entry.status,
                json.dumps(entry.details),
                entry.error
            ))
    
    def get_audit_log(self, job_id: str, limit: int = 100) -> List[dict]:
        """
        Get audit log entries for a job.
        
        Args:
            job_id: Job identifier
            limit: Maximum entries
            
        Returns:
            List of audit entry dicts
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM ingestion.audit_log
                WHERE job_id = %s
                ORDER BY timestamp DESC
                LIMIT %s
            """, (UUID(job_id), limit))
            return cur.fetchall()
