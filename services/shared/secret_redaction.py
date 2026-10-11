"""Secret hygiene for logs, consoles and scripts (Pattern 11).

One shared mechanism for the whole repo:

- ``mask_secret``: safe one-way display of a credential (prefix plus a
  short fingerprint, never the full value). Use it whenever an operator
  needs to confirm *which* secret was used.
- ``redact_text``: scrub secret-shaped material out of free text before
  it reaches a log sink, an error response or a console.
- ``redact_secrets``: structlog processor wired into
  ``shared.observability.log_config`` so every service redacts by
  default. Never raises; logging must not break because of redaction.
- ``read_secret``: read a credential from the environment only. Secrets
  never come from argv, defaults or committed files.

Plain English, no em dashes or en dashes, and no exactly-once claims.
"""

from __future__ import annotations

import hashlib
import os
import re
from typing import Any

REDACTED = "[REDACTED]"

# Value shown when there is nothing to mask. Distinct from REDACTED so a
# missing secret is distinguishable from a redacted one in output.
_MISSING = "<not-set>"

# Known secret env var names. Used by read_secret docs and by redact_text
# for KEY=value assignment shapes.
SECRET_ENV_NAMES = frozenset(
    {
        "POSTGRES_PASSWORD",
        "NEO4J_PASSWORD",
        "NEO4J_AUTH",
        "KAFKA_PASSWORD",
        "OBJECT_STORAGE_SECRET_ACCESS_KEY",
        "OBJECT_STORAGE_ACCESS_KEY_ID",
        "REGENGINE_API_KEY",
        "REGENGINE_TENANT_API_KEY",
        "ADMIN_MASTER_KEY",
        "AUTH_SECRET_KEY",
        "JWT_SECRET",
        "PHASE2B_API_SECRET",
        "LLAMA_CLOUD_API_KEY",
        "OPENAI_API_KEY",
        "RESEND_API_KEY",
        "STRIPE_SECRET_KEY",
        "API_KEY_HASH_PEPPER",
        "REGENGINE_API_KEY_HASH_PEPPER",
        "PGPASSWORD",
    }
)

# Secret shapes scrubbed out of free text. Each pair is (pattern,
# replacement). Patterns are intentionally narrow: they match credential
# shapes, not ordinary words, so normal log text passes through.
_REDACT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # RegEngine API keys: rge_<keyid>.<secret> or bare rge_ tokens.
    (re.compile(r"\brge_[A-Za-z0-9_.-]{4,}(?:\.[A-Za-z0-9_.-]{4,})?"), REDACTED),
    # Common third-party key prefixes.
    (re.compile(r"\bsk-(?:live|test)-[A-Za-z0-9]{8,}"), REDACTED),
    (re.compile(r"\bxox[abpas]-[A-Za-z0-9-]{8,}"), REDACTED),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{8,}"), REDACTED),
    (re.compile(r"\bAKIA[0-9A-Z]{12,}"), REDACTED),
    # Authorization style headers: "Authorization: Bearer <token>" and the
    # RegEngine header "X-RegEngine-API-Key: <key>".
    (re.compile(r"(?i)(authorization\s*:\s*(?:bearer|token)\s+)\S+"), r"\1" + REDACTED),
    # Standalone auth tokens and JWTs logged as bare values (no header name).
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/=]{8,}"), REDACTED),
    (re.compile(r"\beyJ[A-Za-z0-9\-_]{10,}\.[A-Za-z0-9\-_]{10,}"), REDACTED),
    (re.compile(r"(?i)(x-regengine-api-key\s*:\s*)\S+"), r"\1" + REDACTED),
    (re.compile(r"(?i)(api[_-]?key\s*[:=]\s*['\"]?)\S+"), r"\1" + REDACTED),
    # Password style query params and assignments: ?password=..., &passwd=...
    (
        re.compile(r"(?i)([?&](?:password|passwd|pwd|secret|token)[^=]*=)[^&\s'\"]+"),
        r"\1" + REDACTED,
    ),
    # password=... inside database URLs: postgres://user:pass@host/...
    (re.compile(r"(?i)(://[^/\s:@]+:)[^@\s/]+@"), r"\1" + REDACTED + "@"),
    # KEY=value assignments for known secret env names.
    (
        re.compile(
            r"(?i)\b((?:PASSWORD|PASSWD|SECRET|PRIVATE_KEY|ACCESS_TOKEN|"
            r"REFRESH_TOKEN|CLIENT_SECRET|WEBHOOK_SECRET)\b\s*=)\s*\S+"
        ),
        r"\1=" + REDACTED,
    ),
    # PEM private key blocks.
    (
        re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----"),
        REDACTED,
    ),
)


def _fingerprint(value: str) -> str:
    """Return a short non-reversible fingerprint for correlation."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]


def mask_secret(value: Any, *, show_prefix: int = 4) -> str:
    """Return a safe display form of a credential.

    Shows the first ``show_prefix`` characters plus a short SHA-256
    fingerprint so operators can tell secrets apart without seeing them.
    The full value is never returned. Non-string input is coerced, and
    empty or missing values report as missing rather than blank.

    For RegEngine ``rge_<keyid>.<secret>`` keys the public key id is
    shown in the clear (it is already stored and logged as ``key_id``)
    while the secret half is masked.
    """
    if value is None:
        return _MISSING
    text = value if isinstance(value, str) else str(value)
    if not text:
        return _MISSING
    if text.startswith("rge_") and "." in text:
        key_id, _secret = text.split(".", 1)
        return f"{key_id}.***#sha256:{_fingerprint(text)}"
    prefix = text[:show_prefix] if len(text) > show_prefix else ""
    if prefix:
        return f"{prefix}***#sha256:{_fingerprint(text)}"
    return f"***#sha256:{_fingerprint(text)}"


def redact_text(text: Any) -> Any:
    """Scrub secret-shaped material from free text.

    Non-string input passes through unchanged. Strings have every known
    credential shape replaced with ``[REDACTED]``. Ordinary text,
    including key ids without secrets, is returned unchanged.
    """
    if not isinstance(text, str) or not text:
        return text
    result = text
    for pattern, replacement in _REDACT_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def _redact_value(value: Any, *, _depth: int = 0) -> Any:
    """Recursively redact strings inside log event structures."""
    if _depth > 4:
        return value
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {key: _redact_value(item, _depth=_depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        redacted = [_redact_value(item, _depth=_depth + 1) for item in value]
        return type(value)(redacted) if isinstance(value, tuple) else redacted
    return value


def redact_secrets(logger: Any, method: str, event_dict: dict) -> dict:
    """Structlog processor: redact secret shapes from every log record.

    Registered once in ``shared.observability.log_config`` so all
    services mask by default. Never raises: on any internal error the
    original event dict is returned untouched, because logging must not
    break due to redaction.
    """
    try:
        return {key: _redact_value(item) for key, item in event_dict.items()}
    except Exception:
        return event_dict


def read_secret(name: str, *, required: bool = False, default: str = "") -> str:
    """Read a credential from the environment only.

    Secrets never come from argv, interactive defaults written to disk,
    or committed files. When ``required`` is true and the variable is
    missing or empty, raise ``RuntimeError`` naming the variable, never
    its value.
    """
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(f"Secret {name} is not set; export it in the environment")
    return value
