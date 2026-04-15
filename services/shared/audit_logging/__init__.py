"""
Comprehensive Audit Logging — re-exports from submodules.

Package layout:
    shared/audit_logging/schema.py     — enums + data classes
    shared/audit_logging/integrity.py  — HMAC hash chain (TRUST-CRITICAL)
    shared/audit_logging/storage.py    — storage backends (abstract + in-memory)
    shared/audit_logging/writer.py     — AuditLogger, convenience methods, decorator
"""

# Schema — enums and data classes
from shared.audit_logging.schema import (  # noqa: F401
    AuditEventCategory,
    AuditEventType,
    AuditSeverity,
    AuditActor,
    AuditResource,
    AuditContext,
    AuditEvent,
)

# Integrity — TRUST-CRITICAL hash chain logic
from shared.audit_logging.integrity import (  # noqa: F401
    AuditIntegrity,
    verify_audit_chain,
)

# Storage backends
from shared.audit_logging.storage import (  # noqa: F401
    AuditStorageBackend,
    InMemoryAuditStorage,
)

# Writer — main interface, convenience methods, decorator
from shared.audit_logging.writer import (  # noqa: F401
    AuditLogger,
    audit_action,
    get_audit_logger,
)
