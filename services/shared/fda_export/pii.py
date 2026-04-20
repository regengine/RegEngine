"""PII redaction for FDA / FSMA-204 export rows.

An FDA export identifies lot codes and event types that the agency
legitimately needs to see. It also tends to sweep in *customer* PII:
supplier contact names, facility addresses, carrier driver names,
phone numbers. That material is not regulatory primary-key data — GLN
and FDA registration numbers are — so by default it must be redacted
from any export the regulated entity does not explicitly authorize.

EPIC-L mandates one redaction strategy shared by every export path:

* A fixed allowlist of PII column names gets replaced with a
  constant placeholder, *or* a stable SHA-256 hash prefix when the
  caller needs to correlate rows without learning the plaintext.
* The ``fda.export.full_pii`` permission (a strict superset of
  ``fda.export``) opts out of redaction; every such call is audited
  by the surrounding router, not this module.

Related issue: EPIC-L (#1655).
"""
from __future__ import annotations

import hashlib
from typing import Iterable, Mapping

# Permission required to receive un-redacted PII in an FDA export.
# Checked by the router with ``shared.permissions.has_permission``.
PII_PERMISSION = "fda.export.full_pii"

# Aliases accepted for back-compatibility — older routes used
# ``fda.export.pii`` before EPIC-L consolidated the scope name. Both
# grant the same capability during the migration window.
_PII_PERMISSION_ALIASES = frozenset({"fda.export.full_pii", "fda.export.pii"})

# Placeholder text used when a redacted value is still non-empty.
# Empty source values pass through unchanged — a blank cell should
# stay blank, not turn into "[REDACTED]".
PII_REDACTION_PLACEHOLDER = "[REDACTED]"

# Canonical set of column names (matching the FDA spreadsheet spec)
# whose contents are customer PII. Covered by default redaction.
# Column names are the *emitted* CSV header labels, not snake_case
# internal keys — routers map their internal keys through their own
# normalization before calling into this module.
DEFAULT_PII_COLUMNS: frozenset[str] = frozenset(
    {
        # Ingestion-service / FDA spreadsheet column labels
        "Location Name",
        "Ship From Name",
        "Ship To Name",
        "Immediate Previous Source",
        "Receiving Location",
        # Compliance-service / FSMA spreadsheet column keys
        "origin_name",
        "origin_address",
        "destination_name",
        "destination_address",
        "immediate_previous_source",
    }
)

# Key substrings that signal PII inside a JSON "extras" blob. Kept
# deliberately broad because the extras map carries customer-supplied
# KDE keys with inconsistent casing and naming.
_PII_KEY_SUBSTRINGS = (
    "address",
    "street",
    "location_name",
    "facility_name",
    "contact",
    "phone",
    "email",
    "owner_name",
    "operator_name",
    "driver_name",
    "receiver_name",
    "consignee_name",
)


def _caller_has_full_pii(caller_scopes: Iterable[str] | None) -> bool:
    """Return True if ``caller_scopes`` grants un-redacted PII access.

    Wildcard ``*`` grants everything; the explicit PII permissions are
    also accepted. A missing / empty scope list is treated as "no".
    """
    if not caller_scopes:
        return False
    scopes = {s.strip().lower() for s in caller_scopes if s}
    if "*" in scopes:
        return True
    for scope in scopes:
        if scope in _PII_PERMISSION_ALIASES:
            return True
        # Dotted / colon wildcard matching: ``fda.*`` implies PII.
        if scope in {"fda.*", "fda:*"}:
            return True
    return False


def hash_pii_value(value: str, *, length: int = 12) -> str:
    """Return a stable short hash of ``value``.

    Used when the export caller needs to see that two rows carry the
    same underlying PII (e.g. same carrier across shipments) without
    receiving the plaintext. Empty or falsy values return ``""``.
    """
    if not value:
        return ""
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()
    return "pii_" + digest[:length]


def redact_pii_row(
    row: Mapping[str, object],
    caller_scopes: Iterable[str] | None = None,
    *,
    pii_columns: Iterable[str] | None = None,
    strategy: str = "placeholder",
) -> dict[str, object]:
    """Return a copy of ``row`` with PII columns redacted.

    Parameters
    ----------
    row:
        Dict-style row. Values are assumed to already be formula-safe
        (callers pass in :func:`safe_cell`-processed strings), this
        module only handles the PII dimension.
    caller_scopes:
        The authenticated principal's permission list. When it grants
        :data:`PII_PERMISSION` (or ``*``), the row is returned
        unchanged — the caller is responsible for router-level
        auditing of that decision.
    pii_columns:
        Override the default set of PII column names. Defaults to
        :data:`DEFAULT_PII_COLUMNS`.
    strategy:
        ``"placeholder"`` (default) replaces PII values with
        :data:`PII_REDACTION_PLACEHOLDER`.
        ``"hash"`` replaces them with a short stable hash via
        :func:`hash_pii_value` — useful when downstream readers need to
        correlate rows without learning plaintext.

    Empty string values are never substituted — a blank column stays
    blank so a downstream reader sees a gap, not a confusing
    "[REDACTED]" marker.
    """
    if _caller_has_full_pii(caller_scopes):
        # Copy to keep the contract stable (callers shouldn't have to
        # worry about whether we mutated their input).
        return dict(row)

    columns = set(pii_columns) if pii_columns is not None else set(DEFAULT_PII_COLUMNS)
    out: dict[str, object] = {}
    for key, value in row.items():
        if key in columns and isinstance(value, str) and value:
            if strategy == "hash":
                out[key] = hash_pii_value(value)
            else:
                out[key] = PII_REDACTION_PLACEHOLDER
        else:
            out[key] = value
    return out


def redact_pii_extras(
    extras: Mapping[str, object],
    caller_scopes: Iterable[str] | None = None,
) -> dict[str, object]:
    """Redact PII values inside a freeform "Additional KDEs" blob.

    Preserves the key so auditors still see "this field existed but
    was redacted"; only the string value is substituted. Non-string
    values pass through (numeric PII is uncommon in KDE data).
    """
    if _caller_has_full_pii(caller_scopes):
        return dict(extras)
    out: dict[str, object] = {}
    for key, value in extras.items():
        key_lower = str(key).lower()
        is_pii = any(marker in key_lower for marker in _PII_KEY_SUBSTRINGS)
        if is_pii and isinstance(value, str) and value:
            out[key] = PII_REDACTION_PLACEHOLDER
        else:
            out[key] = value
    return out


__all__ = [
    "DEFAULT_PII_COLUMNS",
    "PII_PERMISSION",
    "PII_REDACTION_PLACEHOLDER",
    "hash_pii_value",
    "redact_pii_extras",
    "redact_pii_row",
]
