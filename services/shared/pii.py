"""PII masking utilities for safe logging.

Provides functions to redact personally identifiable information before
it reaches log output, error responses, or observability pipelines.

Note: The immutable audit log (AuditLogger / AuditLogModel) intentionally
stores unmasked actor_email for FSMA 204 traceability. These masking
functions are for application logs, NOT audit records.
"""

from __future__ import annotations

import re

# PII patterns for redaction before external API calls (#981)
_PII_PATTERNS = [
    (re.compile(r'\b\d{3}-\d{2}-\d{4}\b'), '[SSN_REDACTED]'),
    (re.compile(r'\b(?:\+?1[-.]?)?\(?\d{3}\)?[-.]?\d{3}[-.]?\d{4}\b'), '[PHONE_REDACTED]'),
    (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), '[EMAIL_REDACTED]'),
    (re.compile(
        r'\b\d{1,5}\s+[\w\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|'
        r'Drive|Dr|Lane|Ln|Court|Ct|Way|Place|Pl)\b',
        re.IGNORECASE,
    ), '[ADDRESS_REDACTED]'),
]


def redact_pii(text: str) -> str:
    """Redact PII patterns from text before sending to external services.

    Targets SSNs, phone numbers, email addresses, and street addresses.
    """
    if not text or not isinstance(text, str):
        return text or ""
    result = text
    for pattern, replacement in _PII_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


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
