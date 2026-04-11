"""Audit logging for complete provenance tracking."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("audit-logger")

from ..models import AuditEntry


class AuditLogger:
    """
    Audit logger for complete provenance tracking.
    
    Writes audit entries to both JSONL files and database.
    """
    
    def __init__(
        self,
        job_id: str,
        audit_dir: Optional[Path] = None,
        db_connection=None
    ):
        """
        Initialize audit logger.
        
        Args:
            job_id: Job ID for this audit trail
            audit_dir: Directory for JSONL audit logs
            db_connection: Database connection for audit table
        """
        self.job_id = job_id
        self.audit_dir = audit_dir
        self.db_connection = db_connection
        
        if audit_dir:
            audit_dir.mkdir(parents=True, exist_ok=True)
            self.audit_file = audit_dir / f"job_{job_id}.jsonl"
        else:
            self.audit_file = None
    
    def log(
        self,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        status: str = "success",
        details: Optional[dict] = None,
        error: Optional[str] = None
    ) -> None:
        """
        Log an audit entry.
        
        Args:
            action: Action performed (e.g., "fetch", "parse", "store")
            resource_type: Type of resource (e.g., "document", "url")
            resource_id: Identifier for the resource
            status: Status of the action ("success", "failure", "skipped")
            details: Additional details dictionary
            error: Error message if status is "failure"
        """
        entry = AuditEntry(
            timestamp=datetime.utcnow(),
            job_id=self.job_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            status=status,
            details=details or {},
            error=error
        )
        
        # Write to JSONL file
        if self.audit_file:
            with open(self.audit_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict()) + "\n")
        
        # Write to database
        if self.db_connection:
            self._write_to_db(entry)
    
    def _write_to_db(self, entry: AuditEntry) -> None:
        """Write audit entry to database."""
        if self.db_connection:
            try:
                self.db_connection.insert_audit_entry(entry)
            except Exception:
                # JSONL is primary audit trail
                logger.debug("Audit DB write failed (JSONL is primary)", exc_info=True)
    
    def log_fetch(self, url: str, status: str, http_status: Optional[int] = None, error: Optional[str] = None) -> None:
        """Log a URL fetch operation."""
        details = {}
        if http_status:
            details["http_status"] = http_status
        
        self.log(
            action="fetch",
            resource_type="url",
            resource_id=url,
            status=status,
            details=details,
            error=error
        )
    
    def log_parse(self, document_id: str, status: str, parser: str, error: Optional[str] = None) -> None:
        """Log a document parsing operation."""
        self.log(
            action="parse",
            resource_type="document",
            resource_id=document_id,
            status=status,
            details={"parser": parser},
            error=error
        )
    
    def log_store(self, document_id: str, status: str, storage_key: str, error: Optional[str] = None) -> None:
        """Log a document storage operation."""
        self.log(
            action="store",
            resource_type="document",
            resource_id=document_id,
            status=status,
            details={"storage_key": storage_key},
            error=error
        )
    
    def log_skip(self, document_id: str, reason: str) -> None:
        """Log a skipped document (e.g., duplicate)."""
        self.log(
            action="skip",
            resource_type="document",
            resource_id=document_id,
            status="skipped",
            details={"reason": reason}
        )
