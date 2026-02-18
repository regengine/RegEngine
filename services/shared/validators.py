"""
SEC-VAL: Active Validation Library for Data Integrity.

Provides validation functions for identifiers and data quality checks
to prevent corrupt data from entering the knowledge graph.

Validators:
- validate_gln: GS1 Global Location Number (13 digits + checksum)
- validate_fda_reg: FDA Facility Registration Number format
- validate_event_chain: Logic gate validation for event sequences
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

import structlog

logger = structlog.get_logger("validators")


class ValidationSeverity(str, Enum):
    """Severity levels for validation failures."""
    WARNING = "WARNING"       # Data quality issue, not blocking
    ERROR = "ERROR"           # Invalid data, should be reviewed
    CRITICAL = "CRITICAL"     # Invalid data, blocks processing


@dataclass
class ValidationError:
    """Individual validation error."""
    field: str
    message: str
    severity: ValidationSeverity
    value: Optional[str] = None
    expected: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of a validation check."""
    is_valid: bool
    original_value: str
    normalized_value: Optional[str] = None
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """Return JSON-serializable representation."""
        return {
            "is_valid": self.is_valid,
            "original_value": self.original_value,
            "normalized_value": self.normalized_value,
            "errors": [
                {
                    "field": e.field,
                    "message": e.message,
                    "severity": e.severity.value,
                    "value": e.value,
                    "expected": e.expected,
                }
                for e in self.errors
            ],
            "warnings": self.warnings,
        }


# =============================================================================
# GS1 CHECK DIGIT ALGORITHM
# =============================================================================

def calculate_gs1_check_digit(digits: str) -> int:
    """
    Calculate GS1 check digit using modulo 10 algorithm.
    
    The algorithm (from right to left):
    1. Multiply digits at odd positions (from right) by 3
    2. Multiply digits at even positions by 1
    3. Sum all products
    4. Check digit = (10 - (sum % 10)) % 10
    
    Args:
        digits: String of digits (without check digit)
        
    Returns:
        Single check digit (0-9)
    """
    if not digits or not digits.isdigit():
        raise ValueError(f"Invalid input for check digit calculation: {digits}")
    
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
    if not full_number or not full_number.isdigit() or len(full_number) < 2:
        return False
    
    digits = full_number[:-1]
    check_digit = int(full_number[-1])
    
    return calculate_gs1_check_digit(digits) == check_digit


# =============================================================================
# GLN VALIDATION
# =============================================================================

def validate_gln(gln_str: str) -> ValidationResult:
    """
    Validate Global Location Number (GLN) using GS1 standards.
    
    GLN is exactly 13 digits with a GS1 check digit. Used to identify
    physical locations in the supply chain (warehouses, facilities, etc.).
    
    GS1 Check Digit Algorithm:
    1. From right to left, multiply alternating digits by 3 and 1
    2. Sum all products
    3. Check digit = (10 - (sum % 10)) % 10
    
    Args:
        gln_str: GLN string to validate
        
    Returns:
        ValidationResult with validity status and any errors
        
    Examples:
        >>> validate_gln("0614141000036").is_valid
        True
        >>> validate_gln("0614141000037").is_valid  # Wrong check digit
        False
        >>> validate_gln("123456789").is_valid  # Wrong length
        False
    """
    if not gln_str:
        return ValidationResult(
            is_valid=False,
            original_value=gln_str or "",
            errors=[
                ValidationError(
                    field="gln",
                    message="GLN cannot be empty",
                    severity=ValidationSeverity.CRITICAL,
                )
            ],
        )
    
    # Normalize: remove spaces, dashes, and leading/trailing whitespace
    normalized = re.sub(r'[\s\-]', '', gln_str.strip())
    errors = []
    warnings = []
    
    # Check if all digits
    if not normalized.isdigit():
        errors.append(
            ValidationError(
                field="gln",
                message="GLN must contain only digits, found non-digit characters",
                severity=ValidationSeverity.CRITICAL,
                value=gln_str,
            )
        )
        return ValidationResult(
            is_valid=False,
            original_value=gln_str,
            normalized_value=normalized,
            errors=errors,
        )
    
    # Check length (must be exactly 13 digits)
    if len(normalized) != 13:
        errors.append(
            ValidationError(
                field="gln",
                message=f"GLN must be exactly 13 digits, got {len(normalized)} digits",
                severity=ValidationSeverity.CRITICAL,
                value=gln_str,
                expected="13 digits",
            )
        )
        return ValidationResult(
            is_valid=False,
            original_value=gln_str,
            normalized_value=normalized,
            errors=errors,
        )
    
    # Verify GS1 check digit
    if not verify_gs1_check_digit(normalized):
        expected_check = calculate_gs1_check_digit(normalized[:-1])
        actual_check = normalized[-1]
        errors.append(
            ValidationError(
                field="gln",
                message=f"Invalid check digit: expected {expected_check}, got {actual_check}",
                severity=ValidationSeverity.CRITICAL,
                value=gln_str,
                expected=str(expected_check),
            )
        )
        return ValidationResult(
            is_valid=False,
            original_value=gln_str,
            normalized_value=normalized,
            errors=errors,
        )
    
    # Check for suspicious patterns (all zeros, repeating digits)
    if normalized == "0" * 13:
        warnings.append("GLN is all zeros - verify this is intentional")
    elif len(set(normalized)) == 1:
        warnings.append("GLN has all identical digits - verify this is correct")
    
    logger.debug("gln_validated", gln=normalized, valid=True)
    
    return ValidationResult(
        is_valid=True,
        original_value=gln_str,
        normalized_value=normalized,
        warnings=warnings,
    )


# =============================================================================
# FDA REGISTRATION VALIDATION
# =============================================================================

# FDA Facility Registration Number patterns
# Standard format: 11-digit numeric (newer) or alphanumeric legacy formats
FDA_REG_PATTERNS = [
    (r'^\d{11}$', 'FDA_STANDARD'),           # 11-digit standard format
    (r'^\d{5,10}$', 'FDA_LEGACY'),            # Legacy shorter numeric format
    (r'^[A-Z]{2}\d{7,9}$', 'FDA_STATE_PREFIX'),  # State prefix format (e.g., NY1234567)
]


def validate_fda_reg(reg_str: str) -> ValidationResult:
    """
    Validate FDA Facility Registration Number format.
    
    FDA registration numbers are typically 11-digit numeric identifiers
    assigned to food facilities. This performs basic format validation.
    
    Supported formats:
    - Standard: 11 digits (e.g., "12345678901")
    - Legacy: 5-10 digits for older registrations
    - State prefix: 2 letters + 7-9 digits (e.g., "NY1234567")
    
    Note: This validates format only. To verify registration status,
    use FDA's Food Facility Registration database.
    
    Args:
        reg_str: FDA registration number string to validate
        
    Returns:
        ValidationResult with validity status and any errors
        
    Examples:
        >>> validate_fda_reg("12345678901").is_valid
        True
        >>> validate_fda_reg("ABC").is_valid  # Too short
        False
    """
    if not reg_str:
        return ValidationResult(
            is_valid=False,
            original_value=reg_str or "",
            errors=[
                ValidationError(
                    field="fda_registration",
                    message="FDA registration number cannot be empty",
                    severity=ValidationSeverity.ERROR,
                )
            ],
        )
    
    # Normalize: remove spaces, dashes, and uppercase
    normalized = re.sub(r'[\s\-]', '', reg_str.strip().upper())
    errors = []
    warnings = []
    
    # Check against known patterns
    matched_format = None
    for pattern, format_name in FDA_REG_PATTERNS:
        if re.match(pattern, normalized):
            matched_format = format_name
            break
    
    if not matched_format:
        errors.append(
            ValidationError(
                field="fda_registration",
                message="FDA registration number format not recognized. Expected 11 digits or valid legacy format.",
                severity=ValidationSeverity.ERROR,
                value=reg_str,
                expected="11-digit number or legacy format",
            )
        )
        return ValidationResult(
            is_valid=False,
            original_value=reg_str,
            normalized_value=normalized,
            errors=errors,
        )
    
    # Add warning for legacy formats
    if matched_format == 'FDA_LEGACY':
        warnings.append(
            f"Legacy FDA registration format ({len(normalized)} digits). "
            "Consider updating to current 11-digit format."
        )
    
    # Check for test/placeholder patterns
    if normalized in ('12345678901', '00000000000', '11111111111'):
        warnings.append("FDA registration appears to be a test/placeholder value")
    
    logger.debug(
        "fda_reg_validated",
        registration=normalized,
        format=matched_format,
        valid=True,
    )
    
    return ValidationResult(
        is_valid=True,
        original_value=reg_str,
        normalized_value=normalized,
        warnings=warnings,
    )


# =============================================================================
# EVENT CHAIN VALIDATION (Logic Gates)
# =============================================================================

# Event type dependencies: event -> required preceding events
EVENT_CHAIN_RULES = {
    "SHIPPING": ["CREATION", "RECEIVING", "TRANSFORMATION"],
    "TRANSFORMATION": ["CREATION", "RECEIVING"],
}


def validate_event_chain(
    event_type: str,
    preceding_event_types: List[str],
) -> ValidationResult:
    """
    Validate that an event has the required preceding events.
    
    Implements logic gate validation:
    - SHIPPING requires a preceding CREATION, RECEIVING, or TRANSFORMATION
    - TRANSFORMATION requires a preceding CREATION or RECEIVING
    
    This prevents orphan events that break the chain of custody.
    
    Args:
        event_type: The event type being validated (e.g., "SHIPPING")
        preceding_event_types: List of event types that precede this event
        
    Returns:
        ValidationResult indicating if the event chain is valid
        
    Examples:
        >>> validate_event_chain("SHIPPING", ["RECEIVING"]).is_valid
        True
        >>> validate_event_chain("SHIPPING", []).is_valid  # No preceding events
        False
    """
    event_type_upper = event_type.upper() if event_type else ""
    preceding_upper = [e.upper() for e in preceding_event_types if e]
    
    errors = []
    warnings = []
    
    # Check if this event type has chain requirements
    required_precedents = EVENT_CHAIN_RULES.get(event_type_upper, [])
    
    if not required_precedents:
        # No chain requirements for this event type
        return ValidationResult(
            is_valid=True,
            original_value=event_type,
            warnings=warnings,
        )
    
    # Check if any required preceding event exists
    has_valid_precedent = any(
        precedent in preceding_upper 
        for precedent in required_precedents
    )
    
    if not has_valid_precedent:
        required_str = " or ".join(required_precedents)
        errors.append(
            ValidationError(
                field="event_chain",
                message=f"{event_type_upper} event requires a preceding {required_str} event",
                severity=ValidationSeverity.CRITICAL,
                value=f"preceding: {preceding_upper}",
                expected=required_str,
            )
        )
        return ValidationResult(
            is_valid=False,
            original_value=event_type,
            errors=errors,
        )
    
    logger.debug(
        "event_chain_validated",
        event_type=event_type_upper,
        preceding_events=preceding_upper,
        valid=True,
    )
    
    return ValidationResult(
        is_valid=True,
        original_value=event_type,
        warnings=warnings,
    )


# =============================================================================
# BATCH VALIDATION UTILITIES
# =============================================================================

@dataclass
class BatchValidationResult:
    """Result of batch validation across multiple fields."""
    is_valid: bool
    total_fields: int
    valid_count: int
    error_count: int
    warning_count: int
    field_results: List[dict] = field(default_factory=list)
    critical_errors: List[ValidationError] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """Return JSON-serializable representation."""
        return {
            "is_valid": self.is_valid,
            "total_fields": self.total_fields,
            "valid_count": self.valid_count,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "field_results": self.field_results,
            "critical_errors": [
                {
                    "field": e.field,
                    "message": e.message,
                    "severity": e.severity.value,
                    "value": e.value,
                }
                for e in self.critical_errors
            ],
        }


def validate_location_identifiers(
    record: dict,
    location_fields: Optional[List[str]] = None,
) -> BatchValidationResult:
    """
    Validate all location identifier fields in a record.
    
    Scans the record for location identifier fields and validates
    each one as a GLN.
    
    Args:
        record: Dictionary containing fields to validate
        location_fields: Specific fields to check. If None, uses defaults:
                        ['location_identifier', 'source_location', 
                         'destination_location', 'facility_gln']
    
    Returns:
        BatchValidationResult with validation status for all fields
    """
    if location_fields is None:
        location_fields = [
            'location_identifier',
            'source_location',
            'destination_location',
            'facility_gln',
            'origin_gln',
            'ship_to_gln',
            'ship_from_gln',
        ]
    
    field_results = []
    critical_errors = []
    valid_count = 0
    warning_count = 0
    total_checked = 0
    
    for field_name in location_fields:
        value = record.get(field_name)
        if value is None or value == "":
            continue
        
        total_checked += 1
        result = validate_gln(str(value))
        
        field_results.append({
            "field": field_name,
            "value": value,
            "is_valid": result.is_valid,
            "errors": [e.message for e in result.errors],
            "warnings": result.warnings,
        })
        
        if result.is_valid:
            valid_count += 1
        else:
            for error in result.errors:
                if error.severity == ValidationSeverity.CRITICAL:
                    error.field = field_name  # Update field name
                    critical_errors.append(error)
        
        if result.warnings:
            warning_count += len(result.warnings)
    
    is_valid = len(critical_errors) == 0
    
    logger.info(
        "location_identifiers_validated",
        total=total_checked,
        valid=valid_count,
        errors=len(critical_errors),
        warnings=warning_count,
    )
    
    return BatchValidationResult(
        is_valid=is_valid,
        total_fields=total_checked,
        valid_count=valid_count,
        error_count=len(critical_errors),
        warning_count=warning_count,
        field_results=field_results,
        critical_errors=critical_errors,
    )
