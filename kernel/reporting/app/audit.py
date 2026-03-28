"""
HIPAA Audit Logger.

Provides secure, immutable logging for PHI-related events and compliance checks.
Ensures that all sensitive detections are recorded for evidence chains.
"""
import fcntl
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from pydantic import BaseModel

logger = logging.getLogger("hipaa-audit")

# Configurable audit log path with secure defaults
_AUDIT_LOG_DIR = Path(os.environ.get("HIPAA_AUDIT_LOG_DIR", "/var/log/regengine/audit"))
_AUDIT_LOG_PATH = _AUDIT_LOG_DIR / "hipaa_audit_trail.log"


def _write_audit_entry(entry_json: str) -> None:
    """Write an audit entry with file locking and restrictive permissions."""
    # Ensure directory exists with restrictive permissions (owner-only)
    os.makedirs(_AUDIT_LOG_DIR, mode=0o700, exist_ok=True)

    # Open file with restrictive permissions (0o600 = owner read/write only); create if needed
    fd = os.open(
        str(_AUDIT_LOG_PATH),
        os.O_WRONLY | os.O_CREAT | os.O_APPEND,
        0o600,
    )
    try:
        with os.fdopen(fd, "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(entry_json + "\n")
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except Exception:
        # fd is already closed by os.fdopen on success; only close on fdopen failure
        try:
            os.close(fd)
        except OSError:
            pass
        raise


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
    - File locking (fcntl.flock) for concurrent write safety
    - Restrictive file permissions (0o600) on audit log
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

        # Write to secure audit file with locking and restrictive permissions
        _write_audit_entry(entry.model_dump_json())

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
        _write_audit_entry(entry.model_dump_json())
