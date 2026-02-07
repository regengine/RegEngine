"""
Tests for SEC-048: LDAP Injection Prevention.

Tests cover:
- Character encoding
- Input validation
- Filter building
- DN building
- Injection prevention
"""

import pytest

from shared.ldap_security import (
    # Enums
    LDAPThreatType,
    LDAPValidationResult,
    # Data classes
    LDAPSecurityConfig,
    LDAPValidationReport,
    # Classes
    LDAPCharacterEncoder,
    LDAPInputValidator,
    LDAPFilterBuilder,
    LDAPDNBuilder,
    LDAPSecurityService,
    # Convenience functions
    get_ldap_service,
    escape_ldap_filter,
    escape_ldap_dn,
    build_ldap_filter,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def config():
    """Create LDAP security config."""
    return LDAPSecurityConfig()


@pytest.fixture
def config_with_wildcards():
    """Create config allowing wildcards."""
    return LDAPSecurityConfig(allow_wildcards=True)


@pytest.fixture
def encoder():
    """Create encoder."""
    return LDAPCharacterEncoder()


@pytest.fixture
def validator(config):
    """Create validator."""
    return LDAPInputValidator(config)


@pytest.fixture
def filter_builder(config):
    """Create filter builder."""
    return LDAPFilterBuilder(config)


@pytest.fixture
def dn_builder(config):
    """Create DN builder."""
    return LDAPDNBuilder(config)


@pytest.fixture
def service(config):
    """Create service."""
    LDAPSecurityService._instance = None
    return LDAPSecurityService(config)


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_threat_types(self):
        """Should have expected threat types."""
        assert LDAPThreatType.INJECTION == "injection"
        assert LDAPThreatType.FILTER_BYPASS == "filter_bypass"
        assert LDAPThreatType.DN_MANIPULATION == "dn_manipulation"
    
    def test_validation_results(self):
        """Should have expected validation results."""
        assert LDAPValidationResult.VALID == "valid"
        assert LDAPValidationResult.BLOCKED == "blocked"
        assert LDAPValidationResult.SANITIZED == "sanitized"


# =============================================================================
# Test: LDAPSecurityConfig
# =============================================================================

class TestLDAPSecurityConfig:
    """Test LDAPSecurityConfig class."""
    
    def test_default_values(self):
        """Should have secure defaults."""
        config = LDAPSecurityConfig()
        
        assert config.allow_wildcards is False
        assert config.strict_dn_validation is True
        assert config.max_filter_length == 1000


# =============================================================================
# Test: LDAPCharacterEncoder
# =============================================================================

class TestLDAPCharacterEncoder:
    """Test LDAPCharacterEncoder."""
    
    def test_escape_filter_backslash(self, encoder):
        """Should escape backslash."""
        result = encoder.escape_filter_value("test\\value")
        
        assert "\\5c" in result
    
    def test_escape_filter_asterisk(self, encoder):
        """Should escape asterisk."""
        result = encoder.escape_filter_value("test*value")
        
        assert "\\2a" in result
    
    def test_escape_filter_parentheses(self, encoder):
        """Should escape parentheses."""
        result = encoder.escape_filter_value("test(value)")
        
        assert "\\28" in result
        assert "\\29" in result
    
    def test_escape_filter_null(self, encoder):
        """Should escape null byte."""
        result = encoder.escape_filter_value("test\x00value")
        
        assert "\\00" in result
    
    def test_escape_dn_comma(self, encoder):
        """Should escape comma in DN."""
        result = encoder.escape_dn_value("Smith, John")
        
        assert "\\," in result
    
    def test_escape_dn_plus(self, encoder):
        """Should escape plus in DN."""
        result = encoder.escape_dn_value("John+Jane")
        
        assert "\\+" in result
    
    def test_escape_dn_quote(self, encoder):
        """Should escape quote in DN."""
        result = encoder.escape_dn_value('John "Johnny" Doe')
        
        assert '\\"' in result
    
    def test_encode_special_chars(self, encoder):
        """Should hex-encode special chars."""
        result = encoder.encode_value("test\x01value")
        
        assert "\\01" in result
    
    def test_empty_value(self, encoder):
        """Should handle empty value."""
        assert encoder.escape_filter_value("") == ""
        assert encoder.escape_dn_value("") == ""


# =============================================================================
# Test: LDAPInputValidator
# =============================================================================

class TestLDAPInputValidator:
    """Test LDAPInputValidator."""
    
    def test_validates_safe_value(self, validator):
        """Should pass safe value."""
        result = validator.validate_filter_value("john.doe")
        
        assert result.is_safe is True
        assert result.status == LDAPValidationResult.VALID
    
    def test_blocks_null_byte(self, validator):
        """Should block null byte."""
        result = validator.validate_filter_value("john\x00doe")
        
        assert result.is_safe is False
        assert LDAPThreatType.INJECTION in result.threats_detected
    
    def test_blocks_newline(self, validator):
        """Should block newline."""
        result = validator.validate_filter_value("john\ndoe")
        
        assert result.is_safe is False
    
    def test_blocks_filter_concatenation(self, validator):
        """Should block filter concatenation."""
        result = validator.validate_filter_value("admin)(uid=*")
        
        assert result.is_safe is False
    
    def test_blocks_or_injection(self, validator):
        """Should block OR injection."""
        result = validator.validate_filter_value("admin)|(uid=*")
        
        assert result.is_safe is False
    
    def test_blocks_wildcard(self, validator):
        """Should block wildcard by default."""
        result = validator.validate_filter_value("admin*")
        
        assert result.is_safe is False
        assert LDAPThreatType.WILDCARD_ABUSE in result.threats_detected
    
    def test_blocks_oversized_value(self, validator):
        """Should block oversized value."""
        result = validator.validate_filter_value("x" * 2000)
        
        assert result.is_safe is False
    
    def test_validates_dn(self, validator):
        """Should validate safe DN."""
        result = validator.validate_dn("cn=john,ou=users,dc=example,dc=com", is_full_dn=True)
        
        assert result.is_safe is True
    
    def test_blocks_dn_manipulation(self, validator):
        """Should block DN manipulation in user input."""
        # User input shouldn't contain DN components
        result = validator.validate_dn("john,cn=admin", is_full_dn=False)
        
        assert result.is_safe is False
        assert LDAPThreatType.DN_MANIPULATION in result.threats_detected
    
    def test_validates_attribute(self, validator):
        """Should validate safe attribute."""
        result = validator.validate_attribute("uid")
        
        assert result.is_safe is True
    
    def test_blocks_invalid_attribute(self, validator):
        """Should block invalid attribute."""
        result = validator.validate_attribute("uid=admin")
        
        assert result.is_safe is False


# =============================================================================
# Test: LDAPFilterBuilder
# =============================================================================

class TestLDAPFilterBuilder:
    """Test LDAPFilterBuilder."""
    
    def test_builds_equals_filter(self, filter_builder):
        """Should build equals filter."""
        result = filter_builder.equals("uid", "john")
        
        assert result == "(uid=john)"
    
    def test_escapes_filter_value(self, filter_builder):
        """Should escape filter value."""
        result = filter_builder.equals("cn", "John (Admin)")
        
        assert result == r"(cn=John \28Admin\29)"
    
    def test_builds_presence_filter(self, filter_builder):
        """Should build presence filter."""
        result = filter_builder.presence("mail")
        
        assert result == "(mail=*)"
    
    def test_rejects_invalid_attribute(self, filter_builder):
        """Should reject invalid attribute."""
        result = filter_builder.equals("invalid=attr", "value")
        
        assert result is None
    
    def test_rejects_injection_value(self, filter_builder):
        """Should reject injection value."""
        result = filter_builder.equals("uid", "admin)(uid=*")
        
        assert result is None
    
    def test_builds_and_filter(self, filter_builder):
        """Should build AND filter."""
        f1 = filter_builder.equals("uid", "john")
        f2 = filter_builder.equals("objectClass", "person")
        
        result = filter_builder.and_filter(f1, f2)
        
        assert result == "(&(uid=john)(objectClass=person))"
    
    def test_builds_or_filter(self, filter_builder):
        """Should build OR filter."""
        f1 = filter_builder.equals("uid", "john")
        f2 = filter_builder.equals("uid", "jane")
        
        result = filter_builder.or_filter(f1, f2)
        
        assert result == "(|(uid=john)(uid=jane))"
    
    def test_builds_not_filter(self, filter_builder):
        """Should build NOT filter."""
        f = filter_builder.equals("status", "disabled")
        
        result = filter_builder.not_filter(f)
        
        assert result == "(!(status=disabled))"
    
    def test_starts_with_requires_wildcards(self, filter_builder):
        """Should reject starts_with without wildcard config."""
        result = filter_builder.starts_with("cn", "John")
        
        assert result is None
    
    def test_starts_with_with_wildcards(self, config_with_wildcards):
        """Should build starts_with with wildcard config."""
        builder = LDAPFilterBuilder(config_with_wildcards)
        
        result = builder.starts_with("cn", "John")
        
        assert result == "(cn=John*)"
    
    def test_contains_with_wildcards(self, config_with_wildcards):
        """Should build contains with wildcard config."""
        builder = LDAPFilterBuilder(config_with_wildcards)
        
        result = builder.contains("description", "admin")
        
        assert result == "(description=*admin*)"


# =============================================================================
# Test: LDAPDNBuilder
# =============================================================================

class TestLDAPDNBuilder:
    """Test LDAPDNBuilder."""
    
    def test_builds_dn(self, dn_builder):
        """Should build DN."""
        result = dn_builder.build_dn(cn="JohnDoe", ou="Users", dc="example")
        
        assert "cn=JohnDoe" in result
        assert "ou=Users" in result
    
    def test_escapes_dn_value(self, dn_builder):
        """Should escape DN value."""
        result = dn_builder.build_dn(cn="Smith, John")
        
        assert "\\," in result
    
    def test_builds_user_dn(self, dn_builder):
        """Should build user DN."""
        result = dn_builder.build_user_dn(
            username="john.doe",
            base_dn="ou=users,dc=example,dc=com",
        )
        
        assert result == "cn=john.doe,ou=users,dc=example,dc=com"
    
    def test_escapes_username_in_dn(self, dn_builder):
        """Should escape username in DN."""
        result = dn_builder.build_user_dn(
            username="John, Jr.",
            base_dn="ou=users,dc=example,dc=com",
        )
        
        assert "\\," in result
    
    def test_rejects_invalid_base_dn(self, dn_builder):
        """Should reject invalid base DN."""
        result = dn_builder.build_user_dn(
            username="john",
            base_dn="ou=users\x00,dc=example",
        )
        
        assert result is None


# =============================================================================
# Test: LDAPSecurityService
# =============================================================================

class TestLDAPSecurityService:
    """Test LDAPSecurityService."""
    
    def test_singleton(self):
        """Should return singleton instance."""
        LDAPSecurityService._instance = None
        
        s1 = get_ldap_service()
        s2 = get_ldap_service()
        
        assert s1 is s2
    
    def test_escape_filter_value(self, service):
        """Should escape filter value."""
        result = service.escape_filter_value("test*value")
        
        assert "\\2a" in result
    
    def test_escape_dn_value(self, service):
        """Should escape DN value."""
        result = service.escape_dn_value("test,value")
        
        assert "\\," in result
    
    def test_validate_filter_value(self, service):
        """Should validate filter value."""
        safe_result = service.validate_filter_value("john")
        unsafe_result = service.validate_filter_value("john)(uid=*")
        
        assert safe_result.is_safe is True
        assert unsafe_result.is_safe is False
    
    def test_validate_dn(self, service):
        """Should validate DN."""
        safe_result = service.validate_dn("cn=john,dc=example", is_full_dn=True)
        unsafe_result = service.validate_dn("john\x00,cn=admin")
        
        assert safe_result.is_safe is True
        assert unsafe_result.is_safe is False
    
    def test_build_filter(self, service):
        """Should build filter."""
        result = service.build_filter("uid", "john")
        
        assert result == "(uid=john)"
    
    def test_build_dn(self, service):
        """Should build DN."""
        result = service.build_dn(cn="john", dc="example")
        
        assert "cn=john" in result


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_escape_ldap_filter(self):
        """Should escape filter value."""
        LDAPSecurityService._instance = None
        
        result = escape_ldap_filter("test*value")
        
        assert "\\2a" in result
    
    def test_escape_ldap_dn(self):
        """Should escape DN value."""
        LDAPSecurityService._instance = None
        
        result = escape_ldap_dn("test,value")
        
        assert "\\," in result
    
    def test_build_ldap_filter(self):
        """Should build filter."""
        LDAPSecurityService._instance = None
        
        result = build_ldap_filter("uid", "john")
        
        assert result == "(uid=john)"


# =============================================================================
# Test: Injection Vectors
# =============================================================================

class TestInjectionVectors:
    """Test various LDAP injection vectors."""
    
    def test_classic_injection(self, validator):
        """Should block classic injection."""
        result = validator.validate_filter_value("*)(uid=*))(|(uid=*")
        
        assert result.is_safe is False
    
    def test_blind_injection(self, validator):
        """Should block blind injection."""
        result = validator.validate_filter_value("admin)(&(uid=admin")
        
        assert result.is_safe is False
    
    def test_dn_escape_injection(self, validator):
        """Should block DN escape injection in user input."""
        # User-provided value shouldn't contain DN components
        result = validator.validate_dn("test,cn=admin,dc=evil,dc=com", is_full_dn=False)
        
        assert result.is_safe is False
    
    def test_null_byte_injection(self, validator):
        """Should block null byte injection."""
        result = validator.validate_filter_value("admin\x00(uid=*)")
        
        assert result.is_safe is False
    
    def test_hex_encoded_injection(self, validator):
        """Should block hex-encoded injection."""
        result = validator.validate_filter_value("admin\\29\\28uid=*")
        
        assert result.is_safe is False
