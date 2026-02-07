"""
FSMA 204 Traceability Lot Code (TLC) and Identifier Validation.

Provides validation for:
- Traceability Lot Codes (TLC) - flexible format with pattern matching
- Global Trade Item Numbers (GTIN) - 8, 12, 13, or 14 digits with check digit
- Global Location Numbers (GLN) - 13 digits with check digit
- Serial Shipping Container Codes (SSCC) - 18 digits with check digit

FSMA 204 does not mandate a specific TLC format, but requires consistency
and traceability throughout the supply chain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

import structlog

logger = structlog.get_logger("fsma-validation")


class IdentifierType(str, Enum):
    """Types of identifiers used in food traceability."""
    TLC = "TLC"  # Traceability Lot Code (flexible format)
    GTIN = "GTIN"  # Global Trade Item Number (8, 12, 13, or 14 digits)
    GLN = "GLN"  # Global Location Number (13 digits)
    SSCC = "SSCC"  # Serial Shipping Container Code (18 digits)
    CUSTOM = "CUSTOM"  # Custom/proprietary format


@dataclass
class ValidationResult:
    """Result of an identifier validation."""
    is_valid: bool
    identifier_type: IdentifierType
    original_value: str
    normalized_value: Optional[str] = None
    errors: List[str] = None
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []


# =============================================================================
# CHECK DIGIT ALGORITHMS (GS1 Standard)
# =============================================================================

def calculate_gs1_check_digit(digits: str) -> int:
    """
    Calculate GS1 check digit using modulo 10 algorithm.
    
    The algorithm:
    1. From right to left, multiply alternating digits by 3 and 1
    2. Sum all products
    3. Check digit = (10 - (sum % 10)) % 10
    
    Args:
        digits: String of digits (without check digit)
        
    Returns:
        Single check digit (0-9)
    """
    total = 0
    for i, digit in enumerate(reversed(digits)):
        multiplier = 3 if i % 2 == 0 else 1
        total += int(digit) * multiplier
    
    return (10 - (total % 10)) % 10


def verify_gs1_check_digit(full_number: str) -> bool:
    """
    Verify GS1 check digit is correct.
    
    Args:
        full_number: Complete number including check digit
        
    Returns:
        True if check digit is valid
    """
    if not full_number or not full_number.isdigit():
        return False
    
    digits = full_number[:-1]
    check_digit = int(full_number[-1])
    
    return calculate_gs1_check_digit(digits) == check_digit


# =============================================================================
# GTIN VALIDATION
# =============================================================================

# Common TLC patterns seen in food industry
TLC_PATTERNS = [
    # Date-based formats
    (r'^L[-/]?\d{4}[-/]?\d{2}[-/]?\d{2}[-/]?[A-Z0-9]+$', 'DATE_BATCH'),  # L-2024-01-15-A
    (r'^\d{4}[-/]?\d{2}[-/]?\d{2}[-/]?[A-Z0-9]+$', 'DATE_SIMPLE'),  # 20240115A
    (r'^LOT[-:#]?\s*[A-Z0-9-]+$', 'LOT_PREFIX'),  # LOT: ABC123
    (r'^BATCH[-:#]?\s*[A-Z0-9-]+$', 'BATCH_PREFIX'),  # BATCH-123
    (r'^[A-Z]{2,4}\d{6,12}[A-Z]?$', 'PLANT_DATE'),  # ABC20240115B
    # Julian date formats
    (r'^[A-Z]{1,3}\d{5}[A-Z]?$', 'JULIAN'),  # A24015B (plant code + julian date)
    # Sequential/alphanumeric
    (r'^[A-Z0-9]{5,20}$', 'ALPHANUMERIC'),  # Generic alphanumeric
]


def validate_gtin(value: str) -> ValidationResult:
    """
    Validate Global Trade Item Number (GTIN).
    
    GTIN can be 8, 12, 13, or 14 digits with GS1 check digit.
    - GTIN-8: 8 digits (UPC-E)
    - GTIN-12: 12 digits (UPC-A)
    - GTIN-13: 13 digits (EAN-13)
    - GTIN-14: 14 digits (ITF-14)
    
    Args:
        value: GTIN string to validate
        
    Returns:
        ValidationResult with validity status and any errors
    """
    # Normalize: remove spaces, dashes
    normalized = re.sub(r'[\s-]', '', value.strip())
    errors = []
    warnings = []
    
    # Check if all digits
    if not normalized.isdigit():
        errors.append(f"GTIN must contain only digits, found: {value}")
        return ValidationResult(
            is_valid=False,
            identifier_type=IdentifierType.GTIN,
            original_value=value,
            normalized_value=normalized,
            errors=errors,
        )
    
    # Check length
    if len(normalized) not in [8, 12, 13, 14]:
        errors.append(f"GTIN must be 8, 12, 13, or 14 digits. Got {len(normalized)} digits.")
        return ValidationResult(
            is_valid=False,
            identifier_type=IdentifierType.GTIN,
            original_value=value,
            normalized_value=normalized,
            errors=errors,
        )
    
    # Verify check digit
    if not verify_gs1_check_digit(normalized):
        expected = calculate_gs1_check_digit(normalized[:-1])
        actual = normalized[-1]
        errors.append(f"Invalid check digit. Expected {expected}, got {actual}.")
        return ValidationResult(
            is_valid=False,
            identifier_type=IdentifierType.GTIN,
            original_value=value,
            normalized_value=normalized,
            errors=errors,
        )
    
    # Check for known problematic patterns
    if normalized.startswith('0' * 5):
        warnings.append("GTIN has many leading zeros - verify this is correct")
    
    logger.debug("gtin_validated", gtin=normalized, length=len(normalized))
    
    return ValidationResult(
        is_valid=True,
        identifier_type=IdentifierType.GTIN,
        original_value=value,
        normalized_value=normalized,
        warnings=warnings,
    )


def validate_gln(value: str) -> ValidationResult:
    """
    Validate Global Location Number (GLN).
    
    GLN is exactly 13 digits with GS1 check digit.
    Used to identify physical locations in the supply chain.
    
    Args:
        value: GLN string to validate
        
    Returns:
        ValidationResult with validity status
    """
    normalized = re.sub(r'[\s-]', '', value.strip())
    errors = []
    
    if not normalized.isdigit():
        errors.append(f"GLN must contain only digits, found: {value}")
        return ValidationResult(
            is_valid=False,
            identifier_type=IdentifierType.GLN,
            original_value=value,
            normalized_value=normalized,
            errors=errors,
        )
    
    if len(normalized) != 13:
        errors.append(f"GLN must be exactly 13 digits. Got {len(normalized)} digits.")
        return ValidationResult(
            is_valid=False,
            identifier_type=IdentifierType.GLN,
            original_value=value,
            normalized_value=normalized,
            errors=errors,
        )
    
    if not verify_gs1_check_digit(normalized):
        expected = calculate_gs1_check_digit(normalized[:-1])
        actual = normalized[-1]
        errors.append(f"Invalid check digit. Expected {expected}, got {actual}.")
        return ValidationResult(
            is_valid=False,
            identifier_type=IdentifierType.GLN,
            original_value=value,
            normalized_value=normalized,
            errors=errors,
        )
    
    logger.debug("gln_validated", gln=normalized)
    
    return ValidationResult(
        is_valid=True,
        identifier_type=IdentifierType.GLN,
        original_value=value,
        normalized_value=normalized,
    )


def validate_sscc(value: str) -> ValidationResult:
    """
    Validate Serial Shipping Container Code (SSCC).
    
    SSCC is exactly 18 digits with GS1 check digit.
    Used to identify logistics units (pallets, containers).
    
    Args:
        value: SSCC string to validate
        
    Returns:
        ValidationResult with validity status
    """
    normalized = re.sub(r'[\s-]', '', value.strip())
    errors = []
    
    if not normalized.isdigit():
        errors.append(f"SSCC must contain only digits, found: {value}")
        return ValidationResult(
            is_valid=False,
            identifier_type=IdentifierType.SSCC,
            original_value=value,
            normalized_value=normalized,
            errors=errors,
        )
    
    if len(normalized) != 18:
        errors.append(f"SSCC must be exactly 18 digits. Got {len(normalized)} digits.")
        return ValidationResult(
            is_valid=False,
            identifier_type=IdentifierType.SSCC,
            original_value=value,
            normalized_value=normalized,
            errors=errors,
        )
    
    if not verify_gs1_check_digit(normalized):
        expected = calculate_gs1_check_digit(normalized[:-1])
        actual = normalized[-1]
        errors.append(f"Invalid check digit. Expected {expected}, got {actual}.")
        return ValidationResult(
            is_valid=False,
            identifier_type=IdentifierType.SSCC,
            original_value=value,
            normalized_value=normalized,
            errors=errors,
        )
    
    logger.debug("sscc_validated", sscc=normalized)
    
    return ValidationResult(
        is_valid=True,
        identifier_type=IdentifierType.SSCC,
        original_value=value,
        normalized_value=normalized,
    )


# =============================================================================
# TLC VALIDATION
# =============================================================================

def validate_tlc(value: str, strict: bool = False) -> ValidationResult:
    """
    Validate Traceability Lot Code (TLC).
    
    FSMA 204 allows flexible TLC formats. This validator checks:
    1. Minimum length (at least 3 characters)
    2. No dangerous characters (SQL injection, etc.)
    3. Matches a known pattern (optional in non-strict mode)
    4. Consistency with food industry conventions
    
    Args:
        value: TLC string to validate
        strict: If True, TLC must match a known pattern
        
    Returns:
        ValidationResult with validity status
    """
    errors = []
    warnings = []
    
    # Normalize whitespace
    normalized = value.strip().upper()
    
    # Minimum length check
    if len(normalized) < 3:
        errors.append(f"TLC must be at least 3 characters. Got {len(normalized)}.")
        return ValidationResult(
            is_valid=False,
            identifier_type=IdentifierType.TLC,
            original_value=value,
            normalized_value=normalized,
            errors=errors,
        )
    
    # Maximum length check (reasonable upper bound)
    if len(normalized) > 50:
        errors.append(f"TLC exceeds maximum length of 50 characters. Got {len(normalized)}.")
        return ValidationResult(
            is_valid=False,
            identifier_type=IdentifierType.TLC,
            original_value=value,
            normalized_value=normalized,
            errors=errors,
        )
    
    # Dangerous character check (security)
    dangerous_patterns = [
        (r'[<>"\']', 'Contains HTML/quote characters'),
        (r'[;]', 'Contains semicolon'),
        (r'--', 'Contains SQL comment sequence'),
        (r'\x00', 'Contains null byte'),
    ]
    
    for pattern, message in dangerous_patterns:
        if re.search(pattern, normalized):
            errors.append(f"TLC contains invalid characters: {message}")
            return ValidationResult(
                is_valid=False,
                identifier_type=IdentifierType.TLC,
                original_value=value,
                normalized_value=normalized,
                errors=errors,
            )
    
    # Pattern matching
    matched_pattern = None
    for pattern, pattern_name in TLC_PATTERNS:
        if re.match(pattern, normalized, re.IGNORECASE):
            matched_pattern = pattern_name
            break
    
    if strict and not matched_pattern:
        errors.append("TLC does not match any recognized format pattern")
        return ValidationResult(
            is_valid=False,
            identifier_type=IdentifierType.TLC,
            original_value=value,
            normalized_value=normalized,
            errors=errors,
        )
    
    if not matched_pattern:
        warnings.append("TLC format not recognized - ensure consistency across your supply chain")
    
    logger.debug("tlc_validated", tlc=normalized, pattern=matched_pattern)
    
    return ValidationResult(
        is_valid=True,
        identifier_type=IdentifierType.TLC,
        original_value=value,
        normalized_value=normalized,
        warnings=warnings,
    )


# =============================================================================
# AUTO-DETECTION AND VALIDATION
# =============================================================================

def detect_identifier_type(value: str) -> IdentifierType:
    """
    Auto-detect the type of identifier based on format.
    
    Args:
        value: Identifier string
        
    Returns:
        Detected IdentifierType
    """
    normalized = re.sub(r'[\s-]', '', value.strip())
    
    # Check if all digits
    if normalized.isdigit():
        length = len(normalized)
        if length == 18:
            return IdentifierType.SSCC
        elif length == 13:
            return IdentifierType.GLN  # Could also be GTIN-13
        elif length in [8, 12, 14]:
            return IdentifierType.GTIN
    
    # Default to TLC for alphanumeric
    return IdentifierType.TLC


def validate_identifier(
    value: str,
    expected_type: Optional[IdentifierType] = None,
    strict: bool = False,
) -> ValidationResult:
    """
    Validate an identifier with optional auto-detection.
    
    Args:
        value: Identifier string to validate
        expected_type: Expected type (if known), otherwise auto-detect
        strict: Apply strict validation rules
        
    Returns:
        ValidationResult with validity status
    """
    if expected_type is None:
        expected_type = detect_identifier_type(value)
    
    validators = {
        IdentifierType.GTIN: validate_gtin,
        IdentifierType.GLN: validate_gln,
        IdentifierType.SSCC: validate_sscc,
        IdentifierType.TLC: lambda v: validate_tlc(v, strict=strict),
        IdentifierType.CUSTOM: lambda v: validate_tlc(v, strict=False),
    }
    
    validator = validators.get(expected_type, validate_tlc)
    return validator(value)


# =============================================================================
# BATCH VALIDATION
# =============================================================================

def validate_batch(
    identifiers: List[Tuple[str, Optional[IdentifierType]]],
    strict: bool = False,
) -> List[ValidationResult]:
    """
    Validate a batch of identifiers.
    
    Args:
        identifiers: List of (value, expected_type) tuples
        strict: Apply strict validation
        
    Returns:
        List of ValidationResults
    """
    results = []
    for value, expected_type in identifiers:
        result = validate_identifier(value, expected_type, strict)
        results.append(result)
    
    # Log summary
    valid_count = sum(1 for r in results if r.is_valid)
    logger.info(
        "batch_validation_complete",
        total=len(results),
        valid=valid_count,
        invalid=len(results) - valid_count,
    )
    
    return results


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def normalize_gtin(gtin: str, target_length: int = 14) -> str:
    """
    Normalize GTIN to target length by zero-padding.
    
    All GTIN formats can be represented as GTIN-14 by left-padding with zeros.
    
    Args:
        gtin: Input GTIN (8, 12, 13, or 14 digits)
        target_length: Target length (default 14)
        
    Returns:
        Zero-padded GTIN
    """
    normalized = re.sub(r'[\s-]', '', gtin.strip())
    return normalized.zfill(target_length)


def extract_company_prefix(gtin: str) -> str:
    """
    Extract GS1 Company Prefix from GTIN.
    
    The company prefix is variable length (6-10 digits after the indicator).
    This returns the first 7 digits which typically contains the prefix.
    
    Args:
        gtin: Normalized GTIN-14
        
    Returns:
        Company prefix portion
    """
    normalized = normalize_gtin(gtin, 14)
    # Skip indicator digit, take next 7 digits as approximate prefix
    return normalized[1:8]
