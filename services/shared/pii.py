"""PII masking utilities for safe logging.

Provides functions to redact personally identifiable information before
it reaches log output, error responses, or observability pipelines.

Note: The immutable audit log (AuditLogger / AuditLogModel) intentionally
stores unmasked actor_email for FSMA 204 traceability. These masking
functions are for application logs, NOT audit records.
"""

from __future__ import annotations


def mask_email(email: str | None) -> str:
    """Mask an email address for safe logging.

    Preserves the first character of the local part and the full domain
    so logs remain useful for debugging without exposing the full address.

    Examples:
        >>> mask_email("jane.doe@example.com")
        'j***@example.com'
        >>> mask_email("a@b.com")
        'a***@b.com'
        >>> mask_email(None)
        '<no-email>'
    """
    if not email or not isinstance(email, str):
        return "<no-email>"

    try:
        local, domain = email.rsplit("@", 1)
        if not local:
            return f"***@{domain}"
        return f"{local[0]}***@{domain}"
    except ValueError:
        return "***"
