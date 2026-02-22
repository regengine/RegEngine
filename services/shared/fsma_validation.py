"""
FSMA 204 Identifier Validation Utilities.

Self-contained module providing high-integrity validation for GS1 and FDA
identifiers used in food traceability (FSMA 204 compliance).

Exports
-------
IdentifierType          – enum of supported identifier kinds
ValidationSeverity      – enum for error/warning/info
ValidationError         – single validation issue
ValidationResult        – full validation outcome (incl. identifier_type & warnings)
validate_gln            – GLN-13 with GS1 check digit
validate_gtin           – GTIN-8/12/13/14 with GS1 check digit
validate_tlc            – Traceability Lot Code (flexible format)
validate_sscc           – SSCC-18 with GS1 check digit
validate_identifier     – auto-detecting dispatcher
validate_batch          – batch validation helper
"""

import re
from enum import Enum
from typing import List, Optional, Tuple
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class IdentifierType(str, Enum):
    TLC = "TLC"
    GTIN = "GTIN"
    GLN = "GLN"
    SSCC = "SSCC"
    UNKNOWN = "UNKNOWN"


class ValidationSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ValidationError:
    field: str
    message: str
    severity: ValidationSeverity = ValidationSeverity.ERROR


@dataclass
class ValidationResult:
    is_valid: bool
    identifier_type: IdentifierType = IdentifierType.UNKNOWN
    original_value: Optional[str] = None
    normalized_value: Optional[str] = None
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _gs1_check_digit(digits: str) -> int:
    """Calculate GS1 check digit for a numeric string (without the check digit)."""
    total = sum(
        int(d) * (3 if i % 2 else 1)
        for i, d in enumerate(reversed(digits))
    )
    return (10 - (total % 10)) % 10


def _validate_gs1_check(clean: str, field_name: str, id_type: IdentifierType) -> Optional[ValidationResult]:
    """Return a failure result if the GS1 check digit is wrong, else None."""
    expected = _gs1_check_digit(clean[:-1])
    if int(clean[-1]) != expected:
        return ValidationResult(
            is_valid=False,
            identifier_type=id_type,
            original_value=clean,
            errors=[ValidationError(field=field_name, message=f"Check digit invalid (expected {expected})")],
        )
    return None


# ---------------------------------------------------------------------------
# Individual validators
# ---------------------------------------------------------------------------

def validate_gln(gln: str) -> ValidationResult:
    """Validate GS1 Global Location Number (13 digits with check digit)."""
    if not gln:
        return ValidationResult(
            is_valid=False,
            identifier_type=IdentifierType.GLN,
            original_value=gln,
            errors=[ValidationError(field="gln", message="GLN is required")],
        )

    clean = re.sub(r"\D", "", gln)
    if len(clean) != 13:
        return ValidationResult(
            is_valid=False,
            identifier_type=IdentifierType.GLN,
            original_value=gln,
            errors=[ValidationError(field="gln", message="GLN must be 13 numeric digits")],
        )

    chk = _validate_gs1_check(clean, "gln", IdentifierType.GLN)
    if chk:
        chk.original_value = gln
        return chk

    return ValidationResult(
        is_valid=True, identifier_type=IdentifierType.GLN,
        original_value=gln, normalized_value=clean,
    )


def validate_gtin(gtin: str) -> ValidationResult:
    """Validate GS1 Global Trade Item Number (GTIN-8/12/13/14)."""
    if not gtin:
        return ValidationResult(
            is_valid=False,
            identifier_type=IdentifierType.GTIN,
            original_value=gtin,
            errors=[ValidationError(field="gtin", message="GTIN is required")],
        )

    clean = re.sub(r"\D", "", gtin)
    if len(clean) not in (8, 12, 13, 14):
        return ValidationResult(
            is_valid=False,
            identifier_type=IdentifierType.GTIN,
            original_value=gtin,
            errors=[ValidationError(field="gtin", message="GTIN must be 8, 12, 13, or 14 numeric digits")],
        )

    chk = _validate_gs1_check(clean, "gtin", IdentifierType.GTIN)
    if chk:
        chk.original_value = gtin
        return chk

    # Normalize to GTIN-14
    normalized = clean.zfill(14)
    warnings: List[str] = []
    if len(clean) != 14:
        warnings.append(f"Normalized from GTIN-{len(clean)} to GTIN-14")

    return ValidationResult(
        is_valid=True, identifier_type=IdentifierType.GTIN,
        original_value=gtin, normalized_value=normalized, warnings=warnings,
    )


def validate_tlc(tlc: str, *, strict: bool = False) -> ValidationResult:
    """
    Validate Traceability Lot Code (TLC).

    FSMA 204 allows flexible TLC formats.  We enforce minimum length (3)
    and optional strict pattern matching.
    """
    raw = str(tlc) if tlc else ""
    cleaned = raw.strip()

    if len(cleaned) < 3:
        return ValidationResult(
            is_valid=False,
            identifier_type=IdentifierType.TLC,
            original_value=raw,
            errors=[ValidationError(field="tlc", message="TLC must be at least 3 characters")],
        )

    warnings: List[str] = []

    if strict:
        # Strict mode: alphanumeric + hyphens only
        if not re.match(r"^[A-Za-z0-9\-]+$", cleaned):
            return ValidationResult(
                is_valid=False,
                identifier_type=IdentifierType.TLC,
                original_value=raw,
                errors=[ValidationError(
                    field="tlc",
                    message="TLC contains invalid characters (strict mode: alphanumeric + hyphens only)",
                )],
            )

    # Warn on very long TLCs
    if len(cleaned) > 50:
        warnings.append("TLC is unusually long (>50 characters)")

    return ValidationResult(
        is_valid=True, identifier_type=IdentifierType.TLC,
        original_value=raw, normalized_value=cleaned, warnings=warnings,
    )


def validate_sscc(sscc: str) -> ValidationResult:
    """Validate GS1 Serial Shipping Container Code (18 digits with check digit)."""
    if not sscc:
        return ValidationResult(
            is_valid=False,
            identifier_type=IdentifierType.SSCC,
            original_value=sscc,
            errors=[ValidationError(field="sscc", message="SSCC is required")],
        )

    clean = re.sub(r"\D", "", sscc)
    if len(clean) != 18:
        return ValidationResult(
            is_valid=False,
            identifier_type=IdentifierType.SSCC,
            original_value=sscc,
            errors=[ValidationError(field="sscc", message="SSCC must be 18 numeric digits")],
        )

    chk = _validate_gs1_check(clean, "sscc", IdentifierType.SSCC)
    if chk:
        chk.original_value = sscc
        return chk

    return ValidationResult(
        is_valid=True, identifier_type=IdentifierType.SSCC,
        original_value=sscc, normalized_value=clean,
    )


# ---------------------------------------------------------------------------
# Auto-detecting dispatcher
# ---------------------------------------------------------------------------

def _detect_identifier_type(value: str) -> IdentifierType:
    """Best-effort auto-detection of identifier type from its format."""
    clean = re.sub(r"\D", "", value)
    if clean == value:  # purely numeric
        length = len(clean)
        if length == 18:
            return IdentifierType.SSCC
        if length == 13:
            return IdentifierType.GLN
        if length in (8, 12, 14):
            return IdentifierType.GTIN
    # Fallback: if it's alphanumeric, assume TLC
    return IdentifierType.TLC


_VALIDATORS = {
    IdentifierType.GLN: lambda v, **_kw: validate_gln(v),
    IdentifierType.GTIN: lambda v, **_kw: validate_gtin(v),
    IdentifierType.TLC: lambda v, **kw: validate_tlc(v, strict=kw.get("strict", False)),
    IdentifierType.SSCC: lambda v, **_kw: validate_sscc(v),
}


def validate_identifier(
    value: str,
    *,
    expected_type: Optional[IdentifierType] = None,
    strict: bool = False,
) -> ValidationResult:
    """
    Validate any FSMA identifier with optional auto-detection.

    If *expected_type* is ``None`` the type is inferred from format.
    """
    id_type = expected_type or _detect_identifier_type(value)
    validator = _VALIDATORS.get(id_type)
    if validator is None:
        return ValidationResult(
            is_valid=False,
            identifier_type=id_type,
            original_value=value,
            errors=[ValidationError(field="identifier", message=f"Unsupported identifier type: {id_type}")],
        )
    return validator(value, strict=strict)


# ---------------------------------------------------------------------------
# Batch validation
# ---------------------------------------------------------------------------

def validate_batch(
    identifiers: List[Tuple[str, Optional[IdentifierType]]],
    *,
    strict: bool = False,
) -> List[ValidationResult]:
    """Validate a list of ``(value, expected_type)`` tuples."""
    return [
        validate_identifier(value, expected_type=expected_type, strict=strict)
        for value, expected_type in identifiers
    ]
