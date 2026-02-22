"""
FSMA 204 Identifier Validation Utilities.

This module provides high-integrity validation for GS1 and FDA identifiers
used in food traceability (FSMA 204 compliance).
"""

import re
from enum import Enum
from typing import List, Optional
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Validation primitives (self-contained — no external dependency)
# ---------------------------------------------------------------------------

class ValidationSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationError:
    field: str
    message: str
    severity: ValidationSeverity = ValidationSeverity.ERROR


@dataclass
class ValidationResult:
    is_valid: bool
    original_value: Optional[str] = None
    normalized_value: Optional[str] = None
    errors: List[ValidationError] = field(default_factory=list)


# ---------------------------------------------------------------------------
# GS1 Identifier Validators
# ---------------------------------------------------------------------------

def _gs1_check_digit(digits: str) -> int:
    """Calculate GS1 check digit for a numeric string (without the check digit)."""
    total = sum(
        int(d) * (3 if i % 2 else 1)
        for i, d in enumerate(reversed(digits))
    )
    return (10 - (total % 10)) % 10


def validate_gln(gln: str) -> ValidationResult:
    """
    Validate GS1 Global Location Number (13 digits with check digit).
    """
    if not gln:
        return ValidationResult(
            is_valid=False,
            original_value=gln,
            errors=[ValidationError(field="gln", message="GLN is required")],
        )

    clean = re.sub(r"\D", "", gln)
    if len(clean) != 13:
        return ValidationResult(
            is_valid=False,
            original_value=gln,
            errors=[ValidationError(field="gln", message="GLN must be 13 numeric digits")],
        )

    expected = _gs1_check_digit(clean[:12])
    if int(clean[12]) != expected:
        return ValidationResult(
            is_valid=False,
            original_value=gln,
            errors=[ValidationError(field="gln", message=f"GLN check digit invalid (expected {expected})")],
        )

    return ValidationResult(is_valid=True, original_value=gln, normalized_value=clean)

def validate_gtin(gtin: str) -> ValidationResult:
    """
    Validate GS1 Global Trade Item Number (GTIN-14).
    Ensures the code is exactly 14 digits after normalization.
    """
    if not gtin:
        return ValidationResult(
            is_valid=False, 
            original_value=gtin, 
            errors=[ValidationError(field="gtin", message="GTIN is required", severity=ValidationSeverity.ERROR)]
        )
    
    clean_gtin = re.sub(r'\D', '', gtin)
    if len(clean_gtin) != 14:
         return ValidationResult(
            is_valid=False, 
            original_value=gtin, 
            errors=[ValidationError(field="gtin", message="GTIN must be 14 numeric digits", severity=ValidationSeverity.ERROR)]
        )
         
    return ValidationResult(is_valid=True, original_value=gtin, normalized_value=clean_gtin)

def validate_tlc(tlc: str) -> ValidationResult:
    """
    Validate Traceability Lot Code (TLC) format.
    FSMA 204 doesn't mandate a specific TLC format, but this implementation
    enforces a minimum length of 3 characters to prevent junk data.
    """
    if not tlc or len(str(tlc).strip()) < 3:
        return ValidationResult(
            is_valid=False, 
            original_value=str(tlc), 
            errors=[ValidationError(field="tlc", message="TLC must be at least 3 characters", severity=ValidationSeverity.ERROR)]
        )
    
    return ValidationResult(is_valid=True, original_value=str(tlc), normalized_value=str(tlc).strip())
