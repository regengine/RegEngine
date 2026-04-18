"""
GS1 identifier validators for the FSMA 204 rules engine.

The previous GLN validator was a regex with the shape
    ^\\d{13}$|^[^0-9].*$|^$
which passed:
  - any empty string,
  - any non-numeric string,
  - any 13-digit string (regardless of check digit).

That is a no-op — it accepts the exact inputs it should reject. See #1357.

ISO/IEC 15420 (GS1 General Specifications §3.4.2) defines a GLN as exactly
13 numeric digits. The 13th digit is a mod-10 check digit computed from
the first 12 via the GS1 weighting scheme:

    d_12 .. d_1  (right-to-left after you strip the check digit)
    multiply by alternating weights 3, 1, 3, 1, …
    sum, take (10 - sum % 10) % 10  →  check digit

This module provides:

    is_valid_gln(s)  — full validation: 13 digits + correct check digit.
    is_valid_gtin(s) — same rules for GTIN-8 / GTIN-12 / GTIN-13 / GTIN-14.
    gs1_check_digit(digits) — the raw checksum computation, exposed so
                              tests can assert FDA sample values.
"""

from __future__ import annotations

from typing import Optional


# --- Raw GS1 check-digit computation --------------------------------------


def gs1_check_digit(digits: str) -> int:
    """Compute the GS1 mod-10 check digit for the given digit string.

    Args:
        digits: A string of numeric characters — the identifier WITHOUT
                its final check digit. For a GLN pass the first 12 digits.

    Returns:
        The expected check digit as an int 0-9.

    Raises:
        ValueError: if ``digits`` contains non-digit characters or is empty.
    """
    if not digits or not digits.isdigit():
        raise ValueError("digits must be a non-empty numeric string")

    # GS1 rule: right-to-left weighting of 3, 1, 3, 1, …
    total = 0
    for i, ch in enumerate(reversed(digits)):
        weight = 3 if i % 2 == 0 else 1
        total += int(ch) * weight
    return (10 - (total % 10)) % 10


# --- Public validators ----------------------------------------------------


def is_valid_gln(value: Optional[str]) -> bool:
    """True iff ``value`` is a 13-digit GLN with a valid GS1 check digit.

    An empty or non-string input is NOT a valid GLN. Callers that want to
    allow "field may be absent" should check for presence first and only
    invoke this validator when a value is present.
    """
    if not isinstance(value, str):
        return False
    if len(value) != 13 or not value.isdigit():
        return False
    try:
        expected = gs1_check_digit(value[:12])
    except ValueError:
        return False
    return expected == int(value[12])


_GTIN_LENGTHS = {8, 12, 13, 14}


def is_valid_gtin(value: Optional[str]) -> bool:
    """True iff ``value`` is a valid GTIN-8, GTIN-12, GTIN-13, or GTIN-14.

    Used by facility/product identifier rules downstream. Mod-10 is the
    same algorithm as GLN — only the length varies.
    """
    if not isinstance(value, str):
        return False
    if len(value) not in _GTIN_LENGTHS or not value.isdigit():
        return False
    try:
        expected = gs1_check_digit(value[:-1])
    except ValueError:
        return False
    return expected == int(value[-1])


__all__ = ["gs1_check_digit", "is_valid_gln", "is_valid_gtin"]
