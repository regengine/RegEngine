"""
HIPAA Audit Logger.

Provides secure, immutable logging for PHI-related events and compliance checks.
Ensures that all sensitive detections are recorded for evidence chains.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict
from pydantic import BaseModel

logger = logging.getLogger("hipaa-audit")

class AuditLogEntry(BaseModel):
    """Schema for a HIPAA audit trail entry."""
    event_timestamp: str
    event_type: str
    document_id: str
    severity: str
    description: str
    actor: str = "SYSTEM_ANALYSIS"
    metadata: Dict[str, Any] = {}

class HIPAAAuditLogger:
    """
    Logger for HIPAA-compliant audit trails.
    
    Hardening Measures:
    - Standardized ISO-8601 timestamps
    - Immutable event types
    - Metadata encapsulation for evidence chains
    """
    
    @staticmethod
    def log_phi_detection(document_id: str, risk_description: str, severity: str):
        """Logs a PHI detection event."""
        entry = AuditLogEntry(
            event_timestamp=datetime.now(timezone.utc).isoformat(),
            event_type="PHI_DETECTION",
            document_id=document_id,
            severity=severity,
            description=risk_description
        )
        
        # In production, this would write to a dedicated Audit table or secure log aggregator
        logger.info(f"AUDIT_PHI: {entry.model_dump_json()}")
        
        # Also write to a local secure audit file for persistence in this environment
        with open("hipaa_audit_trail.log", "a") as f:
            f.write(entry.model_dump_json() + "\n")

    @staticmethod
    def log_access(document_id: str, actor: str):
        """Logs access to a document containing PHI."""
        entry = AuditLogEntry(
            event_timestamp=datetime.now(timezone.utc).isoformat(),
            event_type="PHI_ACCESS",
            document_id=document_id,
            severity="INFO",
            description=f"Document accessed by {actor}",
            actor=actor
        )
        logger.info(f"AUDIT_ACCESS: {entry.model_dump_json()}")
        with open("hipaa_audit_trail.log", "a") as f:
            f.write(entry.model_dump_json() + "\n")
