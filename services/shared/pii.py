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


# ── Identifier / free-text masking for logs (#1233) ────────────────────────
# Regulated identifiers (DUNS, EIN, FDA registration numbers) and
# canonical names (PII under GDPR when the entity is a sole
# proprietor / natural person) must never land in log sinks in the
# clear. Log retention is typically longer than DB retention and log
# sinks are often accessible to a broader personnel set (SRE, observability
# vendors), so plaintext identifiers in logs widen the blast radius of
# any credential leak or vendor breach. These helpers produce a
# stable, correlatable-but-not-reversible surface.

import hashlib


def mask_identifier(value: str | None, *, keep_suffix: int = 2) -> str:
    """Mask a regulated identifier for safe logging.

    Shows the last ``keep_suffix`` characters plus a short SHA-256 prefix
    so operators can correlate log lines without reconstructing the
    identifier. The full value is never emitted.

    ``keep_suffix`` defaults to 2 so a 9-digit EIN/DUNS reveals only
    the last two characters. Set to 0 to hide all characters.

    Examples:
        >>> mask_identifier("123456789")     # doctest: +SKIP
        '***89#sha256:a3b5...'
        >>> mask_identifier(None)
        '<none>'
        >>> mask_identifier("")
        '<empty>'
    """
    if value is None:
        return "<none>"
    if not isinstance(value, str):
        value = str(value)
    if not value:
        return "<empty>"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    if keep_suffix <= 0 or len(value) <= keep_suffix:
        return f"***#sha256:{digest}"
    return f"***{value[-keep_suffix:]}#sha256:{digest}"


def mask_name(value: str | None) -> str:
    """Mask a canonical entity / personal name for logs.

    Shows only the first character to preserve some debuggability; the
    rest is replaced and a short SHA-256 suffix lets operators join
    log lines that refer to the same name without exposing it.

    Examples:
        >>> mask_name("Acme Supply Co")   # doctest: +SKIP
        'A***#sha256:4f1e...'
        >>> mask_name("")
        '<empty>'
        >>> mask_name(None)
        '<none>'
    """
    if value is None:
        return "<none>"
    if not isinstance(value, str):
        value = str(value)
    if not value:
        return "<empty>"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    return f"{value[:1]}***#sha256:{digest}"


# Alias types that must NEVER have their value logged in the clear.
# This is the authoritative closed set — downstream services
# should import from here rather than hard-coding.
SENSITIVE_ALIAS_TYPES: frozenset[str] = frozenset({
    "duns",
    "fda_registration",
    "internal_code",
    "ein",
    "ssn",
    "tin",
    "passport",
    "drivers_license",
})


def mask_alias_value(alias_type: str | None, alias_value: str | None) -> str:
    """Dispatch on alias_type: sensitive types get hashed+suffixed;
    non-sensitive types (e.g. ``name``, ``trade_name``) get name-masked.

    The function never returns the raw value. Callers that need the
    raw value for DB writes must NOT route it through here.
    """
    if alias_type and alias_type.lower() in SENSITIVE_ALIAS_TYPES:
        return mask_identifier(alias_value)
    return mask_name(alias_value)
