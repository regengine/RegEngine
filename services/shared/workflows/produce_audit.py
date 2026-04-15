"""
Workflow: Audit Artifact Production

Creates tamper-evident audit records for compliance actions.
The audit trail is RegEngine's proof of work — when the FDA asks
"show me your records," this is what produces them.

Pipeline:
    1. Build audit event (actor, resource, action, context)
    2. Compute HMAC hash for tamper evidence
    3. Chain to previous audit entry (hash chain)
    4. Persist to audit storage backend
    5. [Optional] Trigger hooks (notifications, exports)

TRUST-CRITICAL: The integrity module (HMAC chain) is the foundation
of audit immutability. Changes to integrity.py require extreme caution.

Entry point:
    services/shared/audit_logging/writer.py
        AuditLogger (singleton via get_instance())
            .log_event()          — create audit record
            .log_compliance()     — compliance-specific shorthand
            .log_data_access()    — data access audit
        audit_action() decorator  — wrap any function with audit logging

    Integrity (TRUST-CRITICAL):
        services/shared/audit_logging/integrity.py
            AuditIntegrity          — HMAC hash chain builder
            verify_audit_chain()    — chain verification

    Storage backends:
        services/shared/audit_logging/storage.py
            AuditStorageBackend     — abstract interface
            InMemoryAuditStorage    — default (ephemeral — for dev/test only)

    Schema:
        services/shared/audit_logging/schema.py
            AuditEvent, AuditActor, AuditResource, AuditContext
            AuditEventCategory, AuditEventType, AuditSeverity

Side effects (explicit):
    - Storage write: audit record to configured backend
    - HMAC computation: chain hash for tamper evidence

Known issues:
    - Default storage is InMemoryAuditStorage — audit records are LOST
      on process restart unless a persistent backend is configured.
      Production must configure a DB-backed or file-backed storage.
    - Hook system (add_hook) exists but persistent storage hook is not
      auto-configured — requires explicit setup at service startup.
"""
