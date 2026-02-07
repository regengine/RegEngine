"""
Tests for SEC-032: Exception Message Sanitization.

Tests cover:
- Sensitive data detection
- Pattern-based redaction
- Exception sanitization
- Log sanitization
- Custom rules
"""

import pytest
import re

from shared.exception_sanitization import (
    # Enums
    SensitiveDataType,
    # Data classes
    SanitizationResult,
    SanitizationRule,
    # Classes
    MessageSanitizer,
    ExceptionSanitizer,
    LogSanitizer,
    SanitizationService,
    # Convenience functions
    get_sanitization_service,
    sanitize_message,
    sanitize_exception,
    is_sensitive,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sanitizer():
    """Create message sanitizer."""
    return MessageSanitizer()


@pytest.fixture
def exception_sanitizer():
    """Create exception sanitizer."""
    return ExceptionSanitizer()


@pytest.fixture
def log_sanitizer():
    """Create log sanitizer."""
    return LogSanitizer()


@pytest.fixture
def service():
    """Create sanitization service."""
    return SanitizationService()


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_sensitive_data_types(self):
        """Should have expected types."""
        assert SensitiveDataType.PASSWORD == "password"
        assert SensitiveDataType.API_KEY == "api_key"
        assert SensitiveDataType.TOKEN == "token"
        assert SensitiveDataType.IP_ADDRESS == "ip_address"
        assert SensitiveDataType.EMAIL == "email"


# =============================================================================
# Test: SanitizationResult
# =============================================================================

class TestSanitizationResult:
    """Test SanitizationResult class."""
    
    def test_was_sanitized_true(self):
        """Should return true when redacted."""
        result = SanitizationResult(
            original_message="test",
            sanitized_message="[REDACTED]",
            redaction_count=1,
        )
        
        assert result.was_sanitized is True
    
    def test_was_sanitized_false(self):
        """Should return false when not redacted."""
        result = SanitizationResult(
            original_message="test",
            sanitized_message="test",
            redaction_count=0,
        )
        
        assert result.was_sanitized is False


# =============================================================================
# Test: MessageSanitizer - Passwords
# =============================================================================

class TestPasswordSanitization:
    """Test password detection and redaction."""
    
    def test_redacts_password_key_value(self, sanitizer):
        """Should redact password in key-value format."""
        message = "Connection failed with password=secret123"
        result = sanitizer.sanitize(message)
        
        assert "secret123" not in result.sanitized_message
        assert "[REDACTED:PASSWORD]" in result.sanitized_message
    
    def test_redacts_password_quoted(self, sanitizer):
        """Should redact quoted password."""
        message = 'Error: password="myp@ssw0rd"'
        result = sanitizer.sanitize(message)
        
        assert "myp@ssw0rd" not in result.sanitized_message
    
    def test_redacts_pwd_variation(self, sanitizer):
        """Should redact pwd variation."""
        message = "Failed: pwd=hunter2"
        result = sanitizer.sanitize(message)
        
        assert "hunter2" not in result.sanitized_message


# =============================================================================
# Test: MessageSanitizer - API Keys
# =============================================================================

class TestAPIKeySanitization:
    """Test API key detection and redaction."""
    
    def test_redacts_api_key(self, sanitizer):
        """Should redact api_key."""
        message = "Request failed with api_key=abc123xyz"
        result = sanitizer.sanitize(message)
        
        assert "abc123xyz" not in result.sanitized_message
        assert "[REDACTED:API_KEY]" in result.sanitized_message
    
    def test_redacts_stripe_live_key(self, sanitizer):
        """Should redact Stripe live key."""
        message = "Stripe error: sk_live_TESTKEY1234567890abcdef"
        result = sanitizer.sanitize(message)
        
        assert "sk_live_" not in result.sanitized_message
    
    def test_redacts_custom_prefix_key(self, sanitizer):
        """Should redact rk_ prefixed keys."""
        message = "Auth failed for rk_abc123def456"
        result = sanitizer.sanitize(message)
        
        assert "rk_abc123def456" not in result.sanitized_message


# =============================================================================
# Test: MessageSanitizer - Tokens
# =============================================================================

class TestTokenSanitization:
    """Test token detection and redaction."""
    
    def test_redacts_bearer_token(self, sanitizer):
        """Should redact Bearer token."""
        message = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = sanitizer.sanitize(message)
        
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result.sanitized_message
    
    def test_redacts_jwt_token(self, sanitizer):
        """Should redact JWT token."""
        message = "Invalid JWT: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        result = sanitizer.sanitize(message)
        
        assert "eyJhbGciOiJIUzI1NiJ9" not in result.sanitized_message


# =============================================================================
# Test: MessageSanitizer - IP Addresses
# =============================================================================

class TestIPAddressSanitization:
    """Test IP address detection and redaction."""
    
    def test_redacts_ipv4(self, sanitizer):
        """Should redact IPv4 address."""
        message = "Connection refused to 192.168.1.100"
        result = sanitizer.sanitize(message)
        
        assert "192.168.1.100" not in result.sanitized_message
        assert "[REDACTED:IP]" in result.sanitized_message
    
    def test_redacts_multiple_ips(self, sanitizer):
        """Should redact multiple IPs."""
        message = "Failed to connect from 10.0.0.1 to 172.16.0.50"
        result = sanitizer.sanitize(message)
        
        assert "10.0.0.1" not in result.sanitized_message
        assert "172.16.0.50" not in result.sanitized_message


# =============================================================================
# Test: MessageSanitizer - Emails
# =============================================================================

class TestEmailSanitization:
    """Test email detection and redaction."""
    
    def test_redacts_email(self, sanitizer):
        """Should redact email address."""
        message = "User not found: admin@internal.company.com"
        result = sanitizer.sanitize(message)
        
        assert "admin@internal.company.com" not in result.sanitized_message
        assert "[REDACTED:EMAIL]" in result.sanitized_message


# =============================================================================
# Test: MessageSanitizer - File Paths
# =============================================================================

class TestFilePathSanitization:
    """Test file path detection and redaction."""
    
    def test_redacts_unix_path(self, sanitizer):
        """Should redact Unix file path."""
        message = "Error reading /etc/secrets/database.conf"
        result = sanitizer.sanitize(message)
        
        assert "/etc/secrets/database.conf" not in result.sanitized_message
        assert "[REDACTED:PATH]" in result.sanitized_message
    
    def test_redacts_deep_path(self, sanitizer):
        """Should redact deep paths."""
        message = "Cannot open /home/user/app/config/secrets/prod.yaml"
        result = sanitizer.sanitize(message)
        
        assert "/home/user/app" not in result.sanitized_message


# =============================================================================
# Test: MessageSanitizer - Database URLs
# =============================================================================

class TestDatabaseURLSanitization:
    """Test database URL detection and redaction."""
    
    def test_redacts_postgres_url(self, sanitizer):
        """Should redact PostgreSQL URL."""
        message = "Failed to connect: postgres://admin:password@db.internal:5432/mydb"
        result = sanitizer.sanitize(message)
        
        assert "postgres://" not in result.sanitized_message
        assert "db.internal" not in result.sanitized_message
    
    def test_redacts_mysql_url(self, sanitizer):
        """Should redact MySQL URL."""
        message = "MySQL error: mysql://root:secret@localhost/database"
        result = sanitizer.sanitize(message)
        
        assert "mysql://" not in result.sanitized_message


# =============================================================================
# Test: MessageSanitizer - Custom Rules
# =============================================================================

class TestCustomRules:
    """Test custom sanitization rules."""
    
    def test_add_custom_rule(self, sanitizer):
        """Should apply custom rule."""
        rule = SanitizationRule(
            name="account_number",
            pattern=re.compile(r'ACCT-[A-Z]{4}-\d{6}'),
            replacement="[REDACTED:ACCOUNT]",
        )
        sanitizer.add_rule(rule)
        
        message = "Error processing ACCT-XYZW-123456"
        result = sanitizer.sanitize(message)
        
        assert "ACCT-XYZW-123456" not in result.sanitized_message
        assert "[REDACTED:ACCOUNT]" in result.sanitized_message
    
    def test_add_custom_pattern(self, sanitizer):
        """Should add pattern to existing type."""
        sanitizer.add_pattern(
            SensitiveDataType.API_KEY,
            r'myapp_key_[a-z0-9]+',
        )
        
        message = "Using myapp_key_abc123"
        result = sanitizer.sanitize(message)
        
        assert "myapp_key_abc123" not in result.sanitized_message


# =============================================================================
# Test: MessageSanitizer - Detection
# =============================================================================

class TestSensitiveDetection:
    """Test sensitive data detection."""
    
    def test_is_sensitive_true(self, sanitizer):
        """Should detect sensitive data."""
        assert sanitizer.is_sensitive("password=secret") is True
        assert sanitizer.is_sensitive("ip: 192.168.1.1") is True
    
    def test_is_sensitive_false(self, sanitizer):
        """Should not flag clean messages."""
        assert sanitizer.is_sensitive("User login successful") is False
        assert sanitizer.is_sensitive("Request processed") is False
    
    def test_detect_sensitive_types(self, sanitizer):
        """Should detect types of sensitive data."""
        message = "Error: password=secret, ip=192.168.1.1"
        types = sanitizer.detect_sensitive_types(message)
        
        assert SensitiveDataType.PASSWORD in types
        assert SensitiveDataType.IP_ADDRESS in types


# =============================================================================
# Test: ExceptionSanitizer
# =============================================================================

class TestExceptionSanitizer:
    """Test ExceptionSanitizer."""
    
    def test_sanitize_exception_message(self, exception_sanitizer):
        """Should sanitize exception message."""
        exc = ValueError("Database password: secret123 failed")
        result = exception_sanitizer.sanitize_exception(exc)
        
        assert "secret123" not in result
        assert "ValueError" in result
    
    def test_sanitize_without_type(self, exception_sanitizer):
        """Should exclude type when requested."""
        exc = RuntimeError("Error at 192.168.1.1")
        result = exception_sanitizer.sanitize_exception(exc, include_type=False)
        
        assert "RuntimeError" not in result
        assert "192.168.1.1" not in result
    
    def test_get_safe_message_sensitive(self, exception_sanitizer):
        """Should return default for sensitive messages."""
        exc = Exception("Failed with password=secret")
        result = exception_sanitizer.get_safe_message(exc)
        
        assert result == "An error occurred"
    
    def test_get_safe_message_clean(self, exception_sanitizer):
        """Should return original for clean messages."""
        exc = Exception("User not authorized")
        result = exception_sanitizer.get_safe_message(exc)
        
        assert result == "User not authorized"


# =============================================================================
# Test: LogSanitizer
# =============================================================================

class TestLogSanitizer:
    """Test LogSanitizer."""
    
    def test_sanitize_log_message(self, log_sanitizer):
        """Should sanitize log message."""
        message = "Login attempt with password=test123"
        sanitized, _ = log_sanitizer.sanitize_log_record(message)
        
        assert "test123" not in sanitized
    
    def test_sanitize_log_extra(self, log_sanitizer):
        """Should sanitize extra context."""
        message = "Request failed"
        extra = {
            "api_key": "sk_live_abc123",
            "user_ip": "192.168.1.1",
        }
        
        _, sanitized_extra = log_sanitizer.sanitize_log_record(message, extra)
        
        assert "sk_live_abc123" not in str(sanitized_extra)
        assert "192.168.1.1" not in str(sanitized_extra)
    
    def test_sanitize_nested_extra(self, log_sanitizer):
        """Should sanitize nested context."""
        message = "Error"
        extra = {
            "request": {
                "headers": {
                    "Authorization": "Bearer secret_token",
                }
            }
        }
        
        _, sanitized_extra = log_sanitizer.sanitize_log_record(message, extra)
        
        assert "secret_token" not in str(sanitized_extra)


# =============================================================================
# Test: SanitizationService
# =============================================================================

class TestSanitizationService:
    """Test SanitizationService."""
    
    def test_singleton(self):
        """Should return singleton instance."""
        s1 = get_sanitization_service()
        s2 = get_sanitization_service()
        
        assert s1 is s2
    
    def test_sanitize(self, service):
        """Should sanitize messages."""
        result = service.sanitize("password=secret")
        
        assert "secret" not in result
    
    def test_sanitize_exception(self, service):
        """Should sanitize exceptions."""
        exc = ValueError("Error at 10.0.0.1")
        result = service.sanitize_exception(exc)
        
        assert "10.0.0.1" not in result
    
    def test_is_sensitive(self, service):
        """Should detect sensitive data."""
        assert service.is_sensitive("api_key=abc") is True
        assert service.is_sensitive("hello world") is False


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_sanitize_message(self):
        """Should sanitize via convenience function."""
        result = sanitize_message("password=test")
        
        assert "test" not in result
    
    def test_sanitize_exception(self):
        """Should sanitize exception via convenience function."""
        exc = Exception("Error with token=abc123")
        result = sanitize_exception(exc)
        
        assert "abc123" not in result
    
    def test_is_sensitive(self):
        """Should detect via convenience function."""
        assert is_sensitive("password=x") is True
        assert is_sensitive("ok") is False


# =============================================================================
# Test: Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases."""
    
    def test_empty_message(self, sanitizer):
        """Should handle empty message."""
        result = sanitizer.sanitize("")
        
        assert result.sanitized_message == ""
        assert result.was_sanitized is False
    
    def test_none_in_extra(self, log_sanitizer):
        """Should handle None values in extra."""
        message = "Test"
        extra = {"value": None, "name": "test"}
        
        _, sanitized = log_sanitizer.sanitize_log_record(message, extra)
        
        assert sanitized["value"] is None
    
    def test_multiple_sensitive_items(self, sanitizer):
        """Should redact all sensitive items."""
        message = "password=a api_key=b ip=1.1.1.1 email=x@y.com"
        result = sanitizer.sanitize(message)
        
        assert result.redaction_count >= 4
        assert len(result.redacted_types) >= 3
