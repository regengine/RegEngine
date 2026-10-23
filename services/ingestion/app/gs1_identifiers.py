"""
Offline GS1 identifier validation for intake (SEL-429).

Strict format and check digit validation for GTIN, GLN and SSCC values
arriving through CSV uploads and the JSON events API. No network calls and
no GS1 registry lookup: a value that passes here is well formed, not proven
to be assigned to a real company.

The mod-10 math is delegated to ``shared.fsma_validation`` so the platform
keeps one check digit implementation. This module differs from the shared
validators in being strict about format: the shared ones strip every non
digit before checking, which would accept "0000 0000 0000 0" or a value with
letters mixed in. Here only leading and trailing whitespace is forgiven.

Error copy is plain language with no dashes, because it is shown to
suppliers next to the offending row.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from shared.fsma_validation import calculate_gs1_check_digit

# ASCII only: str.isdigit() also accepts superscripts and non Latin digits.
_DIGITS = re.compile(r"[0-9]+")

GTIN_LENGTHS = (8, 12, 13, 14)
GLN_LENGTHS = (13,)
SSCC_LENGTHS = (18,)


@dataclass(frozen=True)
class GS1Result:
    """Outcome of validating one GS1 identifier.

    ``value`` is the whitespace trimmed identifier when valid, else None.
    ``error`` is a plain, dash free sentence when invalid, else None.
    """

    is_valid: bool
    kind: str
    value: Optional[str] = None
    error: Optional[str] = None


def compute_gs1_check_digit(body: str) -> int:
    """Return the GS1 mod-10 check digit for *body* (identifier without its check digit).

    Raises ``ValueError`` if *body* is not a non empty string of digits.
    """
    return calculate_gs1_check_digit(body)


def _lengths_text(lengths: tuple[int, ...]) -> str:
    words = [str(n) for n in lengths]
    if len(words) == 1:
        return words[0]
    return ", ".join(words[:-1]) + " or " + words[-1]


def _validate(raw: Any, kind: str, lengths: tuple[int, ...]) -> GS1Result:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return GS1Result(False, kind, error=f"{kind} is empty. Enter the {kind} exactly as printed or issued.")
    if not isinstance(raw, str):
        # A JSON number silently drops leading zeros, so refuse it outright.
        return GS1Result(False, kind, error=f"{kind} must be sent as text so leading zeros are kept.")

    clean = raw.strip()
    if not _DIGITS.fullmatch(clean):
        return GS1Result(
            False,
            kind,
            error=f"{kind} contains characters other than digits. Use digits only, with no spaces, letters or punctuation.",
        )
    if len(clean) not in lengths:
        return GS1Result(
            False,
            kind,
            error=f"{kind} has {len(clean)} digits. A {kind} must have {_lengths_text(lengths)} digits.",
        )
    # The expected digit is deliberately not shown: a mismatch usually means a
    # typo elsewhere, and quoting the "right" last digit invites users to make
    # a wrong identifier look valid.
    if int(clean[-1]) != compute_gs1_check_digit(clean[:-1]):
        return GS1Result(
            False,
            kind,
            error=f"{kind} check digit does not match. Compare every digit with the source; one is likely mistyped.",
        )
    return GS1Result(True, kind, value=clean)


def validate_gtin(raw: Any) -> GS1Result:
    """Validate a GTIN of 8, 12, 13 or 14 digits."""
    return _validate(raw, "GTIN", GTIN_LENGTHS)


def validate_gln(raw: Any) -> GS1Result:
    """Validate a 13 digit GLN."""
    return _validate(raw, "GLN", GLN_LENGTHS)


def validate_sscc(raw: Any) -> GS1Result:
    """Validate an 18 digit SSCC."""
    return _validate(raw, "SSCC", SSCC_LENGTHS)


def describe_row_issue(result: GS1Result, *, field: str, row: int, supplier: Optional[str] = None) -> str:
    """Turn an invalid result into a per row fix naming the field, supplier and row."""
    who = f" from {supplier}" if supplier else ""
    return f"Row {row}{who}, field {field}: {result.error}"
