"""
Tests for FSMA 204 TLC and Identifier Validation.
"""

import pytest
from shared.fsma_validation import (
    IdentifierType,
    ValidationResult,
    calculate_gs1_check_digit,
    detect_identifier_type,
    extract_company_prefix,
    normalize_gtin,
    validate_batch,
    validate_gln,
    validate_gtin,
    validate_identifier,
    validate_sscc,
    validate_tlc,
    verify_gs1_check_digit,
)


# =============================================================================
# GS1 CHECK DIGIT TESTS
# =============================================================================

class TestGS1CheckDigit:
    """Tests for GS1 check digit calculation and verification."""

    @pytest.mark.parametrize("digits,expected", [
        # GTIN-8 examples
        ("9638507", 4),  # → 96385074
        ("1234567", 0),  # → 12345670
        # GTIN-12 examples
        ("03600029145", 2),  # → 036000291452 (Diet Coke)
        ("01onal001234", None),  # Invalid - contains letters
        # GTIN-13 examples
        ("590123412345", 7),  # → 5901234123457
        ("400599999999", 7),  # → 4005999999997 (corrected)
        # GTIN-14 examples
        ("1034567890123", 3),  # → 10345678901233 (corrected)
    ])
    def test_calculate_check_digit(self, digits, expected):
        """Test GS1 check digit calculation."""
        if expected is not None:
            assert calculate_gs1_check_digit(digits) == expected

    @pytest.mark.parametrize("number,expected", [
        ("96385074", True),  # Valid GTIN-8
        ("96385075", False),  # Invalid check digit
        ("036000291452", True),  # Valid GTIN-12
        ("5901234123457", True),  # Valid GTIN-13
        ("10345678901233", True),  # Valid GTIN-14 (corrected)
        ("10345678901239", False),  # Invalid check digit
    ])
    def test_verify_check_digit(self, number, expected):
        """Test GS1 check digit verification."""
        assert verify_gs1_check_digit(number) == expected

    def test_verify_empty_string(self):
        """Test check digit verification with empty string."""
        assert verify_gs1_check_digit("") == False

    def test_verify_non_digits(self):
        """Test check digit verification with non-digit characters."""
        assert verify_gs1_check_digit("ABC123") == False


# =============================================================================
# GTIN VALIDATION TESTS
# =============================================================================

class TestGTINValidation:
    """Tests for GTIN validation."""

    @pytest.mark.parametrize("gtin", [
        "96385074",  # GTIN-8
        "036000291452",  # GTIN-12
        "5901234123457",  # GTIN-13
        "10345678901233",  # GTIN-14 (corrected)
    ])
    def test_valid_gtin(self, gtin):
        """Test valid GTIN formats."""
        result = validate_gtin(gtin)
        assert result.is_valid
        assert result.identifier_type == IdentifierType.GTIN
        assert len(result.errors) == 0

    @pytest.mark.parametrize("gtin,error_substring", [
        ("1234", "8, 12, 13, or 14 digits"),  # Too short
        ("123456789012345", "8, 12, 13, or 14 digits"),  # Too long
        ("ABC12345", "only digits"),  # Contains letters
        ("96385075", "Invalid check digit"),  # Wrong check digit
    ])
    def test_invalid_gtin(self, gtin, error_substring):
        """Test invalid GTIN formats."""
        result = validate_gtin(gtin)
        assert not result.is_valid
        assert any(error_substring in err for err in result.errors)

    def test_gtin_with_spaces(self):
        """Test GTIN with spaces is normalized."""
        result = validate_gtin("963 850 74")
        assert result.is_valid
        assert result.normalized_value == "96385074"

    def test_gtin_with_dashes(self):
        """Test GTIN with dashes is normalized."""
        result = validate_gtin("963-850-74")
        assert result.is_valid
        assert result.normalized_value == "96385074"

    def test_gtin_leading_zeros_warning(self):
        """Test GTIN with many leading zeros produces warning."""
        # Valid GTIN with many leading zeros
        gtin = "00000291452"
        check = calculate_gs1_check_digit(gtin)
        full_gtin = gtin + str(check)
        result = validate_gtin(full_gtin)
        assert result.is_valid
        assert len(result.warnings) > 0


# =============================================================================
# GLN VALIDATION TESTS
# =============================================================================

class TestGLNValidation:
    """Tests for GLN validation."""

    def test_valid_gln(self):
        """Test valid GLN."""
        # Calculate valid check digit for test GLN
        base = "012345678901"
        check = calculate_gs1_check_digit(base)
        gln = base + str(check)
        
        result = validate_gln(gln)
        assert result.is_valid
        assert result.identifier_type == IdentifierType.GLN

    @pytest.mark.parametrize("gln,error_substring", [
        ("12345678901", "13 digits"),  # Too short
        ("12345678901234", "13 digits"),  # Too long
        ("123456789012A", "only digits"),  # Contains letter
    ])
    def test_invalid_gln(self, gln, error_substring):
        """Test invalid GLN formats."""
        result = validate_gln(gln)
        assert not result.is_valid
        assert any(error_substring in err for err in result.errors)

    def test_gln_invalid_check_digit(self):
        """Test GLN with invalid check digit."""
        # Create GLN with wrong check digit
        result = validate_gln("1234567890129")  # Random 13 digits
        assert not result.is_valid
        assert any("check digit" in err.lower() for err in result.errors)


# =============================================================================
# SSCC VALIDATION TESTS
# =============================================================================

class TestSSCCValidation:
    """Tests for SSCC validation."""

    def test_valid_sscc(self):
        """Test valid SSCC."""
        base = "00123456789012345"  # 17 digits
        check = calculate_gs1_check_digit(base)
        sscc = base + str(check)
        
        result = validate_sscc(sscc)
        assert result.is_valid
        assert result.identifier_type == IdentifierType.SSCC
        assert len(result.normalized_value) == 18

    @pytest.mark.parametrize("sscc,error_substring", [
        ("1234567890123456", "18 digits"),  # Too short (16)
        ("12345678901234567890", "18 digits"),  # Too long (20)
        ("12345678901234567A", "only digits"),  # Contains letter
    ])
    def test_invalid_sscc(self, sscc, error_substring):
        """Test invalid SSCC formats."""
        result = validate_sscc(sscc)
        assert not result.is_valid
        assert any(error_substring in err for err in result.errors)


# =============================================================================
# TLC VALIDATION TESTS
# =============================================================================

class TestTLCValidation:
    """Tests for Traceability Lot Code validation."""

    @pytest.mark.parametrize("tlc", [
        "L-2024-01-15-A",  # Date-based format
        "LOT: ABC123",  # LOT prefix
        "BATCH-456",  # BATCH prefix
        "20240115A",  # Simple date format
        "ABC20240115B",  # Plant + date
        "A24015B",  # Julian date format
        "ABC123XYZ",  # Generic alphanumeric
    ])
    def test_valid_tlc(self, tlc):
        """Test valid TLC formats."""
        result = validate_tlc(tlc)
        assert result.is_valid
        assert result.identifier_type == IdentifierType.TLC

    def test_tlc_normalization(self):
        """Test TLC is normalized to uppercase."""
        result = validate_tlc("lot-abc-123")
        assert result.is_valid
        assert result.normalized_value == "LOT-ABC-123"

    @pytest.mark.parametrize("tlc,error_substring", [
        ("AB", "at least 3"),  # Too short
        ("A" * 51, "maximum length"),  # Too long
        ("LOT<script>", "invalid characters"),  # HTML injection
        ("LOT'DROP", "invalid characters"),  # SQL injection
        ("LOT;SELECT", "semicolon"),  # SQL delimiter
        ("LOT--DROP", "SQL comment"),  # SQL comment
    ])
    def test_invalid_tlc(self, tlc, error_substring):
        """Test invalid TLC formats."""
        result = validate_tlc(tlc)
        assert not result.is_valid
        assert any(error_substring.lower() in err.lower() for err in result.errors)

    def test_tlc_strict_mode(self):
        """Test TLC validation in strict mode."""
        # Recognized pattern should pass
        result = validate_tlc("L-2024-01-15-A", strict=True)
        assert result.is_valid
        
        # Unrecognized pattern should fail
        result = validate_tlc("RANDOM_FORMAT_123", strict=True)
        assert not result.is_valid
        assert any("recognized format" in err.lower() for err in result.errors)

    def test_tlc_warning_for_unknown_pattern(self):
        """Test TLC produces warning for unrecognized pattern."""
        # Use a TLC with hyphens that doesn't match the ALPHANUMERIC pattern
        result = validate_tlc("A-B-C-D-E")
        assert result.is_valid  # Still valid
        assert len(result.warnings) > 0  # But has warning for unrecognized format


# =============================================================================
# AUTO-DETECTION TESTS
# =============================================================================

class TestIdentifierDetection:
    """Tests for automatic identifier type detection."""

    @pytest.mark.parametrize("value,expected_type", [
        ("96385074", IdentifierType.GTIN),  # 8 digits → GTIN
        ("036000291452", IdentifierType.GTIN),  # 12 digits → GTIN
        ("5901234123457", IdentifierType.GLN),  # 13 digits → GLN (or GTIN-13)
        ("10345678901238", IdentifierType.GTIN),  # 14 digits → GTIN
        ("123456789012345678", IdentifierType.SSCC),  # 18 digits → SSCC
        ("LOT-2024-A", IdentifierType.TLC),  # Alphanumeric → TLC
        ("ABC123", IdentifierType.TLC),  # Alphanumeric → TLC
    ])
    def test_detect_type(self, value, expected_type):
        """Test identifier type detection."""
        assert detect_identifier_type(value) == expected_type


class TestUnifiedValidation:
    """Tests for unified validation function."""

    def test_validate_with_auto_detection(self):
        """Test validation with automatic type detection."""
        result = validate_identifier("96385074")
        assert result.is_valid
        assert result.identifier_type == IdentifierType.GTIN

    def test_validate_with_explicit_type(self):
        """Test validation with explicit type."""
        result = validate_identifier("LOT-2024-A", expected_type=IdentifierType.TLC)
        assert result.is_valid
        assert result.identifier_type == IdentifierType.TLC


# =============================================================================
# BATCH VALIDATION TESTS
# =============================================================================

class TestBatchValidation:
    """Tests for batch validation."""

    def test_batch_validation(self):
        """Test batch validation of multiple identifiers."""
        identifiers = [
            ("96385074", IdentifierType.GTIN),
            ("LOT-2024-A", IdentifierType.TLC),
            ("INVALID<>", IdentifierType.TLC),
        ]
        
        results = validate_batch(identifiers)
        
        assert len(results) == 3
        assert results[0].is_valid  # Valid GTIN
        assert results[1].is_valid  # Valid TLC
        assert not results[2].is_valid  # Invalid TLC

    def test_batch_with_auto_detection(self):
        """Test batch validation with auto-detection."""
        identifiers = [
            ("96385074", None),  # Auto-detect as GTIN
            ("LOT-ABC", None),  # Auto-detect as TLC
        ]
        
        results = validate_batch(identifiers)
        
        assert results[0].identifier_type == IdentifierType.GTIN
        assert results[1].identifier_type == IdentifierType.TLC


# =============================================================================
# UTILITY FUNCTION TESTS
# =============================================================================

class TestUtilityFunctions:
    """Tests for utility functions."""

    @pytest.mark.parametrize("input_gtin,expected", [
        ("96385074", "00000096385074"),  # GTIN-8 → GTIN-14
        ("036000291452", "00036000291452"),  # GTIN-12 → GTIN-14
        ("5901234123457", "05901234123457"),  # GTIN-13 → GTIN-14
        ("10345678901238", "10345678901238"),  # GTIN-14 unchanged
    ])
    def test_normalize_gtin(self, input_gtin, expected):
        """Test GTIN normalization to 14 digits."""
        assert normalize_gtin(input_gtin) == expected

    def test_extract_company_prefix(self):
        """Test company prefix extraction."""
        gtin14 = "10345678901238"
        prefix = extract_company_prefix(gtin14)
        assert len(prefix) == 7
        assert prefix == "0345678"


# =============================================================================
# VALIDATION RESULT TESTS
# =============================================================================

class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_default_lists(self):
        """Test default empty lists are created."""
        result = ValidationResult(
            is_valid=True,
            identifier_type=IdentifierType.TLC,
            original_value="TEST",
        )
        assert result.errors == []
        assert result.warnings == []

    def test_with_errors(self):
        """Test result with errors."""
        result = ValidationResult(
            is_valid=False,
            identifier_type=IdentifierType.GTIN,
            original_value="INVALID",
            errors=["Error 1", "Error 2"],
        )
        assert len(result.errors) == 2
        assert result.warnings == []


# =============================================================================
# REAL-WORLD EXAMPLES
# =============================================================================

class TestRealWorldExamples:
    """Tests using real-world identifier patterns."""

    def test_coca_cola_gtin(self):
        """Test well-known Coca-Cola GTIN."""
        result = validate_gtin("049000000443")  # 12-digit UPC
        # Note: May need actual check digit verification
        # This tests the format validation

    def test_julian_date_lot_code(self):
        """Test Julian date format lot code (common in food industry)."""
        # Format: Plant Code (1-3 letters) + Julian Date (5 digits) + Shift (optional)
        result = validate_tlc("A24015B")  # Plant A, day 015 of 2024, shift B
        assert result.is_valid

    def test_iso_date_lot_code(self):
        """Test ISO date format lot code."""
        result = validate_tlc("2024-01-15-001")
        assert result.is_valid

    def test_mixed_case_preservation(self):
        """Test that original value is preserved while normalized is uppercase."""
        result = validate_tlc("Lot-ABC-123")
        assert result.original_value == "Lot-ABC-123"
        assert result.normalized_value == "LOT-ABC-123"
