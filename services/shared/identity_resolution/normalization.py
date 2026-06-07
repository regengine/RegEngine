"""
Structured-identifier normalization for identity resolution (#1212).

Mechanically split out of ``service.py`` — no logic changes. The
``service`` module re-exports these names for backward compatibility.
"""

from __future__ import annotations

# Alias types that carry structured, machine-readable identifiers.
# These must be normalized before lookup and insert to prevent whitespace
# variants (e.g. " 0614141123452 " vs "0614141123452") from creating
# duplicate entity records (#1212).
#
# Excluded intentionally:
#   - "name", "trade_name", "abbreviation", "address_variant" — free-text;
#     normalization would mutate meaningful content.
#   - "tlc", "tlc_prefix" — Traceability Lot Codes are stored VERBATIM per
#     FSMA 204; their internal structure (supplier-defined suffix) must never
#     be altered (#1175).
_STRUCTURED_IDENTIFIER_ALIAS_TYPES: frozenset = frozenset({
    "gln", "gtin", "fda_registration", "internal_code", "duns",
})


def _normalize_identifier(kind: str, value: str) -> str:
    """Normalize a structured identifier before lookup or insert (#1212).

    Rules:
    - Strip leading/trailing whitespace on all structured identifier types.
    - Lowercase URN-form values (``urn:epc:...``, ``urn:gs1:...``).
    - Internal spaces are preserved — some identifier bodies contain them
      legitimately (e.g. certain FDA registration formats).
    - Free-text fields (names, addresses) and TLC values are returned
      unchanged (caller must not pass those types here).

    Args:
        kind:  The alias_type string (e.g. "gln", "fda_registration").
        value: The raw identifier value supplied by the caller.

    Returns:
        The normalized identifier string.
    """
    if kind not in _STRUCTURED_IDENTIFIER_ALIAS_TYPES:
        # Caller error — non-structured types should never reach this helper.
        # Return unchanged so callers that pass a name-type by mistake are not
        # silently mutated.
        return value
    normalized = value.strip()
    # Lowercase only if the value looks like a URN (case-insensitive prefix
    # check). E.g. "URN:EPC:id:sgln:..." → "urn:epc:id:sgln:..."
    if normalized.lower().startswith("urn:"):
        normalized = normalized.lower()
    return normalized
